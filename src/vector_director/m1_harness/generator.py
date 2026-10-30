"""Prompt -> AnimationSpec -> SVG.

`ApiSpecGenerator` asks a model for an AnimationSpec with structured output (the
provider constrains decoding to the spec's JSON schema, Pydantic checks the cross-field
rules), then compiles it. The model is any `llm.JsonLLM`: Claude, Gemini or a local
Ollama model. `BaselineGenerator` needs no API and gives the scoreboard its floor.
"""

from __future__ import annotations

import time
from collections.abc import Sequence

from pydantic import ValidationError

from vector_director.core import AnimationSpec, GenerationResult, Hit
from vector_director.m1_harness.compile import spec_to_svg
from vector_director.m1_harness.llm import JsonLLM, cost_usd, make_llm

__all__ = ["ApiSpecGenerator", "BaselineGenerator", "spec_to_svg"]

SYSTEM_PROMPT = """\
You are an animator who writes short looping vector animations as an AnimationSpec.

Canvas: width x height px, origin top-left, y grows downward. Keep everything on canvas.
Objects: each `svg` is a self-contained SVG fragment (<path>, <circle>, <rect>, <g> ...)
drawn at its starting position with explicit fill/stroke colours. No <script>, no
<image>, no external references, no CSS, no SMIL. Prefer 2 to 8 objects with clear,
readable silhouettes over many tiny details. Draw background scenery as objects first
(earlier objects are drawn underneath later ones).
Tracks animate one property of one object. translate values are [dx, dy] offsets from
where the object is drawn, rotate and scale pivot around the object's own centre.
Keyframes must be sorted by t and the last one must not exceed `duration`. If `loop` is
true, end each track on its first value so the loop is seamless.
Make the motion tell the prompt: what moves, how, and in what order.
"""


def _user_message(prompt: str, context: Sequence[Hit], width: int, height: int) -> str:
    parts = [f"Animate: {prompt}", f"Canvas: {width}x{height}."]
    refs = [h for h in context if h.svg]
    if refs:  # M2 retrieval plugs in here
        parts.append("Reference assets you may reuse or adapt:")
        parts += [f'<asset id="{h.id}">\n{h.svg}\n</asset>' for h in refs]
    return "\n\n".join(parts)


class ApiSpecGenerator:
    """Implements core.interfaces.Generator with any structured-output model.

    If the reply fails validation (say a track targets an unknown object), the bad spec
    and the error go back to the model once for a fix. That validate-and-repair loop is
    the pattern every later generator reuses.
    """

    name = "api-spec"

    def __init__(
        self,
        provider: str = "anthropic",
        model: str | None = None,
        effort: str | None = None,
        width: int = 512,
        height: int = 512,
        max_repairs: int = 1,
        llm: JsonLLM | None = None,
    ) -> None:
        kw = {"effort": effort} if effort and provider == "anthropic" else {}
        self.llm = llm or make_llm(provider, model, **kw)
        self.width, self.height = width, height
        self.max_repairs = max_repairs

    def generate(self, prompt: str, context: Sequence[Hit] = ()) -> GenerationResult:
        ask = _user_message(prompt, context, self.width, self.height)
        meta: dict = {
            "provider": self.llm.provider,
            "model": self.llm.model,
            "attempts": 0,
            "input_tokens": 0,
            "output_tokens": 0,
        }
        start = time.perf_counter()
        error: Exception | None = None
        for _ in range(self.max_repairs + 1):
            meta["attempts"] += 1
            reply = self.llm.ask(SYSTEM_PROMPT, ask, AnimationSpec)
            meta["input_tokens"] += reply.input_tokens
            meta["output_tokens"] += reply.output_tokens
            if not reply.ok:
                error = RuntimeError(f"no spec returned (stop={reply.stop})")
                break
            try:
                spec = AnimationSpec.model_validate_json(reply.text)
            except ValidationError as exc:
                # Schema-constrained decoding gets the shape right, but cross-field
                # rules (unknown targets, tracks past duration) are only checked here.
                error = exc
                ask = (
                    _user_message(prompt, context, self.width, self.height)
                    + f"\n\nYour previous spec was invalid.\n<spec>\n{reply.text}\n</spec>\n"
                    + f"<errors>\n{exc}\n</errors>\nReturn a fixed spec."
                )
                continue
            spec = spec.model_copy(update={"prompt": prompt})
            return GenerationResult(
                svg=spec_to_svg(spec), spec=spec, meta=self._finish(meta, start)
            )
        meta["error"] = repr(error)
        return GenerationResult(svg="", spec=None, meta=self._finish(meta, start))

    def _finish(self, meta: dict, start: float) -> dict:
        meta["latency_ms"] = round((time.perf_counter() - start) * 1000)
        meta["cost_usd"] = round(
            cost_usd(self.llm.model, meta["input_tokens"], meta["output_tokens"]), 5
        )
        return meta


class BaselineGenerator:
    """No-model floor: one circle that drifts right and back, whatever the prompt.

    Any real generator should beat it on clip and judge; it scores well on valid and
    motion, which is a reminder that those two alone are easy to game.
    """

    name = "baseline"

    def generate(self, prompt: str, context: Sequence[Hit] = ()) -> GenerationResult:
        spec = AnimationSpec(
            prompt=prompt,
            objects=[{"id": "dot", "svg": '<circle cx="156" cy="256" r="48" fill="#4c6ef5"/>'}],
            tracks=[
                {
                    "target": "dot",
                    "property": "translate",
                    "keyframes": [
                        {"t": 0, "value": [0, 0]},
                        {"t": 1.5, "value": [200, 0]},
                        {"t": 3, "value": [0, 0]},
                    ],
                }
            ],
        )
        return GenerationResult(svg=spec_to_svg(spec), spec=spec, meta={"model": "baseline"})
