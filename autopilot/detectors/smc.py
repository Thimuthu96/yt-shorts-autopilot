"""SMC detectors for Track 3: `fvg`, `order_block`, `mitigation_breaker`, `premium_discount` and
`sweep_choch_model`. Built on common.py's swing finder (3-candle fractal, ATR-filtered; a swing counts
only from its confirming candle i + 3), ranking and example shape, structure.py's BOS / CHoCH walk
(`structure_events`, the same walk `bos_choch` uses) and liquidity.py's `find_sweeps`.

Deterministic: same candles -> same examples. Input is lesson_data.fetch_history()'s shape
{asset: {timeframe: [{t, o, h, l, c}]}}; each detector returns up to 2 examples, or [] when no
series has a clean case. ATR = ATR(14) at the candle concerned.

Displacement leg of a break (BOS or CHoCH) at candle m through swing s: from its origin, the most
extreme candle against the break between s and m (the lowest low before an up break; on a tie the
later one), to m. Its order-block candle is the last opposite-colour candle (down-close before an up
leg, up-close before a down leg) at or before the origin, after s.

    fvg                 candles k-1, k, k+1 with high[k-1] < low[k+1] (bullish) or low[k-1] > high[k+1]
                        (bearish), gap >= 0.3 x ATR at k (`find_fvgs`). Clean = the gap's middle candle k
                        lies inside the displacement leg of a BOS in its direction (a gap formed by the
                        move that broke structure; loose gaps in a range don't count). Per series the
                        largest gap in ATRs (then the most recent). Zone "FVG" from candle k-1 to the fill
                        (first candle trading back through the gap's far edge) or the window end; facts.filled.
                        Ranked by gap size in ATRs.
    order_block         the order-block candle of a BOS's displacement leg (`find_order_blocks`). Zone "OB"
                        = that candle's low-high from its candle to the first revisit (first candle after
                        the BOS trading back into it) or the window end; level + label "BOS" at the broken
                        swing. Per series the most recent revisited block, else the most recent block.
    mitigation_breaker  an order block that later fails: the first close through its far side after the
                        BOS. The move before the failure is read from the last with-trend swing confirmed
                        by then (it must be the move's extreme): `breaker` if it went beyond the swing of
                        that side before it (swept it), `mitigation` if it failed to make a new high / low.
                        Clean only when, within 30 candles of the failure, price trades wholly on the
                        other side of the zone and then returns into it. Zone "Breaker" / "Mitigation", labels "Fail" and "Return"; facts.kind;
                        the example's glossary is breaker_block / mitigation_block.
    premium_discount    dealing range = the latest confirmed swing pair that ends a run of >= 4 agreeing
                        swings in its direction (HL -> HH in an uptrend, LH -> LL in a downtrend), range
                        >= 3 x ATR. Level "EQ" at 50%, zones "Premium" (upper half) and "Discount" (lower
                        half). Clean = before the next swing is confirmed and before price trades beyond the
                        range's far end, a close enters discount in an uptrend (premium in a downtrend)
                        without closing beyond the range's other end.
    sweep_choch_model   a sweep (`find_sweeps`) of a with-trend swing (a low in a downtrend), then within 20
                        candles a CHoCH against the prior trend, with no candle between them trading beyond
                        the sweep's extreme (the sweep is the turn), then an order block or FVG of that leg,
                        untouched until the CHoCH, that price returns into (whichever is revisited first; a
                        tie keeps the OB). Labels "Sweep", "CHoCH"; level at the CHoCH
                        swing; zone "OB" / "FVG". A CHoCH before the sweep is no model.

Per (asset, timeframe) one case; ranking as common.py (size = gap ATRs, revisit / return, swings shown;
then end time, asset, timeframe). Facts hold only candle values (prices and times read from candles),
booleans and kinds: never derived numbers (the 50% level and gap sizes stay in the primitives / rank).
"""
from autopilot import lessons
from autopilot.detectors.common import RIGHT, _atr, _find, _fits, _runs, _window
from autopilot.detectors.liquidity import find_sweeps
from autopilot.detectors.structure import MIN_SWINGS, structure_events

FVG_MIN = 0.3  # gap, in ATRs
RETURN_N = 30  # mitigation / breaker: candles after the failure for the return
RANGE_MIN = 3.0  # premium / discount: dealing range, in ATRs
MODEL_N = 20  # sweep -> CHoCH: at most this many candles


def _known(s: dict) -> int:
    return s["i"] + RIGHT  # the candle that confirms the swing


def _point(s: dict) -> dict:
    return {"t": s["t"], "price": s["price"]}


def _side(up: bool) -> str:
    return "bullish" if up else "bearish"


def _zone_t2(candles: list[dict], start: int, end: int, at: int | None) -> str:
    """A zone's right edge: candle `at`, or the last candle the chart shows."""
    return candles[at if at is not None else _window(candles, start, end)[1]]["t"]


# ─── shared pieces ─────────────────────────────────────────────────────────

def find_fvgs(candles: list[dict]) -> list[dict]:
    """Every fair value gap >= 0.3 x ATR, oldest first: [{i (middle candle k), up, low, high, size
    (gap in ATRs), fill (first candle after k + 1 trading through the far edge, or None)}]. Candles with no
    range (a daily fix, high = low) never form one."""
    atr = _atr(candles)
    out = []
    for k in range(1, len(candles) - 1):
        a, b = candles[k - 1], candles[k + 1]
        if any(c["h"] == c["l"] for c in (a, candles[k], b)):
            continue
        if a["h"] < b["l"]:
            up, low, high = True, a["h"], b["l"]
        elif a["l"] > b["h"]:
            up, low, high = False, b["h"], a["l"]
        else:
            continue
        if high - low < FVG_MIN * atr[k]:
            continue
        fill = next((x for x in range(k + 2, len(candles))
                     if ((candles[x]["l"] < low) if up else (candles[x]["h"] > high))), None)
        out.append({"i": k, "up": up, "low": low, "high": high, "size": (high - low) / atr[k], "fill": fill})
    return out


def _leg(candles: list[dict], s: dict, m: int, up: bool) -> tuple[int, int | None]:
    """A break's displacement leg through swing s at candle m: (origin, order-block candle or None)."""
    span = range(s["i"] + 1, m + 1)
    if up:
        origin = min(span, key=lambda x: (candles[x]["l"], -x))
    else:
        origin = max(span, key=lambda x: (candles[x]["h"], x))
    opposite = (lambda c: c["c"] < c["o"]) if up else (lambda c: c["c"] > c["o"])  # noqa: E731
    ob = next((x for x in range(origin, s["i"], -1) if opposite(candles[x])), None)
    return origin, ob


def _entered(candles: list[dict], start: int, low: float, high: float, from_above: bool) -> int | None:
    """First candle from `start` trading into [low, high]: from above (its low <= high) or below."""
    for x in range(start, len(candles)):
        if (candles[x]["l"] <= high) if from_above else (candles[x]["h"] >= low):
            return x
    return None


def find_order_blocks(candles: list[dict], swings: list[dict]) -> list[dict]:
    """The order block of every BOS displacement leg, by BOS candle: [{i, t, up, low, high, origin, bos
    (the structure event), revisit (first candle after the BOS trading back into it, or None)}]."""
    out = []
    for e in structure_events(candles, swings):
        if e["kind"] != "BOS":
            continue
        up = e["trend"] == "uptrend"
        origin, k = _leg(candles, e["swing"], e["i"], up)
        if k is None:
            continue
        c = candles[k]
        out.append({"i": k, "t": c["t"], "up": up, "low": c["l"], "high": c["h"], "origin": origin, "bos": e,
                    "revisit": _entered(candles, e["i"] + 1, c["l"], c["h"], from_above=up)})
    out.sort(key=lambda b: (b["bos"]["i"], b["i"]))
    return out


def _shown(swings: list[dict], start: int, end: int) -> list[dict]:
    """Swings on the chart [start, end] that are confirmed by its last candle."""
    return [s for s in swings if start <= s["i"] and _known(s) <= end]


# ─── fair value gap ────────────────────────────────────────────────────────

def _fvg_case(candles: list[dict], swings: list[dict]) -> dict | None:
    legs = []
    for e in structure_events(candles, swings):
        if e["kind"] == "BOS":
            up = e["trend"] == "uptrend"
            legs.append((up, _leg(candles, e["swing"], e["i"], up)[0], e["i"]))
    best = None
    for g in find_fvgs(candles):
        k = g["i"]
        if not any(up == g["up"] and origin < k <= m for up, origin, m in legs):
            continue
        end = g["fill"] if g["fill"] is not None else k + 1
        if not _fits(candles, k - 1, end):
            continue
        if best is None or (g["size"], k) >= (best[0]["size"], best[0]["i"]):
            best = (g, end)
    if best is None:
        return None
    g, end = best
    k, up = g["i"], g["up"]
    a, b = candles[k - 1], candles[k + 1]
    facts = {"kind": _side(up), "gap": {"low": g["low"], "high": g["high"]},
             "before": {"t": a["t"], ("high" if up else "low"): a["h"] if up else a["l"]},
             "after": {"t": b["t"], ("low" if up else "high"): b["l"] if up else b["h"]},
             "filled": g["fill"] is not None}
    if g["fill"] is not None:
        f = candles[g["fill"]]
        facts["fill"] = {"t": f["t"], ("low" if up else "high"): f["l"] if up else f["h"]}
    return {"start": k - 1, "end": end, "rank": g["size"],
            "primitives": [{"type": "zone", "t1": a["t"], "t2": _zone_t2(candles, k - 1, end, g["fill"]),
                            "low": g["low"], "high": g["high"], "label": "FVG"}],
            "facts": facts}


# ─── order block ───────────────────────────────────────────────────────────

def _ob_case(candles: list[dict], swings: list[dict]) -> dict | None:
    blocks = find_order_blocks(candles, swings)
    for ob in sorted(blocks, key=lambda b: (b["revisit"] is not None, b["bos"]["i"]), reverse=True):
        e, s = ob["bos"], ob["bos"]["swing"]
        end = ob["revisit"] if ob["revisit"] is not None else e["i"]
        if not _fits(candles, s["i"], end):
            continue
        facts = {"trend": e["trend"], "block": {"kind": _side(ob["up"]), "t": ob["t"], "low": ob["low"],
                                                 "high": ob["high"]},
                 "revisited": ob["revisit"] is not None}
        if ob["revisit"] is not None:
            r = candles[ob["revisit"]]
            facts["revisit"] = {"t": r["t"], "price": r["l"] if ob["up"] else r["h"]}
        return {"trend": e["trend"], "swings": _shown(swings, s["i"], end), "start": s["i"], "end": end,
                "rank": 2 if ob["revisit"] is not None else 1, "breaks": [("BOS", s, e["i"])],
                "primitives": [{"type": "zone", "t1": ob["t"], "t2": _zone_t2(candles, s["i"], end, ob["revisit"]),
                                "low": ob["low"], "high": ob["high"], "label": "OB"}],
                "facts": facts}
    return None


# ─── mitigation / breaker ──────────────────────────────────────────────────

def _mb_case(candles: list[dict], swings: list[dict]) -> dict | None:
    closes = [c["c"] for c in candles]
    for ob in reversed(find_order_blocks(candles, swings)):  # most recent BOS first
        up, e = ob["up"], ob["bos"]
        # failure: a close through the block's far side (below a bullish block, above a bearish one)
        f = next((x for x in range(e["i"] + 1, len(candles))
                  if ((closes[x] < ob["low"]) if up else (closes[x] > ob["high"]))), None)
        if f is None:
            continue
        side = "high" if up else "low"  # the with-trend side the move after the BOS pushed
        pos = [p for p, s in enumerate(swings) if s["side"] == side and s["i"] > ob["i"] and _known(s) <= f]
        if not pos:
            continue
        w = swings[pos[-1]]
        between = candles[w["i"] + 1:f]
        if between and ((max(c["h"] for c in between) > w["price"]) if up
                        else (min(c["l"] for c in between) < w["price"])):
            continue  # the move's extreme was not a confirmed swing by the failure
        prior = next((s for s in reversed(swings[:pos[-1]]) if s["side"] == side), None)
        if prior is None:
            continue
        swept = w["price"] > prior["price"] if up else w["price"] < prior["price"]
        kind = "breaker" if swept else "mitigation"
        # the return: price first trades wholly on the other side (below a failed bullish block), then
        # comes back into the zone
        away = next((x for x in range(f + 1, min(f + RETURN_N, len(candles) - 1) + 1)
                     if ((candles[x]["h"] < ob["low"]) if up else (candles[x]["l"] > ob["high"]))), None)
        r = _entered(candles, away + 1, ob["low"], ob["high"], from_above=not up) if away is not None else None
        if r is None or r > f + RETURN_N:
            continue
        s = e["swing"]
        start = min(s["i"], prior["i"])
        if not _fits(candles, start, r):
            continue
        fc, rc = candles[f], candles[r]
        r_price = rc["h"] if up else rc["l"]
        name = "Breaker" if swept else "Mitigation"
        return {"trend": e["trend"], "swings": _shown(swings, start, r), "start": start, "end": r,
                "rank": 1, "glossary": f"{kind}_block", "breaks": [("BOS", s, e["i"])],
                "primitives": [{"type": "zone", "t1": ob["t"], "t2": rc["t"], "low": ob["low"], "high": ob["high"],
                                "label": name},
                               {"type": "label", "t": fc["t"], "price": fc["c"], "text": "Fail"},
                               {"type": "label", "t": rc["t"], "price": r_price, "text": "Return"}],
                "facts": {"kind": kind, "block": {"kind": _side(up), "t": ob["t"], "low": ob["low"], "high": ob["high"]},
                          "move": {"prior": _point(prior), "extreme": _point(w), "swept": swept},
                          "failure": {"t": fc["t"], "close": fc["c"]}, "return": {"t": rc["t"], "price": r_price}}}
    return None


# ─── premium / discount ────────────────────────────────────────────────────

def _pd_case(candles: list[dict], swings: list[dict]) -> dict | None:
    atr, n = _atr(candles), len(candles)
    pairs = []
    for trend, a, b in _runs(swings):
        up = trend == "uptrend"
        for q in range(a + MIN_SWINGS - 2, b):  # the pair (q, q + 1) ends >= 4 agreeing swings
            if swings[q + 1]["side"] == ("high" if up else "low"):
                pairs.append((q, up, trend))
    for q, up, trend in sorted(pairs, reverse=True):  # most recent pair first
        x, y = swings[q], swings[q + 1]
        lo, hi = (x["price"], y["price"]) if up else (y["price"], x["price"])
        if hi - lo < RANGE_MIN * atr[y["i"]]:
            continue
        eq = (lo + hi) / 2
        stop = _known(swings[q + 2]) if q + 2 < len(swings) else n  # the next swing replaces the pair
        hit = None
        for m in range(_known(y), min(stop, n)):
            c = candles[m]
            if (c["h"] > hi) if up else (c["l"] < lo):
                break  # the range expanded beyond its far end
            if (c["c"] < eq) if up else (c["c"] > eq):
                hit = m if ((c["c"] >= lo) if up else (c["c"] <= hi)) else None
                break
        if hit is None or not _fits(candles, x["i"], hit):
            continue
        c = candles[hit]
        zone = "discount" if up else "premium"
        low_s, high_s = (x, y) if up else (y, x)
        return {"trend": trend, "swings": [x, y], "start": x["i"], "end": hit,
                "primitives": [{"type": "level", "price": eq, "label": "EQ"},
                               {"type": "zone", "t1": x["t"], "t2": c["t"], "low": eq, "high": hi, "label": "Premium"},
                               {"type": "zone", "t1": x["t"], "t2": c["t"], "low": lo, "high": eq, "label": "Discount"},
                               {"type": "label", "t": c["t"], "price": c["c"], "text": zone.capitalize()}],
                "facts": {"range": {"low": _point(low_s), "high": _point(high_s)},
                          "enters": {"zone": zone, "t": c["t"], "close": c["c"]}}}
    return None


# ─── sweep -> CHoCH -> OB / FVG ────────────────────────────────────────────

def _model_case(candles: list[dict], swings: list[dict]) -> dict | None:
    sweeps = find_sweeps(candles, swings)
    fvgs = find_fvgs(candles)
    events = [e for e in structure_events(candles, swings) if e["kind"] == "CHoCH"]
    for e in sorted(events, key=lambda e: -e["i"]):  # most recent CHoCH first
        m, cs = e["i"], e["swing"]
        up = e["trend"] == "downtrend"  # the CHoCH breaks against the prior trend
        with_side = "low" if up else "high"  # the swing a sweep before a bullish CHoCH takes
        # the sweep must be the turn: no candle after it, up to the CHoCH, trades beyond its extreme
        cands = [sw for sw in sweeps if sw["side"] == with_side and cs["i"] < sw["i"] < m and m - sw["i"] <= MODEL_N
                 and all((c["l"] >= sw["extreme"]) if up else (c["h"] <= sw["extreme"])
                         for c in candles[sw["i"] + 1:m + 1])]
        if not cands:
            continue
        sw = cands[-1]  # the latest sweep before the CHoCH
        origin, ob = _leg(candles, cs, m, up)
        zones = []  # (return candle, order, kind, start candle, low, high)
        # a zone counts only if price first comes back into it after the CHoCH (untested until then)
        if ob is not None and ob >= sw["i"]:
            c = candles[ob]
            away = next((x for x in range(ob + 1, m + 1)  # the leg leaves the block
                         if ((candles[x]["l"] > c["h"]) if up else (candles[x]["h"] < c["l"]))), None)
            r = _entered(candles, away + 1, c["l"], c["h"], from_above=up) if away is not None else None
            if r is not None and r > m:
                zones.append((r, 0, "OB", ob, c["l"], c["h"]))
        for g in fvgs:
            if g["up"] == up and origin < g["i"] <= m and g["i"] - 1 >= sw["i"]:
                r = _entered(candles, g["i"] + 2, g["low"], g["high"], from_above=up)
                if r is not None and r > m:
                    zones.append((r, 1, "FVG", g["i"] - 1, g["low"], g["high"]))
        if not zones:
            continue
        r, _, kind, z0, z_lo, z_hi = min(zones)
        start = min(sw["swing"]["i"], cs["i"])
        if not _fits(candles, start, r):
            continue
        sc, rc = candles[sw["i"]], candles[r]
        r_price = rc["l"] if up else rc["h"]
        shown = sorted({sw["swing"]["i"]: sw["swing"], cs["i"]: cs}.values(), key=lambda s: s["i"])
        return {"trend": e["trend"], "swings": shown, "start": start, "end": r, "rank": 1,
                "breaks": [("CHoCH", cs, m)],
                "primitives": [{"type": "label", "t": sc["t"], "price": sw["extreme"], "text": "Sweep"},
                               {"type": "zone", "t1": candles[z0]["t"], "t2": rc["t"], "low": z_lo, "high": z_hi,
                                "label": kind}],
                "facts": {"sweep": {"t": sc["t"], "level": sw["level"], "level_t": sw["swing"]["t"],
                                    ("low" if up else "high"): sw["extreme"], "close": sw["close"]},
                          "zone": {"kind": kind, "t": candles[z0]["t"], "low": z_lo, "high": z_hi},
                          "return": {"t": rc["t"], "price": r_price}}}
    return None


# ─── detectors ─────────────────────────────────────────────────────────────

def find_fvg_examples(history: dict) -> list[dict]:
    return _find(history, _fvg_case, "fvg", "fair_value_gap")


def find_order_block_examples(history: dict) -> list[dict]:
    return _find(history, _ob_case, "order_block", "order_block")


def find_mitigation_breaker_examples(history: dict) -> list[dict]:
    return _find(history, _mb_case, "mitigation_breaker", "breaker_block")


def find_premium_discount_examples(history: dict) -> list[dict]:
    return _find(history, _pd_case, "premium_discount", "premium_discount")


def find_sweep_choch_model_examples(history: dict) -> list[dict]:
    return _find(history, _model_case, "sweep_choch_model", "sweep_choch_model")


FVG = lessons.register(lessons.Detector("fvg", "fair_value_gap", find_fvg_examples))
ORDER_BLOCK = lessons.register(lessons.Detector("order_block", "order_block", find_order_block_examples))
MITIGATION_BREAKER = lessons.register(lessons.Detector("mitigation_breaker", ("mitigation_block", "breaker_block"),
                                                       find_mitigation_breaker_examples))
PREMIUM_DISCOUNT = lessons.register(lessons.Detector("premium_discount", ("premium_discount", "equilibrium"),
                                                     find_premium_discount_examples))
SWEEP_CHOCH_MODEL = lessons.register(lessons.Detector("sweep_choch_model", "sweep_choch_model",
                                                      find_sweep_choch_model_examples))
