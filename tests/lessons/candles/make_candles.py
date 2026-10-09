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


if __name__ == "__main__":
    main()
