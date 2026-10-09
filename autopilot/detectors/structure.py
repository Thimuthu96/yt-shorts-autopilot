"""Market-structure detectors for Track 0: `swings` (HH/HL/LH/LL) and `bos_choch` (break of
structure, change of character).

Deterministic: same candles -> same examples (no randomness, no clock). Input is
lesson_data.fetch_history()'s shape {asset: {timeframe: [{t, o, h, l, c}]}}; each detector returns
up to 2 examples in autopilot.lessons' example schema, or [] when no series has a clean case.

Swings: a 3-candles-each-side fractal on highs / lows; consecutive same-type swings collapse to
the more extreme; a swing whose leg from the previous opposite swing is under 1.0x ATR(14) is
dropped. Highs are labelled HH/LH against the previous high, lows HL/LL against the previous low
(the first high / low, or an exact tie, stay plain "high" / "low").

    swings     clean case: >= 4 consecutive labelled swings that agree (HH+HL or LH+LL)
    bos_choch  clean case, walking swings and closes in time order: a run of >= 4 agreeing swings;
               a BOS is a close beyond the run's most recent with-trend swing at that moment (in a
               downtrend the latest LL); a CHoCH is the first close beyond the run's most recent
               against-trend swing (the latest LH) after a BOS. The example shows the last BOS
               before the CHoCH. Case swings are the run's swings up to the CHoCH plus at most one
               disagreeing swing right before it (e.g. the HL that failed to make a LL); if a
               second swing outside the run forms first, the run has no clean CHoCH.
               A swing only counts from its confirming candle (i + 3), never earlier.

Per (asset, timeframe) the most recent clean case is kept; cases rank by (swings desc, end time
desc, asset order, timeframe order 1D/4H/1H). Example 1 is the top case, example 2 the best
remaining one on another asset, else on another timeframe.

The fractal / ATR code is a separate copy of gold.py's helpers on purpose: the daily gold outlook
must not drift when the lessons change.
"""
from datetime import datetime

from autopilot import lessons
from autopilot.lesson_data import ASSETS, SOURCES, TIMEFRAMES

LEFT = RIGHT = 3  # fractal width
ATR_N = 14
ATR_MULT = 1.0  # minimum leg between opposite swings, in ATRs
MIN_SWINGS = 4  # = 2 agreeing swing pairs
PAD = 5  # candles shown either side of the region
MAX_CANDLES = 150
UP, DOWN = {"HH", "HL"}, {"LH", "LL"}
REFERENCE_FIX = {"EUR/USD"}  # daily central-bank fix, not traded candles


# ─── shared swing finder ───────────────────────────────────────────────────

def _atr(candles: list[dict]) -> list[float]:
    """ATR(14) at each candle: the mean true range of the (up to) 14 candles ending there."""
    trs, out = [], []
    for i, b in enumerate(candles):
        if i == 0:
            trs.append(b["h"] - b["l"])
        else:
            pc = candles[i - 1]["c"]
            trs.append(max(b["h"] - b["l"], abs(b["h"] - pc), abs(b["l"] - pc)))
        win = trs[-ATR_N:]
        out.append(sum(win) / len(win))
    return out


def find_swings(candles: list[dict]) -> list[dict]:
    """Alternating, ATR-filtered, labelled swings: [{i, t, side, price, kind}], oldest first."""
    raw = []
    for i in range(LEFT, len(candles) - RIGHT):
        h, lo = candles[i]["h"], candles[i]["l"]
        left, right = candles[i - LEFT:i], candles[i + 1:i + RIGHT + 1]
        found = []
        if h > max(c["h"] for c in left) and h >= max(c["h"] for c in right):
            found.append(("high", h))
        if lo < min(c["l"] for c in left) and lo <= min(c["l"] for c in right):
            found.append(("low", lo))
        if len(found) == 2 and raw and raw[-1]["side"] == "high":  # outside candle: alternate
            found.reverse()
        raw += [{"i": i, "t": candles[i]["t"], "side": side, "price": p} for side, p in found]

    atr = _atr(candles)
    swings: list[dict] = []
    for s in raw:
        if swings and swings[-1]["side"] == s["side"]:
            last = swings[-1]
            if (s["price"] > last["price"]) if s["side"] == "high" else (s["price"] < last["price"]):
                swings[-1] = s  # keep the more extreme (a tie keeps the earlier)
            continue
        if swings and abs(s["price"] - swings[-1]["price"]) < ATR_MULT * atr[s["i"]]:
            continue  # leg too small to count
        swings.append(s)

    prev: dict[str, float | None] = {"high": None, "low": None}
    out = []
    for s in swings:
        p = prev[s["side"]]
        if p is None or s["price"] == p:
            kind = s["side"]
        elif s["side"] == "high":
            kind = "HH" if s["price"] > p else "LH"
        else:
            kind = "HL" if s["price"] > p else "LL"
        prev[s["side"]] = s["price"]
        out.append(dict(s, kind=kind))
    return out


def _runs(swings: list[dict]) -> list[tuple[str, int, int]]:
    """Maximal runs of agreeing labels: [(trend, first pos, last pos)] in time order."""
    runs, p = [], 0
    while p < len(swings):
        kind = swings[p]["kind"]
        trend = "uptrend" if kind in UP else "downtrend" if kind in DOWN else None
        if trend is None:
            p += 1
            continue
        agree = UP if trend == "uptrend" else DOWN
        q = p
        while q + 1 < len(swings) and swings[q + 1]["kind"] in agree:
            q += 1
        runs.append((trend, p, q))
        p = q + 1
    return runs


def _window(candles: list[dict], start: int, end: int) -> tuple[int, int]:
    return max(0, start - PAD), min(len(candles) - 1, end + PAD)


def _fits(candles: list[dict], start: int, end: int) -> bool:
    lo, hi = _window(candles, start, end)
    return hi - lo + 1 <= MAX_CANDLES


# ─── cases per series ──────────────────────────────────────────────────────

def _swing_case(candles: list[dict], swings: list[dict]) -> dict | None:
    """The most recent run of >= 4 agreeing swings that fits on one chart (trimmed from the front)."""
    for trend, a, b in reversed(_runs(swings)):
        while b - a + 1 >= MIN_SWINGS and not _fits(candles, swings[a]["i"], swings[b]["i"]):
            a += 1
        if b - a + 1 >= MIN_SWINGS:
            return {"trend": trend, "swings": swings[a:b + 1], "start": swings[a]["i"], "end": swings[b]["i"],
                    "breaks": []}
    return None


def _bos_choch_case(candles: list[dict], swings: list[dict]) -> dict | None:
    """The most recent trend -> BOS -> CHoCH sequence that fits on one chart."""
    closes = [c["c"] for c in candles]

    def known(pos: int) -> int:
        return swings[pos]["i"] + RIGHT  # the candle that confirms the swing

    found = []  # (choch candle, bos candle, run start, last run swing, last case swing, bos swing, choch swing, trend)
    for trend, a, b in _runs(swings):
        if b - a + 1 < MIN_SWINGS:
            continue
        up = trend == "uptrend"
        with_side = "high" if up else "low"
        beyond = (lambda c, p: c > p) if up else (lambda c, p: c < p)  # noqa: E731  (in the trend's direction)
        behind = (lambda c, p: c < p) if up else (lambda c, p: c > p)  # noqa: E731  (against it)
        # a swing is only known once its fractal is confirmed, at candle i + RIGHT
        outside = known(b + 2) if b + 2 < len(swings) else len(candles)  # 2nd swing after the run
        last_with = last_against = bos = None
        broken = set()
        p = a  # next run swing not yet confirmed
        for m in range(swings[a]["i"] + 1, len(candles)):
            if m >= outside:
                break  # the structure moved on without a CHoCH of this run
            while p <= b and known(p) <= m:
                if swings[p]["side"] == with_side:
                    last_with = p
                else:
                    last_against = p
                p += 1
            if (bos is not None and last_against is not None and p - a >= MIN_SWINGS
                    and behind(closes[m], swings[last_against]["price"])):
                run_end = p - 1  # the run's swings formed before the CHoCH
                last = b + 1 if p > b and b + 1 < len(swings) and known(b + 1) <= m else run_end
                found.append((m, bos[1], a, run_end, last, bos[0], last_against, trend))
                break
            if last_with is not None and last_with not in broken and beyond(closes[m], swings[last_with]["price"]):
                broken.add(last_with)
                bos = (last_with, m)  # the latest BOS so far
    for m, bos, a, run_end, last, j, opp, trend in sorted(found, key=lambda f: -f[0]):  # most recent CHoCH first
        # trim from the front to fit one chart, keeping >= 4 run swings and both broken swings
        while a < min(j, opp) and run_end - a >= MIN_SWINGS and not _fits(candles, swings[a]["i"], m):
            a += 1
        if not _fits(candles, swings[a]["i"], m):
            continue
        return {"trend": trend, "swings": swings[a:last + 1], "start": swings[a]["i"], "end": m,
                "breaks": [("BOS", swings[j], bos), ("CHoCH", swings[opp], m)]}
    return None


# ─── examples ──────────────────────────────────────────────────────────────

def _day(t) -> str:
    return datetime.fromisoformat(t).date().isoformat() if isinstance(t, str) else t.date().isoformat()


def _example(detector: str, glossary: str, asset: str, tf: str, candles: list[dict], case: dict) -> dict:
    lo, hi = _window(candles, case["start"], case["end"])
    span = candles[case["start"]:case["end"] + 1]
    swings = [{"t": s["t"], "kind": s["kind"], "price": s["price"]} for s in case["swings"]]
    prims = [{"type": "swing", **s} for s in swings]
    facts = {"trend": case["trend"], "swings": swings}
    for name, swing, m in case["breaks"]:
        prims.append({"type": "level", "price": swing["price"], "label": name})
        prims.append({"type": "label", "t": candles[m]["t"], "price": candles[m]["c"], "text": name})
        facts[name.lower()] = {"level": swing["price"], "swing_t": swing["t"], "swing_kind": swing["kind"],
                               "t": candles[m]["t"], "close": candles[m]["c"]}
    facts["source"] = SOURCES.get(asset, "")
    if asset in REFERENCE_FIX:
        facts["daily_reference_fix"] = True  # not live prices: open = high = low = close = the day's fix
    last_t = candles[case["end"]]["t"]
    return {
        "detector": detector, "glossary": glossary, "asset": asset, "timeframe": tf, "date": _day(last_t),
        "candles": [{k: c[k] for k in ("t", "o", "h", "l", "c")} for c in candles[lo:hi + 1]],
        "region": {"start": candles[case["start"]]["t"], "end": last_t,
                   "low": min(c["l"] for c in span), "high": max(c["h"] for c in span)},
        "primitives": prims,
        "facts": facts,
    }


def _order(seq: tuple, key: str) -> tuple[int, str]:
    return (seq.index(key), "") if key in seq else (len(seq), key)


def _ts(t) -> float:
    return (datetime.fromisoformat(t) if isinstance(t, str) else t).timestamp()


def _find(history: dict, case_fn, detector: str, glossary: str) -> list[dict]:
    ranked = []
    for asset in sorted(history, key=lambda a: _order(ASSETS, a)):
        for tf in sorted(history[asset], key=lambda t: _order(TIMEFRAMES, t)):
            candles = history[asset][tf]
            if len(candles) < LEFT + RIGHT + 1:
                continue
            case = case_fn(candles, find_swings(candles))
            if case:
                ex = _example(detector, glossary, asset, tf, candles, case)
                key = (-len(case["swings"]), -_ts(ex["region"]["end"]), _order(ASSETS, asset), _order(TIMEFRAMES, tf))
                ranked.append((key, ex))
    if not ranked:
        return []
    ranked.sort(key=lambda r: r[0])
    first = ranked[0][1]
    rest = [ex for _, ex in ranked[1:]]
    second = next((ex for ex in rest if ex["asset"] != first["asset"]), rest[0] if rest else None)
    return [first] + ([second] if second else [])


def find_swing_examples(history: dict) -> list[dict]:
    return _find(history, _swing_case, "swings", "market_structure")


def find_bos_choch_examples(history: dict) -> list[dict]:
    return _find(history, _bos_choch_case, "bos_choch", "change_of_character")


SWINGS = lessons.register(lessons.Detector("swings", ("swing_point", "market_structure"), find_swing_examples))
BOS_CHOCH = lessons.register(lessons.Detector("bos_choch", ("break_of_structure", "change_of_character"),
                                              find_bos_choch_examples))
