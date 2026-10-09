"""Lesson example detectors. Importing this package registers every detector in
`autopilot.lessons.DETECTORS`.

    structure   swings (HH/HL/LH/LL), bos_choch (break of structure, change of character)
    mtf         top_down (higher-timeframe structure + the lower-timeframe structure in its last leg)
"""
from autopilot.detectors import structure  # noqa: F401  (registers on import)
from autopilot.detectors import mtf  # noqa: F401,E402  (registers on import)
