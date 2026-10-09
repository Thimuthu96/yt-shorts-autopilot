"""Offline check of the lesson formats: curriculum + glossary validator, episode picker, example
schema and scene plan (no API keys, no network).

    python tests/test_lessons.py
"""
import copy
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from autopilot import lessons  # noqa: E402
from autopilot.history import History  # noqa: E402

SAMPLE = ROOT / "tests" / "lessons"


def stub_detectors() -> dict:
    """Test-only registry standing in for entry 2's structure detectors."""
    reg = {}
    lessons.register(lessons.Detector("swings", "swing_point", lambda *a, **k: []), reg)
    lessons.register(lessons.Detector("bos_choch", ("break_of_structure", "change_of_character"),
                                      lambda *a, **k: []), reg)
    return reg


def sample():
    return (lessons.load_curriculum(SAMPLE / "curriculum.yaml"), lessons.load_glossary(SAMPLE / "glossary.yaml"),
            stub_detectors())


def test_validate():
    cur, glo, det = sample()
    assert len(cur) == 2 and all(e["track"] == 0 and e["visual"] == "chart" for e in cur)
    assert lessons.validate(cur, glo, det) == [], lessons.validate(cur, glo, det)

    def errors(mutate, glossary=glo):
        c = copy.deepcopy(cur)
        mutate(c)
        return lessons.validate(c, glossary, det)

    e = errors(lambda c: c[1].update(visual="sessions"))
    assert e == ["bos-vs-choch: unknown visual type 'sessions'"], e
    e = errors(lambda c: c[0].update(detector="fvg"))
    assert e == ["swing-structure: detector 'fvg' is not registered"], e
    e = errors(lambda c: c[0]["concepts"].append("order_block"))
    assert e == ["swing-structure: glossary key 'order_block' is missing"], e
    # the detector's own glossary key must exist too
    g = {k: v for k, v in glo.items() if k != "change_of_character"}
    e = errors(lambda c: c[1]["concepts"].remove("change_of_character"), g)
    assert e == ["bos-vs-choch: glossary key 'change_of_character' is missing"], e
    g = copy.deepcopy(glo)
    g["swing_point"]["definition"] = " "
    e = lessons.validate(cur, g, det)
    assert e == ["swing-structure: glossary key 'swing_point' has an empty definition",
                 "bos-vs-choch: glossary key 'swing_point' has an empty definition"], e
    e = errors(lambda c: c[1].update(id="swing-structure", prerequisites=[]))
    assert e == ["swing-structure: duplicate id"], e
    e = errors(lambda c: c[0].pop("key_points"))
    assert e == ["swing-structure: missing field 'key_points'"], e
    e = errors(lambda c: c[0].update(key_points=[]))
    assert e == ["swing-structure: key_points must be a non-empty list of text"], e
    e = errors(lambda c: c.reverse())  # prerequisites must come earlier
    assert e == ["bos-vs-choch: prerequisite 'swing-structure' is not an earlier episode"], e
    e = errors(lambda c: c[0].update(track=7))
    assert e == ["swing-structure: track 7 is not 0-6"], e
    # non-string values are listed, never raised
    e = errors(lambda c: c[0].update(visual=["chart"]))
    assert e == ["swing-structure: unknown visual type '['chart']'"], e
    e = errors(lambda c: c[0].update(concepts=[["swing_point"]]))
    assert e == ["swing-structure: concepts must be a list of glossary keys"], e
    e = errors(lambda c: c[1].update(prerequisites=[{"id": "swing-structure"}]))
    assert e == ["bos-vs-choch: prerequisites must be a list of episode ids"], e
    e = errors(lambda c: c[0].pop("id"))
    assert "#1: missing field 'id'" in e and "bos-vs-choch: prerequisite 'swing-structure' is not an earlier episode" in e
    print("OK validate (sample passes; unknown visual, missing detector, missing/empty glossary key, "
          "duplicates, missing fields, prerequisites)")


def test_pick():
    cur, _, _ = sample()
    with tempfile.TemporaryDirectory() as tmp:
        h = History(Path(tmp) / "history.json")
        p = lessons.pick(cur, h, "2026-10-12", "lesson")
        assert p.entry["id"] == "swing-structure" and not p.rerun and p.held == []
        h.add({"brief_date": "2026-10-12", "session": "lesson", "kind": "lesson", "episode": "swing-structure",
               "video_id": "L1"})
        p = lessons.pick(cur, h, "2026-10-13", "lesson")
        assert p.entry["id"] == "bos-vs-choch" and not p.rerun
        # reordering the curriculum changes the next pick with no code change
        assert lessons.pick(list(reversed(cur)), History(Path(tmp) / "none.json"), "2026-10-13", "lesson") \
            .entry["id"] == "bos-vs-choch"
        # re-run of a slot: the recorded episode again, even though it's published, and even if held
        p = lessons.pick(cur, h, "2026-10-12", "lesson", hold=lambda e: "no clean example")
        assert p.entry["id"] == "swing-structure" and p.rerun and p.held == []
        # a manual run (counts: false) publishes the episode but doesn't fill the slot
        h.add({"brief_date": "2026-10-13", "session": "lesson", "episode": "bos-vs-choch", "fb_reel_id": "M1",
               "trigger": "manual", "counts": False})
        p = lessons.pick(cur, h, "2026-10-13", "lesson")
        assert p.entry is None and not p.rerun, p  # both published: queue exhausted
        # held: skipped with its reason, the next one returned
        h2 = History(Path(tmp) / "h2.json")
        hold = lambda e: "no clean example in BTC/ETH/gold 1H-1D" if e["id"] == "swing-structure" else None  # noqa: E731
        p = lessons.pick(cur, h2, "2026-10-12", "lesson", hold=hold)
        assert p.entry["id"] == "bos-vs-choch" and p.held == [("swing-structure", "no clean example in BTC/ETH/gold 1H-1D")]
        # all held → nothing, holds listed
        p = lessons.pick(cur, h2, "2026-10-12", "lesson", hold=lambda e: "no data")
        assert p.entry is None and p.held == [("swing-structure", "no data"), ("bos-vs-choch", "no data")]
        # an unpublished history entry (no platform id) doesn't count
        h2.add({"brief_date": "2026-10-12", "session": "lesson", "episode": "swing-structure"})
        assert lessons.pick(cur, h2, "2026-10-12", "lesson").entry["id"] == "swing-structure"
        # deterministic: same inputs, same answer
        assert lessons.pick(cur, h, "2026-10-14", "lesson") == lessons.pick(cur, h, "2026-10-14", "lesson")
    print("OK pick (next, re-run, held, exhausted, manual runs, curriculum order)")


def example(**over) -> dict:
    ex = {
        "detector": "bos_choch", "glossary": "break_of_structure", "asset": "BTC/USD", "timeframe": "1H",
        "date": "2026-09-30",
        "candles": [{"t": "2026-09-30T00:00:00+00:00", "o": 63000.0, "h": 63250.0, "l": 62900.0, "c": 63200.0},
                    {"t": "2026-09-30T01:00:00+00:00", "o": 63200.0, "h": 63600.0, "l": 63150.0, "c": 63550.0}],
        "region": {"start": "2026-09-30T00:00:00+00:00", "end": "2026-09-30T01:00:00+00:00",
                   "low": 62900.0, "high": 63600.0},
        "primitives": [
            {"type": "swing", "t": "2026-09-30T00:00:00+00:00", "price": 63250.0, "kind": "HH"},
            {"type": "level", "price": 63250.0, "label": "BOS"},
            {"type": "trendline", "t1": "2026-09-30T00:00:00+00:00", "p1": 62900.0,
             "t2": "2026-09-30T01:00:00+00:00", "p2": 63150.0},
            {"type": "zone", "t1": "2026-09-30T00:00:00+00:00", "t2": "2026-09-30T01:00:00+00:00",
             "low": 63150.0, "high": 63250.0, "label": "FVG"},
            {"type": "label", "t": "2026-09-30T01:00:00+00:00", "price": 63600.0, "text": "BOS"},
        ],
        "facts": {"broken_level": 63250.0, "close": 63550.0},
    }
    ex.update(over)
    return ex


def test_examples():
    assert lessons.validate_example(example()) == [], lessons.validate_example(example())
    bad = example(primitives=[{"type": "arrow", "t": "2026-09-30T00:00:00+00:00"}])
    e = lessons.validate_example(bad)
    assert e == ["primitive 0: unknown primitive type 'arrow'"], e
    bad = example(primitives=[{"type": "zone", "t1": "2026-09-30T00:00:00+00:00", "low": 1.0, "high": 1.1}])
    e = lessons.validate_example(bad)
    assert e == ["primitive 0 (zone): missing field 't2'"], e
    bad = example(primitives=[{"type": "swing", "t": "yesterday", "price": 1.0, "kind": "top"}])
    e = lessons.validate_example(bad)
    assert any("(swing): t 'yesterday' is not ISO-8601" in x for x in e) and any("kind 'top'" in x for x in e), e
    e = lessons.validate_example({k: v for k, v in example().items() if k != "region"})
    assert e == ["missing field 'region'"], e
    bad = example()
    bad["candles"][0]["h"] = 62000.0
    assert lessons.validate_example(bad) == ["candle 0: low/high don't contain open/close"]
    assert set(lessons.PRIMITIVES) == {"level", "trendline", "zone", "swing", "label"}
    print("OK examples (valid example, unknown primitive, missing field, bad time/kind, candles)")


def test_scene_plan():
    cur, _, _ = sample()
    ex2 = example(asset="XAU/USD", timeframe="4H")
    plan = lessons.scene_plan(cur[1], [example(), ex2], next_entry=None)
    assert [s["id"] for s in plan] == ["hook", "concept", "example_1", "example_2", "misreads", "recap"]
    assert plan[2]["visual"]["type"] == "chart" and plan[2]["visual"]["label"] == "Historical example · BTC/USD · 2026-09-30"
    assert plan[3]["visual"]["example"]["asset"] == "XAU/USD"
    assert all(set(s) == {"id", "visual", "covers"} and s["visual"]["type"] for s in plan)
    assert plan[-1]["visual"]["disclaimer"] and not plan[-1]["visual"]["non_affiliation"]
    plan = lessons.scene_plan(cur[0], [example(), ex2, example()], next_entry=cur[1])
    assert [s["id"] for s in plan] == ["hook", "concept", "example_1", "example_2", "misreads", "recap"]  # max 2
    plan = lessons.scene_plan(cur[0], [example()], next_entry=cur[1])
    assert [s["id"] for s in plan] == ["hook", "concept", "example_1", "misreads", "recap"]
    assert plan[-1]["visual"]["next"] == cur[1]["title"] and cur[1]["title"] in plan[-1]["covers"]
    ict = dict(cur[0], track=4)
    assert lessons.scene_plan(ict, [example()])[-1]["visual"]["non_affiliation"]
    try:
        lessons.scene_plan(cur[0], [])
        raise AssertionError("scene_plan without an example must fail")
    except ValueError:
        pass
    print("OK scene plan (hook, concept, example_1, optional example_2, misreads, recap)")


def test_real_files():
    cur = lessons.load_curriculum(lessons.CURRICULUM)
    glo = lessons.load_glossary(lessons.GLOSSARY)
    assert lessons.validate(cur, glo) == [], lessons.validate(cur, glo)
    stubs = {"swing_point", "market_structure", "break_of_structure", "change_of_character", "top_down_analysis",
             "trendline", "trendline_break", "fakeout", "retest", "trendline_liquidity",
             "buy_side_liquidity", "sell_side_liquidity", "equal_highs_lows", "session_high_low",
             "liquidity_sweep", "breakout", "inducement",
             "fair_value_gap", "order_block", "mitigation_block", "breaker_block", "premium_discount",
             "equilibrium", "sweep_choch_model"}
    assert stubs <= set(glo), stubs - set(glo)
    assert all(g.get("term") for g in glo.values())
    print(f"OK real lessons/ files ({len(cur)} episodes, {len(glo)} glossary keys, validate passes)")


def main():
    test_validate()
    test_pick()
    test_examples()
    test_scene_plan()
    test_real_files()


if __name__ == "__main__":
    main()
