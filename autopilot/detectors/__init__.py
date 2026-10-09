"""Lesson example detectors. Importing this package registers every detector in
`autopilot.lessons.DETECTORS`.

    structure   swings (HH/HL/LH/LL), bos_choch (break of structure, change of character)
    mtf         top_down (higher-timeframe structure + the lower-timeframe structure in its last leg)
    trendlines  trendline, trendline_break (break / fakeout / retest), trendline_liquidity
    liquidity   liquidity_pools (BSL / SSL), equal_highs_lows, session_highs_lows, sweep_vs_breakout, inducement

Shared swing finder, example shape and ranking: common.py.
"""
from autopilot.detectors import structure  # noqa: F401  (registers on import)
from autopilot.detectors import mtf  # noqa: F401,E402  (registers on import)
from autopilot.detectors import trendlines  # noqa: F401,E402  (registers on import)
from autopilot.detectors import liquidity  # noqa: F401,E402  (registers on import)
