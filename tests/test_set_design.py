"""Sets: the sky, the time-of-day tint and the solid floor come from code."""

import json
import xml.etree.ElementTree as ET

import pytest

from vector_director.m1_harness.llm import Reply
from vector_director.m1_harness.set_design import compose, make_set

GROUND = '<rect x="0" y="500" width="1200" height="300" fill="#C89"/>'
HOLEY = '<rect x="0" y="500" width="600" height="300" fill="#C89"/>'


def test_compose_has_a_sky_per_time_and_follows_the_players_classes():
    svg = compose("", "", GROUND, "outdoor", "well")
    ET.fromstring(svg)
    for t in ("day", "dusk", "night"):
        assert f"well-sky-{t}" in svg and f".set-{t}" in svg
    assert "well-tint" in svg


class FakeLLM:
    provider, model = "fake", "fake"

    def __init__(self, *drafts):
        self.drafts, self.prompts = list(drafts), []

    def ask(self, system, prompt, schema, images=(), max_tokens=16000):
        self.prompts.append(prompt)
        return Reply(json.dumps(self.drafts.pop(0)))


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


def test_a_floor_with_holes_is_sent_back(page):
    llm = FakeLLM(
        {"back": "", "middle": "", "ground": HOLEY}, {"back": "", "middle": "", "ground": GROUND}
    )
    art = make_set("a yard", "yard", "outdoor", llm, page)
    assert art.meta["attempts"] == 2 and "empty below" in llm.prompts[1]
    assert art.png[:4] == b"\x89PNG"


def test_an_interior_needs_its_back_wall(page):
    with pytest.raises(ValueError):
        make_set(
            "a room",
            "room",
            "interior",
            FakeLLM(*[{"back": "", "middle": "", "ground": GROUND}] * 2),
            page,
        )
