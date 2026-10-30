"""LLM-as-judge over rendered frames (a vision model grades the animation)."""

from __future__ import annotations

import io

from pydantic import BaseModel, Field, ValidationError

from vector_director.core import Sample
from vector_director.m1_harness.llm import JsonLLM, cost_usd, make_llm

RUBRIC = """\
You grade short vector animations. You see a strip of frames in time order, left to
right, top to bottom. Grade each criterion from 1 (bad) to 5 (excellent):

- match: the subjects and the action in the prompt are recognisable.
- motion: things move in a way that tells the prompt (not random drift or flicker).
- craft: clean shapes, sensible composition, nothing broken or off canvas.

Then give one or two sentences of feedback an animator could act on next.
"""


class Verdict(BaseModel):
    match: int = Field(ge=1, le=5)
    motion: int = Field(ge=1, le=5)
    craft: int = Field(ge=1, le=5)
    feedback: str

    @property
    def score(self) -> float:
        """Mean of the three criteria, mapped from 1..5 to 0..1."""
        return ((self.match + self.motion + self.craft) / 3 - 1) / 4


def contact_sheet(images: list, n: int = 6, cols: int = 3, cell: int = 256):
    """n evenly spaced frames tiled into one image, with thin grey gutters."""
    from PIL import Image

    step = max(1, len(images) // n)
    picked = images[::step][:n]
    rows = (len(picked) + cols - 1) // cols
    gap = 4
    sheet = Image.new(
        "RGB", (cols * cell + (cols - 1) * gap, rows * cell + (rows - 1) * gap), "#888"
    )
    for i, im in enumerate(picked):
        thumb = im.copy()
        thumb.thumbnail((cell, cell))
        x, y = (i % cols) * (cell + gap), (i // cols) * (cell + gap)
        sheet.paste(Image.new("RGB", (cell, cell), "white"), (x, y))
        sheet.paste(thumb, (x + (cell - thumb.width) // 2, y + (cell - thumb.height) // 2))
    return sheet


class VisionJudge:
    """Implements core.interfaces.Critic. Returns (score 0..1, feedback text).

    The full Verdict (per-criterion grades) is stored on the sample under
    `meta["judge_verdict"]` so you can look at disagreements later.
    """

    rubric = RUBRIC

    def __init__(
        self,
        provider: str = "anthropic",
        model: str | None = None,
        n_frames: int = 6,
        llm: JsonLLM | None = None,
    ) -> None:
        kw = {"effort": "low"} if provider == "anthropic" and llm is None else {}
        self.llm = llm or make_llm(provider, model, vision=True, **kw)
        self.n_frames = n_frames

    def critique(self, sample: Sample) -> tuple[float, str]:
        if not sample.frames or not sample.frames.images:
            return 0.0, "nothing rendered"
        buf = io.BytesIO()
        contact_sheet(sample.frames.images, n=self.n_frames).save(buf, format="PNG")
        reply = self.llm.ask(
            self.rubric,
            f"Prompt: {sample.prompt}",
            Verdict,
            images=[buf.getvalue()],
            max_tokens=4000,
        )
        meta = sample.result.meta
        meta["judge_cost_usd"] = round(
            cost_usd(self.llm.model, reply.input_tokens, reply.output_tokens), 5
        )
        try:
            verdict = Verdict.model_validate_json(reply.text)
        except ValidationError as exc:
            return 0.0, f"judge returned no valid verdict (stop={reply.stop}): {exc}"
        meta["judge_verdict"] = verdict.model_dump()
        return verdict.score, verdict.feedback
