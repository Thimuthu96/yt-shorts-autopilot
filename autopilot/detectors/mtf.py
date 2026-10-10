"""Multi-timeframe detector for Track 0's top-down episode: `top_down` (glossary `top_down_analysis`,
`market_structure`). Built on common.py's swing finder and example shape and structure.py's swing case,
so the higher-timeframe panel is exactly what the `swings` detector would show for that series.

Deterministic: same candles -> same examples. Input is lesson_data.fetch_history()'s shape
{asset: {timeframe: [{t, o, h, l, c}]}}; returns up to 2 examples, or [] when no pair is clean.

Pairs (same asset): 1D -> 4H and 4H -> 1H.

    higher timeframe  structure's most recent swing case (>= 4 agreeing labelled swings)
    LTF window        from the case's second-to-last swing to the end of its last swing's candle
                      (its last leg), mapped to lower-timeframe candles by time; trimmed from the front
                      if the panel would exceed 150 candles
    lower timeframe   swings found on the whole lower series (common.find_swings), kept if they
                      fall inside the window; clean = >= 4 labelled swings (HH/HL/LH/LL) there.
                      They need not agree: the lower trend is the trend of their most recent run of
                      >= 2 agreeing swings (a single trailing swing, e.g. one LH after HH/HL, doesn't
                      flip it), "mixed" if no two agree; `aligned` = it matches the higher trend.

Example = structure's example of the higher-timeframe case (detector "top_down") plus
    lower: {timeframe, candles, region, primitives}   region = the LTF window; primitives = its swings
    facts: trend, swings, source (as structure), htf {timeframe, trend},
           ltf {timeframe, trend, swings}, aligned (bool)

Ranking as structure: (higher-timeframe swings desc, end time desc, asset order, timeframe order);
example 2 is the best remaining pair on another asset, else the other pair on the same asset.
"""
from datetime import timedelta

from autopilot import lessons
from autopilot.detectors.common import (
    DOWN, LEFT, MAX_CANDLES, PAD, RIGHT, UP, _example as _htf_example, _order, _runs, _two, _window, find_swings,
)
from autopilot.detectors.structure import MIN_SWINGS, _swing_case
from autopilot.lesson_data import ASSETS, TF_SECONDS, TIMEFRAMES
from autopilot.lessons import timestamp, to_datetime

LOWER = {"1D": "4H", "4H": "1H"}  # higher timeframe -> the next lower one
LABELLED = UP | DOWN
MIN_RUN = 2  # agreeing swings that set the lower timeframe's trend


def _trend(labelled: list[dict]) -> str:
    """Trend of the most recent run of >= MIN_RUN agreeing labelled swings, else "mixed"."""
    for trend, a, b in reversed(_runs(labelled)):
        if b - a + 1 >= MIN_RUN:
            return trend
    return "mixed"


def _lower_case(htf: str, case: dict, ltf_candles: list[dict]) -> dict | None:
    """The lower-timeframe structure inside the higher-timeframe case's last leg, or None."""
    start = to_datetime(case["swings"][-2]["t"])
    stop = to_datetime(case["swings"][-1]["t"]) + timedelta(seconds=TF_SECONDS[htf])  # end of the swing's candle
    idx = [i for i, c in enumerate(ltf_candles) if start <= to_datetime(c["t"]) < stop]
    if not idx:
        return None
    a, b = idx[0], idx[-1]
    a = max(a, b - (MAX_CANDLES - 2 * PAD) + 1)  # keep the panel within 150 candles
    inside = [s for s in find_swings(ltf_candles) if a <= s["i"] <= b]
    labelled = [s for s in inside if s["kind"] in LABELLED]
    if len(labelled) < MIN_SWINGS:
        return None
    return {"start": a, "end": b, "swings": inside, "trend": _trend(labelled)}


def _example(asset: str, htf: str, htf_candles: list[dict], case: dict, ltf_candles: list[dict], low: dict) -> dict:
    ltf = LOWER[htf]
    ex = _htf_example("top_down", "top_down_analysis", asset, htf, htf_candles, case)
    lo, hi = _window(ltf_candles, low["start"], low["end"])
    span = ltf_candles[low["start"]:low["end"] + 1]
    swings = [{"t": s["t"], "kind": s["kind"], "price": s["price"]} for s in low["swings"]]
    ex["lower"] = {
        "timeframe": ltf,
        "candles": [{k: c[k] for k in ("t", "o", "h", "l", "c")} for c in ltf_candles[lo:hi + 1]],
        "region": {"start": span[0]["t"], "end": span[-1]["t"],
                   "low": min(c["l"] for c in span), "high": max(c["h"] for c in span)},
        "primitives": [{"type": "swing", **s} for s in swings],
    }
    f = ex["facts"]
    f["htf"] = {"timeframe": htf, "trend": case["trend"]}
    f["ltf"] = {"timeframe": ltf, "trend": low["trend"], "swings": swings}
    f["aligned"] = low["trend"] == case["trend"]
    return ex


def find_top_down_examples(history: dict) -> list[dict]:
    ranked = []
    for asset in sorted(history, key=lambda a: _order(ASSETS, a)):
        series = history[asset]
        for htf in sorted((t for t in series if t in LOWER), key=lambda t: _order(TIMEFRAMES, t)):
            hc, lc = series[htf], series.get(LOWER[htf]) or []
            if len(hc) < LEFT + RIGHT + 1 or not lc:
                continue
            case = _swing_case(hc, find_swings(hc))
            if not case:
                continue
            low = _lower_case(htf, case, lc)
            if not low:
                continue
            ex = _example(asset, htf, hc, case, lc, low)
            key = (-len(case["swings"]), -timestamp(ex["region"]["end"]), _order(ASSETS, asset),
                   _order(TIMEFRAMES, htf))
            ranked.append((key, ex))
    ranked.sort(key=lambda r: r[0])
    return _two([ex for _, ex in ranked])


TOP_DOWN = lessons.register(lessons.Detector("top_down", ("top_down_analysis", "market_structure"),
                                             find_top_down_examples))
