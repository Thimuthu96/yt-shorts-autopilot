"""Search metadata built from the data, so every upload is findable for what it's actually about.

- Title: the primary keyword ("XRP price today", "Gold price today") must sit in the first ~45
  characters (what search and the Shorts feed show); otherwise a data-built title is used.
- Description: keyword-first summary, then key numbers / key levels, stories, what to watch,
  the posting schedule, data credits, disclaimer, hashtags.
- Hashtags: the first three show above the title in the Shorts player, so they're the lead
  asset's own tags, its market, and a related asset; #Shorts goes last.
- Tags: keyword seeds for the lead asset first, then the writer's tags (low weight, but free).
"""
from datetime import datetime

NAMES = {"BTC": "Bitcoin", "ETH": "Ethereum", "SOL": "Solana", "XRP": "XRP", "XAU": "Gold",
         "EURUSD": "EUR/USD", "GBPUSD": "GBP/USD", "USDJPY": "USD/JPY", "AUDUSD": "AUD/USD",
         "USDCAD": "USD/CAD", "USDCHF": "USD/CHF", "USD": "US Dollar"}
HASHTAGS = {"BTC": ["#Bitcoin", "#BTC"], "ETH": ["#Ethereum", "#ETH"], "SOL": ["#Solana"], "XRP": ["#XRP"],
            "XAU": ["#Gold", "#XAUUSD"], "EURUSD": ["#EURUSD"], "GBPUSD": ["#GBPUSD"], "USDJPY": ["#USDJPY"],
            "AUDUSD": ["#AUDUSD"], "USDCAD": ["#USDCAD"], "USDCHF": ["#USDCHF"], "USD": ["#Fed", "#USD"]}
MARKET_TAG = {"crypto": "#CryptoNews", "fx": "#Forex", "gold": "#GoldPrice", "theme": "#Forex"}


def _kind(asset: str, data: dict) -> str:
    if asset in data.get("crypto", {}):
        return "crypto"
    if asset in data.get("fx", {}):
        return "fx"
    return "gold" if asset == "XAU" else "theme"


def primary(data: dict) -> tuple[str, str] | None:
    """(name that must appear in the title, primary search phrase)"""
    lead = (data.get("focus") or {}).get("lead")
    if not lead:
        return None
    name = NAMES.get(lead, lead)
    if lead == "USD":
        return "Dollar", "US dollar news today"
    return name, f"{name} {'price' if _kind(lead, data) in ('crypto', 'gold') else 'forecast'} today"


def _date(data: dict) -> str:
    dt = datetime.fromisoformat(data["date_utc"])
    return f"{dt:%b} {dt.day}"


def _pct(v: float) -> str:
    return f"{'+' if v >= 0 else '−'}{abs(v):.1f}%"


def _change(asset: str, data: dict) -> float | None:
    if asset in data.get("crypto", {}):
        return data["crypto"][asset]["change_24h"]
    if asset in data.get("fx", {}):
        return data["fx"][asset]["change_1d"]
    if asset == "XAU" and data.get("gold"):
        return data["gold"]["change_24h"]
    return None


def fallback_title(data: dict, edition: str) -> str:
    lead = data["focus"]["lead"]
    kind = _kind(lead, data)
    head = {"crypto": "Price Today", "gold": "Price Today", "fx": "Forecast Today"}.get(kind, "News Today")
    chg = _change(lead, data)
    move = f"{'Up' if chg >= 0 else 'Down'} {abs(chg):.1f}%" if chg is not None else "What's Moving Markets"
    return f"{NAMES.get(lead, lead)} {head}: {move} | {edition}, {_date(data)}".replace(" | ,", " |")


def title(pkg_title: str, data: dict, edition: str) -> str:
    t = " ".join((pkg_title or "").split())
    p = primary(data)
    if not p:
        return t[:95]
    if not t or len(t) > 95 or p[0].lower() not in t[:45].lower():
        return fallback_title(data, edition)
    return t


def hashtags(data: dict, llm: list[str]) -> list[str]:
    out: list[str] = []
    f = data.get("focus") or {}
    assets = f.get("assets") or []
    lead = f.get("lead")
    if lead:
        out += HASHTAGS.get(lead, [])[:1]
        out.append(MARKET_TAG[_kind(lead, data)])
    for a in assets:
        if a != lead:
            out += HASHTAGS.get(a, [])[:1]
    for h in llm or []:
        h = h if h.startswith("#") else f"#{h}"
        out.append("".join(h.split()))
    seen, final = set(), []
    for h in out:
        if len(h) > 1 and h.lower() not in seen and h.lower() != "#shorts":
            seen.add(h.lower())
            final.append(h)
    return final[:4] + ["#Shorts"]


def tag_seeds(data: dict, edition: str) -> list[str]:
    f = data.get("focus") or {}
    lead = f.get("lead")
    if not lead:
        return []
    name = NAMES.get(lead, lead).lower()
    kind = _kind(lead, data)
    seeds = [primary(data)[1].lower(), f"{name} news today", f"{name} price" if kind != "theme" else "fed news today"]
    seeds.append("crypto news today" if kind == "crypto" else "forex news today")
    seeds += [f"{NAMES.get(a, a).lower()} price today" for a in f.get("assets", []) if a != lead][:2]
    if edition:
        seeds.append(f"{edition.lower()} market brief")
    return seeds


def key_numbers(data: dict) -> list[str]:
    out = []
    for a in (data.get("focus") or {}).get("assets") or []:
        chg = _change(a, data)
        if a in data.get("crypto", {}):
            p = data["crypto"][a]["price"]
            out.append(f"• {NAMES.get(a, a)}: ${p:,.2f} ({_pct(chg)} 24h)" if p < 10 else
                       f"• {NAMES.get(a, a)}: ${p:,.0f} ({_pct(chg)} 24h)")
        elif a in data.get("fx", {}):
            f = data["fx"][a]
            out.append(f"• {f['name']}: {f['price']:.{2 if 'JPY' in a else 4}f} ({_pct(chg)} daily fix)")
        elif a == "XAU" and data.get("gold"):
            out.append(f"• Gold: ${data['gold']['price']:,.0f} ({_pct(chg)} 24h)")
    return out


def watch(data: dict) -> list[str]:
    cur = set((data.get("focus") or {}).get("currencies") or [])
    evs = [e for e in data.get("calendar", []) if not cur or e.get("currency") in cur]
    return [f"• {e['time_utc']} GMT · {e['currency']} {e['event']}" for e in evs[:3]]


def schedule(cfg: dict) -> str:
    # only the editions that go to YouTube (the Facebook-only news posts aren't listed)
    s = {k: v for k, v in cfg.get("sessions", {}).items()
         if v.get("kind") != "post" and "youtube" in (v.get("platforms") or ["youtube"])}
    parts = [f"{v['label']} {v['start_utc']}"
             for v in sorted(s.values(), key=lambda v: v.get("start_utc", "")) if v.get("start_utc")]
    return "Daily briefs (GMT): " + " · ".join(parts) + ". Subscribe so you don't miss the next one."
