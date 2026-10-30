"""Props: the contract is enforced in code. The browser tests skip without Chromium."""

import json
import xml.etree.ElementTree as ET

import pytest

from vector_director.m1_harness.llm import Reply
from vector_director.m1_harness.prop import (
    CENTRE_X,
    GROUND_Y,
    PX_PER_CM,
    check,
    clean_fragment,
    make_prop,
    measure,
    place,
)

WELL = '<rect x="10" y="40" width="80" height="60" fill="#888"/><circle cx="50" cy="30" r="20" fill="#642"/>'


def test_clean_prefixes_ids_and_their_references():
    out = clean_fragment(
        '<defs><linearGradient id="a"/></defs><rect id="b" width="9" height="9" fill="url(#a)"/>',
        "well",
    )
    assert 'id="well-a"' in out and 'id="well-b"' in out and "url(#well-a)" in out


def test_clean_drops_references_to_nothing():
    assert "url(#" not in clean_fragment('<rect width="9" height="9" fill="url(#gone)"/>', "x")


@pytest.mark.parametrize(
    "bad",
    [
        "<script>x</script><rect/>",
        '<image href="a.png"/>',
        "<style>*{}</style><rect/>",
        "<rect",
        "<g></g>",
    ],
)
def test_clean_refuses(bad):
    with pytest.raises(ValueError):
        clean_fragment(bad, "x")


def test_clean_strips_handlers_and_outer_svg():
    out = clean_fragment(
        '<svg viewBox="0 0 9 9"><rect width="9" height="9" onclick="x()"/></svg>', "x"
    )
    assert "onclick" not in out and "<svg" not in out


def test_place_stands_it_on_the_ground_at_its_real_height():
    svg = place(WELL, (10, 10, 80, 90), 100)
    t = ET.fromstring(svg).find("{http://www.w3.org/2000/svg}g").get("transform")
    tx, ty = [float(v) for v in t[len("translate(") : t.index(")")].split()]
    s = float(t[t.index("scale(") + 6 : -1])
    assert s * 90 == pytest.approx(100 * PX_PER_CM, abs=0.01)
    assert (10 + 40) * s + tx == pytest.approx(CENTRE_X, abs=0.01)
    assert (10 + 90) * s + ty == pytest.approx(GROUND_Y, abs=0.01)


def test_check_flags_backgrounds_and_empty():
    assert check({"coverage": 0.5, "bbox": [1, 1, 9, 9]}) == []
    assert check({"coverage": 0.99, "bbox": [1, 1, 9, 9]})
    assert check({"coverage": 0.01, "bbox": [1, 1, 9, 9]})
    assert check({"coverage": 0.0, "bbox": None})


class FakeLLM:
    provider, model = "fake", "fake"

    def __init__(self, *svgs):
        self.svgs, self.prompts = list(svgs), []

    def ask(self, system, prompt, schema, images=(), max_tokens=16000):
        self.prompts.append(prompt)
        return Reply(json.dumps({"svg": self.svgs.pop(0)}))


@pytest.fixture(scope="module")
def page():
    try:
        from playwright.sync_api import sync_playwright

        pw = sync_playwright().start()
        browser = pw.chromium.launch()
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"no browser: {e}")
    yield browser.new_page()
    browser.close()
    pw.stop()


def test_measure_uses_the_browser(page):
    assert measure(page, WELL) == pytest.approx((10, 10, 80, 90))


def test_make_prop_repairs_once_and_meets_the_contract(page):
    llm = FakeLLM('<rect width="100" height="100" fill="#888"/>', WELL)
    prop = make_prop("a well", "well", 110, llm, page)
    assert prop.meta["attempts"] == 2 and "Fix these problems" in llm.prompts[1]
    left, top, right, bottom = prop.meta["bbox"]
    assert bottom == pytest.approx(GROUND_Y, abs=2)
    assert (left + right) / 2 == pytest.approx(CENTRE_X, abs=2)
    assert bottom - top == pytest.approx(110 * PX_PER_CM, abs=3)


def test_make_prop_gives_up_with_the_reasons(page):
    with pytest.raises(ValueError, match="not allowed"):
        make_prop("a well", "well", 110, FakeLLM("<script/>", "<script/>"), page)


def test_clean_fragment_refuses_a_bad_number():
    import pytest

    with pytest.raises(ValueError, match="not a number"):
        clean_fragment('<circle cx="115,302" cy="10" r="3"/>', "x")
