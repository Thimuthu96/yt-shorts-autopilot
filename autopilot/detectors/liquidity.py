"""Liquidity detectors for Track 2: `liquidity_pools`, `equal_highs_lows`, `session_highs_lows`,
`sweep_vs_breakout` and `inducement`. Built on common.py's swing finder (3-candle fractal,
ATR-filtered; a swing counts only from its confirming candle i + 3), ranking and example shape.

Deterministic: same candles -> same examples. Input is lesson_data.fetch_history()'s shape
{asset: {timeframe: [{t, o, h, l, c}]}}; each detector returns up to 2 examples, or [] when no
series has a clean case. ATR = ATR(14) at the candle concerned.

    liquidity_pools     at the most recent candle that sits in a trend (its known swings end in a
                        run of >= 4 agreeing swings): the nearest <= 2 known swing highs above its
                        close (BSL) and swing lows below it (SSL) that no candle has traded through
                        since; clean needs >= 1 each side. Levels labelled BSL / SSL.
    equal_highs_lows    the most recent two consecutive swing highs (or lows) within 0.15 x ATR of each
                        other, >= 5 candles apart (the opposite swing lies between them). Level at the
                        outer of the two + both markers labelled EQH / EQL.
    session_highs_lows  1H only (4H candles don't line up with the sessions; 1D can't show them). UTC
                        sessions Asia 00-06, London 07-12, New York 12-20 (by the candle's hour). Clean = the most recent day with all
                        three sessions complete where Asia was a range (net move open -> close <= half
                        its high-low) and London or New York traded beyond the Asia high or low. A zone
                        per session, levels at the Asia high / low, a label where each was first taken.
    sweep_vs_breakout   levels = known swings that are the extreme of the 20 candles before them (an
                        obvious high / low; equal highs / lows are tagged EQH / EQL). The first candle
                        trading beyond an untaken level decides: a sweep if it closes back inside and
                        the next 3 closes stay inside; a breakout if a close beyond comes within those
                        3 candles and the next 3 closes hold beyond. Example 1 is the best (most recent)
                        sweep, example 2 the best breakout, on any asset / timeframe; facts.kind.
    inducement          major swings (fractal 3) plus minor swings (fractal 1). In a trend (a HH then
                        its HL, or a LL then its LH), the first minor pullback swing after the major
                        extreme is taken out before price reaches the next major swing, then a close
                        beyond the major extreme (BOS) follows before price trades beyond that next
                        major swing. Label + level "IDM" at the minor swing, BOS level + label.

Per (asset, timeframe) the most recent clean case is kept; ranking as common.py (size = pools,
swings shown, sessions' takes; then end time, asset, timeframe). Facts hold only candle values
(prices and times read from candles), counts and kinds.
"""
from datetime import datetime, timezone

from autopilot import lessons
from autopilot.detectors.common import RIGHT, _atr, _find, _fits, _ranked, _runs, find_swings
from autopilot.lesson_data import TF_SECONDS

MIN_SWINGS = 4  # agreeing swings that make a trend (as structure.py)
POOLS = 2  # nearest pools shown per side
EQUAL = 0.15  # equal highs / lows: within this many ATRs
EQUAL_GAP = 5  # candles between the two
SESSIONS = (("Asia", 0, 6), ("London", 7, 12), ("New York", 12, 20))  # UTC hours [start, end)
INTRADAY = ("1H",)  # 4H buckets (00-04, 04-08, ...) don't line up with Asia 00-06 / London 07-12
ASIA_DRIFT = 0.5  # Asia range: |last close - first open| <= this x (high - low)
LOOKBACK = 20  # a sweep / breakout level is the extreme of this many candles before it
HOLD = 3  # closes after the sweep / breakout candle
MINOR = 1  # inducement's minor swings: fractal width


def _known(s: dict) -> int:
    return s["i"] + RIGHT  # the candle that confirms the swing


def _taken(candles: list[dict], s: dict, start: int | None = None) -> int | None:
    """First candle after the swing (from `start`) trading beyond its price, or None."""
    up = s["side"] == "high"
    for k in range(s["i"] + 1 if start is None else start, len(candles)):
        if (candles[k]["h"] > s["price"]) if up else (candles[k]["l"] < s["price"]):
            return k
    return None


def _point(s: dict) -> dict:
    return {"t": s["t"], "price": s["price"]}


# ─── liquidity pools ───────────────────────────────────────────────────────

def _pools_case(candles: list[dict], swings: list[dict]) -> dict | None:
    taken = [_taken(candles, s) for s in swings]
    known, trend = -1, None
    for m in range(len(candles) - 1, -1, -1):  # most recent clean candle first
        p = sum(1 for s in swings if _known(s) <= m)
        if p != known:
            known, trend = p, None
            runs = _runs(swings[:p])
            if runs and runs[-1][2] == p - 1 and runs[-1][2] - runs[-1][1] + 1 >= MIN_SWINGS:
                trend = runs[-1][0]
        if trend is None:
            continue
        close = candles[m]["c"]
        live = [(s, k) for s, k in zip(swings[:p], taken) if (k is None or k > m) and _fits(candles, s["i"], m)]
        above = [s for s, _ in live if s["side"] == "high" and s["price"] > close]
        below = [s for s, _ in live if s["side"] == "low" and s["price"] < close]
        bsl = sorted(above, key=lambda s: s["price"])[:POOLS]  # nearest first
        ssl = sorted(below, key=lambda s: -s["price"])[:POOLS]
        if not bsl or not ssl:
            continue
        pools = sorted(bsl + ssl, key=lambda s: s["i"])
        prims = [{"type": "level", "price": s["price"], "label": "BSL"} for s in bsl]
        prims += [{"type": "level", "price": s["price"], "label": "SSL"} for s in ssl]
        return {"trend": trend, "swings": pools, "start": pools[0]["i"], "end": m, "rank": len(pools),
                "primitives": prims,
                "facts": {"at": {"t": candles[m]["t"], "close": close},
                          "bsl": [_point(s) for s in bsl], "ssl": [_point(s) for s in ssl]}}
    return None


# ─── equal highs / lows ────────────────────────────────────────────────────

def _equal(atr: list[float], s1: dict, s2: dict) -> bool:
    return (s1["side"] == s2["side"] and abs(s1["price"] - s2["price"]) <= EQUAL * atr[s2["i"]]
            and s2["i"] - s1["i"] >= EQUAL_GAP)


def _equal_case(candles: list[dict], swings: list[dict]) -> dict | None:
    atr = _atr(candles)
    for p in range(len(swings) - 3, -1, -1):  # swings alternate: p and p + 2 are the same side
        s1, s2 = swings[p], swings[p + 2]
        if not _equal(atr, s1, s2) or not _fits(candles, s1["i"], s2["i"]):
            continue
        high = s1["side"] == "high"
        name = "EQH" if high else "EQL"
        level = max(s1["price"], s2["price"]) if high else min(s1["price"], s2["price"])
        prims = [{"type": "level", "price": level, "label": name}]
        prims += [{"type": "label", "t": s["t"], "price": s["price"], "text": name} for s in (s1, s2)]
        return {"swings": [s1, s2], "start": s1["i"], "end": s2["i"], "rank": 2, "primitives": prims,
                "facts": {"label": name, "level": level, "first": _point(s1), "second": _point(s2)}}
    return None


# ─── session highs / lows ──────────────────────────────────────────────────

def _utc(t) -> datetime:
    d = datetime.fromisoformat(t) if isinstance(t, str) else t
    return d.astimezone(timezone.utc) if d.tzinfo else d.replace(tzinfo=timezone.utc)


def _slots(hours: int, start: int, end: int) -> int:
    """How many candles of `hours` (UTC-aligned) fit wholly inside [start, end)."""
    return sum(1 for h in range(0, 24, hours) if start <= h and h + hours <= end)


def _session_case(candles: list[dict], swings: list[dict], tf: str) -> dict | None:
    if tf not in INTRADAY:
        return None
    hours = TF_SECONDS[tf] // 3600
    days: dict[str, dict[str, list[int]]] = {}
    for i, c in enumerate(candles):
        d = _utc(c["t"])
        if d.minute or d.second or d.hour % hours:
            continue  # not on the UTC grid
        for name, a, b in SESSIONS:
            if a <= d.hour and d.hour + hours <= b:
                days.setdefault(d.date().isoformat(), {}).setdefault(name, []).append(i)
    for day in sorted(days, reverse=True):
        sess = days[day]
        if any(len(sess.get(name, [])) != _slots(hours, a, b) for name, a, b in SESSIONS):
            continue  # a session is missing candles (gap, weekend, series edge)
        asia = [candles[i] for i in sess["Asia"]]
        hi, lo = max(c["h"] for c in asia), min(c["l"] for c in asia)
        if hi <= lo or abs(asia[-1]["c"] - asia[0]["o"]) > ASIA_DRIFT * (hi - lo):
            continue  # Asia trended instead of ranging
        taken = []
        for name in ("London", "New York"):
            for side, beyond in (("high", lambda c: c["h"] > hi), ("low", lambda c: c["l"] < lo)):
                k = next((i for i in sess[name] if beyond(candles[i])), None)
                if k is not None:
                    taken.append((k, name, side))
        if not taken:
            continue
        taken.sort()
        prims, facts = [], {"day": day}
        for name, _, _ in SESSIONS:
            idx = sess[name]
            s_lo, s_hi = min(candles[i]["l"] for i in idx), max(candles[i]["h"] for i in idx)
            prims.append({"type": "zone", "t1": candles[idx[0]]["t"], "t2": candles[idx[-1]]["t"],
                          "low": s_lo, "high": s_hi, "label": name})
            facts[name.lower().replace(" ", "_")] = {"high": s_hi, "low": s_lo}
        prims += [{"type": "level", "price": hi, "label": "Asia high"},
                  {"type": "level", "price": lo, "label": "Asia low"}]
        facts["taken"] = []
        for k, name, side in taken:
            price = candles[k]["h"] if side == "high" else candles[k]["l"]
            prims.append({"type": "label", "t": candles[k]["t"], "price": price, "text": f"{name} takes Asia {side}"})
            facts["taken"].append({"session": name, "side": side, "t": candles[k]["t"], "price": price})
        return {"start": sess["Asia"][0], "end": sess["New York"][-1], "rank": len(taken),
                "primitives": prims, "facts": facts}
    return None


# ─── sweeps and breakouts ──────────────────────────────────────────────────

def _obvious(candles: list[dict], s: dict) -> bool:
    """The swing is the extreme of the LOOKBACK candles before it."""
    before = candles[max(0, s["i"] - LOOKBACK):s["i"]]
    if not before:
        return False
    return s["price"] > max(c["h"] for c in before) if s["side"] == "high" else s["price"] < min(c["l"] for c in before)


def _events(candles: list[dict], swings: list[dict]) -> list[dict]:
    """Every clean sweep and breakout, ordered by (event candle, swing candle)."""
    atr = _atr(candles)
    closes = [c["c"] for c in candles]
    n, out = len(candles), []
    for p, s in enumerate(swings):
        if not _obvious(candles, s):
            continue
        up, level = s["side"] == "high", s["price"]
        k = _taken(candles, s, _known(s))  # the fractal's right side never trades beyond it
        if k is None:
            continue
        beyond = (lambda c: c > level) if up else (lambda c: c < level)  # noqa: E731
        j = next((x for x in range(k, n) if beyond(closes[x])), None)
        twin = any(0 <= x < len(swings) and _known(swings[x]) < k
                   and _equal(atr, *sorted((s, swings[x]), key=lambda o: o["i"]))
                   for x in (p - 2, p + 2))  # an equal high / low known before the level is traded
        kind = None
        if not beyond(closes[k]) and k + HOLD < n and (j is None or j > k + HOLD):
            kind, at = "sweep", k
        elif (j is not None and j <= k + HOLD and j + HOLD < n
              and all(beyond(closes[x]) for x in range(j + 1, j + HOLD + 1))):
            kind, at = "breakout", j
        if kind is None:
            continue
        c = candles[at]
        out.append({"kind": kind, "i": at, "t": c["t"], "side": s["side"], "level": level, "swing": s,
                    "level_type": ("EQH" if up else "EQL") if twin else ("swing high" if up else "swing low"),
                    "extreme": c["h"] if up else c["l"], "close": c["c"],
                    "next_closes": closes[at + 1:at + HOLD + 1]})
    out.sort(key=lambda e: (e["i"], e["swing"]["i"]))
    return out


def find_sweeps(candles: list[dict], swings: list[dict]) -> list[dict]:
    """Clean liquidity sweeps, oldest first: [{kind, i, t, side, level, swing, level_type, extreme,
    close, next_closes}]. For the SMC detectors (entry 8)."""
    return [e for e in _events(candles, swings) if e["kind"] == "sweep"]


def _event_case(candles: list[dict], swings: list[dict], kind: str) -> dict | None:
    for e in reversed([e for e in _events(candles, swings) if e["kind"] == kind]):  # most recent first
        s, end = e["swing"], e["i"] + HOLD
        if not _fits(candles, s["i"], end):
            continue
        up = s["side"] == "high"
        text = "Sweep" if kind == "sweep" else "Breakout"
        price = e["extreme"] if kind == "sweep" else e["close"]
        facts = {"kind": kind, "level": e["level"], "level_t": s["t"], "level_type": e["level_type"],
                 "candle": {"t": e["t"], ("high" if up else "low"): e["extreme"], "close": e["close"]},
                 "next_closes": e["next_closes"]}
        return {"swings": [s], "start": s["i"], "end": end, "rank": 1,
                "glossary": "liquidity_sweep" if kind == "sweep" else "breakout",
                "primitives": [{"type": "level", "price": e["level"], "label": e["level_type"]},
                               {"type": "label", "t": e["t"], "price": price, "text": text}],
                "facts": facts}
    return None


def find_sweep_vs_breakout_examples(history: dict) -> list[dict]:
    sweeps = _ranked(history, lambda c, s: _event_case(c, s, "sweep"), "sweep_vs_breakout", "liquidity_sweep")
    breakouts = _ranked(history, lambda c, s: _event_case(c, s, "breakout"), "sweep_vs_breakout", "breakout")
    return sweeps[:1] + breakouts[:1]


# ─── inducement ────────────────────────────────────────────────────────────

def _inducement_case(candles: list[dict], swings: list[dict]) -> dict | None:
    minor = find_swings(candles, MINOR, 0.0)
    closes = [c["c"] for c in candles]
    for q in range(len(swings) - 2, -1, -1):  # most recent major extreme first
        x, y = swings[q], swings[q + 1]
        if (x["kind"], y["kind"]) == ("HH", "HL"):
            up = True
        elif (x["kind"], y["kind"]) == ("LL", "LH"):
            up = False
        else:
            continue
        # the first minor pullback swing after the major extreme (a minor low in an uptrend's pullback)
        side = "low" if up else "high"
        m = next((s for s in minor if s["side"] == side and x["i"] < s["i"] < y["i"]), None)
        if m is None:
            continue
        k = _taken(candles, m)
        if k is None or k >= y["i"]:
            continue  # not taken before price reached the major swing
        # BOS: first close beyond the major extreme after the major swing, before y is traded through
        bos = None
        for b in range(y["i"] + 1, len(candles)):
            if (candles[b]["l"] < y["price"]) if up else (candles[b]["h"] > y["price"]):
                break
            if (closes[b] > x["price"]) if up else (closes[b] < x["price"]):
                bos = b
                break
        if bos is None:
            continue
        shown = swings[max(0, q - 1):q + 2]
        if not _fits(candles, shown[0]["i"], bos):
            continue
        kc = candles[k]
        taken_price = kc["l"] if up else kc["h"]
        return {"trend": "uptrend" if up else "downtrend", "swings": shown, "start": shown[0]["i"], "end": bos,
                "breaks": [("BOS", x, bos)],
                "primitives": [{"type": "level", "price": m["price"], "label": "IDM"},
                               {"type": "label", "t": m["t"], "price": m["price"], "text": "IDM"}],
                "facts": {"idm": {"t": m["t"], "price": m["price"], "taken_t": kc["t"], "taken_price": taken_price}}}
    return None


# ─── detectors ─────────────────────────────────────────────────────────────

def find_liquidity_pool_examples(history: dict) -> list[dict]:
    return _find(history, _pools_case, "liquidity_pools", "buy_side_liquidity")


def find_equal_highs_lows_examples(history: dict) -> list[dict]:
    return _find(history, _equal_case, "equal_highs_lows", "equal_highs_lows")


def find_session_examples(history: dict) -> list[dict]:
    return _find(history, _session_case, "session_highs_lows", "session_high_low", INTRADAY, pass_tf=True)


def find_inducement_examples(history: dict) -> list[dict]:
    return _find(history, _inducement_case, "inducement", "inducement")


LIQUIDITY_POOLS = lessons.register(lessons.Detector("liquidity_pools", ("buy_side_liquidity", "sell_side_liquidity"),
                                                    find_liquidity_pool_examples))
EQUAL_HIGHS_LOWS = lessons.register(lessons.Detector("equal_highs_lows", "equal_highs_lows",
                                                     find_equal_highs_lows_examples))
SESSION_HIGHS_LOWS = lessons.register(lessons.Detector("session_highs_lows", "session_high_low",
                                                       find_session_examples))
SWEEP_VS_BREAKOUT = lessons.register(lessons.Detector("sweep_vs_breakout", ("liquidity_sweep", "breakout"),
                                                      find_sweep_vs_breakout_examples))
INDUCEMENT = lessons.register(lessons.Detector("inducement", "inducement", find_inducement_examples))
