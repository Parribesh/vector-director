"""AnimationSpec -> one self-contained animated SVG, using CSS keyframes.

Why CSS: it plays in every browser, a headless browser can pause it at an exact time
(document.getAnimations) for frame grabs, and it maps one-to-one onto GSAP tweens later.

Each object becomes a stack of nested groups so that transforms never fight over the
one CSS `transform` property:

    <g class="vd-translate">        translate
      <g class="vd-rotate">         rotate   (around the object's own centre)
        <g class="vd-scale">        scale + opacity (around the object's own centre)
          <g class="vd-paint">      fill / stroke / path, applied to the shapes inside
            ...object svg...
"""

from __future__ import annotations

from html import escape

from vector_director.core import AnimationSpec, Keyframe, Track

# CSS timing functions for the spec's easing names. "spring" is an overshoot curve,
# close enough to a damped spring for short moves.
EASING_CSS = {
    "linear": "linear",
    "ease-in": "ease-in",
    "ease-out": "ease-out",
    "ease-in-out": "ease-in-out",
    "step": "steps(1, end)",
    "spring": "cubic-bezier(0.34, 1.56, 0.64, 1)",
}

# Which wrapper group each property animates, and the CSS property it writes.
LAYER = {
    "translate": ("translate", "transform"),
    "rotate": ("rotate", "transform"),
    "scale": ("scale", "transform"),
    "opacity": ("scale", "opacity"),
    "fill": ("paint", "fill"),
    "stroke": ("paint", "stroke"),
    "path": ("paint", "d"),
}
LAYERS = ("translate", "rotate", "scale", "paint")
SHAPES = "path, rect, circle, ellipse, polygon, polyline, line, text"


def _nums(value: float | str | list[float]) -> list[float]:
    if isinstance(value, (int, float)):
        return [float(value)]
    if isinstance(value, str):
        return [float(v) for v in value.replace(",", " ").split()]
    return [float(v) for v in value]


def _fmt(x: float) -> str:
    return f"{x:.4g}"


def css_value(prop: str, value: float | str | list[float]) -> str:
    """One keyframe value as a CSS declaration value."""
    if prop == "translate":
        xy = _nums(value) + [0.0]
        return f"translate({_fmt(xy[0])}px, {_fmt(xy[1])}px)"
    if prop == "rotate":
        return f"rotate({_fmt(_nums(value)[0])}deg)"
    if prop == "scale":
        s = _nums(value)
        return f"scale({_fmt(s[0])}, {_fmt(s[1] if len(s) > 1 else s[0])})"
    if prop == "opacity":
        return _fmt(min(1.0, max(0.0, _nums(value)[0])))
    if prop == "path":
        return f'path("{value}")'
    return str(value)  # fill / stroke: any CSS colour


def _keyframes_css(name: str, track: Track, duration: float) -> str:
    """@keyframes block. Holds the first value before it starts and the last after it ends."""
    css_prop = LAYER[track.property][1]
    frames: list[tuple[float, Keyframe]] = [(k.t / duration * 100, k) for k in track.keyframes]
    if frames[0][0] > 0:
        frames.insert(0, (0.0, frames[0][1]))
    if frames[-1][0] < 100:
        frames.append((100.0, frames[-1][1]))
    lines = [f"@keyframes {name} {{"]
    for i, (pct, k) in enumerate(frames):
        value = css_value(track.property, k.value)
        # A keyframe's easing is how motion arrives at it (as in a GSAP tween), but CSS
        # puts the timing function on the keyframe a segment starts from.
        ease = EASING_CSS[frames[i + 1][1].easing] if i + 1 < len(frames) else "linear"
        lines.append(f"  {pct:.3f}% {{ {css_prop}: {value}; animation-timing-function: {ease}; }}")
    lines.append("}")
    return "\n".join(lines)


def _selector(obj_id: str, layer: str) -> str:
    base = f"#{obj_id}-{layer}"
    # Paint properties must land on the shapes themselves: CSS on a parent group
    # loses to a child's own fill="..." attribute, CSS on the child does not.
    # All paint props share this one selector so their `animation` lists merge.
    if layer == "paint":
        return f"{base} :is({SHAPES})"
    return base


def spec_to_svg(spec: AnimationSpec) -> str:
    """Compile a spec into one self-contained animated SVG string."""
    iteration = "infinite" if spec.loop else "1"
    css: list[str] = [
        ".vd-rotate, .vd-scale { transform-box: fill-box; transform-origin: center; }",
    ]
    # selector -> list of "name duration" animation entries (several props can share a layer)
    rules: dict[str, list[str]] = {}
    for i, track in enumerate(spec.tracks):
        name = f"vd-{track.target}-{track.property}-{i}"
        css.append(_keyframes_css(name, track, spec.duration))
        layer = LAYER[track.property][0]
        sel = _selector(track.target, layer)
        rules.setdefault(sel, []).append(
            f"{name} {_fmt(spec.duration)}s linear 0s {iteration} both"
        )
    for sel, anims in rules.items():
        css.append(f"{sel} {{ animation: {', '.join(anims)}; }}")

    body: list[str] = []
    if spec.background:
        body.append(f'<rect width="100%" height="100%" fill="{escape(spec.background)}"/>')
    for obj in spec.objects:
        label = f' aria-label="{escape(obj.label)}"' if obj.label else ""
        body.append(
            f'<g id="{obj.id}"{label} data-source="{escape(obj.source or "")}">'
            + "".join(f'<g id="{obj.id}-{layer}" class="vd-{layer}">' for layer in LAYERS)
            + obj.svg
            + "</g>" * (len(LAYERS) + 1)
        )

    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{spec.width}" height="{spec.height}" '
        f'viewBox="0 0 {spec.width} {spec.height}" data-vd-duration="{_fmt(spec.duration)}">\n'
        f"<title>{escape(spec.prompt)}</title>\n"
        "<style>\n" + "\n".join(css) + "\n</style>\n" + "\n".join(body) + "\n</svg>\n"
    )
