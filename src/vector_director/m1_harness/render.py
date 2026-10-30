"""Headless rendering: SVG -> Frames."""

from __future__ import annotations

import io
import os
import re
from typing import Self

from vector_director.core import Frames

DEFAULT_DURATION = 3.0
MAX_DURATION = 10.0

# Pause every clock at `t` seconds: CSS animations and transitions via the Web
# Animations API, SMIL via the SVG element's own timeline. GSAP would need its
# global timeline paused too; add it here if sadhu turns out to use GSAP.
_SEEK_JS = """
(t) => {
  for (const a of document.getAnimations()) { a.pause(); a.currentTime = t * 1000; }
  const svg = document.querySelector('svg');
  if (svg && svg.pauseAnimations) { svg.pauseAnimations(); svg.setCurrentTime(t); }
}
"""

# Longest finite animation end time in seconds, or null if all are infinite / none.
_DURATION_JS = """
() => {
  let end = 0;
  for (const a of document.getAnimations()) {
    const t = a.effect.getComputedTiming();
    const d = Number(t.duration) || 0;
    const iters = Number.isFinite(t.iterations) ? t.iterations : 1;
    end = Math.max(end, (t.delay || 0) + d * iters);
  }
  return end > 0 ? end / 1000 : null;
}
"""


def _page_html(svg: str) -> str:
    return (
        "<!doctype html><html><head><style>"
        "html,body{margin:0;padding:0;background:#fff}svg{display:block}"
        "</style></head><body>" + svg + "</body></html>"
    )


class PlaywrightRenderer:
    """Implements core.interfaces.Renderer with headless Chromium.

    One browser is started lazily and reused across renders; call `close()` (or use
    `with PlaywrightRenderer() as r:`) when done. Frames are PIL images on white.
    """

    def __init__(
        self, fps: int = 12, size: int | None = None, executable_path: str | None = None
    ) -> None:
        self.fps = fps  # used when render() is called without an fps
        self.size = size  # force a square viewport; None uses the SVG's own width/height
        self.executable_path = executable_path or os.environ.get("VD_CHROMIUM")
        self._pw = None
        self._browser = None

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def _ensure_browser(self):
        if self._browser is None:
            from playwright.sync_api import sync_playwright

            self._pw = sync_playwright().start()
            kwargs = {"executable_path": self.executable_path} if self.executable_path else {}
            self._browser = self._pw.chromium.launch(**kwargs)
        return self._browser

    def close(self) -> None:
        if self._browser is not None:
            self._browser.close()
            self._pw.stop()
            self._browser = self._pw = None

    def render(self, svg: str, fps: int | None = None, duration: float | None = None) -> Frames:
        from PIL import Image

        fps = fps or self.fps
        width, height = _svg_size(svg)
        if self.size:
            width = height = self.size
        page = self._ensure_browser().new_page(viewport={"width": width, "height": height})
        try:
            page.set_content(_page_html(svg))
            root = page.query_selector("svg")
            if root is None:
                raise ValueError("no <svg> element rendered")
            if duration is None:
                duration = _declared_duration(svg) or page.evaluate(_DURATION_JS)
            duration = min(duration or DEFAULT_DURATION, MAX_DURATION)
            n = max(1, round(duration * fps))
            images = []
            for i in range(n):
                page.evaluate(_SEEK_JS, i / fps)
                png = page.screenshot(clip={"x": 0, "y": 0, "width": width, "height": height})
                images.append(Image.open(io.BytesIO(png)).convert("RGB"))
        finally:
            page.close()
        return Frames(images=images, fps=fps, width=width, height=height)


def _svg_size(svg: str, default: int = 512) -> tuple[int, int]:
    """Width and height from the root <svg>, falling back to its viewBox, then 512."""
    head = re.search(r"<svg\b[^>]*>", svg, re.DOTALL)
    tag = head.group(0) if head else ""

    def attr(name: str) -> float | None:
        m = re.search(rf'\b{name}\s*=\s*"([\d.]+)(px)?"', tag)
        return float(m.group(1)) if m else None

    w, h = attr("width"), attr("height")
    if not (w and h):
        vb = re.search(r'viewBox\s*=\s*"[\d.\s,-]*?([\d.]+)[\s,]+([\d.]+)"', tag)
        if vb:
            w, h = float(vb.group(1)), float(vb.group(2))
    return int(w or default), int(h or default)


def _declared_duration(svg: str) -> float | None:
    m = re.search(r'data-vd-duration="([\d.]+)"', svg)
    return float(m.group(1)) if m else None
