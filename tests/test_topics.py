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


# ─── backlog changes (the workflow re-applies a run's changes to origin's backlog) ───
def _changed():
    before = [entry("a", "history"), entry("b", "science"), entry("c", "engineering")]
    after = [dict(e) for e in before]
    T.mark(after, "a", "used", None, "2026-11-13")
    T.mark(after, "b", "failed", "too long: narration 64.0s", "2026-11-13")
    after.append(entry("d", "what_if", title="What If the Moon Had Rings"))
    return before, after


def test_changes_lists_marks_and_added():
    before, after = _changed()
    ch = T.changes(before, after)
    assert [m["id"] for m in ch["marks"]] == ["a", "b"]
    assert ch["marks"][1] == {"id": "b", "status": "failed", "reason": "too long: narration 64.0s",
                              "used_on": "2026-11-13"}
    assert [e["id"] for e in ch["added"]] == ["d"]
    assert T.changes(before, [dict(e) for e in before]) == {"marks": [], "added": []}


def test_apply_reproduces_the_run_on_a_newer_backlog_and_is_idempotent():
    before, after = _changed()
    ch = T.changes(before, after)
    origin = [dict(e) for e in before] + [entry("e", "luck_games", title="Why Dice Have Dots Not Numbers")]
    once = T.apply([dict(e) for e in origin], ch)
    twice = T.apply([dict(e) for e in once], ch)
    assert once == twice
    by = {e["id"]: e for e in once}
    assert by["a"]["status"] == "used" and by["b"]["status"] == "failed" and by["c"]["status"] == "queued"
    assert [e["id"] for e in once] == ["a", "b", "c", "e", "d"]


def test_apply_skips_unknown_ids_and_near_duplicate_additions():
    logs = []
    origin = [entry("x", "science", title="What If the Moon Had Rings Too")]
    ch = {"marks": [{"id": "gone", "status": "used", "reason": None, "used_on": "2026-11-13"}],
          "added": [entry("d", "what_if", title="What If the Moon Had Rings")]}
    out = T.apply(origin, ch, log=logs.append)
    assert [e["id"] for e in out] == ["x"]
    assert any("gone" in m for m in logs) and any("Moon" in m for m in logs)


def test_apply_cli(tmp_path):
    import json
    import subprocess
    before, after = _changed()
    bl = tmp_path / "backlog.yaml"
    T.save(bl, before)
    f1 = tmp_path / "1.json"
    f1.write_text(json.dumps(T.changes(before, after)))
    py = sys.executable
    for _ in range(2):
        r = subprocess.run([py, "-m", "autopilot.topics", "apply", "--backlog", str(bl), str(f1)], cwd=ROOT,
                           capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
    assert T.load(bl) == after
