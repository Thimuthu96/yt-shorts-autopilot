"""Daily market data: news headlines, economic calendar, crypto and forex prices.

All sources are free and need no API key:
  - News: public RSS feeds (the same ones the World Monitor finance dashboard uses)
  - Calendar: ForexFactory's official weekly calendar export (JSON)
  - Crypto prices: Coinbase Exchange public candles
  - Forex rates: Frankfurter (official central-bank reference rates, daily)
"""
import html
import re
import time
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

import feedparser
import requests

UA = {"User-Agent": "Mozilla/5.0 (compatible; daily-market-brief/1.0)"}

GN = "https://news.google.com/rss/search?q={q}+when:1d&hl=en-US&gl=US&ceid=US:en"
DEFAULT_FEEDS = {
    "crypto": [
        ("CoinDesk", "https://www.coindesk.com/arc/outboundfeeds/rss/"),
        ("Cointelegraph", "https://cointelegraph.com/rss"),
        ("Google News", GN.format(q='(bitcoin+OR+ethereum+OR+crypto+OR+"digital+assets")')),
    ],
    "forex": [
        ("Google News", GN.format(q='("forex"+OR+"currency"+OR+"FX+market")+trading')),
        ("Google News", GN.format(q='("dollar+index"+OR+DXY+OR+"US+dollar"+OR+"euro+dollar")')),
        ("Google News", GN.format(q='("central+bank"+OR+"interest+rate"+OR+"rate+decision"+OR+"monetary+policy")')),
        ("Federal Reserve", "https://www.federalreserve.gov/feeds/press_all.xml"),
    ],
    "macro": [
        ("Google News", GN.format(q='(CPI+OR+inflation+OR+GDP+OR+"jobs+report"+OR+"nonfarm+payrolls"+OR+PMI)')),
    ],
}

CRYPTO = [("BTC", "Bitcoin", "BTC-USD"), ("ETH", "Ethereum", "ETH-USD"),
          ("SOL", "Solana", "SOL-USD"), ("XRP", "XRP", "XRP-USD")]
# pair, display, Frankfurter quote currency, True if the pair is quoted as 1/rate (EUR/USD = 1 / USD→EUR)
FX = [("EURUSD", "EUR/USD", "EUR", True), ("GBPUSD", "GBP/USD", "GBP", True),
      ("USDJPY", "USD/JPY", "JPY", False), ("AUDUSD", "AUD/USD", "AUD", True),
      ("USDCAD", "USD/CAD", "CAD", False), ("USDCHF", "USD/CHF", "CHF", False)]


def _get(url: str, params: dict | None = None, timeout: int = 30) -> requests.Response:
    last = None
    for attempt in range(3):
        try:
            r = requests.get(url, params=params, headers=UA, timeout=timeout)
            if r.status_code == 429:
                time.sleep(10 * (attempt + 1))
                continue
            r.raise_for_status()
            return r
        except requests.RequestException as e:
            last = e
            time.sleep(3)
    raise RuntimeError(f"{url}: {last or 'rate limited'}")


# ─── news ──────────────────────────────────────────────────────────────────

def _clean(text: str) -> str:
    text = html.unescape(re.sub(r"<[^>]+>", " ", text or ""))
    return re.sub(r"\s+", " ", text).strip()


def _entry_time(e) -> datetime | None:
    for key in ("published_parsed", "updated_parsed"):
        if e.get(key):
            return datetime(*e[key][:6], tzinfo=timezone.utc)
    for key in ("published", "updated"):
        if e.get(key):
            try:
                return parsedate_to_datetime(e[key]).astimezone(timezone.utc)
            except (TypeError, ValueError):
                pass
    return None


def fetch_news(feeds: dict | None = None, hours: int = 30, per_feed: int = 12, log=print) -> list[dict]:
    feeds = feeds or DEFAULT_FEEDS
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    seen, items = set(), []
    for category, entries in feeds.items():
        for source, url in entries:
            try:
                parsed = feedparser.parse(_get(url).content)
            except RuntimeError as e:
                log(f"News feed failed ({source}): {e}")
                continue
            for e in parsed.entries[:per_feed]:
                title = _clean(e.get("title", ""))
                publisher = source
                src = e.get("source")
                if source == "Google News":
                    if src and src.get("title"):
                        publisher = src["title"]
                    # Google News titles end with " - Publisher"
                    if " - " in title:
                        title, tail = title.rsplit(" - ", 1)
                        publisher = publisher if publisher != "Google News" else tail
                when = _entry_time(e)
                if not title or (when and when < cutoff):
                    continue
                key = re.sub(r"[^a-z0-9]", "", title.lower())[:80]
                if key in seen:
                    continue
                seen.add(key)
                items.append({
                    "category": category, "source": publisher, "title": title,
                    "summary": _clean(e.get("summary", ""))[:280],
                    "published": when.isoformat() if when else None,
                    "link": e.get("link", ""),
                })
    items.sort(key=lambda x: x["published"] or "", reverse=True)
    return items


# ─── economic calendar ─────────────────────────────────────────────────────

FF_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"


def fetch_calendar(hours_ahead: int = 24, impacts=("High",), log=print) -> list[dict]:
    """High-impact events from now until `hours_ahead` hours later (times in UTC)."""
    try:
        events = _get(FF_URL).json()
    except (RuntimeError, ValueError) as e:
        log(f"Calendar failed: {e}")
        return []
    now = datetime.now(timezone.utc)
    start, end = now - timedelta(hours=2), now + timedelta(hours=hours_ahead)
    out = []
    for ev in events:
        try:
            when = datetime.fromisoformat(ev["date"]).astimezone(timezone.utc)
        except (KeyError, ValueError):
            continue
        if ev.get("impact") in impacts and start <= when <= end:
            out.append({"time_utc": when.strftime("%H:%M"), "datetime": when.isoformat(),
                        "currency": ev.get("country", ""), "event": ev.get("title", ""),
                        "forecast": ev.get("forecast", "") or "", "previous": ev.get("previous", "") or "",
                        "impact": ev.get("impact", "")})
    out.sort(key=lambda e: e["datetime"])
    return out


# ─── prices ────────────────────────────────────────────────────────────────

def _pct(new: float, old: float) -> float:
    return (new / old - 1) * 100 if old else 0.0


def fetch_crypto(log=print) -> dict:
    """7 days of hourly closes per coin, plus price and 24h / 7d change."""
    out = {}
    end = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    start = end - timedelta(hours=24 * 7)
    for sym, name, product in CRYPTO:
        try:
            rows = _get(f"https://api.exchange.coinbase.com/products/{product}/candles",
                        {"granularity": 3600, "start": start.isoformat(), "end": end.isoformat()}).json()
        except (RuntimeError, ValueError) as e:
            log(f"Price data failed for {sym}: {e}")
            continue
        if not isinstance(rows, list) or len(rows) < 30:
            log(f"Price data for {sym} incomplete")
            continue
        rows.sort(key=lambda r: r[0])  # Coinbase returns newest first
        times = [datetime.fromtimestamp(r[0], timezone.utc).isoformat() for r in rows]
        closes = [float(r[4]) for r in rows]
        price = closes[-1]
        day_ago = closes[-25] if len(closes) >= 25 else closes[0]
        out[sym] = {"name": name, "price": price, "change_24h": _pct(price, day_ago),
                    "change_7d": _pct(price, closes[0]), "series_times": times, "series": closes,
                    "high_24h": max(closes[-24:]), "low_24h": min(closes[-24:])}
    return out


def fetch_fx(days: int = 45, log=print) -> dict:
    """Daily reference rates (central-bank fixings) with day-over-day change."""
    start = (datetime.now(timezone.utc) - timedelta(days=days)).date().isoformat()
    quotes = ",".join(q for _, _, q, _ in FX)
    try:
        rows = _get("https://api.frankfurter.dev/v2/rates",
                    {"base": "USD", "quotes": quotes, "from": start}).json()
    except (RuntimeError, ValueError) as e:
        log(f"Forex data failed: {e}")
        return {}
    by_quote: dict[str, list] = {}
    for r in rows if isinstance(rows, list) else []:
        by_quote.setdefault(str(r.get("quote", "")).upper(), []).append((r["date"], float(r["rate"])))
    out = {}
    for pair, display, q, inverse in FX:
        series = sorted(by_quote.get(q, []))
        if len(series) < 5:
            continue
        dates = [d for d, _ in series]
        vals = [(1 / v if inverse else v) for _, v in series]
        out[pair] = {"name": display, "price": vals[-1], "as_of": dates[-1],
                     "change_1d": _pct(vals[-1], vals[-2]), "change_30d": _pct(vals[-1], vals[max(0, len(vals) - 22)]),
                     "series_times": dates[-30:], "series": vals[-30:]}
    return out


def gather(cfg: dict, log=print) -> dict:
    """Everything the script writer needs. Raises if there is no usable price data."""
    now = datetime.now(timezone.utc)
    m = cfg.get("market", {})
    data = {
        "date_utc": now.strftime("%Y-%m-%d"),
        "weekday": now.strftime("%A"),
        "weekend": now.weekday() >= 5,
        "crypto": fetch_crypto(log=log),
        "fx": fetch_fx(log=log),
        "calendar": fetch_calendar(hours_ahead=int(m.get("calendar_hours_ahead", 24)),
                                   impacts=tuple(m.get("calendar_impacts", ["High"])), log=log),
        "news": fetch_news(hours=int(m.get("news_hours", 30)), log=log),
    }
    if not data["crypto"] and not data["fx"]:
        raise RuntimeError("No price data from any source; skipping today rather than guessing")
    log(f"Data: {len(data['crypto'])} coins, {len(data['fx'])} FX pairs, "
        f"{len(data['calendar'])} calendar events, {len(data['news'])} headlines")
    return data
