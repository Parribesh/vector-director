"""Builds a place: a backdrop drawn in code, then gallery items stood on it.

The backdrop is only what no item can be: the sky (each time of day), the far view and the ground.
Everything else is its own item, so it can be moved, resized or swapped in Studio.
"""

from __future__ import annotations

import random

from vector_director.m1_harness.prop import PX_PER_CM
from vector_director.m1_harness.set_design import H, W, compose

PEOPLE_SCALE = {"interior": 0.75, "outdoor": 0.8}
MARK_X = {"far-left": 130, "left": 330, "centre": 600, "right": 870, "far-right": 1070}
ROW_Y = {"back": 560, "front": 640}
ROOM_ROW_Y = {"back": 540, "front": 600}
ROW_DISTANCE = {"back": 0.72, "front": 1.0}  # further away, smaller
TOP_MARGIN = 40  # nothing reaches past the top of the frame

FAR = {
    "sea": "open sea to the horizon",
    "river": "a wide river with a far bank",
    "hills": "low green hills",
    "mountains": "high mountains",
    "desert": "sand dunes",
    "forest": "a dark line of forest",
    "fields": "flat farmland",
    "town": "rooftops of a town",
    "none": "only sky",
}
GROUND = {
    "sand": ("#E8D3A0", "#CFB57D", "#BFA36B"),
    "shore": ("#D9C48F", "#B8A070", "#9D8660"),
    "dirt": ("#C9A675", "#AD8B5C", "#94754C"),
    "dry": ("#CDB27A", "#B39762", "#9A8050"),
    "grass": ("#8DAF5A", "#749548", "#5F7F3A"),
    "paved": ("#B3A898", "#94897A", "#7B7164"),
    "stone": ("#A39C90", "#857E73", "#6E685E"),
    "snow": ("#EEF2F5", "#D5DEE6", "#BCC8D2"),
}
HORIZON = 440
INK = "#2A1A10"


def _band(rng: random.Random, y: int, bump: int, fill: str, step: int = 120, bottom: int = 560) -> str:
    """A rolling shape from y down to the ground line."""
    pts = [(x, y + rng.randint(-bump, bump)) for x in range(-step, W + 2 * step, step)]
    d = f"M{pts[0][0]} {pts[0][1]}" + "".join(f" Q{x - step // 2} {py + rng.randint(-bump, bump)} {x} {py}" for x, py in pts[1:])
    return f'<path d="{d} L{W + step} {bottom} L{-step} {bottom} Z" fill="{fill}"/>'


def _far(kind: str, rng: random.Random) -> str:
    if kind in ("sea", "river"):
        out = f'<rect x="0" y="{HORIZON}" width="{W}" height="140" fill="#3F7FA6"/><rect x="0" y="{HORIZON}" width="{W}" height="16" fill="#6AA3C2"/>'
        if kind == "river":
            out = _band(rng, HORIZON - 30, 14, "#7E9A62") + out.replace(f'y="{HORIZON}"', f'y="{HORIZON + 18}"')
        for _ in range(26):
            x, y, w = rng.randint(0, W), rng.randint(HORIZON + 24, 560), rng.randint(30, 110)
            out += f'<path d="M{x} {y} q{w / 2} -7 {w} 0" fill="none" stroke="#BCD9E6" stroke-width="3" opacity=".7" stroke-linecap="round"/>'
        return out
    if kind == "hills":
        return _band(rng, HORIZON - 70, 26, "#9DB98C") + _band(rng, HORIZON - 25, 18, "#7FA46C")
    if kind == "desert":
        return _band(rng, HORIZON - 40, 30, "#E2C48C", 200) + _band(rng, HORIZON, 18, "#D4B277", 200)
    if kind == "fields":
        return _band(rng, HORIZON - 12, 5, "#A8B86C", 240) + _band(rng, HORIZON + 22, 5, "#C4B868", 240)
    if kind == "forest":
        trees = "".join(f'<circle cx="{x}" cy="{HORIZON - rng.randint(10, 50)}" r="{rng.randint(34, 62)}" fill="#3E5F3C"/>' for x in range(-20, W + 40, 44))
        return trees + _band(rng, HORIZON, 6, "#4C7045")
    if kind == "mountains":
        out = ""
        for i, (fill, top) in enumerate((("#8A97AB", 150), ("#6F7D92", 240))):
            x = -100
            while x < W + 100:
                w, peak = rng.randint(260, 460), rng.randint(top, top + 90)
                out += f'<polygon points="{x},560 {x + w / 2},{peak} {x + w},560" fill="{fill}"/>'
                if i == 0:
                    out += f'<polygon points="{x + w / 2 - 44},{peak + 62} {x + w / 2},{peak} {x + w / 2 + 44},{peak + 62} {x + w / 2 + 8},{peak + 44}" fill="#F2F4F6"/>'
                x += w - rng.randint(60, 140)
        return out
    if kind == "town":
        out, x = "", -20
        while x < W:
            w, h = rng.randint(50, 110), rng.randint(40, 130)
            roof = rng.choice(("#A5634A", "#8B5A44", "#B37D54"))
            out += f'<rect x="{x}" y="{HORIZON - h}" width="{w}" height="{h + 120}" fill="{rng.choice(("#C9B08C", "#BDA27E", "#D2BC99"))}"/>'
            out += f'<polygon points="{x - 6},{HORIZON - h} {x + w / 2},{HORIZON - h - 26} {x + w + 6},{HORIZON - h}" fill="{roof}"/>'
            x += w - 4
        return out
    return ""


def _ground(kind: str, rng: random.Random) -> str:
    base, mid, dark = GROUND[kind]
    out = f'<path d="M0 510 Q300 {rng.randint(490, 520)} 600 505 T1200 512 L1200 {H} L0 {H} Z" fill="{base}"/>'
    out += _band(rng, 590, 10, mid, 240, H)
    out += _band(rng, 690, 10, base, 240, H)
    if kind in ("paved", "stone"):
        for i, y in enumerate((540, 580, 630, 690, 760)):
            out += f'<line x1="0" x2="{W}" y1="{y}" y2="{y}" stroke="{dark}" stroke-width="{1.5 + i * 0.5}" opacity=".7"/>'
            step, off = 60 + i * 34, (i % 2) * (30 + i * 17)
            next_y = (540, 580, 630, 690, 760, 800)[i + 1]
            out += "".join(f'<line x1="{x}" x2="{x}" y1="{y}" y2="{next_y}" stroke="{dark}" stroke-width="{1.5 + i * 0.5}" opacity=".7"/>' for x in range(off, W, step))
        return out
    if kind == "shore":
        out = '<path d="M0 530 Q260 548 520 530 T1200 536 L1200 556 Q900 572 600 556 T0 552 Z" fill="#E9EEF0" opacity=".85"/>' + out
    for _ in range(46):
        x, y = rng.randint(0, W), rng.randint(530, H - 6)
        size = 1 + (y - 520) / 70
        if kind == "grass":
            out += f'<path d="M{x} {y} l{-3 * size} {-9 * size} M{x} {y} l0 {-11 * size} M{x} {y} l{3 * size} {-9 * size}" stroke="{dark}" stroke-width="2" fill="none"/>'
        elif rng.random() < 0.5:
            out += f'<ellipse cx="{x}" cy="{y}" rx="{5 * size}" ry="{2.4 * size}" fill="{dark}" opacity=".55"/>'
        else:
            out += f'<path d="M{x} {y} q{10 * size} {-4 * size} {22 * size} 0" stroke="{dark}" stroke-width="2" fill="none" opacity=".5"/>'
    return out


def backdrop(far: str, ground: str, name: str, kind: str = "outdoor") -> str:
    """The sky for every time of day, the far view and the ground, as one SVG for the stage."""
    rng = random.Random(name)
    prefix = "".join(c if c.isalnum() else "-" for c in name).strip("-")
    return compose(_far(far if far in FAR else "none", rng), "", _ground(ground if ground in GROUND else "dirt", rng), kind, prefix)


def scale_for(item: dict, row: str, kind: str, y: int) -> float:
    """Its real size beside the people here, further back smaller, and never past the top of the frame."""
    people = PEOPLE_SCALE.get(kind, 0.8)
    real = item["height_cm"] / item["drawn_cm"] * people * ROW_DISTANCE.get(row, 1.0)
    fits = (y - TOP_MARGIN) / (item["drawn_cm"] * PX_PER_CM)
    return round(min(real, fits), 3)
