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
               The walk itself is public as `structure_events` (every BOS and CHoCH it finds), used by
               the Track 3 SMC detectors (smc.py).

Per (asset, timeframe) the most recent clean case is kept; cases rank by (swings desc, end time
desc, asset order, timeframe order 1D/4H/1H). Example 1 is the top case, example 2 the best
remaining one on another asset, else on another timeframe.

The swing finder, swing confirmation, chart window, example builder and ranking live in common.py
(shared with every detector module).
"""
from autopilot import lessons
from autopilot.detectors.common import _find, _fits, _runs, known

MIN_SWINGS = 4  # = 2 agreeing swing pairs


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


def structure_events(candles: list[dict], swings: list[dict]) -> list[dict]:
    """The BOS / CHoCH walk behind `bos_choch`, as events in run order (each run's BOS events in time
    order, then its CHoCH if it has one): [{kind: "BOS" | "CHoCH", i (the closing candle), pos (index
    of the broken swing in `swings`), swing, trend (the run's trend)}]. A CHoCH also carries bos_pos /
    bos_i (the last BOS before it), run_start, run_end (last run swing formed before the CHoCH) and
    last (last case swing: run_end, or the one disagreeing swing right after the run).
    Also used by the SMC detectors (smc.py)."""
    closes = [c["c"] for c in candles]
    events = []
    for trend, a, b in _runs(swings):
        if b - a + 1 < MIN_SWINGS:
            continue
        up = trend == "uptrend"
        with_side = "high" if up else "low"
        beyond = (lambda c, p: c > p) if up else (lambda c, p: c < p)  # noqa: E731  (in the trend's direction)
        behind = (lambda c, p: c < p) if up else (lambda c, p: c > p)  # noqa: E731  (against it)
        # a swing is only known once its fractal is confirmed, at candle i + RIGHT
        outside = known(swings[b + 2]) if b + 2 < len(swings) else len(candles)  # 2nd swing after the run
        last_with = last_against = bos = None
        broken = set()
        p = a  # next run swing not yet confirmed
        for m in range(swings[a]["i"] + 1, len(candles)):
            if m >= outside:
                break  # the structure moved on without a CHoCH of this run
            while p <= b and known(swings[p]) <= m:
                if swings[p]["side"] == with_side:
                    last_with = p
                else:
                    last_against = p
                p += 1
            if (bos is not None and last_against is not None and p - a >= MIN_SWINGS
                    and behind(closes[m], swings[last_against]["price"])):
                run_end = p - 1  # the run's swings formed before the CHoCH
                last = b + 1 if p > b and b + 1 < len(swings) and known(swings[b + 1]) <= m else run_end
                events.append({"kind": "CHoCH", "i": m, "pos": last_against, "swing": swings[last_against],
                               "trend": trend, "bos_pos": bos[0], "bos_i": bos[1], "run_start": a,
                               "run_end": run_end, "last": last})
                break
            if last_with is not None and last_with not in broken and beyond(closes[m], swings[last_with]["price"]):
                broken.add(last_with)
                bos = (last_with, m)  # the latest BOS so far
                events.append({"kind": "BOS", "i": m, "pos": last_with, "swing": swings[last_with], "trend": trend})
    return events


def _bos_choch_case(candles: list[dict], swings: list[dict]) -> dict | None:
    """The most recent trend -> BOS -> CHoCH sequence that fits on one chart."""
    found = [(e["i"], e["bos_i"], e["run_start"], e["run_end"], e["last"], e["bos_pos"], e["pos"], e["trend"])
             for e in structure_events(candles, swings) if e["kind"] == "CHoCH"]
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

def find_swing_examples(history: dict) -> list[dict]:
    return _find(history, _swing_case, "swings", "market_structure")


def find_bos_choch_examples(history: dict) -> list[dict]:
    return _find(history, _bos_choch_case, "bos_choch", "change_of_character")


SWINGS = lessons.register(lessons.Detector("swings", ("swing_point", "market_structure"), find_swing_examples))
BOS_CHOCH = lessons.register(lessons.Detector("bos_choch", ("break_of_structure", "change_of_character"),
                                              find_bos_choch_examples))
