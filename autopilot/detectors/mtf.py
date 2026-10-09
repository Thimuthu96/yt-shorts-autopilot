"""Multi-timeframe detector for Track 0's top-down episode: `top_down` (glossary `top_down_analysis`,
`market_structure`). Built on structure.py's swing finder and swing case, so the higher-timeframe
panel is exactly what the `swings` detector would show for that series.

Deterministic: same candles -> same examples. Input is lesson_data.fetch_history()'s shape
{asset: {timeframe: [{t, o, h, l, c}]}}; returns up to 2 examples, or [] when no pair is clean.

Pairs (same asset): 1D -> 4H and 4H -> 1H.

    higher timeframe  structure's most recent swing case (>= 4 agreeing labelled swings)
    LTF window        from the case's second-to-last swing to the end of its last swing's candle
                      (its last leg), mapped to lower-timeframe candles by time; trimmed from the front
                      if the panel would exceed 150 candles
    lower timeframe   swings found on the whole lower series (structure.find_swings), kept if they
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
from datetime import datetime, timedelta

from autopilot import lessons
from autopilot.detectors import structure
from autopilot.detectors.structure import MAX_CANDLES, MIN_SWINGS, PAD, find_swings
from autopilot.lesson_data import ASSETS, TF_SECONDS, TIMEFRAMES

LOWER = {"1D": "4H", "4H": "1H"}  # higher timeframe -> the next lower one
LABELLED = structure.UP | structure.DOWN
MIN_RUN = 2  # agreeing swings that set the lower timeframe's trend


def _trend(labelled: list[dict]) -> str:
    """Trend of the most recent run of >= MIN_RUN agreeing labelled swings, else "mixed"."""
    for trend, a, b in reversed(structure._runs(labelled)):
        if b - a + 1 >= MIN_RUN:
            return trend
    return "mixed"


def _dt(t) -> datetime:
    return datetime.fromisoformat(t) if isinstance(t, str) else t


def _lower_case(htf: str, case: dict, ltf_candles: list[dict]) -> dict | None:
    """The lower-timeframe structure inside the higher-timeframe case's last leg, or None."""
    start = _dt(case["swings"][-2]["t"])
    stop = _dt(case["swings"][-1]["t"]) + timedelta(seconds=TF_SECONDS[htf])  # end of the swing's candle
    idx = [i for i, c in enumerate(ltf_candles) if start <= _dt(c["t"]) < stop]
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
    ex = structure._example("top_down", "top_down_analysis", asset, htf, htf_candles, case)
    lo, hi = max(0, low["start"] - PAD), min(len(ltf_candles) - 1, low["end"] + PAD)
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
    for asset in sorted(history, key=lambda a: structure._order(ASSETS, a)):
        series = history[asset]
        for htf in sorted((t for t in series if t in LOWER), key=lambda t: structure._order(TIMEFRAMES, t)):
            hc, lc = series[htf], series.get(LOWER[htf]) or []
            if len(hc) < structure.LEFT + structure.RIGHT + 1 or not lc:
                continue
            case = structure._swing_case(hc, find_swings(hc))
            if not case:
                continue
            low = _lower_case(htf, case, lc)
            if not low:
                continue
            ex = _example(asset, htf, hc, case, lc, low)
            key = (-len(case["swings"]), -structure._ts(ex["region"]["end"]), structure._order(ASSETS, asset),
                   structure._order(TIMEFRAMES, htf))
            ranked.append((key, ex))
    if not ranked:
        return []
    ranked.sort(key=lambda r: r[0])
    first = ranked[0][1]
    rest = [ex for _, ex in ranked[1:]]
    second = next((ex for ex in rest if ex["asset"] != first["asset"]), rest[0] if rest else None)
    return [first] + ([second] if second else [])


TOP_DOWN = lessons.register(lessons.Detector("top_down", ("top_down_analysis", "market_structure"),
                                             find_top_down_examples))
