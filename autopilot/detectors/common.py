"""Shared detector pieces: the swing finder, swing confirmation, ATR, chart window, example builder and
ranking. Every detector module (structure, mtf, trendlines, liquidity, smc) imports them from here.

Deterministic: no randomness, no clock. Input series are lesson_data.fetch_history()'s candles
[{t, o, h, l, c}], oldest first.

Swings (`find_swings`): a fractal of `width` candles each side on highs / lows (3 by default);
consecutive same-type swings collapse to the more extreme; a swing whose leg from the previous
opposite swing is under `atr_mult` x ATR(14) is dropped (1.0 by default, 0 keeps every leg). Highs
are labelled HH/LH against the previous high, lows HL/LL against the previous low (the first high /
low, or an exact tie, stay plain "high" / "low"). A swing at candle i is only known from its
confirming candle i + width (`known(s)` = i + RIGHT for the default swings).

Case -> example (`_example`): a case is {start, end, swings?, trend?, breaks?, primitives?, facts?,
glossary?, rank?}. Swing markers come first, then each break's level + label (BOS / CHoCH), then the
case's own `primitives`; facts are trend, swings, the breaks, the case's own `facts`, then source
(+ daily_reference_fix for EUR/USD). `glossary` overrides the detector's key for that example.

Ranking (`_ranked` / `_find`): per (asset, timeframe) one case; cases rank by (size desc, end time
desc, asset order, timeframe order 1D/4H/1H), size = the case's `rank` or else its swing count.
Example 1 is the top case, example 2 the best remaining one on another asset, else another timeframe.

The fractal / ATR code is a separate copy of gold.py's helpers on purpose: the daily gold outlook
must not drift when the lessons change.
"""
from autopilot.lesson_data import ASSETS, SOURCES, TIMEFRAMES
from autopilot.lessons import day, timestamp

LEFT = RIGHT = 3  # fractal width
ATR_N = 14
ATR_MULT = 1.0  # minimum leg between opposite swings, in ATRs
PAD = 5  # candles shown either side of the region
MAX_CANDLES = 150
UP, DOWN = {"HH", "HL"}, {"LH", "LL"}
REFERENCE_FIX = {"EUR/USD"}  # daily central-bank fix, not traded candles


# ─── swing finder ──────────────────────────────────────────────────────────

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


def find_swings(candles: list[dict], width: int = LEFT, atr_mult: float = ATR_MULT) -> list[dict]:
    """Alternating, ATR-filtered, labelled swings: [{i, t, side, price, kind}], oldest first."""
    raw = []
    for i in range(width, len(candles) - width):
        h, lo = candles[i]["h"], candles[i]["l"]
        left, right = candles[i - width:i], candles[i + 1:i + width + 1]
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
        if swings and abs(s["price"] - swings[-1]["price"]) < atr_mult * atr[s["i"]]:
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


def known(s: dict) -> int:
    """The candle that confirms a default (width RIGHT) swing: it counts from here, never earlier."""
    return s["i"] + RIGHT


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


# ─── examples ──────────────────────────────────────────────────────────────

def _example(detector: str, glossary: str, asset: str, tf: str, candles: list[dict], case: dict) -> dict:
    lo, hi = _window(candles, case["start"], case["end"])
    span = candles[case["start"]:case["end"] + 1]
    swings = [{"t": s["t"], "kind": s["kind"], "price": s["price"]} for s in case.get("swings", [])]
    prims = [{"type": "swing", **s} for s in swings]
    facts = {}
    if "trend" in case:
        facts["trend"] = case["trend"]
    if "swings" in case:
        facts["swings"] = swings
    for name, swing, m in case.get("breaks", []):
        prims.append({"type": "level", "price": swing["price"], "label": name})
        prims.append({"type": "label", "t": candles[m]["t"], "price": candles[m]["c"], "text": name})
        facts[name.lower()] = {"level": swing["price"], "swing_t": swing["t"], "swing_kind": swing["kind"],
                               "t": candles[m]["t"], "close": candles[m]["c"]}
    prims += case.get("primitives", [])
    facts.update(case.get("facts", {}))
    facts["source"] = SOURCES.get(asset, "")
    if asset in REFERENCE_FIX:
        facts["daily_reference_fix"] = True  # not live prices: open = high = low = close = the day's fix
    last_t = candles[case["end"]]["t"]
    return {
        "detector": detector, "glossary": case.get("glossary", glossary), "asset": asset, "timeframe": tf,
        "date": day(last_t),
        "candles": [{k: c[k] for k in ("t", "o", "h", "l", "c")} for c in candles[lo:hi + 1]],
        "region": {"start": candles[case["start"]]["t"], "end": last_t,
                   "low": min(c["l"] for c in span), "high": max(c["h"] for c in span)},
        "primitives": prims,
        "facts": facts,
    }


def _order(seq: tuple, key: str) -> tuple[int, str]:
    return (seq.index(key), "") if key in seq else (len(seq), key)


def _ranked(history: dict, case_fn, detector: str, glossary: str, timeframes: tuple | None = None,
            pass_tf: bool = False) -> list[dict]:
    """Every series' case as an example, best first. `timeframes` limits the series looked at;
    `pass_tf` calls case_fn(candles, swings, timeframe) instead of case_fn(candles, swings)."""
    ranked = []
    for asset in sorted(history, key=lambda a: _order(ASSETS, a)):
        for tf in sorted(history[asset], key=lambda t: _order(TIMEFRAMES, t)):
            if timeframes is not None and tf not in timeframes:
                continue
            candles = history[asset][tf]
            if len(candles) < LEFT + RIGHT + 1:
                continue
            swings = find_swings(candles)
            case = case_fn(candles, swings, tf) if pass_tf else case_fn(candles, swings)
            if case:
                ex = _example(detector, glossary, asset, tf, candles, case)
                size = case.get("rank", len(case.get("swings", [])))
                key = (-size, -timestamp(ex["region"]["end"]), _order(ASSETS, asset), _order(TIMEFRAMES, tf))
                ranked.append((key, ex))
    ranked.sort(key=lambda r: r[0])
    return [ex for _, ex in ranked]


def _two(ranked: list[dict]) -> list[dict]:
    """The top example plus the best remaining one on another asset, else the next one."""
    if not ranked:
        return []
    first, rest = ranked[0], ranked[1:]
    second = next((ex for ex in rest if ex["asset"] != first["asset"]), rest[0] if rest else None)
    return [first] + ([second] if second else [])


def _find(history: dict, case_fn, detector: str, glossary: str, timeframes: tuple | None = None,
          pass_tf: bool = False) -> list[dict]:
    return _two(_ranked(history, case_fn, detector, glossary, timeframes, pass_tf))
