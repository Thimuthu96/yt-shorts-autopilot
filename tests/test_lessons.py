"""Offline check of the lesson formats: curriculum + glossary validator, episode picker, example
schema (incl. the mtf `lower` panel) and scene plan, the structure, top-down and Track 1-2 trendline /
liquidity detectors (candle fixtures in tests/lessons/candles/), the lesson price-history fetch with
sources._get mocked and the lesson narration with Gemini mocked (no API keys, no network).

    python tests/test_lessons.py
"""
import copy
import json
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from autopilot import detectors, lesson_data, lesson_script, lessons, script, sources  # noqa: E402,F401  (detectors registers)
from autopilot.history import History  # noqa: E402

SAMPLE = ROOT / "tests" / "lessons"
CANDLES = SAMPLE / "candles"


def stub_detectors() -> dict:
    """Test-only registry standing in for the structure and top-down detectors."""
    reg = {}
    lessons.register(lessons.Detector("swings", "swing_point", lambda *a, **k: []), reg)
    lessons.register(lessons.Detector("bos_choch", ("break_of_structure", "change_of_character"),
                                      lambda *a, **k: []), reg)
    lessons.register(lessons.Detector("top_down", ("top_down_analysis", "market_structure"), lambda *a, **k: []), reg)
    return reg


def sample():
    return (lessons.load_curriculum(SAMPLE / "curriculum.yaml"), lessons.load_glossary(SAMPLE / "glossary.yaml"),
            stub_detectors())


def test_validate():
    cur, glo, det = sample()
    assert len(cur) == 3 and all(e["track"] == 0 for e in cur)
    assert [e["visual"] for e in cur] == ["chart", "chart", "mtf"] and cur[2]["detector"] == "top_down"
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
    assert e == ["swing-structure: duplicate id",
                 "top-down-reading: prerequisite 'bos-vs-choch' is not an earlier episode"], e
    e = errors(lambda c: c[0].pop("key_points"))
    assert e == ["swing-structure: missing field 'key_points'"], e
    e = errors(lambda c: c[0].update(key_points=[]))
    assert e == ["swing-structure: key_points must be a non-empty list of text"], e
    e = errors(lambda c: c.reverse())  # prerequisites must come earlier
    assert e == ["top-down-reading: prerequisite 'swing-structure' is not an earlier episode",
                 "top-down-reading: prerequisite 'bos-vs-choch' is not an earlier episode",
                 "bos-vs-choch: prerequisite 'swing-structure' is not an earlier episode"], e
    e = errors(lambda c: c[2].update(visual="walkthrough"))  # only chart and mtf exist
    assert e == ["top-down-reading: unknown visual type 'walkthrough'"], e
    assert lessons.VISUAL_TYPES == {"chart", "mtf"}
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
            .entry["id"] == "top-down-reading"
        # re-run of a slot: the recorded episode again, even though it's published, and even if held
        p = lessons.pick(cur, h, "2026-10-12", "lesson", hold=lambda e: "no clean example")
        assert p.entry["id"] == "swing-structure" and p.rerun and p.held == []
        # a manual run (counts: false) publishes the episode but doesn't fill the slot
        h.add({"brief_date": "2026-10-13", "session": "lesson", "episode": "bos-vs-choch", "fb_reel_id": "M1",
               "trigger": "manual", "counts": False})
        p = lessons.pick(cur, h, "2026-10-13", "lesson")
        assert p.entry["id"] == "top-down-reading" and not p.rerun, p
        h.add({"brief_date": "2026-10-14", "session": "lesson", "episode": "top-down-reading", "video_id": "L3"})
        p = lessons.pick(cur, h, "2026-10-15", "lesson")
        assert p.entry is None and not p.rerun, p  # all published: queue exhausted
        # held: skipped with its reason, the next one returned
        h2 = History(Path(tmp) / "h2.json")
        hold = lambda e: "no clean example in BTC/ETH/gold 1H-1D" if e["id"] == "swing-structure" else None  # noqa: E731
        p = lessons.pick(cur, h2, "2026-10-12", "lesson", hold=hold)
        assert p.entry["id"] == "bos-vs-choch" and p.held == [("swing-structure", "no clean example in BTC/ETH/gold 1H-1D")]
        # all held → nothing, holds listed
        p = lessons.pick(cur, h2, "2026-10-12", "lesson", hold=lambda e: "no data")
        assert p.entry is None and p.held == [("swing-structure", "no data"), ("bos-vs-choch", "no data"),
                                              ("top-down-reading", "no data")]
        # an unpublished history entry (no platform id) doesn't count
        h2.add({"brief_date": "2026-10-12", "session": "lesson", "episode": "swing-structure"})
        assert lessons.pick(cur, h2, "2026-10-12", "lesson").entry["id"] == "swing-structure"
        # deterministic: same inputs, same answer
        assert lessons.pick(cur, h, "2026-10-16", "lesson") == lessons.pick(cur, h, "2026-10-16", "lesson")
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


def mtf_example(**over) -> dict:
    """example() as a 4H higher-timeframe panel with a 1H `lower` panel inside it."""
    ex = example(detector="top_down", glossary="top_down_analysis", timeframe="4H", **over)
    ex["lower"] = {
        "timeframe": "1H",
        "candles": [{"t": "2026-09-30T00:00:00+00:00", "o": 63000.0, "h": 63100.0, "l": 62900.0, "c": 63050.0},
                    {"t": "2026-09-30T01:00:00+00:00", "o": 63050.0, "h": 63250.0, "l": 63000.0, "c": 63200.0}],
        "region": {"start": "2026-09-30T00:00:00+00:00", "end": "2026-09-30T01:00:00+00:00",
                   "low": 62900.0, "high": 63250.0},
        "primitives": [{"type": "swing", "t": "2026-09-30T01:00:00+00:00", "price": 63250.0, "kind": "HH"}],
    }
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

    # mtf: an optional `lower` panel, checked by the same rules, each problem prefixed "lower: "
    good = mtf_example()
    assert lessons.validate_example(good) == [], lessons.validate_example(good)
    bad = mtf_example()
    del bad["lower"]["candles"]
    assert lessons.validate_example(bad) == ["lower: missing field 'candles'"], lessons.validate_example(bad)
    bad = mtf_example()
    bad["lower"]["primitives"].append({"type": "arrow", "t": "2026-09-30T00:00:00+00:00"})
    assert lessons.validate_example(bad) == ["lower: primitive 1: unknown primitive type 'arrow'"], \
        lessons.validate_example(bad)
    bad = mtf_example()
    bad["lower"]["candles"][1]["l"] = 70000.0
    bad["lower"]["region"]["low"] = 99999.0
    e = lessons.validate_example(bad)
    assert e == ["lower: candle 1: low/high don't contain open/close",
                 "lower: region start/end or low/high are reversed"], e
    bad = mtf_example()
    bad["lower"]["timeframe"] = ""
    assert lessons.validate_example(bad) == ["lower: timeframe must be text"], lessons.validate_example(bad)
    assert lessons.validate_example(dict(example(), lower=[])) == ["lower: panel is not a mapping"]
    # the example's own problems keep their (unprefixed) names next to the panel's
    bad = mtf_example(primitives=[{"type": "arrow"}])
    del bad["lower"]["region"]
    assert lessons.validate_example(bad) == ["primitive 0: unknown primitive type 'arrow'",
                                             "lower: missing field 'region'"], lessons.validate_example(bad)
    print("OK examples (valid example, unknown primitive, missing field, bad time/kind, candles; "
          "mtf lower panel: missing candles, unknown primitive, bad candle/region, timeframe, not a mapping)")


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
    # mtf entry: example scenes take the entry's visual type, the example (with its lower panel) as is
    plan = lessons.scene_plan(cur[2], [mtf_example()])
    assert [s["id"] for s in plan] == ["hook", "concept", "example_1", "misreads", "recap"]
    v = plan[2]["visual"]
    assert v["type"] == "mtf" and v["example"]["lower"]["timeframe"] == "1H"
    assert v["label"] == "Historical example · BTC/USD · 2026-09-30"
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
    # the real registry (autopilot.detectors is imported above), not the test stubs
    assert {"swings", "bos_choch", "top_down"} <= set(lessons.DETECTORS), sorted(lessons.DETECTORS)
    assert lessons.DETECTORS["top_down"].glossary_keys() == ("top_down_analysis", "market_structure")
    for d in lessons.DETECTORS.values():
        assert set(d.glossary_keys()) <= set(glo), d
    s_cur, s_glo, _ = sample()
    assert lessons.validate(s_cur, s_glo) == [], lessons.validate(s_cur, s_glo)  # real registry
    td = next(e for e in s_cur if e["id"] == "top-down-reading")
    assert td["visual"] == "mtf" and td["detector"] == "top_down"
    print(f"OK real lessons/ files ({len(cur)} episodes, {len(glo)} glossary keys, validate passes; "
          f"real detectors: {', '.join(sorted(lessons.DETECTORS))})")


# ─── structure detectors ───────────────────────────────────────────────────

def candles(name: str) -> list[dict]:
    return json.loads((CANDLES / f"{name}.json").read_text(encoding="utf-8"))


def daily_fix(series: list[dict]) -> list[dict]:
    """A series as a daily reference fix would look (EUR/USD): o = h = l = c."""
    return [dict(c, o=c["c"], h=c["c"], l=c["c"]) for c in series]


def find(name: str, history: dict) -> list[dict]:
    return lessons.DETECTORS[name].find(history)


def check(examples: list[dict], history: dict):
    """Every example: valid schema, only 1.1's primitives, candles/region taken from the history."""
    assert len(examples) <= 2
    for ex in examples:
        assert lessons.validate_example(ex) == [], (ex["asset"], ex["timeframe"], lessons.validate_example(ex))
        assert {p["type"] for p in ex["primitives"]} <= set(lessons.PRIMITIVES)
        assert all(p["kind"] in lessons.SWING_KINDS for p in ex["primitives"] if p["type"] == "swing")
        src = history[ex["asset"]][ex["timeframe"]]
        assert 0 < len(ex["candles"]) <= 150 and all(c in src for c in ex["candles"])
        times = [c["t"] for c in ex["candles"]]
        assert times[0] <= ex["region"]["start"] <= ex["region"]["end"] <= times[-1]
        assert ex["date"] == ex["region"]["end"][:10]
        assert ex["facts"]["source"] and ex["facts"]["trend"] in ("uptrend", "downtrend")
        assert len(ex["facts"]["swings"]) >= 4
        # markers agree with the stated trend; only bos_choch may end on one disagreeing swing
        agree = {"HH", "HL"} if ex["facts"]["trend"] == "uptrend" else {"LH", "LL"}
        kinds = [s["kind"] for s in ex["facts"]["swings"]]
        allowed_off = 1 if ex["detector"] == "bos_choch" else 0
        off = [k for k in kinds if k not in agree]
        assert len(off) <= allowed_off and (not off or kinds[-1] not in agree), kinds
        assert sum(k in agree for k in kinds) >= 4, kinds
        if ex["detector"] == "bos_choch":
            f, swing_ts = ex["facts"], [s["t"] for s in ex["facts"]["swings"]]
            assert f["bos"]["swing_t"] in swing_ts and f["choch"]["swing_t"] in swing_ts
            assert f["bos"]["swing_kind"] in agree and f["choch"]["swing_kind"] in agree
            assert swing_ts[-1] < f["choch"]["t"] == ex["region"]["end"]


def test_detectors():
    up, down, chop = candles("uptrend"), candles("downtrend_bos_choch"), candles("choppy")

    # clean uptrend: HH/HL swing markers, no CHoCH so no bos_choch case
    h = {"BTC/USD": {"1H": up}}
    ex = find("swings", h)
    check(ex, h)
    assert len(ex) == 1 and ex[0]["detector"] == "swings" and ex[0]["facts"]["trend"] == "uptrend"
    kinds = [p["kind"] for p in ex[0]["primitives"] if p["type"] == "swing"]
    assert len(kinds) >= 4 and set(kinds) == {"HH", "HL"}, kinds
    assert {p["type"] for p in ex[0]["primitives"]} == {"swing"}
    assert find("bos_choch", h) == []

    # downtrend, BOS close, later CHoCH close
    h = {"BTC/USD": {"1H": down}}
    ex = find("bos_choch", h)
    check(ex, h)
    assert len(ex) == 1 and ex[0]["detector"] == "bos_choch" and ex[0]["facts"]["trend"] == "downtrend"
    e, f = ex[0], ex[0]["facts"]
    assert [p["label"] for p in e["primitives"] if p["type"] == "level"] == ["BOS", "CHoCH"]
    assert [p["text"] for p in e["primitives"] if p["type"] == "label"] == ["BOS", "CHoCH"]
    assert f["bos"]["close"] < f["bos"]["level"] and f["bos"]["swing_kind"] == "LL"  # close below the last low
    assert f["choch"]["close"] > f["choch"]["level"] and f["choch"]["swing_kind"] == "LH"  # first close above
    assert f["bos"]["t"] < f["choch"]["t"] == e["region"]["end"]
    assert {(c["t"], c["c"]) for c in down} >= {(f["bos"]["t"], f["bos"]["close"]), (f["choch"]["t"], f["choch"]["close"])}
    assert {p["kind"] for p in e["primitives"] if p["type"] == "swing"} <= {"LH", "LL"}
    sw = find("swings", h)
    check(sw, h)
    assert len(sw) == 1 and sw[0]["facts"]["trend"] == "downtrend"

    # BOS is the break of the run's latest LL at that moment, CHoCH the first close above the
    # latest LH after it; the HL that failed to make a LL is the one disagreeing swing, shown last
    hl = candles("downtrend_hl_choch")
    h = {"BTC/USD": {"1H": hl}}
    ex = find("bos_choch", h)
    check(ex, h)
    assert len(ex) == 1 and ex[0]["facts"]["trend"] == "downtrend"
    f, sws = ex[0]["facts"], ex[0]["facts"]["swings"]
    assert [s["kind"] for s in sws][-2:] == ["LH", "HL"], [s["kind"] for s in sws]
    assert f["choch"]["swing_t"] == sws[-2]["t"] and f["choch"]["level"] == sws[-2]["price"]  # the latest LH
    lls = [s for s in sws if s["kind"] == "LL"]
    assert f["bos"]["swing_t"] == lls[-2]["t"]  # the newest LL (the bottom) was never closed below
    assert lls[-2]["t"] < f["bos"]["t"] < lls[-1]["t"]  # broken while it was the latest LL
    assert all(c["c"] >= lls[-1]["price"] for c in hl if lls[-1]["t"] < c["t"] <= f["choch"]["t"])

    # a new low wicks below the last LL and a close below that LL follows before the new low's
    # fractal is confirmed (3 candles): the BOS is the break of the last *confirmed* LL at that close
    t0, wick = datetime(2026, 9, 1, tzinfo=timezone.utc), 0.3
    seq, price = [], 200.0
    for n, target in ((8, 208), (10, 190), (8, 197), (10, 184), (8, 191), (10, 177), (8, 184), (10, 170),
                      (8, 177), (10, 170.4)):
        for k in range(n):
            o, price = price, round(target if k == n - 1 else price + (target - price) / (n - k), 2)
            seq.append((o, max(o, price) + wick, min(o, price) - wick, price))
    seq += [(170.4, 170.6, 169.0, 170.3),  # wicks to a new low 169.0, closes above the LL (169.7)
            (170.3, 170.4, 169.2, 169.5)]  # closes below 169.7: the real BOS (169.0 not yet confirmed)
    price = 169.5
    for n, target in ((12, 186), (6, 181)):
        for k in range(n):
            o, price = price, round(target if k == n - 1 else price + (target - price) / (n - k), 2)
            seq.append((o, max(o, price) + wick, min(o, price) - wick, price))
    wick_bos = [{"t": (t0 + timedelta(hours=k)).isoformat(), "o": round(o, 2), "h": round(hi, 2),
                 "l": round(lo, 2), "c": round(c, 2)} for k, (o, hi, lo, c) in enumerate(seq)]
    h = {"BTC/USD": {"1H": wick_bos}}
    ex = find("bos_choch", h)
    check(ex, h)
    assert len(ex) == 1, ex
    f, close_t = ex[0]["facts"], wick_bos[91]["t"]  # candle 91 = the 169.5 close
    assert wick_bos[90]["l"] == 169.0 and wick_bos[91]["c"] == 169.5
    assert (f["bos"]["level"], f["bos"]["t"], f["bos"]["close"]) == (169.7, close_t, 169.5), f["bos"]
    assert f["swings"][-1]["price"] == 169.0  # the new low is shown once confirmed, before the CHoCH

    # after the run, a second swing outside it (HL, then LH, LL: a range) forms before price closes
    # above the run's last LH: no clean CHoCH, so no example built from a stale BOS and mixed swings
    h = {"BTC/USD": {"1H": candles("range_after_trend")}}
    assert find("bos_choch", h) == []
    sw = find("swings", h)
    check(sw, h)
    assert len(sw) == 1 and sw[0]["facts"]["trend"] == "downtrend"

    # two sources: second example on another asset, else another timeframe; asset beats timeframe
    h = {"BTC/USD": {"1H": down}, "ETH/USD": {"1H": up}}
    ex = find("swings", h)
    check(ex, h)
    assert len(ex) == 2 and {e["asset"] for e in ex} == {"BTC/USD", "ETH/USD"}
    h = {"XAU/USD": {"1H": up, "4H": down}}
    ex = find("swings", h)
    check(ex, h)
    assert len(ex) == 2 and ex[0]["asset"] == ex[1]["asset"] and ex[0]["timeframe"] != ex[1]["timeframe"]
    h = {"BTC/USD": {"1D": up, "4H": down}, "XAU/USD": {"1H": down}}  # all tie on swings + end: asset, tf order
    ex = find("swings", h)
    check(ex, h)
    assert [(e["asset"], e["timeframe"]) for e in ex] == [("BTC/USD", "1D"), ("XAU/USD", "1H")], ex
    h = {"BTC/USD": {"1H": down}, "EUR/USD": {"1D": daily_fix(down)}}
    ex = find("bos_choch", h)
    check(ex, h)
    assert [e["asset"] for e in ex] == ["BTC/USD", "EUR/USD"]
    assert ex[1]["facts"]["daily_reference_fix"] is True and "daily_reference_fix" not in ex[0]["facts"]
    assert "Frankfurter" in ex[1]["facts"]["source"]

    # more swings ranks first; a long run is trimmed to fit 150 candles
    long = []
    for k in range(3):
        for c in up:
            t = datetime.fromisoformat(c["t"]) + timedelta(hours=96 * k)
            long.append({"t": t.isoformat(), **{x: round(c[x] + 48 * k, 2) for x in "ohlc"}})
    h = {"BTC/USD": {"1H": up}, "ETH/USD": {"4H": long}}
    ex = find("swings", h)
    check(ex, h)
    assert ex[0]["asset"] == "ETH/USD" and len(ex[0]["facts"]["swings"]) > len(ex[1]["facts"]["swings"])
    assert len(ex[0]["candles"]) <= 150 and ex[0]["region"]["end"][:10] == "2026-09-12"

    # no clean case: choppy range, empty and too-short history
    for h in ({"BTC/USD": {"1H": chop}}, {"EUR/USD": {"1D": daily_fix(chop)}}, {}, {"BTC/USD": {"1H": up[:6]}}):
        assert find("swings", h) == [] and find("bos_choch", h) == [], h.keys()

    # repeat run: same history -> identical examples, byte for byte; input untouched
    h = {"BTC/USD": {"1H": down, "4H": up}, "ETH/USD": {"1H": up}, "EUR/USD": {"1D": daily_fix(down)}}
    before = json.dumps(h, sort_keys=True)
    for name in ("swings", "bos_choch"):
        a, b = find(name, h), find(name, copy.deepcopy(h))
        assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True) and a
    assert json.dumps(h, sort_keys=True) == before
    print("OK detectors (uptrend swings, BOS then CHoCH, latest-swing breaks + one disagreeing swing, "
          "range after trend -> no CHoCH, second example on another asset/timeframe, daily fix, "
          "ranking + 150-candle cap, choppy -> [], repeat runs identical, all examples valid)")


# ─── top-down (mtf) detector ───────────────────────────────────────────────

def aggregate(series: list[dict], seconds: int) -> list[dict]:
    """Higher-timeframe candles built the way lesson_data builds 4H from 1H."""
    rows = {int(datetime.fromisoformat(c["t"]).timestamp()): (c["o"], c["h"], c["l"], c["c"]) for c in series}
    return lesson_data._candles(lesson_data._aggregate(rows, seconds))


def retime(series: list[dict], hours: int) -> list[dict]:
    """The same candles spaced `hours` apart (the 1H fixture read as 4H candles)."""
    t0 = datetime.fromisoformat(series[0]["t"])
    return [dict(c, t=(t0 + timedelta(hours=hours * k)).isoformat()) for k, c in enumerate(series)]


def check_top_down(examples: list[dict], history: dict):
    """Every top_down example: valid with its lower panel, 1.1's primitives only, real candles of the
    same asset on the paired timeframes, the higher panel = the swings detector's case, the lower
    window inside the higher case's last leg with >= 4 labelled swings taken from its candles."""
    assert len(examples) <= 2
    for ex in examples:
        assert lessons.validate_example(ex) == [], lessons.validate_example(ex)
        low, f = ex["lower"], ex["facts"]
        htf, ltf = ex["timeframe"], low["timeframe"]
        assert (htf, ltf) in (("1D", "4H"), ("4H", "1H")) and ex["detector"] == "top_down"
        assert ex["glossary"] == "top_down_analysis"
        for panel in (ex, low):
            assert {p["type"] for p in panel["primitives"]} == {"swing"}
        src_h, src_l = history[ex["asset"]][htf], history[ex["asset"]][ltf]
        assert 0 < len(ex["candles"]) <= 150 and all(c in src_h for c in ex["candles"])
        assert 0 < len(low["candles"]) <= 150 and all(c in src_l for c in low["candles"])
        # higher panel: exactly what the swings detector shows for that series
        same = find("swings", {ex["asset"]: {htf: src_h}})[0]
        assert (ex["candles"], ex["region"], f["swings"], f["trend"]) == \
            (same["candles"], same["region"], same["facts"]["swings"], same["facts"]["trend"])
        assert f["htf"] == {"timeframe": htf, "trend": f["trend"]} and f["ltf"]["timeframe"] == ltf
        assert f["ltf"]["trend"] in ("uptrend", "downtrend", "mixed") and f["source"]
        assert f["aligned"] is (f["ltf"]["trend"] == f["trend"])
        # lower window: inside the higher case's last leg (2nd-to-last swing -> end of the last swing's candle)
        dt = datetime.fromisoformat
        leg0 = dt(f["swings"][-2]["t"])
        leg1 = dt(f["swings"][-1]["t"]) + timedelta(seconds=lesson_data.TF_SECONDS[htf])
        r = low["region"]
        assert leg0 <= dt(r["start"]) <= dt(r["end"]) < leg1, (r, leg0, leg1)
        assert ex["region"]["low"] <= r["low"] <= r["high"] <= ex["region"]["high"]
        times = [c["t"] for c in low["candles"]]
        assert times[0] <= r["start"] <= r["end"] <= times[-1]
        window = [c for c in src_l if r["start"] <= c["t"] <= r["end"]]
        assert (r["low"], r["high"]) == (min(c["l"] for c in window), max(c["h"] for c in window))
        sw = f["ltf"]["swings"]
        assert [{"type": "swing", **s} for s in sw] == low["primitives"]
        assert sum(s["kind"] in ("HH", "HL", "LH", "LL") for s in sw) >= 4, sw
        by_t = {c["t"]: c for c in src_l}
        for s in sw:  # every lower swing is a real candle's high or low inside the window
            assert r["start"] <= s["t"] <= r["end"] and s["price"] in (by_t[s["t"]]["h"], by_t[s["t"]]["l"]), s


def test_top_down():
    h1 = candles("top_down_1h")
    h4 = aggregate(h1, 4 * 3600)
    assert all(datetime.fromisoformat(c["t"]).hour % 4 == 0 for c in h4) and len(h4) == len(h1) // 4

    # clean pair: the 4H uptrend, and inside its last up leg the 1H's own HH/HL
    h = {"BTC/USD": {"4H": h4, "1H": h1}}
    ex = find("top_down", h)
    check_top_down(ex, h)
    assert len(ex) == 1 and (ex[0]["timeframe"], ex[0]["lower"]["timeframe"]) == ("4H", "1H")
    f = ex[0]["facts"]
    assert f["trend"] == f["ltf"]["trend"] == "uptrend" and f["aligned"] is True
    assert [s["kind"] for s in f["swings"]][-2:] == ["HL", "HH"]  # the last leg is an up leg
    assert lessons.example_label(ex[0]) == f"Historical example · BTC/USD · {ex[0]['date']}"

    # 1D -> 4H: the same nested candles read as 4H, aggregated to 1D
    d4 = retime(h1, 4)
    h = {"ETH/USD": {"1D": aggregate(d4, 86400), "4H": d4}}
    ex = find("top_down", h)
    check_top_down(ex, h)
    assert len(ex) == 1 and (ex[0]["timeframe"], ex[0]["lower"]["timeframe"]) == ("1D", "4H") and ex[0]["facts"]["aligned"]

    # two assets: one example each (the second on another asset)
    h = {"BTC/USD": {"4H": h4, "1H": h1}, "ETH/USD": {"1D": aggregate(d4, 86400), "4H": d4}}
    ex = find("top_down", h)
    check_top_down(ex, h)
    assert {(e["asset"], e["timeframe"]) for e in ex} == {("BTC/USD", "4H"), ("ETH/USD", "1D")}, ex

    # no LTF structure: the HTF case exists (swings finds it) but the 1H is flat -> [] for that asset
    flat = [dict(c, o=100.0, h=100.0, l=100.0, c=100.0) for c in h1]
    h = {"BTC/USD": {"4H": h4, "1H": flat}}
    assert find("swings", {"BTC/USD": {"4H": h4}}) and find("top_down", h) == []
    # ... and the other asset still gives its example
    h["ETH/USD"] = {"1D": aggregate(d4, 86400), "4H": d4}
    assert [e["asset"] for e in find("top_down", h)] == ["ETH/USD"]
    # no lower series, lower candles that end before the last leg, a 1H with nothing below it, empty
    for h in ({"BTC/USD": {"4H": h4}}, {"BTC/USD": {"4H": h4, "1H": h1[:120]}}, {"BTC/USD": {"1H": h1}}, {}):
        assert find("top_down", h) == [], h.keys()

    # lower trend = the most recent run of >= 2 agreeing swings: one trailing pullback swing doesn't
    # flip it; no two agreeing -> "mixed" (never aligned)
    kinds = lambda *ks: [{"kind": k} for k in ks]  # noqa: E731
    assert detectors.mtf._trend(kinds("HH", "HL", "HH", "HL", "LH")) == "uptrend"
    assert detectors.mtf._trend(kinds("LH", "LL", "LH", "LL", "HL")) == "downtrend"
    assert detectors.mtf._trend(kinds("HH", "HL", "HH", "LL", "LH")) == "downtrend"
    assert detectors.mtf._trend(kinds("HH", "LL", "HL", "LH")) == "mixed"
    # end to end: the lower window ends on one LH after HH/HL -> still uptrend and aligned; mixed -> not aligned
    real = detectors.mtf.find_swings

    def ltf_swings(kinds_at_end):
        def fake(candles):
            sw = real(candles)
            if candles is not h1:
                return sw
            w = [k for k, s in enumerate(sw) if s["kind"] in ("HH", "HL", "LH", "LL")][-len(kinds_at_end):]
            for k, kind in zip(w, kinds_at_end):
                sw[k] = dict(sw[k], kind=kind)
            return sw
        return fake
    h = {"BTC/USD": {"4H": h4, "1H": h1}}
    for tail, trend, aligned in ((("HH", "HL", "HH", "HL", "LH"), "uptrend", True),
                                 (("HH", "LL", "HL", "LH") * 4, "mixed", False)):  # no two agree anywhere
        with mock.patch.object(detectors.mtf, "find_swings", ltf_swings(tail)):
            f = find("top_down", h)[0]["facts"]
        got = [s["kind"] for s in f["ltf"]["swings"]]
        n = min(len(got), len(tail))
        assert n >= 5 and got[-n:] == list(tail[-n:]), (got, tail)
        assert (f["ltf"]["trend"], f["aligned"]) == (trend, aligned), (tail, f["ltf"]["trend"], f["aligned"])

    # repeat run: same history -> identical examples, byte for byte; input untouched
    h = {"BTC/USD": {"4H": h4, "1H": h1}, "ETH/USD": {"1D": aggregate(d4, 86400), "4H": d4}}
    before = json.dumps(h, sort_keys=True)
    a, b = find("top_down", h), find("top_down", copy.deepcopy(h))
    assert a and json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
    assert json.dumps(h, sort_keys=True) == before
    # earlier detectors unchanged by the new registry entry
    assert lessons.DETECTORS["swings"].glossary_keys() == ("swing_point", "market_structure")
    print("OK top_down (4H -> 1H and 1D -> 4H pairs, LTF window inside the HTF last leg, facts + aligned, "
          "one-swing pullback keeps the LTF trend, mixed -> not aligned, flat LTF -> [], missing / short LTF -> [], "
          "repeat runs identical, examples valid)")


# ─── tracks 1-2 detectors (trendlines, liquidity) ──────────────────────────

TRACK12 = {  # detector -> (its own fixture, primitive types its example must draw)
    "trendline": ("trendline_retest", {"swing", "trendline", "label"}),
    "trendline_break": ("trendline_retest", {"swing", "trendline", "label"}),
    "trendline_liquidity": ("trendline_liquidity", {"swing", "trendline", "zone"}),
    "liquidity_pools": ("liquidity_pools", {"swing", "level"}),
    "equal_highs_lows": ("equal_highs", {"swing", "level", "label"}),
    "session_highs_lows": ("sessions_1h", {"zone", "level", "label"}),
    "sweep_vs_breakout": ("sweep_breakout", {"swing", "level", "label"}),
    "inducement": ("inducement", {"swing", "level", "label"}),
}
# sha256 of the swings / bos_choch examples on the 1.2 fixtures, taken before the shared code moved
# to detectors/common.py: the move must not change a byte
STRUCTURE_DIGEST = "bcac0aba0d47fa432ccadf62b96f1809ec4365db5805c19c24f3d31b626cdcde"
COUNTS = {"touches"}  # facts that are counts, not prices


def _numbers(v, key=""):
    if isinstance(v, bool) or key in COUNTS:
        return
    if isinstance(v, (int, float)):
        yield v
    elif isinstance(v, dict):
        for k, x in v.items():
            yield from _numbers(x, k)
    elif isinstance(v, list):
        for x in v:
            yield from _numbers(x, key)


def check_track12(examples: list[dict], history: dict):
    """Every example: valid, 1.1's primitives only, its detector's glossary keys, real candles, and
    every number in its facts read from a candle of its series."""
    assert len(examples) <= 2
    glo = lessons.load_glossary(lessons.GLOSSARY)
    for ex in examples:
        assert lessons.validate_example(ex) == [], (ex["detector"], lessons.validate_example(ex))
        assert {p["type"] for p in ex["primitives"]} <= set(lessons.PRIMITIVES)
        keys = lessons.DETECTORS[ex["detector"]].glossary_keys()
        assert ex["glossary"] in keys and set(keys) <= set(glo), (ex["detector"], ex["glossary"])
        src = history[ex["asset"]][ex["timeframe"]]
        assert 0 < len(ex["candles"]) <= 150 and all(c in src for c in ex["candles"])
        times = [c["t"] for c in ex["candles"]]
        assert times[0] <= ex["region"]["start"] <= ex["region"]["end"] <= times[-1]
        assert ex["date"] == ex["region"]["end"][:10] and ex["facts"]["source"]
        values = {c[k] for c in src for k in "ohlc"}
        bad = [v for v in _numbers({k: v for k, v in ex["facts"].items()}) if v not in values]
        assert not bad, (ex["detector"], bad)
        by_t = {c["t"]: c for c in src}
        for s in ex["facts"].get("swings", []):
            assert s["price"] in (by_t[s["t"]]["h"], by_t[s["t"]]["l"]), s


def test_detectors_tracks_1_2():
    new = sorted(TRACK12)
    assert set(new) <= set(lessons.DETECTORS), sorted(lessons.DETECTORS)
    glo = lessons.load_glossary(lessons.GLOSSARY)
    for name in new:
        assert set(lessons.DETECTORS[name].glossary_keys()) <= set(glo), name

    # clean case per detector: its own seeded fixture -> >= 1 example with its primitives and glossary key
    found = {}
    for name, (fixture, prims) in TRACK12.items():
        h = {"BTC/USD": {"1H": candles(fixture)}}
        ex = find(name, h)
        check_track12(ex, h)
        assert ex and all(e["detector"] == name for e in ex), name
        assert prims <= {p["type"] for p in ex[0]["primitives"]}, (name, ex[0]["primitives"])
        found[name] = ex

    # trendline: 4 swing lows on one rising line, label "4 touches", line from the first touch to the last candle
    e = found["trendline"][0]
    f, line = e["facts"], next(p for p in e["primitives"] if p["type"] == "trendline")
    assert f["trend"] == "uptrend" and f["touches"] == len(f["swings"]) == 4 and f["line"] == "rising support"
    assert [p["text"] for p in e["primitives"] if p["type"] == "label"] == ["4 touches"]
    assert (line["t1"], line["p1"]) == (f["swings"][0]["t"], f["swings"][0]["price"]) and line["t2"] == e["candles"][-1]["t"]
    assert all(s["kind"] in ("low", "HL") for s in f["swings"])

    # trendline_break: retest (break close below, a rally back that closes below the line), fakeout
    e = found["trendline_break"][0]
    f = e["facts"]
    assert f["kind"] == "retest" and e["glossary"] == "retest", f
    assert f["break"]["t"] < f["retest"]["t"] == e["region"]["end"] and f["retest"]["close"] < f["retest"]["high"]
    assert [p["text"] for p in e["primitives"] if p["type"] == "label"] == ["Break", "Retest"]
    last_touch = f["swings"][-1]["t"]
    hl = candles("trendline_retest")
    k = next(i for i, c in enumerate(hl) if c["t"] == last_touch)
    assert f["break"]["t"] >= hl[k + 3]["t"]  # broken only after the last touch was confirmed
    h = {"BTC/USD": {"1H": candles("trendline_fakeout")}}
    ex = find("trendline_break", h)
    check_track12(ex, h)
    f = ex[0]["facts"]
    assert len(ex) == 1 and f["kind"] == "fakeout" and ex[0]["glossary"] == "fakeout" and f["trend"] == "downtrend"
    assert f["break"]["close"] > f["fakeout"]["close"] and f["fakeout"]["t"] == ex[0]["region"]["end"]
    assert [p["text"] for p in ex[0]["primitives"] if p["type"] == "label"] == ["Break", "Fakeout"]
    # a plain break: the retest rally cut off -> after 10 candles with no retest
    plain = trendline_plain()
    h = {"BTC/USD": {"1H": plain}}
    ex = find("trendline_break", h)
    check_track12(ex, h)
    assert len(ex) == 1 and ex[0]["facts"]["kind"] == "break" and ex[0]["glossary"] == "trendline_break", ex

    # a close below the line 1 candle after its 4th touch, before that touch is confirmed (3 candles):
    # the break belongs to the line as known then, through 3 touches
    early = early_break()
    h = {"BTC/USD": {"1H": early}}
    ex = find("trendline_break", h)
    check_track12(ex, h)
    f = ex[0]["facts"]
    assert f["touches"] == 3 and f["swings"][-1]["price"] == 105.5 and f["break"]["t"] == early[54]["t"], f

    # trendline_liquidity: a wick >= 0.5 ATR through the rising line, closing back above it; zone = the stops
    e = found["trendline_liquidity"][0]
    f, zone = e["facts"], next(p for p in e["primitives"] if p["type"] == "zone")
    assert f["touches"] >= 3 and f["pierce"]["low"] == 116.0 and f["pierce"]["close"] > zone["high"]
    assert zone["low"] == f["pierce"]["low"] < zone["high"] and zone["t2"] == f["pierce"]["t"] == e["region"]["end"]
    # the same wick but the candle closes below the line: a break, not a pierce -> no trendline_liquidity
    tl = candles("trendline_liquidity")
    k = next(i for i, c in enumerate(tl) if c["l"] == 116.0)
    closed = tl[:k] + [dict(tl[k], c=116.5)] + tl[k + 1:]
    assert find("trendline_liquidity", {"BTC/USD": {"1H": closed}}) == []

    # liquidity_pools: in the uptrend's pullback, BSL above the last HH, SSL below the two latest HLs
    e = found["liquidity_pools"][0]
    f = e["facts"]
    assert e["glossary"] == "buy_side_liquidity" and f["trend"] == "uptrend"
    assert [p["price"] for p in e["primitives"] if p.get("label") == "BSL"] == [s["price"] for s in f["bsl"]]
    assert all(s["price"] > f["at"]["close"] for s in f["bsl"]) and all(s["price"] < f["at"]["close"] for s in f["ssl"])
    assert len(f["bsl"]) == 1 and len(f["ssl"]) == 2
    # the top is a pool from its confirming candle (top + 3) on, never earlier
    lp = candles("liquidity_pools")
    top = max(range(len(lp)), key=lambda i: lp[i]["h"])
    for cut in (top + 1, top + 3):
        ex = find("liquidity_pools", {"BTC/USD": {"1H": lp[:cut]}})
        assert all(s["price"] != lp[top]["h"] for e in ex for s in e["facts"]["bsl"]), cut
    ex = find("liquidity_pools", {"BTC/USD": {"1H": lp[:top + 4]}})
    assert ex[0]["facts"]["bsl"][0]["price"] == lp[top]["h"] and ex[0]["facts"]["at"]["t"] == lp[top + 3]["t"]

    # equal_highs_lows: two highs 0.05 apart, 16 candles apart, EQH level at the higher one
    f = found["equal_highs_lows"][0]["facts"]
    assert f["label"] == "EQH" and (f["first"]["price"], f["second"]["price"], f["level"]) == (110.0, 110.05, 110.05)

    # session_highs_lows: day 1 (Asia ranged), not day 2 (Asia trended); 1H only (4H and 1D -> [])
    e = found["session_highs_lows"][0]
    f = e["facts"]
    assert f["day"] == "2026-09-01" and e["date"] == "2026-09-01"
    assert [z["label"] for z in e["primitives"] if z["type"] == "zone"] == ["Asia", "London", "New York"]
    assert {(t["session"], t["side"]) for t in f["taken"]} >= {("London", "high"), ("New York", "low")}
    assert all(t["price"] > f["asia"]["high"] if t["side"] == "high" else t["price"] < f["asia"]["low"] for t in f["taken"])
    s1h = candles("sessions_1h")
    # 4H buckets don't line up with the sessions, and daily data has none: only 4H / 1D series -> []
    for h in ({"BTC/USD": {"4H": aggregate(s1h, 4 * 3600)}}, {"BTC/USD": {"1D": retime(s1h, 24)}}, {"EUR/USD": {"1D": daily_fix(retime(s1h, 24))}},
              {"BTC/USD": {"1D": aggregate(s1h, 86400)}}):
        assert find("session_highs_lows", h) == [], h.keys()

    # sweep vs breakout: one of each in the fixture -> example 1 the sweep, example 2 the breakout
    ex = found["sweep_vs_breakout"]
    assert [e["facts"]["kind"] for e in ex] == ["sweep", "breakout"], ex
    assert [e["glossary"] for e in ex] == ["liquidity_sweep", "breakout"]
    sw, bo = ex[0]["facts"], ex[1]["facts"]
    assert sw["candle"]["high"] > sw["level"] >= sw["candle"]["close"] and all(c <= sw["level"] for c in sw["next_closes"])
    assert bo["candle"]["close"] > bo["level"] and all(c > bo["level"] for c in bo["next_closes"])
    assert len(bo["next_closes"]) == len(sw["next_closes"]) == 3
    sweeps = detectors.liquidity.find_sweeps(candles("sweep_breakout"),
                                             detectors.common.find_swings(candles("sweep_breakout")))
    assert [(s["kind"], s["t"]) for s in sweeps] == [("sweep", sw["candle"]["t"])]
    # any asset / timeframe: the best sweep (ETH) then the best breakout (the more recent one, BTC)
    h = {"BTC/USD": {"1H": candles("liquidity_pools")}, "ETH/USD": {"4H": candles("sweep_breakout")}}
    ex = find("sweep_vs_breakout", h)
    check_track12(ex, h)
    assert [(e["asset"], e["facts"]["kind"]) for e in ex] == [("ETH/USD", "sweep"), ("BTC/USD", "breakout")], ex

    # inducement: HH, first minor pullback low (IDM) taken before the HL, then a close above the HH
    e = found["inducement"][0]
    f = e["facts"]
    assert f["trend"] == "uptrend" and [s["kind"] for s in f["swings"]] == ["HL", "HH", "HL"]
    hh, hl2 = f["swings"][1], f["swings"][2]
    assert hh["t"] < f["idm"]["t"] < f["idm"]["taken_t"] < hl2["t"] < f["bos"]["t"] == e["region"]["end"]
    assert hl2["price"] < f["idm"]["taken_price"] < f["idm"]["price"] and f["bos"]["close"] > hh["price"] == f["bos"]["level"]
    assert [p["text"] for p in e["primitives"] if p["type"] == "label"] == ["BOS", "IDM"]
    # the BOS is the first close above the HH, even when it comes 2 candles after the HL (before the HL
    # is confirmed): a fast rally off the HL
    ind = candles("inducement")
    y = next(i for i, c in enumerate(ind) if c["t"] == hl2["t"])
    lo, top = ind[y]["l"] + 0.2, hh["price"]
    rows = [(ind[y]["c"], top - 4.5, lo, top - 5), (top - 5, top + 1.0, top - 5.2, top + 0.8)]
    rows += [(top + 0.8 + 0.5 * j, top + 1.5 + 0.5 * j, top + 0.6 + 0.5 * j, top + 1.3 + 0.5 * j) for j in range(6)]
    t0 = datetime.fromisoformat(ind[y]["t"])
    fast = ind[:y + 1] + [{"t": (t0 + timedelta(hours=j)).isoformat(), "o": round(o, 2), "h": round(hi, 2),
                           "l": round(lw, 2), "c": round(c, 2)} for j, (o, hi, lw, c) in enumerate(rows, 1)]
    h = {"BTC/USD": {"1H": fast}}
    ex = find("inducement", h)
    check_track12(ex, h)
    f = ex[0]["facts"]
    assert f["swings"][-1]["t"] == hl2["t"] and f["bos"]["level"] == top
    assert (f["bos"]["t"], f["bos"]["close"]) == (fast[y + 2]["t"], fast[y + 2]["c"]), f["bos"]
    assert fast[y + 1]["c"] <= top < fast[y + 2]["c"]

    # second example on another asset, else another timeframe
    h = {"BTC/USD": {"1H": candles("trendline_retest")}, "ETH/USD": {"1H": candles("trendline_liquidity")}}
    ex = find("trendline", h)
    check_track12(ex, h)
    assert len(ex) == 2 and {e["asset"] for e in ex} == {"BTC/USD", "ETH/USD"}
    h = {"XAU/USD": {"1H": candles("equal_highs"), "4H": candles("equal_highs")}}
    ex = find("equal_highs_lows", h)
    check_track12(ex, h)
    assert [e["timeframe"] for e in ex] == ["4H", "1H"]

    # no clean case: choppy range, its daily-fix twin, empty and too-short series -> [] from every new detector
    chop, short = candles("choppy"), candles("trendline_retest")[:6]
    for h in ({"BTC/USD": {"1H": chop}}, {"EUR/USD": {"1D": daily_fix(chop)}}, {}, {"BTC/USD": {"1H": short}},
              {"BTC/USD": {"1H": chop, "4H": aggregate(chop, 4 * 3600)}}):
        for name in new:
            assert find(name, h) == [], (name, h.keys())

    # repeat run: same history -> identical examples, byte for byte; input untouched
    h = {"BTC/USD": {fixture_tf: candles(f) for fixture_tf, f in (("1H", "sweep_breakout"), ("4H", "trendline_retest"))},
         "ETH/USD": {"1H": candles("sessions_1h")}, "XAU/USD": {"1H": candles("inducement")},
         "EUR/USD": {"1D": daily_fix(candles("liquidity_pools"))}}
    before = json.dumps(h, sort_keys=True)
    for name in new:
        a, b = find(name, h), find(name, copy.deepcopy(h))
        assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True), name
    assert json.dumps(h, sort_keys=True) == before

    # 1.2 regression: swings / bos_choch on the existing fixtures are byte-identical to before
    assert structure_digest() == STRUCTURE_DIGEST
    print(f"OK tracks 1-2 detectors ({', '.join(new)}: clean case per fixture, break / fakeout / retest, "
          "wick-only pierce zone, BSL/SSL + confirmation, EQH, sessions 1H only, sweep then breakout, IDM + first BOS, "
          "choppy / short -> [], repeat runs identical, facts from candles, 1.2 outputs unchanged)")


def trendline_plain() -> list[dict]:
    """trendline_retest with the retest rally replaced by a steady fall: a break with no retest."""
    series = candles("trendline_retest")
    k = next(i for i, c in enumerate(series) if c["c"] == 110 and i > 60)  # end of the drop after the break
    out = series[:k + 1]
    price, t = out[-1]["c"], datetime.fromisoformat(out[-1]["t"])
    for _ in range(12):
        o, price, t = price, round(price - 0.8, 2), t + timedelta(hours=1)
        out.append({"t": t.isoformat(), "o": o, "h": round(o + 0.2, 2), "l": round(price - 0.2, 2), "c": price})
    return out


def early_break() -> list[dict]:
    """trendline_retest up to its 4th touch (candle 53, low 111.5, close 112), then closes just under the
    line that keep every low above 111.5 for 3 candles (so candle 53 still confirms as a swing low),
    then a steady fall."""
    series = candles("trendline_retest")[:54]
    assert series[53]["l"] == 111.5 and series[53]["c"] == 112
    t = datetime.fromisoformat(series[53]["t"])
    rows = [(112.0, 112.2, 111.55, 111.7), (111.7, 111.9, 111.52, 111.6), (111.6, 111.7, 111.51, 111.55)]
    price = 111.55
    for _ in range(14):
        rows.append((price, round(price + 0.2, 2), round(price - 1.0, 2), round(price - 0.8, 2)))
        price = round(price - 0.8, 2)
    for k, (o, hi, lo, c) in enumerate(rows, 1):
        series.append({"t": (t + timedelta(hours=k)).isoformat(), "o": o, "h": hi, "l": lo, "c": c})
    return series


def structure_digest() -> str:
    import hashlib
    names = ("uptrend", "downtrend_bos_choch", "choppy", "downtrend_hl_choch", "range_after_trend", "top_down_1h")
    s = {n: candles(n) for n in names}
    out = {n: json.dumps({d: find(d, {"BTC/USD": {"1H": s[n]}}) for d in ("swings", "bos_choch")}, sort_keys=True)
           for n in names}
    h = {"BTC/USD": {"1H": s["downtrend_bos_choch"], "4H": s["uptrend"]}, "ETH/USD": {"1H": s["uptrend"]},
         "XAU/USD": {"1D": s["downtrend_hl_choch"]}}
    out["mixed"] = json.dumps({d: find(d, h) for d in ("swings", "bos_choch")}, sort_keys=True)
    return hashlib.sha256("".join(out[k] for k in sorted(out)).encode()).hexdigest()


# ─── lesson price history (network mocked) ─────────────────────────────────

class _Resp:
    def __init__(self, data):
        self.data = data

    def json(self):
        return self.data


def _cb(t: int) -> tuple:
    base = 1000.0 + (t // 3600) % 50
    return base, base + 2, base - 2, base + 1  # o, h, l, c


def _kr(t: int) -> tuple:
    base = 4000.0 + (t // 3600) % 30
    return base, base + 3, base - 3, base + 1


def fake_market(now: datetime, spot_shift: float | None = 5.0, fail=(), spot_body=None):
    """A stand-in for sources._get: Coinbase (newest first, inclusive ends), Kraken, Swissquote,
    Frankfurter. Like the real APIs, each returns the candle still forming at `now` but nothing
    later. `fail` names sources that raise; `spot_body` replaces Swissquote's answer."""
    calls = []
    kr_end = int(now.timestamp()) // 3600 * 3600

    def get(url, params=None, timeout=30):
        params = dict(params or {})
        calls.append((url, params))
        name = next((n for n in ("ETH-USD", "BTC-USD", "kraken", "swissquote", "frankfurter") if n in url), url)
        if name in fail or (name == "kraken" and f"kraken{params['interval']}" in fail):
            raise RuntimeError(f"{name}: 503 Service Unavailable")
        if name in ("BTC-USD", "ETH-USD"):
            g = params["granularity"]
            s, e = (int(datetime.fromisoformat(params[k]).timestamp()) for k in ("start", "end"))
            assert (e - s) // g < 300, "more than 300 candles asked of Coinbase"
            top = min(e, int(now.timestamp()) // g * g)  # up to the forming candle, never the future
            return _Resp([[t, _cb(t)[2], _cb(t)[1], _cb(t)[0], _cb(t)[3], 12.5] for t in range(top, s - 1, -g)])
        if name == "kraken":
            step = params["interval"] * 60
            end = kr_end - kr_end % step  # the forming candle is Kraken's last row
            rows = [[t, *(f"{v:.2f}" for v in _kr(t)), "0", "1.0", 3] for t in range(end - 719 * step, end + 1, step)]
            return _Resp({"error": [], "result": {"PAXGUSD": rows, "last": end}})
        if name == "swissquote":
            if spot_body is not None:
                return _Resp(spot_body)
            last = _kr(kr_end)[3]  # spot moves with the newest (forming) PAXG price
            return _Resp([{"spreadProfilePrices": [{"bid": last + spot_shift - 0.1, "ask": last + spot_shift + 0.1}]}])
        if name == "frankfurter":
            d0 = datetime.fromisoformat(params["from"]).date()
            # v2 has weekend rows too; today's row (still the forming day) is the last one
            rows = [{"date": (d0 + timedelta(days=i)).isoformat(), "quote": "EUR", "rate": 0.9 + i * 0.0001}
                    for i in range(0, 366) if d0 + timedelta(days=i) <= now.date()]
            return _Resp(rows + [{"date": d0.isoformat(), "quote": "GBP", "rate": 0.75}])
        raise AssertionError(f"unexpected request {url}")
    return get, calls


def test_fetch():
    now = datetime(2026, 10, 9, 6, 30, tzinfo=timezone.utc)
    get, calls = fake_market(now, fail=("ETH-USD", "kraken240"))
    logs = []
    with mock.patch.object(sources, "_get", get):
        h = lesson_data.fetch_history(log=logs.append, now=now)

    # one source down (ETH) and one timeframe down (gold 4H): logged and left out, the rest present
    assert list(h) == ["BTC/USD", "XAU/USD", "EUR/USD"], list(h)
    assert list(h["BTC/USD"]) == ["1D", "4H", "1H"] and list(h["XAU/USD"]) == ["1D", "1H"]
    assert any("ETH/USD 1H" in m and "503" in m for m in logs) and any("ETH/USD 1D" in m for m in logs), logs
    assert any("ETH/USD 4H" in m and "1H, which failed" in m for m in logs), logs  # 4H skip has its own line
    assert any("XAU/USD 4H" in m for m in logs), logs
    assert any(m == "Lesson data: BTC/USD 1H 1440 candles" for m in logs), logs
    for asset in h:
        for tf, cs in h[asset].items():
            ts = [c["t"] for c in cs]
            assert ts == sorted(ts) and len(ts) == len(set(ts)), (asset, tf)  # oldest first, de-duplicated
            assert all(t.endswith("+00:00") and set(c) == set("tohlc") for t, c in zip(ts, cs))
            # completed candles only: every period closed by `now`, the forming one dropped
            span = lesson_data.TF_SECONDS[tf]
            assert all(datetime.fromisoformat(t).timestamp() + span <= now.timestamp() for t in ts), (asset, tf)

    # Coinbase: [t, l, h, o, c] reordered to o/h/l/c, paged under the 300 cap over 60 / 365 days;
    # the forming 06:00 hour and today's forming day are returned by the API but dropped
    btc = h["BTC/USD"]
    c = btc["1H"][-1]
    t = int(datetime.fromisoformat(c["t"]).timestamp())
    assert (c["o"], c["h"], c["l"], c["c"]) == _cb(t) and c["t"] == "2026-10-09T05:00:00+00:00"
    assert btc["1H"][0]["t"] == "2026-08-10T06:00:00+00:00" and len(btc["1H"]) == 60 * 24
    pages = lambda g: [p for u, p in calls if "BTC-USD" in u and p["granularity"] == g]  # noqa: E731
    assert len(pages(3600)) == 5 and len(pages(86400)) == 2, (len(pages(3600)), len(pages(86400)))
    assert len(btc["1D"]) == 365 and btc["1D"][-1]["t"] == "2026-10-08T00:00:00+00:00"
    assert btc["1D"][0]["t"] == "2025-10-09T00:00:00+00:00"

    # 4H from 1H on 00/04/08... UTC; the leading partial bucket (04:00, starts 06:00) and the
    # trailing forming one (04:00 today, closes 08:00) are dropped, so every bucket has 4 hours
    assert btc["4H"][0]["t"] == "2026-08-10T08:00:00+00:00"
    assert btc["4H"][-1]["t"] == "2026-10-09T00:00:00+00:00"
    assert all(datetime.fromisoformat(b["t"]).hour % 4 == 0 for b in btc["4H"])
    hourly = {x["t"]: x for x in btc["1H"]}
    for b in btc["4H"]:
        t0 = datetime.fromisoformat(b["t"])
        hs = [hourly[(t0 + timedelta(hours=k)).isoformat()] for k in range(4)]
        assert b == {"t": b["t"], "o": hs[0]["o"], "h": max(x["h"] for x in hs), "l": min(x["l"] for x in hs),
                     "c": hs[-1]["c"]}, b
    assert any(m == "Lesson data: BTC/USD 4H 359 candles" for m in logs), logs

    # Kraken PAXG + one Swissquote offset (+5.00, against the newest, forming price) on every
    # timeframe; Kraken's forming last row is dropped
    for tf in ("1H", "1D"):
        for g in h["XAU/USD"][tf]:
            raw = _kr(int(datetime.fromisoformat(g["t"]).timestamp()))
            assert (g["o"], g["h"], g["l"], g["c"]) == tuple(round(v + 5.0, 2) for v in raw), (tf, g)
    assert len(h["XAU/USD"]["1H"]) == 719 and h["XAU/USD"]["1H"][-1]["t"] == "2026-10-09T05:00:00+00:00"
    assert h["XAU/USD"]["1D"][-1]["t"] == "2026-10-08T00:00:00+00:00"
    assert any("offset +5.00" in m for m in logs)

    # Frankfurter: EUR/USD = 1 / (USD->EUR), o = h = l = c, weekend rows kept, today's row dropped,
    # other quotes ignored
    eur = h["EUR/USD"]["1D"]
    assert eur[0]["t"] == "2025-10-09T00:00:00+00:00" and eur[0]["c"] == round(1 / 0.9, 5)
    assert len(eur) == 365 and eur[-1]["t"] == "2026-10-08T00:00:00+00:00"
    assert all(x["o"] == x["h"] == x["l"] == x["c"] for x in eur) and all(x["c"] > 1 for x in eur)
    assert "ECB" not in lesson_data.SOURCES["EUR/USD"] and "Frankfurter" in lesson_data.SOURCES["EUR/USD"]

    # spot quote fails its sanity check / fails outright / answers an unexpected shape: PAXG as is
    for kw in ({"spot_shift": 400.0}, {"fail": ("swissquote",)}, {"spot_body": {"error": "maintenance"}}):
        get, _ = fake_market(now, **kw)
        logs = []
        with mock.patch.object(sources, "_get", get):
            g = lesson_data.fetch_history(log=logs.append, now=now)["XAU/USD"]["1H"][-1]
        assert g["c"] == _kr(int(datetime.fromisoformat(g["t"]).timestamp()))[3], (kw, g)
        assert any("using PAXG prices" in m for m in logs) and any("offset +0.00" in m for m in logs), logs

    # everything down: empty history, nothing raised, each series logged (4H skips included)
    get, _ = fake_market(now, fail=("ETH-USD", "BTC-USD", "kraken", "frankfurter"))
    logs = []
    with mock.patch.object(sources, "_get", get):
        assert lesson_data.fetch_history(log=logs.append, now=now) == {}
    assert len(logs) == 10 and sum("4H" in m for m in logs) == 3 and find("swings", {}) == [], logs
    print("OK fetch (Coinbase reorder/sort/paging/dedupe, completed candles only, 4H aggregation, "
          "Kraken + spot offset and its sanity check / errors, Frankfurter inversion, failed source / "
          "timeframe skipped and logged)")


# ─── narration ─────────────────────────────────────────────────────────────

FILLER = ("A swing point marks where price turned and the next close tells us whether "
          "the structure held or changed character").split()


def draft(plan: list[dict], words: int = 600, inserts: dict | None = None, recap_tail: str | None = None) -> dict:
    """A mocked writer reply: exactly `words` words over the plan's scenes; `inserts` {id: sentence}
    replace filler at the start of a scene; the recap ends with `recap_tail` (default the disclaimer)."""
    inserts = inserts or {}
    tail = lesson_script.DISCLAIMER if recap_tail is None else recap_tail
    fixed = {p["id"]: inserts.get(p["id"], "").split() for p in plan}
    fixed["recap"] = fixed.get("recap", []) + tail.split()
    free = words - sum(len(v) for v in fixed.values())
    scenes, used = [], 0
    for i, p in enumerate(plan):
        n = free // len(plan) + (free % len(plan) if i == len(plan) - 1 else 0)
        body = [FILLER[(used + k) % len(FILLER)] for k in range(n)]
        used += n
        sid = p["id"]
        parts = fixed[sid] + body if sid != "recap" else body + fixed[sid]
        scenes.append({"id": sid, "text": " ".join(parts)})
    return {"scenes": scenes}


def test_narration():
    entry, glossary, plan, examples = lesson_script.sample_episode()
    assert entry["id"] == "bos-vs-choch" and len(examples) == 2
    assert [p["id"] for p in plan] == ["hook", "concept", "example_1", "example_2", "misreads", "recap"]
    facts = lesson_script.lesson_facts(entry, glossary, examples)
    assert set(facts) == {"title", "key_points", "glossary", "examples"}
    assert set(facts["glossary"]) == {"break_of_structure", "change_of_character", "swing_point"}
    assert all(set(x) == {"scene", "asset", "timeframe", "date", "facts"} for x in facts["examples"])
    f1 = examples[0]["facts"]
    level, close = f"{f1['bos']['level']:.2f}", f"{f1['choch']['close']:.2f}"

    cfg = {"channel": {"display_name": "CryptoFX Daily"},
           "llm": {"model": "m", "fallback_models": [], "min_words": 115, "max_words": 145}}
    cfg_before = copy.deepcopy(cfg)
    prompts, drafts = [], []

    def fake_llm(prompt, models, temperature=0.9):
        prompts.append(prompt)
        if "strict financial news editor" in prompt:
            pkg = json.loads(prompt.split("SCRIPT:\n", 1)[1].rsplit("\n\n1. Every", 1)[0])
            return {"verdict": "revised", "issues": ["tightened wording"], "package": pkg}
        return copy.deepcopy(drafts.pop(0))

    def run(*replies, e=entry, p=plan):
        drafts[:] = list(replies)
        prompts.clear()
        logs = []
        with mock.patch.object(lesson_script, "generate_json", fake_llm), \
                mock.patch.object(script, "generate_json", fake_llm):
            pkg = lesson_script.make_lesson_script(cfg, e, glossary, p, examples, log=logs.append)
        return pkg, logs

    clean = draft(plan, 600, {"example_1": f"Price closed below {level} and later closed above {close}."})

    # good draft: one text per plan scene, fact_check verdict kept, lesson bounds + rules sent
    pkg, logs = run(clean)
    assert [s["id"] for s in pkg["scenes"]] == [p["id"] for p in plan] and all(s["text"] for s in pkg["scenes"])
    assert pkg["scenes"][2]["visual"]["example"] is examples[0]
    assert pkg["fact_check"] == {"verdict": "revised", "issues": ["tightened wording"]}
    assert lesson_script.check_lesson(pkg, entry, plan, facts) == []
    writer, checker = prompts
    assert "intermediate traders" in writer and "calm, precise trading educator" in writer
    assert all(k in writer for k in entry["key_points"]) and glossary["swing_point"]["definition"] in writer
    assert all(f'- "{p["id"]}": {p["covers"]}' in writer for p in plan)
    assert '"candles"' not in writer and '"primitives"' not in writer and '"region"' not in writer
    assert "Keep 550-700 words" in checker and "trading LESSON" in checker and '"candles"' not in checker
    assert cfg == cfg_before  # fact_check got a copy

    # banned claims → rejected with the reason, next attempt used
    for bad in ("Buy here when it breaks.", "Put a stop loss under it.", "This setup has a high win rate.",
                "Price will reach the next swing.", "Set a target at the next level."):
        pkg, logs = run(draft(plan, 600, {"concept": bad}), clean)
        assert pkg["scenes"][0]["text"] == clean["scenes"][0]["text"] and len(drafts) == 0
        assert any("Discarding draft" in m and "banned wording" in m for m in logs), (bad, logs)
    problems = lesson_script.check_lesson(draft(plan, 600, {"concept": "Buy here and set a stop-loss."}),
                                          entry, plan, facts)
    assert problems == ["banned wording: buy, stop-loss"], problems

    # liquidity terms are allowed
    liq = draft(plan, 600, {"misreads": "Sell-side liquidity rests below lows and buy-side liquidity above highs; "
                                        "buy side and sell side are names, not instructions."})
    assert lesson_script.check_lesson(liq, entry, plan, facts) == []
    uni = draft(plan, 600, {"misreads": "Sell\u2011side liquidity sits below lows, buy\u2013side liquidity above highs."})
    assert lesson_script.check_lesson(uni, entry, plan, facts) == []  # non-breaking hyphen, en dash
    pkg, _ = run(liq)
    assert "Sell-side liquidity" in pkg["scenes"][-2]["text"]

    # too short / too long → rejected with the word count
    for n in (400, 800):
        pkg, logs = run(draft(plan, n), clean)
        assert any(f"{n} words (target 550-700)" in m for m in logs), logs
    assert lesson_script.check_lesson(draft(plan, 550), entry, plan, facts) == []
    assert lesson_script.check_lesson(draft(plan, 700), entry, plan, facts) == []
    extra = draft(plan, 600)
    extra["scenes"].append({"id": "bonus", "text": " ".join(["word"] * 300)})  # not a plan scene: not counted
    assert lesson_script.check_lesson(extra, entry, plan, facts) == []

    # unbacked number → rejected naming it
    pkg, logs = run(draft(plan, 600, {"example_1": "Price then traded at 123.45 before turning."}), clean)
    assert any("numbers not in the facts: 123.45" in m for m in logs), logs
    assert lesson_script.check_lesson(draft(plan, 600, {"hook": "Two key points, one idea."}),
                                      entry, plan, facts) == []  # bare small integers are fine
    # dates / times in the facts don't back numbers; spoken dates and clock times aren't numbers
    for said, num in (("Price fell 19% that week.", "19"), ("It tested the level 23 times.", "23"),
                      ("Price then traded at $112,345.67 that day.", "112,345.67"),
                      ("Volume reached 1234567 contracts.", "1,234,567")):
        p = lesson_script.check_lesson(draft(plan, 600, {"example_1": said}), entry, plan, facts)
        assert p == [f"numbers not in the facts: {num}"], (said, p)
    d, dt = examples[0]["date"], datetime.fromisoformat(examples[0]["date"])
    spoken = f"On {dt:%B} {dt.day}, {dt.year}, at 12:00 UTC ({d}), price closed above {close}."
    assert lesson_script.check_lesson(draft(plan, 600, {"example_1": spoken}), entry, plan, facts) == [], spoken

    # missing disclaimer; track 4 also needs the non-affiliation line
    no_disc = draft(plan, 600, recap_tail="That is the whole lesson.")
    assert lesson_script.check_lesson(no_disc, entry, plan, facts) == [
        "recap lacks the disclaimer (\"not financial advice\")"]
    pkg, logs = run(no_disc, clean)
    assert any("recap lacks the disclaimer" in m for m in logs), logs
    ict = dict(entry, track=4)
    ict_plan = lessons.scene_plan(ict, examples)
    p = lesson_script.check_lesson(draft(ict_plan, 600), ict, ict_plan, facts)
    assert p == ["recap lacks the non-affiliation line (The Inner Circle Trader)"], p
    both = draft(ict_plan, 600, recap_tail=f"{lesson_script.DISCLAIMER} {lesson_script.NON_AFFILIATION}")
    assert lesson_script.check_lesson(both, ict, ict_plan, facts) == []
    pkg, _ = run(draft(ict_plan, 600), both, e=ict, p=ict_plan)
    assert "Inner Circle Trader" in pkg["scenes"][-1]["text"]
    assert "not affiliated with The Inner Circle Trader" in prompts[0] and "Inner Circle Trader" in prompts[1]

    # fact-check reject → retried
    def rejecting(prompt, models, temperature=0.9):
        if "strict financial news editor" in prompt:
            rejecting.n += 1
            if rejecting.n == 1:
                return {"verdict": "reject", "issues": ["wrong"], "package": {}}
        return fake_llm(prompt, models, temperature)
    rejecting.n = 0
    drafts[:] = [clean, clean]
    logs = []
    with mock.patch.object(lesson_script, "generate_json", rejecting), mock.patch.object(script, "generate_json", rejecting):
        pkg = lesson_script.make_lesson_script(cfg, entry, glossary, plan, examples, log=logs.append)
    assert any("fact-check verdict: reject" in m for m in logs) and pkg["fact_check"]["verdict"] == "revised"

    # all attempts fail → RuntimeError with the last problems
    try:
        run(draft(plan, 400), draft(plan, 600, {"concept": "Buy now."}), draft(plan, 800))
        raise AssertionError("3 bad drafts must fail")
    except RuntimeError as e:
        assert "3 attempts" in str(e) and "800 words (target 550-700)" in str(e), e
    print("OK narration (good draft, banned claims retried, liquidity terms allowed, word bounds, unbacked number, "
          "disclaimer + ICT non-affiliation, fact-check reject retried, 3 failures raise; Gemini mocked)")


def main():
    test_validate()
    test_pick()
    test_examples()
    test_scene_plan()
    test_real_files()
    test_detectors()
    test_top_down()
    test_detectors_tracks_1_2()
    test_fetch()
    test_narration()


if __name__ == "__main__":
    main()
