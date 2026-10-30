"""One structured LLM call for the director, as cheaply as it can be done.

A task names a prompt file (director/prompts/<task>.md, with {{var}} slots) and comes with a JSON schema in
Gemini's format (OBJECT, STRING, ... in upper case). The answer is JSON in that shape.

Cost rules:
  - Every answer is cached on disk by (prompt text, schema, model), so asking again is free.
  - Gemini first: the cheap model for small tasks (GEMINI_LITE_MODEL, if set), the main model otherwise.
  - A failed call (rate limit, server error, unreadable JSON) is tried once more on Gemini after a pause.
  - OpenAI only after that, and only if OPENAI_API_KEY is set (model: OPENAI_MODEL).
  - Each call, prompt and answer included, goes to runs/<project>/calls.jsonl: the data to train on.

The keys stay in this process; nothing here returns or logs them.
"""
import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.request

PROMPTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "prompts")
CACHE = os.environ.get("VD_LLM_CACHE", os.path.join(".cache", "llm"))
RUNS = os.environ.get("VD_RUNS", "runs")
MAIN = os.environ.get("GEMINI_TEXT_MODEL", "gemini-3.8-flash")
LITE = os.environ.get("GEMINI_LITE_MODEL", MAIN)
OPENAI = os.environ.get("OPENAI_MODEL", "gpt-5-mini")
# tasks small enough for the cheapest model
LITE_TASKS = {"look", "room", "land", "repair", "dress", "pick"}
# how hard the model thinks before answering: thinking is most of the time and output tokens of a
# small pick-from-a-menu answer, so only the story and the plan get the model's default
THINK = {"look": "low", "room": "low", "land": "low", "repair": "low", "scene": "low", "direct": "low", "dress": "low", "pick": "low"}


class LLMError(Exception):
    pass


def fill(task, vars):
    with open(os.path.join(PROMPTS, task + ".md")) as f:
        text = f.read()
    for k, v in vars.items():
        text = text.replace("{{" + k + "}}", v if isinstance(v, str) else json.dumps(v, ensure_ascii=False, indent=1))
    return text


def to_json_schema(s):
    """Gemini's schema dialect -> plain JSON Schema for OpenAI."""
    out = {"type": s["type"].lower()}
    if "enum" in s:
        out["enum"] = s["enum"]
    if "items" in s:
        out["items"] = to_json_schema(s["items"])
    if "properties" in s:
        out["properties"] = {k: to_json_schema(v) for k, v in s["properties"].items()}
        out["required"] = s.get("required", list(s["properties"]))
        out["additionalProperties"] = False
    return out


def post(url, body, headers, timeout=300):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"content-type": "application/json", **headers})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def call_gemini(model, prompt, schema, temperature, think=None):
    config = {"responseMimeType": "application/json", "responseSchema": schema, "temperature": temperature}
    if think:
        config["thinkingConfig"] = {"thinkingLevel": think}
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    body, headers = {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": config}, {"x-goog-api-key": os.environ["GEMINI_API_KEY"]}
    try:
        data = post(url, body, headers)
    except urllib.error.HTTPError as e:
        if not think or e.code != 400:
            raise
        del config["thinkingConfig"]                                # a model without thinking levels: ask plainly
        data = post(url, body, headers)
    parts = data["candidates"][0]["content"]["parts"]
    u = data.get("usageMetadata", {})
    text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
    return json.loads(text), {"in": u.get("promptTokenCount", 0), "out": u.get("candidatesTokenCount", 0) + u.get("thoughtsTokenCount", 0),
                              "cachedIn": u.get("cachedContentTokenCount", 0)}


def call_openai(model, prompt, schema, temperature, think=None):
    data = post("https://api.openai.com/v1/chat/completions",
                {"model": model, "messages": [{"role": "user", "content": prompt}],
                 "response_format": {"type": "json_schema", "json_schema": {"name": "answer", "schema": to_json_schema(schema), "strict": False}},
                 **({"reasoning_effort": "low"} if think else {})},
                {"authorization": "Bearer " + os.environ["OPENAI_API_KEY"]})
    u = data.get("usage", {})
    return json.loads(data["choices"][0]["message"]["content"]), {"in": u.get("prompt_tokens", 0), "out": u.get("completion_tokens", 0),
                                                                 "cachedIn": (u.get("prompt_tokens_details") or {}).get("cached_tokens", 0)}


def retry_after(e):
    """Seconds Google asks us to wait on a per-minute limit (429 with RetryInfo), else None."""
    if not isinstance(e, urllib.error.HTTPError) or e.code != 429:
        return None
    body = getattr(e, "body_text", None)
    if body is None:
        body = e.body_text = e.read().decode(errors="replace")
    m = re.search(r'"retryDelay":\s*"(\d+(?:\.\d+)?)s"', body)
    return float(m.group(1)) if m and "PerMinute" in body else None


def why(e):
    if isinstance(e, urllib.error.HTTPError):
        body = getattr(e, "body_text", None)
        if body is None:
            body = e.body_text = e.read().decode(errors="replace")
        text = f"HTTP {e.code}: {body}"
    else:
        text = f"{type(e).__name__}: {e}"
    return re.sub(r"(sk|AIza)[-\w*]{6,}", "[key hidden]", text)[:300]          # providers echo part of a bad key


def log(project, entry):
    if not project:
        return
    d = os.path.join(RUNS, project)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "calls.jsonl"), "a") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def run(task, vars, schema, project=None, temperature=0.7, only=None):
    """-> {"data", "provider", "model", "cached", "usage", "tries"}; raises LLMError when every provider failed.
    only: "gemini" or "openai" to use just that provider (for testing the fallback)."""
    prompt = fill(task, vars)
    model = LITE if task in LITE_TASKS else MAIN
    chain = []
    if os.environ.get("GEMINI_API_KEY") and only != "openai":
        chain += [("gemini", model, 0), ("gemini", model, 4)]          # (provider, model, seconds to wait first)
    if os.environ.get("OPENAI_API_KEY") and only != "gemini":
        chain.append(("openai", OPENAI, 0))
    if not chain:
        raise LLMError("no GEMINI_API_KEY or OPENAI_API_KEY in the environment of vd serve")

    os.makedirs(CACHE, exist_ok=True)
    tries, asked_wait = [], 0
    for provider, m, wait in chain:
        key = hashlib.sha256(json.dumps([prompt, schema, provider, m], ensure_ascii=False).encode()).hexdigest()
        path = os.path.join(CACHE, key + ".json")
        if os.path.exists(path):
            with open(path) as f:
                out = json.load(f)
            log(project, {"t": time.time(), "task": task, "provider": provider, "model": m, "cached": True})
            return {**out, "cached": True, "tries": tries}
        if wait or asked_wait:
            time.sleep(max(wait, min(asked_wait, 65)))              # a per-minute limit says how long; otherwise a short pause
            asked_wait = 0
        t0 = time.time()
        try:
            data, usage = (call_gemini if provider == "gemini" else call_openai)(m, prompt, schema, temperature, THINK.get(task))
        except Exception as e:  # noqa: BLE001                      # rate limit, server error, bad JSON: next in line
            asked_wait = retry_after(e) or 0
            tries.append(f"{provider} {m}: {why(e)}")
            log(project, {"t": time.time(), "task": task, "provider": provider, "model": m, "error": tries[-1]})
            continue
        out = {"data": data, "provider": provider, "model": m, "usage": usage}
        with open(path, "w") as f:
            json.dump(out, f, ensure_ascii=False)
        log(project, {"t": time.time(), "task": task, "provider": provider, "model": m, "cached": False, "prompt": prompt, "data": data,
                      "ms": round((time.time() - t0) * 1000), **usage, **({"after": tries} if tries else {})})
        return {**out, "cached": False, "tries": tries}
    raise LLMError("; ".join(tries))
