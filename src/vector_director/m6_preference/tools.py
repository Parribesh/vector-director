"""Tools the model can call mid-generation: render, validate, measure."""

from __future__ import annotations

TOOLS = {
    "render": "Render the SVG so far and return a frame summary.",
    "validate": "Parse the SVG and return errors, if any.",
    "measure": "Return bounding boxes and path lengths.",
}


def run_tool(name: str, svg: str) -> str:
    raise NotImplementedError
