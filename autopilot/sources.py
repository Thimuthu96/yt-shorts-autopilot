"""Daily market data: news headlines, economic calendar, crypto, forex and gold prices, macro.

All sources are free and need no API key:
  - News: public RSS feeds (CoinDesk, Cointelegraph, The Daily Hodl, Federal Reserve, Google News)
  - Calendar: ForexFactory's official weekly calendar export (JSON)
  - Crypto prices: Coinbase Exchange public candles
  - Forex rates: Frankfurter (official central-bank reference rates, daily)
  - Gold: PAXG (a token backed 1:1 by physical gold) hourly candles from Kraken (Coinbase as
    backup), shifted onto spot XAU/USD with Swissquote's public quote (PAXG is within ~0.1%)
  - Macro: US Treasury daily yields (nominal + real), BLS consumer prices (CPI)

Not used (block bots and/or forbid scraping): forexfactory.com pages, Myfxbook, CME FedWatch.
FedWatch odds still reach the script through headlines that quote them.
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
        ("The Daily Hodl", "https://dailyhodl.com/feed/"),
        ("Google News", GN.format(q='(bitcoin+OR+ethereum+OR+crypto+OR+"digital+assets")')),
    ],
    "forex": [
        ("Google News", GN.format(q='("forex"+OR+"currency"+OR+"FX+market")+trading')),
        ("Google News", GN.format(q='("dollar+index"+OR+DXY+OR+"US+dollar"+OR+"euro+dollar")')),
        ("Google News", GN.format(q='("central+bank"+OR+"interest+rate"+OR+"rate+decision"+OR+"monetary+policy")')),
        ("Federal Reserve", "https://www.federalreserve.gov/feeds/press_monetary.xml"),
        ("Federal Reserve", "https://www.federalreserve.gov/feeds/speeches.xml"),
    ],
    "rates": [
        ("Google News", GN.format(q='(FedWatch+OR+"rate+cut+odds"+OR+"rate+hike+odds"+OR+"rate+cut+bets")')),
    ],
    "macro": [
        ("Google News", GN.format(q='(CPI+OR+inflation+OR+GDP+OR+"jobs+report"+OR+"nonfarm+payrolls"+OR+PMI)')),
    ],
    "gold": [
        ("Google News", GN.format(q='("gold+price"+OR+XAUUSD+OR+"spot+gold"+OR+bullion)')),
    ],
}
# Paid press releases (e.g. Chainwire posts on The Daily Hodl) are adverts, not news.
SPONSORED = re.compile(r"chainwire|press release|sponsored|partner content|\[pr\]", re.I)

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
    text = re.sub(r"\bclass=\S*", " ", text)
    text = re.sub(r"The post .{0,300}? appeared first on .{0,60}?\.", " ", text)
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
                summary = _clean(e.get("summary", ""))
                if SPONSORED.search(f"{title} {summary[:400]}"):
                    continue
                key = re.sub(r"[^a-z0-9]", "", title.lower())[:80]
                if key in seen:
                    continue
                seen.add(key)
                content = e.get("content") or []
                body = _clean(content[0].get("value", "")) if content else ""
                items.append({
                    "category": category, "source": publisher, "title": title,
                    "summary": summary[:280],
                    "body": body[:1500] if len(body) > len(summary) else "",
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


# ─── gold ──────────────────────────────────────────────────────────────────

def _gold_kraken() -> list[list]:
    """~30 days of hourly [unix, open, high, low, close] for PAXG/USD, oldest first."""
    res = _get("https://api.kraken.com/0/public/OHLC", {"pair": "PAXGUSD", "interval": 60}).json()
    if res.get("error"):
        raise RuntimeError(f"Kraken: {res['error']}")
    rows = next(v for k, v in res["result"].items() if k != "last")
    return [[int(r[0]), float(r[1]), float(r[2]), float(r[3]), float(r[4])] for r in rows]


def _gold_coinbase(days: int = 30) -> list[list]:
    end = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    rows: dict[int, list] = {}
    while days > 0:
        chunk = min(days, 12)  # Coinbase returns at most 300 candles per call
        start = end - timedelta(days=chunk)
        for r in _get("https://api.exchange.coinbase.com/products/PAXG-USD/candles",
                      {"granularity": 3600, "start": start.isoformat(), "end": end.isoformat()}).json():
            rows[int(r[0])] = [int(r[0]), float(r[3]), float(r[2]), float(r[1]), float(r[4])]  # t,l,h,o,c → t,o,h,l,c
        end, days = start, days - chunk
    return [rows[t] for t in sorted(rows)]


def _spot_xau() -> float | None:
    """Spot XAU/USD mid from Swissquote's public quote feed."""
    rows = _get("https://forex-data-feed.swissquote.com/public-quotes/bboquotes/instrument/XAU/USD").json()
    for r in rows:
        for p in r.get("spreadProfilePrices", []):
            if p.get("bid") and p.get("ask"):
                return (float(p["bid"]) + float(p["ask"])) / 2
    return None


def fetch_gold(log=print) -> dict:
    """Hourly gold prices (~30 days) on the spot XAU/USD scale, plus price and 24h / 7d change."""
    rows, source = [], ""
    for name, fn in (("Kraken", _gold_kraken), ("Coinbase", _gold_coinbase)):
        try:
            rows, source = fn(), name
            if len(rows) >= 24 * 7:
                break
        except (RuntimeError, ValueError, KeyError, StopIteration) as e:
            log(f"Gold data failed ({name}): {e}")
    if len(rows) < 24 * 7:
        log("Gold data incomplete")
        return {}
    basis = 0.0
    try:
        spot = _spot_xau()
        if spot and abs(spot / rows[-1][4] - 1) < 0.01:  # sanity: PAXG tracks spot within ~0.1%
            basis = spot - rows[-1][4]
    except (RuntimeError, ValueError, KeyError) as e:
        log(f"Spot gold quote failed: {e}; using PAXG prices as they are")
    bars = [[datetime.fromtimestamp(t, timezone.utc).isoformat(), o + basis, h + basis, lo + basis, c + basis]
            for t, o, h, lo, c in rows]
    closes = [b[4] for b in bars]
    price = closes[-1]
    week = bars[-24 * 7:]
    return {"name": "Gold", "symbol": "XAU/USD", "price": price,
            "change_24h": _pct(price, closes[-25]), "change_7d": _pct(price, closes[-24 * 7]),
            "high_24h": max(b[2] for b in bars[-24:]), "low_24h": min(b[3] for b in bars[-24:]),
            "series_times": [b[0] for b in week], "series": [b[4] for b in week], "bars": bars,
            "source": f"PAXG via {source}" + (" (spot-calibrated)" if basis else ""),
            "basis": round(basis, 2)}


# ─── macro: yields, inflation, rate expectations ───────────────────────────

TREASURY = ("https://home.treasury.gov/resource-center/data-chart-center/interest-rates/"
            "daily-treasury-rates.csv/{year}/all?type={kind}&field_tdr_date_value={year}&page&_format=csv")


def _treasury(kind: str, column: str) -> list[tuple[str, float]]:
    """[(YYYY-MM-DD, yield %)], newest first."""
    year = datetime.now(timezone.utc).year
    out = []
    for y in (year, year - 1):
        lines = _get(TREASURY.format(year=y, kind=kind)).text.strip().splitlines()
        head = [h.strip('"').upper() for h in lines[0].split(",")]
        col = head.index(column.upper())
        for line in lines[1:]:
            cells = line.split(",")
            try:
                m, d, yy = cells[0].split("/")
                out.append((f"{yy}-{m}-{d}", float(cells[col])))
            except (ValueError, IndexError):
                continue
        if len(out) >= 2:
            break
    return sorted(out, reverse=True)


def _cpi() -> dict:
    """Latest US CPI (all items + core), year-over-year, from the BLS public API (no key)."""
    res = requests.post("https://api.bls.gov/publicAPI/v1/timeseries/data/", headers=UA, timeout=30,
                        json={"seriesid": ["CUUR0000SA0", "CUUR0000SA0L1E"]}).json()
    if res.get("status") != "REQUEST_SUCCEEDED":
        raise RuntimeError(f"BLS: {res.get('message')}")
    out = {}
    for series in res["Results"]["series"]:
        rows = {}
        for r in series["data"]:
            try:  # months BLS couldn't collect are "-"
                rows[(r["year"], r["period"])] = float(r["value"])
            except ValueError:
                continue
        rows = {k: v for k, v in rows.items() if k[1].startswith("M")}
        if not rows:
            continue
        latest = max(rows)
        prev = (str(int(latest[0]) - 1), latest[1])
        if prev not in rows:
            continue
        key = "core_yoy" if series["seriesID"].endswith("L1E") else "headline_yoy"
        out[key] = round(_pct(rows[latest], rows[prev]), 1)
        month = next(r["periodName"] for r in series["data"] if (r["year"], r["period"]) == latest)
        out["month"] = f"{month} {latest[0]}"
    return out


# a percentage right next to an odds word ("hike odds drop to 18%", "a 70% chance of a cut"),
# so yields or inflation figures in the same headline aren't mistaken for odds
ODDS = re.compile(r"(fedwatch|odds|probabilit\w*|chance|likelihood)[^.%\d]{0,40}\d{1,3}(\.\d)?\s?%|"
                  r"\d{1,3}(\.\d)?\s?%\s*(chance|odds|probability|likelihood)", re.I)
RATE_WORDS = re.compile(r"\bfed\b|fomc|rate[- ](cut|hike)|interest rate", re.I)


def rate_expectations(news: list[dict], limit: int = 4) -> list[dict]:
    """Headlines that quote market odds for the Fed (e.g. CME FedWatch probabilities)."""
    out = []
    for n in news:
        text = f"{n['title']}. {n.get('summary', '')}"
        if ODDS.search(text) and RATE_WORDS.search(text):
            out.append({"source": n["source"], "title": n["title"], "published": n["published"]})
        if len(out) >= limit:
            break
    return out


def fetch_macro(log=print) -> dict:
    out = {}
    try:
        nominal = _treasury("daily_treasury_yield_curve", "10 Yr")
        two = _treasury("daily_treasury_yield_curve", "2 Yr")
        out["us10y"] = {"yield_pct": nominal[0][1], "change_bp": round((nominal[0][1] - nominal[1][1]) * 100),
                        "date": nominal[0][0]}
        out["us2y"] = {"yield_pct": two[0][1], "change_bp": round((two[0][1] - two[1][1]) * 100), "date": two[0][0]}
        real = _treasury("daily_treasury_real_yield_curve", "10 YR")
        out["us10y_real"] = {"yield_pct": real[0][1], "change_bp": round((real[0][1] - real[1][1]) * 100),
                             "date": real[0][0]}
    except (RuntimeError, ValueError, IndexError) as e:
        log(f"Treasury yields failed: {e}")
    try:
        out["us_cpi"] = _cpi()
    except (requests.RequestException, RuntimeError, ValueError, KeyError) as e:
        log(f"CPI data failed: {e}")
    return out


def usd_strength(fx: dict) -> float | None:
    """Average daily change of the dollar against the other currencies we track (+ = dollar up)."""
    vals = []
    for pair, f in fx.items():
        if pair.startswith("USD"):
            vals.append(f["change_1d"])
        elif pair.endswith("USD"):
            vals.append(-f["change_1d"])
    return sum(vals) / len(vals) if vals else None


def gather(cfg: dict, kind: str = "market", log=print) -> dict:
    """Everything the script writer needs. Raises if there is no usable price data.
    kind "market" = crypto/forex brief; "gold" = the daily gold outlook."""
    now = datetime.now(timezone.utc)
    m = cfg.get("market", {})
    feeds = DEFAULT_FEEDS if kind == "market" else \
        {k: v for k, v in DEFAULT_FEEDS.items() if k in ("gold", "rates", "macro", "forex")}
    data = {
        "kind": kind,
        "date_utc": now.strftime("%Y-%m-%d"),
        "weekday": now.strftime("%A"),
        "weekend": now.weekday() >= 5,
        "crypto": fetch_crypto(log=log) if kind == "market" else {},
        "fx": fetch_fx(log=log),
        "gold": fetch_gold(log=log),
        "calendar": fetch_calendar(hours_ahead=int(m.get("calendar_hours_ahead", 24)),
                                   impacts=tuple(m.get("calendar_impacts", ["High"])), log=log),
        "news": fetch_news(feeds, hours=int(m.get("news_hours", 30)), log=log),
        "macro": fetch_macro(log=log),
    }
    data["rate_expectations"] = rate_expectations(data["news"])
    if kind == "gold" and not data["gold"]:
        raise RuntimeError("No gold price data; skipping rather than guessing")
    if not data["crypto"] and not data["fx"] and not data["gold"]:
        raise RuntimeError("No price data from any source; skipping today rather than guessing")
    log(f"Data: {len(data['crypto'])} coins, {len(data['fx'])} FX pairs, "
        f"gold {'ok (' + data['gold']['source'] + ')' if data['gold'] else 'missing'}, "
        f"{len(data['calendar'])} calendar events, {len(data['news'])} headlines, "
        f"macro {sorted(data['macro'])}, {len(data['rate_expectations'])} rate-odds headlines")
    return data
