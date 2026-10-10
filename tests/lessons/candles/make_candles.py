"""Writes the lesson detector candle fixtures in this folder (seeded, so re-running gives the same
files). Prices walk between hand-picked turning points with small seeded noise.

    python tests/lessons/candles/make_candles.py

    uptrend.json              HH/HL staircase, no reversal close            -> swings, not bos_choch
    downtrend_bos_choch.json  LH/LL downtrend, a BOS close, then a CHoCH    -> swings and bos_choch
    choppy.json               range whose highs and lows alternate up/down  -> neither
    downtrend_hl_choch.json   LH/LL downtrend, a HL that fails to make a LL, then the CHoCH close
                              -> bos_choch with that one disagreeing swing last
    range_after_trend.json    LH/LL downtrend, then a range (HL, LH, LL) before price finally closes
                              above the run's last LH -> no bos_choch (structure moved on)
    top_down_1h.json          long 1H series with nested structure: a HH/HL staircase whose up legs
                              zigzag on 1H (up 6 candles, down 3), so aggregated to 4H it is an
                              uptrend and inside its last up leg the 1H makes its own HH/HL
                              -> top_down (4H -> 1H; read as 4H candles and aggregated to 1D, 1D -> 4H)

Tracks 1-2 (trendlines, liquidity); a leg may carry a third value, the wick of its last candle:
    trendline_retest.json     rising support through 4 swing lows on one line, a close below it, a drop
                              away, a rally back to the line that closes below it -> trendline,
                              trendline_break (retest)
    trendline_fakeout.json    falling resistance through 4 swing highs, a close above it, back below
                              within 3 candles -> trendline_break (fakeout)
    trendline_liquidity.json  rising support through 4 swing lows, then a wick 1.5 below the line that
                              closes back above it, trend resumes -> trendline_liquidity
    liquidity_pools.json      HH/HL uptrend ending in a pullback: BSL above the last HH, SSL below the
                              two latest HLs -> liquidity_pools
    equal_highs.json          two swing highs 0.05 apart, 16 candles apart, a low between -> equal_highs_lows
    sessions_1h.json          two 00:00 UTC days: day 1 Asia ranges, London trades above its high and
                              New York below its low; day 2 Asia trends (not a range)
                              -> session_highs_lows on day 1
    sweep_breakout.json       a wick above the obvious high that closes back below (sweep), then a rally
                              that closes above the new high and holds 3 closes (breakout) -> sweep_vs_breakout
    inducement.json           HH/HL uptrend; after the HH the first minor pullback low is taken on the way
                              to the HL, then a close above the HH (BOS) -> inducement

Track 3 (SMC):
    fvg.json                  HH/HL uptrend; one big candle breaks the last HH (BOS) leaving a gap, a later
                              pullback trades back to its far edge -> fvg (bullish, filled)
    order_block.json          LH/LL downtrend; the leg from the last LH closes below the LL (BOS), then a
                              rally back into the up-close candle at that LH -> order_block (bearish, revisited)
    breaker.json              LH/LL downtrend whose last leg makes a new low (BOS), then a rally that closes
                              above the block, holds above it, comes back into it -> mitigation_breaker (breaker)
    mitigation.json           the same, but a HL (failed to make a new low) before the rally -> (mitigation)
    premium_discount.json     HH/HL uptrend, then a pullback that closes below 50% of the last HL -> HH
                              range, still above its low -> premium_discount (discount)
    sweep_choch_model.json    LH/LL downtrend; a wick below the last LL closing back above (sweep), a rally
                              closing above the last LH (CHoCH), a pullback into its OB / FVG -> sweep_choch_model
    choch_before_sweep.json   LH/LL downtrend; the LL is a close break, then the CHoCH, then a sweep of
                              that LL -> no sweep_choch_model
"""
import json
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
START = datetime(2026, 9, 1, tzinfo=timezone.utc)

# (start price, [(candles in the leg, turning point price), ...])
SERIES = {
    "uptrend": (100.0, [(8, 92), (10, 108), (8, 101), (10, 116), (8, 109), (10, 124), (8, 117), (10, 132),
                        (8, 125), (10, 140), (6, 136)]),
    "downtrend_bos_choch": (200.0, [(8, 208), (10, 190), (8, 197), (10, 184), (8, 191), (10, 177), (8, 184),
                                    (10, 170), (8, 177), (10, 163), (12, 186), (6, 181)]),
    "choppy": (105.0, [(8, 100), (8, 110), (8, 101), (8, 108), (8, 99), (8, 111), (8, 102), (8, 107),
                       (8, 98), (8, 109), (8, 103), (8, 106), (6, 104)]),
    "downtrend_hl_choch": (200.0, [(8, 208), (10, 190), (8, 197), (10, 184), (8, 191), (10, 177), (8, 184),
                                   (10, 170), (8, 177), (10, 163), (8, 175), (8, 168), (12, 186), (6, 181)]),
    "range_after_trend": (200.0, [(8, 208), (10, 190), (8, 197), (10, 184), (8, 191), (10, 177), (8, 184),
                                  (10, 170), (8, 177), (10, 163), (8, 175), (8, 168), (8, 174), (8, 166),
                                  (12, 186), (6, 181)]),
}


# (start price, [(candles in a straight down leg, higher-timeframe turning point), ...]); up legs zigzag
NESTED = {
    "top_down_1h": (100.0, [(16, 92), (0, 110), (20, 102), (0, 120), (20, 112), (0, 130), (20, 122), (0, 140),
                            (20, 132), (0, 150), (20, 142)]),
}
# Tracks 1-2 fixtures: (start price, [(candles, turning point[, wick of the leg's last candle]), ...])
TRACK12 = {
    "trendline_retest": (100.0, [(6, 94, 93.5), (10, 106), (6, 100, 99.5), (10, 112), (6, 106, 105.5), (10, 118),
                                 (6, 112, 111.5), (10, 124), (6, 114), (3, 110), (4, 119.6, 120.0), (8, 104)]),
    "trendline_fakeout": (130.0, [(6, 136, 136.5), (10, 124), (6, 130, 130.5), (10, 118), (6, 124, 124.5),
                                  (10, 112), (6, 118, 118.5), (10, 106), (6, 114.5), (2, 109), (8, 100)]),
    "trendline_liquidity": (100.0, [(6, 94, 93.5), (10, 106), (6, 100, 99.5), (10, 112), (6, 106, 105.5),
                                    (10, 118), (6, 112, 111.5), (10, 124), (6, 118, 116.0), (10, 130), (4, 127)]),
    "liquidity_pools": (100.0, [(8, 92), (10, 108), (8, 101), (10, 116), (8, 109), (10, 124), (8, 117), (10, 132),
                                (6, 126)]),
    "equal_highs": (100.0, [(8, 96), (8, 108.6, 110.0), (8, 102), (8, 108.7, 110.05), (10, 96), (4, 99)]),
    "sessions_1h": (100.0, [(2, 101), (2, 99.5), (2, 100.3), (1, 100.0), (5, 104), (4, 101), (4, 98.5), (4, 100),
                            (6, 106), (1, 106.5), (5, 109), (8, 107), (4, 108)]),
    "sweep_breakout": (100.0, [(10, 110), (8, 104), (7, 109.5), (1, 109.0, 111.0), (8, 102), (10, 115), (4, 113.5),
                               (8, 106)]),
    "inducement": (100.0, [(8, 92), (10, 108), (8, 100), (10, 116), (3, 112, 111.6), (1, 113.8, 114.6), (5, 106), (12, 120),
                           (4, 118)]),
}

# Track 3 fixtures (SMC), same leg format as TRACK12
TRACK3 = {
    "fvg": (100.0, [(8, 92), (10, 108), (8, 101), (10, 116), (8, 109), (4, 112), (1, 119), (5, 124), (8, 111),
                    (6, 118)]),
    "order_block": (200.0, [(8, 208), (10, 190), (8, 197), (10, 184), (8, 191), (10, 177), (6, 183), (8, 168),
                            (8, 182.8), (8, 174)]),
    "breaker": (200.0, [(8, 208), (10, 190), (8, 197), (10, 184), (8, 191), (10, 177), (8, 184), (10, 170), (8, 177),
                        (10, 163), (12, 186), (6, 176.8), (8, 188)]),
    "mitigation": (200.0, [(8, 208), (10, 190), (8, 197), (10, 184), (8, 191), (10, 177), (8, 184), (10, 170),
                           (8, 177), (10, 163), (8, 175), (8, 168), (12, 186), (6, 176.5), (8, 185)]),
    "premium_discount": (100.0, [(8, 92), (10, 108), (8, 101), (10, 116), (8, 109), (10, 124), (8, 117), (10, 132),
                                 (8, 122)]),
    "sweep_choch_model": (200.0, [(8, 208), (10, 190), (8, 197), (10, 184), (8, 191), (10, 177), (8, 184), (10, 170),
                                  (8, 177), (10, 164), (6, 170.5), (5, 165, 162.5), (3, 168), (4, 180), (6, 172),
                                  (6, 178)]),
    "choch_before_sweep": (200.0, [(8, 208), (10, 190), (8, 197), (10, 184), (8, 191), (10, 177), (8, 184), (10, 170),
                                   (8, 177), (10, 163), (12, 180), (8, 170), (2, 166, 162.0), (8, 175)]),
}

UP_WAVE, DOWN_WAVE = (6, 1.0), (3, 0.8)  # 1H waves inside an up leg: (candles, price step per candle)


def nested_legs(start: float, turns: list) -> list:
    """Higher-timeframe turning points -> 1H legs: up legs as waves (up 6 x 1.0, down 3 x 0.8, net up),
    down legs straight."""
    legs, price = [], start
    (n1, s1), (n2, s2) = UP_WAVE, DOWN_WAVE
    for n, target in turns:
        if target > price:
            while target - price > n1 * s1:
                price += n1 * s1
                legs.append((n1, round(price, 2)))
                price -= n2 * s2
                legs.append((n2, round(price, 2)))
            legs.append((max(2, round((target - price) / s1)), target))
        else:
            legs.append((n, target))
        price = target
    return legs


def make(start: float, legs: list, seed: int) -> list[dict]:
    rnd = random.Random(seed)
    out, price, t = [], start, START
    for n, target, *wick in legs:
        step = (target - price) / n
        for k in range(n):
            o = price
            c = target if k == n - 1 else price + step + rnd.gauss(0, abs(step) * 0.25)
            h = max(o, c) + abs(rnd.gauss(0, abs(step) * 0.15))
            lo = min(o, c) - abs(rnd.gauss(0, abs(step) * 0.15))
            if wick and k == n - 1:  # the leg's last candle wicks out to a set price
                h, lo = max(h, wick[0]), min(lo, wick[0])
            out.append({"t": t.isoformat(), "o": round(o, 2), "h": round(h, 2), "l": round(lo, 2), "c": round(c, 2)})
            price, t = round(c, 2), t + timedelta(hours=1)
    return out


def main():
    for seed, (name, (start, legs)) in enumerate(SERIES.items(), 1):
        candles = make(start, legs, seed)
        (HERE / f"{name}.json").write_text(json.dumps(candles, indent=1) + "\n", encoding="utf-8")
        print(f"{name}.json: {len(candles)} candles")
    for seed, (name, (start, turns)) in enumerate(NESTED.items(), len(SERIES) + 1):
        candles = make(start, nested_legs(start, turns), seed)
        (HERE / f"{name}.json").write_text(json.dumps(candles, indent=1) + "\n", encoding="utf-8")
        print(f"{name}.json: {len(candles)} candles")
    for seed, (name, (start, legs)) in enumerate(TRACK12.items(), len(SERIES) + len(NESTED) + 1):
        candles = make(start, legs, seed)
        (HERE / f"{name}.json").write_text(json.dumps(candles, indent=1) + "\n", encoding="utf-8")
        print(f"{name}.json: {len(candles)} candles")
    for seed, (name, (start, legs)) in enumerate(TRACK3.items(), len(SERIES) + len(NESTED) + len(TRACK12) + 1):
        candles = make(start, legs, seed)
        (HERE / f"{name}.json").write_text(json.dumps(candles, indent=1) + "\n", encoding="utf-8")
        print(f"{name}.json: {len(candles)} candles")


if __name__ == "__main__":
    main()
