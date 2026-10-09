"""Trendline detectors for Track 1: `trendline`, `trendline_break` and `trendline_liquidity`.
Built on common.py's swing finder (3-candle fractal, ATR-filtered), ranking and example shape.

Deterministic: same candles -> same examples. Input is lesson_data.fetch_history()'s shape
{asset: {timeframe: [{t, o, h, l, c}]}}; each detector returns up to 2 examples, or [] when no
series has a clean case. ATR = ATR(14) at the candle concerned; tolerance = 0.25 x ATR.

Valid line (`find_trendlines`): a line through a first and a last swing low (rising) or swing high
(falling) with >= 1 more swing of that side between them within tolerance (>= 3 touches); no other
swing of that side between them clearly beyond the line (more than the tolerance), no close beyond
the line from the first to the last touch, slope 0.05-2.0 ATR per candle (ATR at the last touch),
first-to-last touch within one chart (140 candles). A rising line is an uptrend's support, a
falling line a downtrend's resistance. The line is known once its last touch is confirmed (i + 3).

    trendline            clean case: the valid line with the most recent last touch (then most
                         touches). Primitives: trendline from the first touch to the last candle
                         shown, swing markers at the touches, label "N touches".
    trendline_break      after a known line, the first close beyond it. `fakeout` if a close returns
                         inside within 3 candles; else `retest` if, within 10 candles, price first
                         leaves the line by more than the tolerance and then comes back within the
                         tolerance of the extended line and closes on the broken side (a close back
                         inside first ends the search); else a plain `break` (needs the 10 candles).
                         facts.kind names which; the example's glossary is fakeout / retest /
                         trendline_break. Labels: "Break", then "Fakeout" / "Retest".
    trendline_liquidity  after a known line with >= 3 touches and before any close beyond it, the first
                         candle whose wick pierces it by >= 0.5 x ATR and whose close stays on the line's
                         side (wick only; a close beyond is a break). Zone from the last touch to the
                         pierce candle between the line and the wick: where the stops sat.

Per (asset, timeframe) the most recent case (last touch / break / pierce, then most touches) is
kept; cases rank by (touches desc, end time desc, asset order, timeframe order). Facts hold only
candle values (touch prices and times, the break / pierce candle's close and wick), counts and kinds.
"""
from autopilot import lessons
from autopilot.detectors.common import MAX_CANDLES, PAD, RIGHT, _atr, _find, _fits, _window

TOL = 0.25  # touch tolerance, in ATRs
MIN_TOUCHES = 3
SLOPE_MIN, SLOPE_MAX = 0.05, 2.0  # |slope| in ATRs per candle
SPAN = MAX_CANDLES - 2 * PAD  # first to last touch must fit one chart
FAKEOUT_N, RETEST_N = 3, 10  # candles after the break
PIERCE = 0.5  # wick beyond the line, in ATRs
KIND_GLOSSARY = {"fakeout": "fakeout", "retest": "retest", "break": "trendline_break"}


def line_at(line: dict, i: int) -> float:
    """The line's price at candle i (extended either way)."""
    return line["first"]["price"] + line["slope"] * (i - line["first"]["i"])


def _beyond(line: dict, price: float, level: float) -> bool:
    """Price on the far side of the line: below a rising support, above a falling resistance."""
    return price < level if line["side"] == "low" else price > level


def find_trendlines(candles: list[dict], swings: list[dict]) -> list[dict]:
    """Every valid line: [{side, trend, first, last, touches, slope}], ordered by (last touch, first touch)."""
    atr = _atr(candles)
    closes = [c["c"] for c in candles]
    out = []
    for side, rising in (("low", True), ("high", False)):
        pts = [s for s in swings if s["side"] == side]
        for a, first in enumerate(pts):
            for b in range(a + 2, len(pts)):
                last = pts[b]
                if last["i"] - first["i"] + 1 > SPAN:
                    break
                slope = (last["price"] - first["price"]) / (last["i"] - first["i"])
                if (slope <= 0) if rising else (slope >= 0):
                    continue
                if not SLOPE_MIN * atr[last["i"]] <= abs(slope) <= SLOPE_MAX * atr[last["i"]]:
                    continue
                line = {"side": side, "trend": "uptrend" if rising else "downtrend", "first": first, "last": last,
                        "slope": slope}
                touches, clean = [first], True
                for s in pts[a + 1:b]:
                    gap = s["price"] - line_at(line, s["i"])
                    if abs(gap) <= TOL * atr[s["i"]]:
                        touches.append(s)
                    elif _beyond(line, s["price"], line_at(line, s["i"])):
                        clean = False  # a swing clearly through the line: not one line
                        break
                if not clean or len(touches) + 1 < MIN_TOUCHES:
                    continue
                if any(_beyond(line, closes[i], line_at(line, i)) for i in range(first["i"], last["i"] + 1)):
                    continue
                out.append(dict(line, touches=touches + [last]))
    out.sort(key=lambda ln: (ln["last"]["i"], ln["first"]["i"], ln["side"]))
    return out


def _line_prims(candles: list[dict], line: dict, hi: int) -> list[dict]:
    f = line["first"]
    return [{"type": "trendline", "t1": f["t"], "p1": f["price"], "t2": candles[hi]["t"],
             "p2": round(line_at(line, hi), 6)}]


def _touch_facts(line: dict) -> dict:
    return {"line": "rising support" if line["side"] == "low" else "falling resistance",
            "touches": len(line["touches"])}


# ─── cases per series ──────────────────────────────────────────────────────

def _trendline_case(candles: list[dict], swings: list[dict]) -> dict | None:
    lines = find_trendlines(candles, swings)
    if not lines:
        return None
    line = max(lines, key=lambda ln: (ln["last"]["i"], len(ln["touches"]), -ln["first"]["i"], ln["side"]))
    f, last = line["first"], line["last"]
    _, hi = _window(candles, f["i"], last["i"])
    n = len(line["touches"])
    return {"trend": line["trend"], "swings": line["touches"], "start": f["i"], "end": last["i"], "rank": n,
            "primitives": _line_prims(candles, line, hi)
            + [{"type": "label", "t": last["t"], "price": last["price"], "text": f"{n} touches"}],
            "facts": _touch_facts(line)}


def _classify(candles: list[dict], atr: list[float], line: dict, m: int) -> tuple[str, int] | None:
    """(kind, deciding candle) of the break at candle m, or None while it can't be told yet."""
    n = len(candles)
    for k in range(m + 1, min(m + FAKEOUT_N, n - 1) + 1):
        if not _beyond(line, candles[k]["c"], line_at(line, k)):
            return "fakeout", k
    if m + FAKEOUT_N >= n:
        return None  # a fakeout can't be ruled out yet
    support = line["side"] == "low"
    left = False
    for k in range(m + 1, min(m + RETEST_N, n - 1) + 1):
        level, tol = line_at(line, k), TOL * atr[k]
        c = candles[k]
        if not _beyond(line, c["c"], level):
            break  # closed back inside after the fakeout window: no retest of a broken line
        near = c["h"] >= level - tol if support else c["l"] <= level + tol
        if left and near:
            return "retest", k
        if not near:
            left = True  # price has left the line
    if m + RETEST_N < n:
        return "break", m + RETEST_N
    return None


def _break_case(candles: list[dict], swings: list[dict]) -> dict | None:
    atr = _atr(candles)
    found = []
    for line in find_trendlines(candles, swings):
        last = line["last"]
        m = next((k for k in range(last["i"] + 1, len(candles))
                  if _beyond(line, candles[k]["c"], line_at(line, k))), None)
        if m is None or m < last["i"] + RIGHT:
            continue  # never broken, or broken before its last touch was confirmed
        res = _classify(candles, atr, line, m)
        if res is None or not _fits(candles, line["first"]["i"], res[1]):
            continue
        found.append((m, len(line["touches"]), last["i"], -line["first"]["i"], line["side"], line, res))
    if not found:
        return None
    m, n, *_, line, (kind, k) = max(found, key=lambda f: f[:5])
    f, bc, kc = line["first"], candles[m], candles[k]
    _, hi = _window(candles, f["i"], k)
    prims = _line_prims(candles, line, hi) + [{"type": "label", "t": bc["t"], "price": bc["c"], "text": "Break"}]
    facts = dict(_touch_facts(line), kind=kind, **{"break": {"t": bc["t"], "close": bc["c"]}})
    if kind == "fakeout":
        prims.append({"type": "label", "t": kc["t"], "price": kc["c"], "text": "Fakeout"})
        facts["fakeout"] = {"t": kc["t"], "close": kc["c"]}
    elif kind == "retest":
        wick = "h" if line["side"] == "low" else "l"
        prims.append({"type": "label", "t": kc["t"], "price": kc[wick], "text": "Retest"})
        facts["retest"] = {"t": kc["t"], ("high" if wick == "h" else "low"): kc[wick], "close": kc["c"]}
    return {"trend": line["trend"], "swings": line["touches"], "start": f["i"], "end": k, "rank": n,
            "glossary": KIND_GLOSSARY[kind], "primitives": prims, "facts": facts}


def _liquidity_case(candles: list[dict], swings: list[dict]) -> dict | None:
    atr = _atr(candles)
    found = []
    for line in find_trendlines(candles, swings):
        last, support = line["last"], line["side"] == "low"
        for k in range(last["i"] + 1, len(candles)):
            c, level = candles[k], line_at(line, k)
            wick = c["l"] if support else c["h"]
            if _beyond(line, c["c"], level):
                break  # closed through the line: a break, not a wick into the stops
            if k >= last["i"] + RIGHT and abs(wick - level) >= PIERCE * atr[k] and _beyond(line, wick, level):
                if _fits(candles, line["first"]["i"], k):
                    found.append((k, len(line["touches"]), last["i"], -line["first"]["i"], line["side"], line))
                break
    if not found:
        return None
    k, n, *_, line = max(found, key=lambda f: f[:5])
    f, c, level = line["first"], candles[k], line_at(line, k)
    support = line["side"] == "low"
    _, hi = _window(candles, f["i"], k)
    wick = c["l"] if support else c["h"]
    zone = {"type": "zone", "t1": line["last"]["t"], "t2": c["t"], "low": wick if support else round(level, 6),
            "high": round(level, 6) if support else wick, "label": "Stops"}
    pierce = {"t": c["t"], ("low" if support else "high"): wick, "close": c["c"]}
    return {"trend": line["trend"], "swings": line["touches"], "start": f["i"], "end": k, "rank": n,
            "primitives": _line_prims(candles, line, hi) + [zone],
            "facts": dict(_touch_facts(line), pierce=pierce)}


# ─── detectors ─────────────────────────────────────────────────────────────

def find_trendline_examples(history: dict) -> list[dict]:
    return _find(history, _trendline_case, "trendline", "trendline")


def find_trendline_break_examples(history: dict) -> list[dict]:
    return _find(history, _break_case, "trendline_break", "trendline_break")


def find_trendline_liquidity_examples(history: dict) -> list[dict]:
    return _find(history, _liquidity_case, "trendline_liquidity", "trendline_liquidity")


TRENDLINE = lessons.register(lessons.Detector("trendline", "trendline", find_trendline_examples))
TRENDLINE_BREAK = lessons.register(lessons.Detector("trendline_break", ("trendline_break", "fakeout", "retest"),
                                                    find_trendline_break_examples))
TRENDLINE_LIQUIDITY = lessons.register(lessons.Detector("trendline_liquidity", "trendline_liquidity",
                                                        find_trendline_liquidity_examples))
