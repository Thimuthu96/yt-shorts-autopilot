"""Offline check of the lesson formats: curriculum + glossary validator, episode picker, example
schema and scene plan, the structure detectors (candle fixtures in tests/lessons/candles/) and the
lesson price-history fetch with sources._get mocked (no API keys, no network).

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

from autopilot import detectors, lesson_data, lessons, sources  # noqa: E402,F401  (detectors registers)
from autopilot.history import History  # noqa: E402

SAMPLE = ROOT / "tests" / "lessons"
CANDLES = SAMPLE / "candles"


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
    # the real registry (autopilot.detectors is imported above), not the test stubs
    assert {"swings", "bos_choch"} <= set(lessons.DETECTORS), sorted(lessons.DETECTORS)
    for d in lessons.DETECTORS.values():
        assert set(d.glossary_keys()) <= set(glo), d
    s_cur, s_glo, _ = sample()
    assert lessons.validate(s_cur, s_glo) == [], lessons.validate(s_cur, s_glo)
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


def main():
    test_validate()
    test_pick()
    test_examples()
    test_scene_plan()
    test_real_files()
    test_detectors()
    test_fetch()


if __name__ == "__main__":
    main()
