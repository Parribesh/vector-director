"""AnimationSpec: the typed middle layer between a prompt and an SVG.

Every generator writes a spec (or SVG directly), every renderer reads one. Keep it
small and boring: the M1 milestone may grow it, later milestones should not need to.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

Easing = Literal["linear", "ease-in", "ease-out", "ease-in-out", "step", "spring"]
AnimProperty = Literal["translate", "rotate", "scale", "opacity", "fill", "stroke", "path"]


class SceneObject(BaseModel):
    """One drawable thing in the scene."""

    id: str = Field(pattern=r"^[A-Za-z][\w-]*$")
    svg: str = Field(description="SVG fragment for this object, e.g. a <path> or <g>.")
    label: str | None = Field(
        default=None, description="Human name, used by retrieval and critics."
    )
    source: str | None = Field(
        default=None, description="Where it came from: generated, asset id, ..."
    )


class Keyframe(BaseModel):
    t: float = Field(ge=0.0, description="Time in seconds.")
    value: float | str | list[float] = Field(
        description=(
            "translate: [dx, dy] px offset from where the object is drawn; rotate: degrees; "
            "scale: s or [sx, sy]; opacity: 0..1; fill/stroke: CSS colour; path: SVG path data."
        )
    )
    easing: Easing = Field(
        default="ease-in-out", description="How motion eases into this keyframe."
    )


class Track(BaseModel):
    """How one property of one object changes over time."""

    target: str = Field(description="SceneObject.id this track animates.")
    property: AnimProperty
    keyframes: list[Keyframe] = Field(min_length=1)

    @model_validator(mode="after")
    def _sorted(self) -> Track:
        times = [k.t for k in self.keyframes]
        if times != sorted(times):
            raise ValueError("keyframes must be sorted by time")
        return self


class AnimationSpec(BaseModel):
    prompt: str
    width: int = 512
    height: int = 512
    duration: float = Field(default=3.0, gt=0)
    loop: bool = True
    background: str | None = None
    objects: list[SceneObject]
    tracks: list[Track] = []

    @model_validator(mode="after")
    def _targets_exist(self) -> AnimationSpec:
        ids = {o.id for o in self.objects}
        if len(ids) != len(self.objects):
            raise ValueError("object ids must be unique")
        for tr in self.tracks:
            if tr.target not in ids:
                raise ValueError(f"track targets unknown object {tr.target!r}")
            if tr.keyframes[-1].t > self.duration:
                raise ValueError(f"track on {tr.target!r} runs past duration")
        return self
