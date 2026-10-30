"""Headless rendering: SVG -> Frames."""

from __future__ import annotations

from vector_director.core import Frames


class PlaywrightRenderer:
    """Implements core.interfaces.Renderer.

    TODO(M1): load the SVG in headless Chromium, pause the animation clock at each
    t = i / fps (document.getAnimations / SVGSVGElement.setCurrentTime), screenshot.
    """

    def render(self, svg: str, fps: int = 12, duration: float | None = None) -> Frames:
        raise NotImplementedError("M1: render SVG to frames")
