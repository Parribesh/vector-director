"""M1: compiler, generator repair loop, scorers, prompts and the harness, all offline.

The renderer tests need Chromium; they skip when Playwright cannot start a browser.
Point VD_CHROMIUM at a Chrome binary if Playwright's own download is missing.
"""

import json
import re
import xml.etree.ElementTree as ET

import pytest
from PIL import Image

from vector_director.core import AnimationSpec, Frames, GenerationResult, Sample
from vector_director.core.interfaces import Critic, Generator, Renderer, Scorer
from vector_director.m1_harness.compile import css_value, spec_to_svg
from vector_director.m1_harness.generator import ApiSpecGenerator, BaselineGenerator
from vector_director.m1_harness.harness import evaluate, save_run
from vector_director.m1_harness.judge import Verdict, VisionJudge, contact_sheet
from vector_director.m1_harness.llm import Reply, inline_schema, make_llm
from vector_director.m1_harness.prompts import make_prompt_set
from vector_director.m1_harness.render import PlaywrightRenderer, _svg_size
from vector_director.m1_harness.scorers import CriticScorer, MotionScorer, ValidityScorer

BALL = {
    "prompt": "a red ball bounces",
    "duration": 2,
    "objects": [{"id": "ball", "svg": '<circle cx="100" cy="100" r="40" fill="red"/>'}],
    "tracks": [
        {
            "target": "ball",
            "property": "translate",
            "keyframes": [
                {"t": 0, "value": [0, 0]},
                {"t": 1, "value": [0, 300], "easing": "ease-in"},
                {"t": 2, "value": [0, 0], "easing": "ease-out"},
            ],
        },
        {
            "target": "ball",
            "property": "fill",
            "keyframes": [{"t": 0, "value": "red"}, {"t": 2, "value": "blue"}],
        },
        {
            "target": "ball",
            "property": "opacity",
            "keyframes": [{"t": 0.5, "value": 1}, {"t": 1.5, "value": 0.2}],
        },
    ],
}


class FakeLLM:
    """Replays canned replies, records what it was asked."""

    provider, model = "fake", "fake-1"

    def __init__(self, *texts: str) -> None:
        self.texts = list(texts)
        self.prompts: list[str] = []

    def ask(self, system, prompt, schema, images=(), max_tokens=16000):
        self.prompts.append(prompt)
        return Reply(self.texts.pop(0), input_tokens=10, output_tokens=20)


def _frames(*colors, size=32):
    return Frames(
        [Image.new("RGB", (size, size), c) for c in colors], fps=12, width=size, height=size
    )


# compiler ------------------------------------------------------------------


def test_compiled_svg_parses_and_has_one_keyframes_block_per_track():
    svg = spec_to_svg(AnimationSpec.model_validate(BALL))
    root = ET.fromstring(svg)
    assert root.tag.endswith("svg") and root.get("data-vd-duration") == "2"
    assert svg.count("@keyframes") == 3
    for layer in ("translate", "rotate", "scale", "paint"):
        assert f'id="ball-{layer}"' in svg


def test_easing_is_how_motion_arrives_at_a_keyframe():
    svg = spec_to_svg(AnimationSpec.model_validate(BALL))
    block = re.search(r"@keyframes vd-ball-translate-0 \{(.*?)\n\}", svg, re.DOTALL).group(1)
    lines = block.strip().splitlines()
    assert "0.000%" in lines[0] and "ease-in;" in lines[0]  # segment 0 -> 1 eases in
    assert "50.000%" in lines[1] and "ease-out;" in lines[1]


def test_track_holds_value_before_first_and_after_last_keyframe():
    svg = spec_to_svg(AnimationSpec.model_validate(BALL))
    block = re.search(r"@keyframes vd-ball-opacity-2 \{(.*?)\n\}", svg, re.DOTALL).group(1)
    assert re.findall(r"([\d.]+)% \{ opacity: ([\d.]+)", block) == [
        ("0.000", "1"),
        ("25.000", "1"),
        ("75.000", "0.2"),
        ("100.000", "0.2"),
    ]


def test_opacity_and_scale_share_one_animation_rule():
    spec = AnimationSpec.model_validate(
        {
            **BALL,
            "tracks": BALL["tracks"]
            + [{"target": "ball", "property": "scale", "keyframes": [{"t": 0, "value": 1}]}],
        }
    )
    rule = re.search(r"#ball-scale \{ animation: (.*?); \}", spec_to_svg(spec)).group(1)
    assert "opacity" in rule and "scale" in rule


@pytest.mark.parametrize(
    "prop,value,css",
    [
        ("translate", [3, 4], "translate(3px, 4px)"),
        ("translate", 5, "translate(5px, 0px)"),
        ("rotate", 90, "rotate(90deg)"),
        ("scale", 2, "scale(2, 2)"),
        ("scale", "1.5 0.5", "scale(1.5, 0.5)"),
        ("opacity", 3, "1"),
        ("path", "M0 0L1 1", 'path("M0 0L1 1")'),
        ("fill", "#f00", "#f00"),
    ],
)
def test_css_value(prop, value, css):
    assert css_value(prop, value) == css


def test_svg_size():
    assert _svg_size('<svg width="300" height="200">') == (300, 200)
    assert _svg_size('<svg viewBox="0 0 64 48">') == (64, 48)
    assert _svg_size("<svg>") == (512, 512)


# generator -----------------------------------------------------------------


def test_generator_repairs_an_invalid_spec_once():
    bad = json.dumps({**BALL, "tracks": [{**BALL["tracks"][0], "target": "ghost"}]})
    llm = FakeLLM(bad, json.dumps(BALL))
    result = ApiSpecGenerator(llm=llm).generate("a red ball bounces")
    assert result.spec is not None and result.svg.startswith("<svg")
    assert result.meta["attempts"] == 2 and result.meta["output_tokens"] == 40
    assert "ghost" in llm.prompts[1] and "invalid" in llm.prompts[1]


def test_generator_gives_up_with_empty_svg():
    bad = json.dumps({**BALL, "duration": 0.5})
    result = ApiSpecGenerator(llm=FakeLLM(bad, bad)).generate("x")
    assert result.svg == "" and "error" in result.meta


def test_generator_uses_prompt_not_model_echo():
    result = ApiSpecGenerator(
        llm=FakeLLM(json.dumps({**BALL, "prompt": "something else"}))
    ).generate("mine")
    assert result.spec.prompt == "mine"


def test_make_llm_defaults_and_inline_schema_has_no_refs():
    assert make_llm("ollama").model == "qwen2.5-coder:7b"
    assert make_llm("ollama", vision=True).model == "qwen2.5vl:7b"
    assert make_llm("gemini", "gemini-x").model == "gemini-x"
    with pytest.raises(ValueError):
        make_llm("nope")
    schema = inline_schema(AnimationSpec)
    assert "$ref" not in json.dumps(schema) and "$defs" not in schema
    assert (
        schema["properties"]["tracks"]["items"]["properties"]["keyframes"]["items"]["type"]
        == "object"
    )


def test_protocols():
    assert isinstance(ApiSpecGenerator(llm=FakeLLM()), Generator)
    assert isinstance(BaselineGenerator(), Generator)
    assert isinstance(PlaywrightRenderer(), Renderer)
    assert isinstance(VisionJudge(llm=FakeLLM()), Critic)
    for s in (ValidityScorer(), MotionScorer(), CriticScorer(VisionJudge(llm=FakeLLM()))):
        assert isinstance(s, Scorer)


# judge ---------------------------------------------------------------------


def test_judge_maps_rubric_to_unit_score():
    verdict = json.dumps({"match": 5, "motion": 3, "craft": 1, "feedback": "ok"})
    sample = Sample("p", GenerationResult(svg="<svg/>"), frames=_frames("red", "blue"))
    score, feedback = VisionJudge(llm=FakeLLM(verdict)).critique(sample)
    assert score == pytest.approx(0.5) and feedback == "ok"
    assert sample.result.meta["judge_verdict"]["match"] == 5


def test_judge_scores_zero_on_garbage():
    sample = Sample("p", GenerationResult(svg="<svg/>"), frames=_frames("red"))
    score, feedback = VisionJudge(llm=FakeLLM("not json")).critique(sample)
    assert score == 0.0 and "no valid verdict" in feedback


def test_contact_sheet_size():
    sheet = contact_sheet([Image.new("RGB", (64, 64))] * 12, n=6, cols=3, cell=100)
    assert sheet.size == (3 * 100 + 2 * 4, 2 * 100 + 4)
    assert Verdict(match=1, motion=1, craft=1, feedback="").score == 0.0


# scorers -------------------------------------------------------------------


def test_validity_reasons():
    ok = Sample("p", GenerationResult(svg="<svg xmlns='http://www.w3.org/2000/svg'/>"))
    ok.frames = Frames([Image.new("RGB", (8, 8), "white")], 12, 8, 8)
    s = ValidityScorer().score(ok)
    assert s["parses"] == 1 and s["renders"] == 1 and s["nonblank"] == 0 and s["valid"] == 0

    img = Image.new("RGB", (8, 8), "white")
    img.putpixel((1, 1), (0, 0, 0))
    ok.frames = Frames([img], 12, 8, 8)
    assert ValidityScorer().score(ok)["valid"] == 1

    bad = Sample(
        "p", GenerationResult(svg="<svg><script>alert(1)</script></svg>"), frames=ok.frames
    )
    assert ValidityScorer().score(bad)["safe"] == 0
    assert ValidityScorer().score(Sample("p", GenerationResult(svg="<svg")))["parses"] == 0


def test_motion():
    still = Sample("p", GenerationResult(svg=""), frames=_frames("red", "red", "red"))
    flip = Sample("p", GenerationResult(svg=""), frames=_frames("red", "blue", "red"))
    assert MotionScorer().score(still)["motion"] == 0
    assert MotionScorer().score(flip) == {"motion": 1.0, "motion_l1": 1.0, "moving_frac": 1.0}


# prompts + harness ---------------------------------------------------------


def test_prompt_set_is_deterministic_and_distinct():
    a, b = make_prompt_set(50, seed=1), make_prompt_set(50, seed=1)
    assert a == b and len(set(a)) == 50
    assert make_prompt_set(50, seed=2) != a


class FakeRenderer:
    def render(self, svg, fps=12, duration=None):
        if "boom" in svg:
            raise ValueError("boom")
        frames = _frames("white", "black")
        frames.images[0].putpixel((0, 0), (0, 0, 0))  # not blank
        return frames


class BoomGenerator:
    name = "boom"

    def generate(self, prompt, context=()):
        if prompt == "raise":
            raise RuntimeError("api down")
        return GenerationResult(svg="<svg>boom</svg>")


def test_harness_survives_failures_and_saves(tmp_path):
    samples = evaluate(BoomGenerator(), ["raise", "render"], FakeRenderer(), [ValidityScorer()])
    assert "api down" in samples[0].result.meta["error"]
    assert "boom" in samples[1].result.meta["render_error"]
    assert all(s.scores["valid"] == 0 for s in samples)

    good = evaluate(BaselineGenerator(), ["a"], FakeRenderer(), [ValidityScorer(), MotionScorer()])
    board = json.loads(save_run(good, tmp_path).read_text())
    assert board["n"] == 1 and board["summary"]["valid"] == 1
    assert len(list(tmp_path.glob("*.gif"))) == 1 and len(list(tmp_path.glob("*.svg"))) == 1


# renderer (needs Chromium) -------------------------------------------------


@pytest.fixture(scope="module")
def renderer():
    r = PlaywrightRenderer(fps=4)
    try:
        r._ensure_browser()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"no browser: {exc!s:.80}")
    yield r
    r.close()


def test_render_seeks_css_animation(renderer):
    import numpy as np

    frames = renderer.render(spec_to_svg(AnimationSpec.model_validate(BALL)))
    assert len(frames.images) == 8 and frames.width == 512

    def ball(im):
        a = np.asarray(im).astype(int)
        ys, xs = np.where(a.sum(-1) < 700)
        return ys.mean(), a[int(ys.mean()), int(xs.mean())]

    y0, c0 = ball(frames.images[0])
    y4, c4 = ball(frames.images[4])  # t = 1s, bottom of the bounce
    assert y0 == pytest.approx(100, abs=3) and y4 == pytest.approx(400, abs=3)
    assert c0[0] > 200 and c4[2] > c0[2]  # red turning blue


def test_render_end_to_end_scores(renderer):
    samples = evaluate(BaselineGenerator(), ["x"], renderer, [ValidityScorer(), MotionScorer()])
    assert samples[0].scores["valid"] == 1 and samples[0].scores["motion"] > 0
