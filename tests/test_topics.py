import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from autopilot import story, topics as T  # noqa: E402


def entry(id, cat, fmt="explainer", title=None, status="queued"):
    return {"id": id, "title_idea": title or f"Title {id}", "category": cat, "format": fmt, "angle": "a",
            "status": status, "used_on": None, "reason": None}


def test_rotation_skips_same_category():
    bl = [entry("a", "history"), entry("b", "science")]
    t = T.next_topic(bl, [], [{"category": "history", "format": "explainer"}])
    assert t.id == "b" and isinstance(t, T.Topic)


def test_no_two_levels_in_a_row():
    bl = [entry("a", "what_if", "levels"), entry("b", "science")]
    t = T.next_topic(bl, [], [{"category": "levels", "format": "levels"}])
    assert t.id == "b"


def test_similar_title_skipped():
    bl = [entry("a", "engineering", title="Why Lighthouses Blink in Patterns"), entry("b", "science")]
    t = T.next_topic(bl, ["Why Lighthouses Flash in Patterns"], [])
    assert t.id == "b"
    assert T.similar("Why Lighthouses Blink in Patterns", "Why Lighthouses Flash in Patterns") >= 0.6


def test_all_blocked_by_rotation_returns_first_non_duplicate():
    logs = []
    bl = [entry("a", "history", title="Why Lighthouses Blink in Patterns"), entry("b", "history"),
          entry("c", "history")]
    t = T.next_topic(bl, ["Why Lighthouses Flash in Patterns"], [{"category": "history"}], log=logs.append)
    assert t.id == "b"
    assert any("rotation relaxed" in x for x in logs)


def test_empty_and_used_only():
    assert T.next_topic([], [], []) is None
    assert T.next_topic([entry("a", "history", status="used")], [], []) is None


def test_needs_refill():
    assert T.needs_refill([entry(str(i), "history") for i in range(9)])
    assert not T.needs_refill([entry(str(i), "history") for i in range(10)])
    assert T.needs_refill([entry(str(i), "history", status="used") for i in range(20)])


def test_mark_save_load_roundtrip(tmp_path):
    bl = [entry("a", "history"), entry("b", "science")]
    T.mark(bl, "a", "failed", reason="not enough sources", date="2026-11-13")
    T.save(tmp_path / "b.yaml", bl)
    back = T.load(tmp_path / "b.yaml")
    assert back[0]["status"] == "failed" and back[0]["reason"] == "not enough sources"
    assert back[0]["used_on"] == "2026-11-13"
    with pytest.raises(KeyError):
        T.mark(bl, "zzz", "used")
    with pytest.raises(ValueError):
        T.mark(bl, "a", "bogus")


def test_add_proposals_dedupes_and_validates():
    bl = [entry("why-x", "history", title="Why X Happens")]
    n = T.add(bl, [{"title_idea": "Why X Happens", "category": "history", "format": "explainer", "angle": "a"},
                   {"title_idea": "A Brand New Idea", "category": "nonsense", "format": "explainer", "angle": "a"},
                   {"title_idea": "Totally Fresh Topic", "category": "science", "format": "explainer", "angle": "a"}],
              ["Old Published Title"], log=lambda *a: None)
    assert n == 1 and bl[-1]["id"] == "totally-fresh-topic" and bl[-1]["status"] == "queued"


def test_seed_backlog_is_valid():
    bl = T.load(ROOT / "topics" / "backlog.yaml")
    assert len(bl) >= 30
    ids = [e["id"] for e in bl]
    assert len(set(ids)) == len(ids)
    cats = {e["category"] for e in bl}
    assert cats == set(T.CATEGORIES)
    ricks = ["Why Sailors Carried Storm Oil", "What the Grave Bell Really Meant", "The Burglar Who Only Moved Furniture",
             "Why Perfect Railroads Don't Work", "This Shape Saved Roller Coasters", "Levels of Pirate Cannonballs",
             "Why Lighthouses Flash in Patterns"]
    for e in bl:
        assert e["format"] in T.FORMATS and e["status"] == "queued" and e["angle"]
        assert len(e["title_idea"]) <= 60, e["title_idea"]
        assert all(T.similar(e["title_idea"], r) < 0.6 for r in ricks), e["title_idea"]
        assert not story.rules.title_problems(e["title_idea"]), e["title_idea"]
        assert (e["format"] == "levels") == (e["category"] == "levels")
