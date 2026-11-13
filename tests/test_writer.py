import copy
import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from autopilot import llm, story, writer  # noqa: E402
from autopilot.topics import Topic  # noqa: E402

CAT = story.load_catalog()
SAMPLE = json.loads((ROOT / "stories/sample/lighthouse.json").read_text())
CFG = {"llm": {"model": "m1", "fallback_models": ["m2"]}}
TOPIC = Topic("t1", "Why Lighthouses Flash in Patterns", "engineering", "explainer", "a wait-really angle")
NOTES = ("VERDICT: TRUE\nFACTS:\n- facts [1]\nSOURCES:\n[1] Light characteristic - https://example.org/a\n"
         "[2] Fresnel lens - https://example.org/b\nHASHTAGS: #lighthouse #sailing #engineering")
GROUNDING = {"groundingChunks": [{"web": {"uri": "https://redirect/1", "title": "wikipedia.org"}},
                                 {"web": {"uri": "https://redirect/2", "title": "noaa.gov"}}]}


def good_draft():
    s = copy.deepcopy(SAMPLE)
    s["sources"] = []
    return s


class Fake:
    """Answers each prompt by its "### TASK:" line; queues per task, the last answer repeats."""

    def __init__(self, drafts=None, facts=None, hooks=None, grounded_error=None):
        self.drafts = drafts or [good_draft()]
        self.facts = facts or [{"ok": True, "problems": []}]
        self.hooks = hooks or [{"score": 9, "problems": []}]
        self.grounded_error = grounded_error
        self.prompts = {"draft_story": [], "fact_check": [], "hook_check": [], "research": []}
        self.tools = []

    def _next(self, q, n):
        return copy.deepcopy(q[min(n, len(q) - 1)])

    def text(self, prompt, models, tools=None, temperature=0.7, rounds=2):
        self.prompts["research"].append(prompt)
        self.tools.append(tools)
        if tools and self.grounded_error:
            raise RuntimeError(self.grounded_error)
        return NOTES, (GROUNDING if tools else {})

    def json(self, prompt, models, temperature=0.9):
        task = prompt.split("\n", 1)[0].replace("### TASK:", "").strip()
        self.prompts[task].append(prompt)
        n = len(self.prompts[task]) - 1
        if task == "draft_story":
            return self._next(self.drafts, n)
        if task == "fact_check":
            return self._next(self.facts, n)
        if task == "hook_check":
            return self._next(self.hooks, n)
        raise AssertionError(task)


@pytest.fixture
def fake(monkeypatch):
    def make(**kw):
        f = Fake(**kw)
        monkeypatch.setattr(llm, "generate_text", f.text)
        monkeypatch.setattr(llm, "generate_json", f.json)
        monkeypatch.setattr(writer, "check_url", lambda u: {"https://redirect/1": "https://en.wikipedia.org/wiki/X",
                                                            "https://redirect/2": "https://www.noaa.gov/y"}.get(u, u))
        return f
    return make


def test_happy_path(fake):
    f = fake()
    s = writer.write(TOPIC, CFG, CAT, log=lambda *a: None)
    assert story.validate(s, CAT) == []
    assert [x["url"] for x in s["sources"]][:2] == ["https://en.wikipedia.org/wiki/X", "https://www.noaa.gov/y"]
    assert s["hashtags"][:3] == ["#lighthouse", "#sailing", "#engineering"]
    assert len(f.prompts["draft_story"]) == 1
    assert f.tools[0] == [{"google_search": {}}]
    p = f.prompts["draft_story"][0]
    for word in ("ship_deck", "fresnel_lens", "low_hero", "whipL", "run_to", "plank", "costume_keys", "at_word",
                 "If your ship got hit by a cannonball", "Never reuse its topic", "Why Lighthouses Flash in Patterns",
                 "act fields"):
        assert word in p, word


def test_invalid_first_draft_redrafts_once(fake):
    bad = good_draft()
    bad["beats"][3]["set"]["type"] = "moon_base"
    f = fake(drafts=[bad, good_draft()])
    s = writer.write(TOPIC, CFG, CAT, log=lambda *a: None)
    assert story.validate(s, CAT) == []
    assert len(f.prompts["draft_story"]) == 2
    assert "unknown set 'moon_base'" in f.prompts["draft_story"][1]
    assert "Your previous draft" in f.prompts["draft_story"][1]


def test_two_invalid_drafts_fail(fake):
    bad = good_draft()
    bad["beats"][3]["set"]["type"] = "moon_base"
    fake(drafts=[bad])
    with pytest.raises(writer.WriteFailed, match="invalid story"):
        writer.write(TOPIC, CFG, CAT, log=lambda *a: None)


def test_fact_check_fails_twice(fake):
    f = fake(facts=[{"ok": False, "problems": ["the 1823 date is wrong"]}])
    with pytest.raises(writer.WriteFailed, match="fact-check failed"):
        writer.write(TOPIC, CFG, CAT, log=lambda *a: None)
    assert "fact-check: the 1823 date is wrong" in f.prompts["draft_story"][1]
    assert len(f.prompts["fact_check"]) == 2


def test_fact_check_redraft_passes(fake):
    f = fake(facts=[{"ok": False, "problems": ["x"]}, {"ok": True, "problems": []}])
    assert writer.write(TOPIC, CFG, CAT, log=lambda *a: None)
    assert len(f.prompts["draft_story"]) == 2


def test_one_working_source_fails(fake, monkeypatch):
    fake()
    monkeypatch.setattr(writer, "check_url", lambda u: "https://en.wikipedia.org/wiki/X" if u.endswith("/1") else None)
    with pytest.raises(writer.WriteFailed, match="not enough sources"):
        writer.write(TOPIC, CFG, CAT, log=lambda *a: None)


def test_grounding_429_falls_back(fake):
    f = fake(grounded_error="All Gemini models failed — m1: 429 rate limit: RESOURCE_EXHAUSTED")
    logs = []
    s = writer.write(TOPIC, CFG, CAT, log=logs.append)
    assert any("grounding unavailable" in x for x in logs)
    assert f.tools == [[{"google_search": {}}], None]
    assert [x["url"] for x in s["sources"]] == ["https://example.org/a", "https://example.org/b"]


def test_weak_hook_redrafts_once(fake):
    f = fake(hooks=[{"score": 4, "problems": ["plain fact"]}, {"score": 8}])
    writer.write(TOPIC, CFG, CAT, log=lambda *a: None)
    assert len(f.prompts["draft_story"]) == 2
    assert "hook: hook score 4/10" in f.prompts["draft_story"][1]


def test_hook_rules():
    s = good_draft()
    assert writer.hook_problems(s) == []
    s["beats"][0]["text"], s["beats"][1]["text"] = "Lighthouses stand on the coast", "beside the dark sea,"
    assert any("second-person" in x for x in writer.hook_problems(s))
    s["beats"][0]["text"] = "If you " + "very " * 16 + "long"
    assert any("words" in x for x in writer.hook_problems(s))


def test_hook_rules_still_broken_after_redraft(fake):
    s = good_draft()
    s["beats"][0]["text"], s["beats"][1]["text"] = "Lighthouses stand on the coast", "beside the dark sea,"
    fake(drafts=[s], hooks=[{"score": 3}])
    with pytest.raises(writer.WriteFailed, match="hook check failed"):
        writer.write(TOPIC, CFG, CAT, log=lambda *a: None)


def test_myth_verdict(fake, monkeypatch):
    fake()
    monkeypatch.setattr(llm, "generate_text", lambda *a, **k: ("VERDICT: MYTH\n", {}))
    with pytest.raises(writer.WriteFailed, match="myth"):
        writer.write(TOPIC, CFG, CAT, log=lambda *a: None)


def test_propose_topics(fake, monkeypatch):
    seen = {}

    def gj(prompt, models, temperature=0.9):
        seen["p"], seen["m"] = prompt, models
        return {"topics": [{"title_idea": "Why X", "category": "history", "format": "explainer", "angle": "a"}, "junk"]}
    monkeypatch.setattr(llm, "generate_json", gj)
    out = writer.propose_topics(3, ["Old Title"], CFG)
    assert out == [{"title_idea": "Why X", "category": "history", "format": "explainer", "angle": "a"}]
    assert "Old Title" in seen["p"] and seen["m"] == ["m1", "m2"]


def test_generate_text_parses_grounding(monkeypatch):
    class R:
        status_code = 200
        text = ""

        def json(self):
            return {"candidates": [{"content": {"parts": [{"text": "hello"}]}, "groundingMetadata": GROUNDING}]}
    sent = {}

    def post(url, headers=None, json=None, timeout=None):
        sent["body"] = json
        return R()
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    monkeypatch.setattr(llm.requests, "post", post)
    text, g = llm.generate_text("hi", ["m1"], tools=[{"google_search": {}}])
    assert text == "hello" and g == GROUNDING
    assert sent["body"]["tools"] == [{"google_search": {}}]
    assert "responseMimeType" not in sent["body"]["generationConfig"]
