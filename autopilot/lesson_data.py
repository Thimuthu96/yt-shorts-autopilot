"""Multi-timeframe price history for the lesson detectors (free source, no keys).

    fetch_history(log) -> {asset: {timeframe: [{t, o, h, l, c}, ...]}}   ISO UTC, oldest first

    BTC/USD, ETH/USD  Coinbase Exchange candles: 1H paged over 60 days, 4H built from the 1H candles
                      (00/04/08/12/16/20 UTC buckets; Coinbase has no 4H granularity), 1D over 365 days

Crypto only since 2026-10-13 (CAP-3): lessons no longer fetch gold or forex history; the daily
editions' gold / FX code in sources.py and gold.py is separate and unchanged.

Only completed candles are kept: a candle whose period hasn't closed at `now` (start + timeframe
length > now) is dropped, aggregated 4H included, so no fact quotes a close that can still change.

A failed series is skipped with a log line, never raised. The daily editions' code is only imported
from (sources._get), never changed.

    python -m autopilot.lesson_data    live fetch + every registered detector (manual smoke check)
"""
from datetime import datetime, timedelta, timezone

from autopilot import sources

ASSETS = ("BTC/USD", "ETH/USD")  # the only lesson assets; also the detectors' tie-break order
TIMEFRAMES = ("1D", "4H", "1H")  # detectors' tie-break order
SOURCES = {
    "BTC/USD": "Coinbase",
    "ETH/USD": "Coinbase",
}
COINBASE = {"BTC/USD": "BTC-USD", "ETH/USD": "ETH-USD"}
HOUR, DAY = 3600, 86400
TF_SECONDS = {"1H": HOUR, "4H": 4 * HOUR, "1D": DAY}
COINBASE_MAX = 300  # candles per call


def _iso(ts: int) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).isoformat()


def _completed(rows: dict[int, tuple], tf: str, now: datetime) -> dict[int, tuple]:
    """Only candles whose period has closed at `now` (the forming candle is dropped)."""
    limit = now.timestamp() - TF_SECONDS[tf]
    return {t: v for t, v in rows.items() if t <= limit}


def _candles(rows: dict[int, tuple]) -> list[dict]:
    """{unix: (o, h, l, c)} -> candles, oldest first (dict keys already de-duplicate)."""
    return [{"t": _iso(t), "o": o, "h": h, "l": lo, "c": c} for t, (o, h, lo, c) in sorted(rows.items())]


# ─── Coinbase (BTC, ETH) ───────────────────────────────────────────────────

def _coinbase(product: str, granularity: int, days: int, now: datetime) -> dict[int, tuple]:
    step = timedelta(seconds=granularity)
    floor = int(now.timestamp()) // granularity * granularity  # start of the forming candle
    end = datetime.fromtimestamp(floor, timezone.utc)
    stop = end - timedelta(days=days)
    chunk = step * (COINBASE_MAX - 10)  # stay under the 300-candle cap
    rows: dict[int, tuple] = {}
    while end > stop:
        start = max(stop, end - chunk)
        page = sources._get(f"https://api.exchange.coinbase.com/products/{product}/candles",
                            {"granularity": granularity, "start": start.isoformat(), "end": end.isoformat()}).json()
        if not isinstance(page, list):
            raise ValueError(f"unexpected Coinbase answer: {str(page)[:120]}")
        for r in page:  # [t, low, high, open, close, volume], newest first
            rows[int(r[0])] = (float(r[3]), float(r[2]), float(r[1]), float(r[4]))
        end = start
    return rows


def _aggregate(rows: dict[int, tuple], seconds: int) -> dict[int, tuple]:
    """Group candles into UTC-aligned buckets of `seconds`; a leading partial bucket is dropped."""
    out: dict[int, list] = {}
    for t in sorted(rows):
        o, h, lo, c = rows[t]
        k = t - t % seconds
        if k not in out:
            out[k] = [o, h, lo, c]
        else:
            b = out[k]
            b[1], b[2], b[3] = max(b[1], h), min(b[2], lo), c
    if rows:
        first = min(rows)
        if first % seconds:
            out.pop(first - first % seconds, None)
    return {k: tuple(v) for k, v in out.items()}


# ─── history ───────────────────────────────────────────────────────────────

def fetch_history(log=print, now: datetime | None = None) -> dict[str, dict[str, list[dict]]]:
    """{asset: {timeframe: candles}}; a failed asset/timeframe is logged and left out."""
    now = now or datetime.now(timezone.utc)
    raw: dict[str, dict[str, dict[int, tuple]]] = {}

    def attempt(asset: str, tf: str, fn) -> None:
        """Fetch one series and keep its completed candles; a failure is logged, never raised."""
        try:
            rows = fn()
        except Exception as e:  # noqa: BLE001 — a source failing must never stop the run
            log(f"Lesson data failed ({asset} {tf}, {SOURCES[asset]}): {type(e).__name__}: {e}")
            return
        done = _completed(rows or {}, tf, now)
        if not done:
            log(f"Lesson data empty ({asset} {tf}, {SOURCES[asset]}): no completed candles; skipped")
            return
        raw.setdefault(asset, {})[tf] = done

    for asset, product in COINBASE.items():
        attempt(asset, "1H", lambda: _coinbase(product, HOUR, 60, now))
        if "1H" in raw.get(asset, {}):
            attempt(asset, "4H", lambda: _aggregate(raw[asset]["1H"], 4 * HOUR))
        else:
            log(f"Lesson data skipped ({asset} 4H, {SOURCES[asset]}): built from 1H, which failed")
        attempt(asset, "1D", lambda: _coinbase(product, DAY, 365, now))

    history = {}
    for asset in ASSETS:
        if asset not in raw:
            continue
        history[asset] = {}
        for tf in TIMEFRAMES:
            if tf in raw[asset]:
                history[asset][tf] = _candles(raw[asset][tf])
                log(f"Lesson data: {asset} {tf} {len(history[asset][tf])} candles")
    return history


def main():
    from autopilot import lessons, detectors  # noqa: F401  (registers the detectors)

    history = fetch_history()
    if not history:
        print("No lesson price history loaded")
        return
    for name in sorted(lessons.DETECTORS):
        found = lessons.DETECTORS[name].find(history)
        print(f"\n{name}: {len(found)} example(s)")
        for ex in found:
            problems = lessons.validate_example(ex)
            print(f"  {lessons.example_label(ex)} · {ex['timeframe']} · {len(ex['candles'])} candles · "
                  f"{len([p for p in ex['primitives'] if p['type'] == 'swing'])} swings"
                  + (f" · INVALID: {problems}" if problems else ""))
            print(f"    facts: {ex['facts']}")


if __name__ == "__main__":
    main()
