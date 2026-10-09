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
    for n, target in legs:
        step = (target - price) / n
        for k in range(n):
            o = price
            c = target if k == n - 1 else price + step + rnd.gauss(0, abs(step) * 0.25)
            h = max(o, c) + abs(rnd.gauss(0, abs(step) * 0.15))
            lo = min(o, c) - abs(rnd.gauss(0, abs(step) * 0.15))
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


if __name__ == "__main__":
    main()
