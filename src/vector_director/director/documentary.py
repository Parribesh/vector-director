"""A documentary's breakdown from a brief (POST /documentary): the director plans the shots, then writes them one by
one, each saved into Studio as it is written, so Studio's documentary screen shows the timeline fill in live.

    1. the brief       noted in the project's activity (Studio: POST /api/doc/<id>/activity)
    2. the plan        title and shots, each a draft (its purpose, the kind it shows, its length): saved at once
    3. each shot       its line, what it shows and its beats; checked alone by Studio (POST /api/doc/<id>/check),
                       once more with the check's problems; saved in place of its draft
    4. the whole       saved with Studio's check (PUT /api/doc/<id>?check=1); a refused shot written again, once

Everything goes through Studio's API (STUDIO_URL, STUDIO_TOKEN; X-Who: director): the project, the document, the check,
the activity. The narration and the render are Studio's, asked for by whoever drives it (the agent, or you).

brief: {"topic", "concepts"?, "level"?, "outcome"?, "minutes"? 1-4, "material"? {...}, "sources"?, "kind"?, "reveal"?,
        "question"?, "notes"?}: the coach's brief (Guru's ExplainIn); only topic is needed.
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request

from vector_director.director.pipeline import N, Run, S, arr, en, obj

PROMPTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "prompts")
STUDIO = os.environ.get("STUDIO_URL_FOR_DIRECTOR", "http://127.0.0.1:8771").rstrip("/")
KINDS = ["title", "words", "terms", "diagram", "trace", "code", "recall"]
# Microsoft Edge's neural voice, free, the one Guru speaks with (VIDEO_LESSON_ENGINE / VIDEO_LESSON_VOICE to change it)
VOICE = {"engine": os.environ.get("VIDEO_LESSON_ENGINE", "edge"), "voice": os.environ.get("VIDEO_LESSON_VOICE", "en-US-ChristopherNeural"),
         "note": "a warm, clear teacher talking to one learner: conversational, steady pace, a small pause after each step"}
ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")


class StudioError(RuntimeError):
    pass


def studio(method: str, path: str, body=None) -> dict:
    """One call to Studio's API as the director."""
    token = os.environ.get("STUDIO_TOKEN", "")
    req = urllib.request.Request(STUDIO + path, data=None if body is None else json.dumps(body).encode(), method=method,
                                 headers={"content-type": "application/json", "x-who": "director", **({"authorization": f"Bearer {token}"} if token else {})})
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        try:
            said = json.loads(e.read())
        except ValueError:
            said = {}
        if e.code == 400 and "problems" in said:
            return said
        raise StudioError(f"Studio answered {e.code} to {method} {path}: {said.get('error', '')}") from e
    except (urllib.error.URLError, OSError) as e:
        raise StudioError(f"Studio isn't answering ({STUDIO})") from e


def say(pid: str, kind: str, what: str, detail=None, shot: str | None = None) -> None:
    body = {"who": "director", "kind": kind, "what": what, **({"detail": detail} if detail is not None else {}), **({"shot": shot} if shot else {})}
    try:
        studio("POST", f"/api/doc/{pid}/activity", body)
    except StudioError:
        pass                                                      # the work goes on; only the live view misses a line


def kinds_text() -> str:
    with open(os.path.join(PROMPTS, "doc_kinds.txt")) as f:
        return f.read().strip()


def outline_schema() -> dict:
    return obj({"title": S, "shots": arr(obj({"id": S, "kind": en(*KINDS), "purpose": S, "words": N}))})


def shot_schema() -> dict:
    return obj({"say": S, "show": S, "beats": S, "seconds": N})


def brief_text(brief: dict) -> str:
    return json.dumps({k: v for k, v in brief.items() if v not in (None, "", [], {}) and k != "key"}, ensure_ascii=False, indent=1)


def as_json(text: str, what: str):
    text = (text or "").strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except ValueError as e:
        raise ValueError(f"{what} isn't valid JSON ({e.msg})") from e


def draft(s: dict) -> dict:
    words = max(4, int(s.get("words") or 20))
    return {"id": s["id"], "say": "", "show": {"kind": "words", "text": s["purpose"][:120], "sub": f"{s['kind']} · being written"},
            "seconds": round(words / 2.6 + 1, 1), "caption": False, "draft": s["purpose"]}


def write_shot(run: Run, pid: str, doc: dict, plan: list[dict], k: int, brief: dict, problems: list[str] | None = None) -> dict:
    """Shot k written, checked alone by Studio, and once more with the check's problems; the last try is kept either way."""
    p = plan[k]
    for attempt in range(2):
        before = "\n".join(f"- {s['id']}: {s.get('say', '')}" for s in doc["shots"][:k] if not s.get("draft")) or "(none yet)"
        said = ("\nThis shot was refused by Studio's check; fix these:\n- " + "\n- ".join(problems)) if problems else ""
        say(pid, "think", f"writing {p['id']}" + (" again, with the check's problems" if problems else "") + f": {p['purpose']}", shot=p["id"])
        data = run.ask("doc_shot", {"brief": brief_text(brief), "title": doc["title"],
                                    "outline": "\n".join(f"{j + 1}. {s['id']} ({s['kind']}, ~{s.get('words', 20)} words): {s['purpose']}" for j, s in enumerate(plan)),
                                    "before": before, "id": p["id"], "kind": p["kind"], "words": str(int(p.get("words") or 20)),
                                    "purpose": p["purpose"], "problems": said, "kinds": kinds_text()},
                       shot_schema(), f"shot {p['id']}", temperature=0.6)
        try:
            show = as_json(data.get("show"), "show")
            beats = as_json(data.get("beats"), "beats")
            if not isinstance(show, dict):
                raise ValueError("show is a JSON object")
            shot = {"id": p["id"], "say": (data.get("say") or "").strip(), "show": show, "caption": False}
            if isinstance(beats, list) and beats:
                shot["beats"] = beats
            if data.get("seconds"):
                shot["seconds"] = float(data["seconds"])
            problems = [x for x in studio("POST", f"/api/doc/{pid}/check", {**doc, "shots": [shot]})["problems"]
                        if not x.startswith(("the documentary has no title", "no narrator"))]
        except ValueError as e:
            shot, problems = {**doc["shots"][k], "draft": p["purpose"]}, [str(e)]
        if not problems or attempt == 1:
            return shot, problems
    raise AssertionError("unreachable")


def write_documentary(run: Run, req: dict) -> dict:
    """The breakdown, from the brief; or, with "resume": true, the drafts an earlier breakdown left, written."""
    pid = req.get("project") or ""
    if isinstance(pid, dict):
        pid = pid.get("id", "")
    try:
        return breakdown(run, pid, req)
    except Exception as e:
        if ID.match(pid or ""):
            say(pid, "problem", f"The breakdown stopped: {str(e)[:200]}. Ask the director to resume it.", {"error": str(e)[:1000]})
        raise


def breakdown(run: Run, pid: str, req: dict) -> dict:
    if req.get("resume"):
        doc = studio("GET", f"/api/doc/{pid}")["doc"]
        plan, brief = doc.get("plan") or [], doc.get("brief") or {}
        if not plan:
            raise ValueError("there's no plan to resume: ask for a breakdown from the brief")
        say(pid, "think", f"resuming the breakdown: {sum(1 for s in doc['shots'] if s.get('draft'))} drafts left")
        return write_shots(run, pid, doc, plan, brief)
    brief = req.get("brief") or {}
    if not ID.match(pid) or not (brief.get("topic") or "").strip():
        raise ValueError("needs a project id (lowercase letters, digits, dashes) and a brief with a topic")
    minutes = max(1, min(4, int(brief.get("minutes") or 2)))
    try:
        studio("GET", f"/api/project/{pid}")
    except StudioError:
        studio("PUT", f"/api/project/{pid}", {"id": pid, "title": brief["topic"][:80], "kind": "documentary", "lesson": True})
    say(pid, "brief", f"Got the brief: {brief['topic']}", brief)

    run.on_step("Planning the shots", "running")
    say(pid, "think", "planning the shots: what the video teaches, in what order, and what each shot shows")
    out = run.ask("doc_outline", {"brief": brief_text(brief), "minutes": str(minutes), "words": str(150 * minutes), "kinds": kinds_text()},
                  outline_schema(), "the plan", temperature=0.6)
    plan, seen = [], set()
    for s in out.get("shots") or []:
        sid = re.sub(r"[^a-z0-9-]+", "-", (s.get("id") or "").lower()).strip("-")[:40] or f"shot-{len(plan) + 1}"
        while sid in seen:
            sid += "-2"
        seen.add(sid)
        plan.append({**s, "id": sid, "kind": s.get("kind") if s.get("kind") in KINDS else "words"})
    if not plan:
        raise RuntimeError("the plan had no shots")
    doc = {"title": (out.get("title") or brief["topic"])[:60], "narrator": VOICE, "brief": brief, "plan": plan, "shots": [draft(s) for s in plan]}
    studio("PUT", f"/api/doc/{pid}", doc)
    say(pid, "made", f"The plan: \"{doc['title']}\", {len(plan)} shots", [f"{s['id']} ({s['kind']}): {s['purpose']}" for s in plan])
    run.on_step("Planning the shots", "done", f"{len(plan)} shots")
    return write_shots(run, pid, doc, plan, brief)


def write_shots(run: Run, pid: str, doc: dict, plan: list[dict], brief: dict) -> dict:
    """Each shot still a draft, written and saved in turn; then the whole checked."""
    left = {}
    for k, p in enumerate(plan):
        if k < len(doc["shots"]) and not doc["shots"][k].get("draft"):
            continue
        run.on_step(f"Writing {p['id']}", "running")
        shot, problems = write_shot(run, pid, doc, plan, k, brief)
        doc["shots"][k] = shot
        studio("PUT", f"/api/doc/{pid}?shot={p['id']}", doc)
        if problems:
            left[p["id"]] = problems
            say(pid, "problem", f"{p['id']} still has problems after a second try", problems, shot=p["id"])
        else:
            say(pid, "draft", f"wrote {p['id']}: {shot['say'][:140]}", {"say": shot["say"], "show": shot["show"], **({"beats": shot["beats"]} if shot.get("beats") else {})}, shot=p["id"])
        run.on_step(f"Writing {p['id']}", "done" if not problems else "failed", "; ".join(problems)[:200])

    run.on_step("Studio's check", "running")
    answer = studio("PUT", f"/api/doc/{pid}?check=1", doc)
    problems = answer.get("problems") or []
    if problems:
        say(pid, "problem", f"Studio's check still finds {len(problems)} problem(s); the agent or you can fix them in Studio", problems)
    else:
        say(pid, "made", "The breakdown is written and passes Studio's check: ready to narrate")
    run.on_step("Studio's check", "done" if not problems else "failed", f"{len(problems)} problem(s)")
    return {"project": pid, "title": doc["title"], "shots": len(doc["shots"]), "problems": problems, "stats": run.stats}
