"""Pick each brief's lead story and the few assets it actually moves, so a Short tells one
story ("Bitcoin liquidations → ETH and SOL follow") instead of reading out every market.

Deterministic: scores come from the day's headlines, price moves and calendar.
pick() writes data["focus"]; the script writer, thumbnail and slides then stay on it.
"""
import re
from datetime import datetime, timedelta, timezone

# What each asset is called in headlines. "USD" is a theme (Fed, US data, the dollar), not a chart.
KEYWORDS = {
    "BTC": r"\bbitcoin\b|\bbtc\b|saylor|microstrategy",
    "ETH": r"\bether(eum)?\b|\beth\b",
    "SOL": r"\bsolana\b|\bsol\b",
    "XRP": r"\bxrp\b|\bripple\b",
    "EURUSD": r"\beuro\b|\beurozone\b|\becb\b|lagarde|eur/usd|eurusd",
    "GBPUSD": r"\bpound\b|\bsterling\b|\bboe\b|bank of england|eur/gbp|gbp/usd|gbpusd|\buk (inflation|cpi|gdp|economy)",
    "USDJPY": r"\byen\b|\bboj\b|bank of japan|\bueda\b|usd/jpy|usdjpy",
    "AUDUSD": r"aussie dollar|australian dollar|\brba\b|aud/usd",
    "USDCAD": r"canadian dollar|loonie|bank of canada|usd/cad",
    "USDCHF": r"swiss franc|\bsnb\b|usd/chf",
    "XAU": r"\bgold\b|bullion|\bxau|precious metal",
    "USD": r"\bdollar\b|\bdxy\b|\bfed\b|federal reserve|powell|fomc|treasury yields?|\bcpi\b|inflation|"
           r"payrolls|jobs report|\bpce\b|rate (cut|hike)",
}
_RX = {k: re.compile(v, re.I) for k, v in KEYWORDS.items()}

LABELS = {"BTC": "Bitcoin", "ETH": "Ethereum", "SOL": "Solana", "XRP": "XRP", "XAU": "Gold",
          "USD": "the US dollar and the Fed"}
CURRENCIES = {"EURUSD": {"EUR", "USD"}, "GBPUSD": {"GBP", "USD"}, "USDJPY": {"USD", "JPY"},
              "AUDUSD": {"AUD", "USD"}, "USDCAD": {"USD", "CAD"}, "USDCHF": {"USD", "CHF"},
              "XAU": {"USD"}, "USD": {"USD"}, "BTC": {"USD"}, "ETH": {"USD"}, "SOL": {"USD"}, "XRP": {"USD"}}

# Where a story usually spreads, in order of how directly it is linked.
RELATED = {
    "BTC": ["ETH", "SOL", "XRP"],
    "ETH": ["BTC", "SOL"],
    "SOL": ["BTC", "ETH"],
    "XRP": ["BTC", "ETH"],
    "EURUSD": ["GBPUSD", "XAU", "USDCHF"],
    "GBPUSD": ["EURUSD"],
    "USDJPY": ["XAU", "BTC", "EURUSD"],
    "AUDUSD": ["XAU", "USDJPY"],
    "USDCAD": ["EURUSD"],
    "USDCHF": ["EURUSD", "XAU"],
    "XAU": ["EURUSD", "USDJPY", "BTC"],
    "USD": ["EURUSD", "XAU", "USDJPY", "GBPUSD", "BTC"],
}

# General market relationships the script may explain with "usually / tends to" wording.
LINKS = {
    ("BTC", "ETH"): "Ether and other large coins usually move in the same direction as Bitcoin, often by more.",
    ("BTC", "SOL"): "Smaller coins like Solana tend to amplify Bitcoin's moves.",
    ("BTC", "XRP"): "XRP usually follows Bitcoin's direction on big crypto-wide moves.",
    ("ETH", "BTC"): "Ether-specific news can spill over to Bitcoin when it changes crypto sentiment.",
    ("USD", "EURUSD"): "EUR/USD moves opposite to the dollar: a stronger dollar pushes it lower.",
    ("USD", "GBPUSD"): "GBP/USD moves opposite to the dollar.",
    ("USD", "USDJPY"): "USD/JPY rises when the dollar strengthens or US yields climb.",
    ("USD", "XAU"): "Gold is priced in dollars and pays no interest, so a stronger dollar and higher "
                    "yields usually weigh on it, and the reverse supports it.",
    ("USD", "BTC"): "Expectations of easier Fed policy tend to support risk assets like Bitcoin; "
                    "a hawkish Fed tends to weigh on them.",
    ("XAU", "EURUSD"): "Gold and EUR/USD often rise together when the dollar weakens.",
    ("XAU", "USDJPY"): "A falling USD/JPY (stronger yen) often comes with safe-haven demand that also lifts gold.",
    ("XAU", "BTC"): "Bitcoin is sometimes called digital gold, but the two often decouple day to day.",
    ("EURUSD", "GBPUSD"): "The euro and the pound often move together against the dollar.",
    ("EURUSD", "XAU"): "A weaker dollar usually lifts both EUR/USD and gold.",
    ("USDJPY", "XAU"): "Yen strength often comes with safe-haven demand that also supports gold.",
    ("USDJPY", "BTC"): "Sharp yen rallies can force carry-trade unwinds that hit risk assets like crypto.",
}

MOVE_SCALE = {"crypto": 4.0, "fx": 0.8, "gold": 1.5}  # a move this big scores 1.0
EVENT_ASSETS = {"USD", "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "USDCHF"}


def tag(item: dict) -> dict:
    """{asset: 1.0 if named in the title, 0.4 if only in the summary/body}"""
    title = item.get("title", "")
    rest = f"{item.get('summary', '')} {item.get('body', '')[:600]}"
    out = {}
    for key, rx in _RX.items():
        if rx.search(title):
            out[key] = 1.0
        elif rx.search(rest):
            out[key] = 0.4
    return out


def _moves(data: dict) -> dict:
    """{asset: (kind, % change, score)} for every asset with price data."""
    out = {}
    for sym, c in data.get("crypto", {}).items():
        out[sym] = ("crypto", c["change_24h"], abs(c["change_24h"]) / MOVE_SCALE["crypto"])
    if not data.get("weekend"):  # forex and spot gold are closed at weekends
        for pair, f in data.get("fx", {}).items():
            out[pair] = ("fx", f["change_1d"], abs(f["change_1d"]) / MOVE_SCALE["fx"])
        g = data.get("gold")
        if g:
            out["XAU"] = ("gold", g["change_24h"], abs(g["change_24h"]) / MOVE_SCALE["gold"])
    return out


def _words(title: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9$%]+", title.lower()) if len(w) > 3}


def _story(items: list[dict], lead: str, used: set[str]) -> dict | None:
    """The lead's main story: named in the title, covered by several outlets, recent, not used before."""
    cands = [n for n in items if n["_tags"].get(lead, 0) >= 1.0 and n["title"].lower() not in used] or \
            [n for n in items if lead in n["_tags"] and n["title"].lower() not in used]
    if not cands:
        return None
    now = datetime.now(timezone.utc)

    def score(n):
        overlap = sum(1 for m in items if m is not n and len(_words(m["title"]) & _words(n["title"])) >= 2)
        try:
            age = (now - datetime.fromisoformat(n["published"])).total_seconds() / 3600
        except (TypeError, ValueError):
            age = 24
        return overlap * 0.5 + (0.6 if age < 6 else 0.3 if age < 12 else 0) + (0.3 if n.get("body") else 0)
    return max(cands, key=score)


def pick(data: dict, last_lead: str | None = None, used_headlines: list[str] | None = None) -> dict:
    used = {h.lower() for h in (used_headlines or [])}
    moves = _moves(data)
    items = [dict(n, _tags=tag(n)) for n in data.get("news", [])]

    scores: dict[str, float] = {}
    why: dict[str, list[str]] = {}
    for key in KEYWORDS:
        if key != "USD" and key not in moves:
            continue
        hits = sum(n["_tags"].get(key, 0) for n in items if n["title"].lower() not in used)
        news_score = min(hits / 2, 1.5)  # two headlines naming it ≈ a big move
        if key == "USD":
            fx = data.get("fx", {}) if not data.get("weekend") else {}
            vals = [f["change_1d"] if p.startswith("USD") else -f["change_1d"] for p, f in fx.items()]
            move = abs(sum(vals) / len(vals)) / 0.4 if vals else 0.0
        else:
            move = moves[key][2]
        event = 0.0
        if key in EVENT_ASSETS:  # a big scheduled release today makes its currency the story
            soon = datetime.now(timezone.utc) + timedelta(hours=12)
            for ev in data.get("calendar", []):
                try:
                    when = datetime.fromisoformat(ev["datetime"])
                except (KeyError, ValueError):
                    continue
                if when <= soon and ev.get("currency") in CURRENCIES[key] - ({"USD"} if key != "USD" else set()):
                    event = 0.6
                    break
        if hits == 0:
            move *= 0.7  # a move with no story behind it makes a thin Short; only a big one should lead
        total = move + news_score + event - (0.3 if key == last_lead else 0.0)
        scores[key] = total
        why[key] = [f"move {move:.2f}", f"news {news_score:.2f}", f"event {event:.1f}"]

    if not scores:
        data["focus"] = {}
        return {}
    lead = max(scores, key=scores.get)
    story = _story(items, lead, used)

    # assets shown with charts: the lead (if it has prices) + the related assets that moved most
    related = [a for a in RELATED.get(lead, []) if a in moves]
    related.sort(key=lambda a: moves[a][2], reverse=True)
    if lead == "USD":
        assets = related[:3]
    else:
        assets = [lead] + related[:2]
    pairs = [(lead, a) for a in assets if (lead, a) in LINKS]
    if lead not in ("USD",):
        for a in assets[1:]:
            if ("USD", a) in LINKS and moves.get(a, ("", 0, 0))[0] in ("fx", "gold"):
                pairs.append(("USD", a))

    focus_keys = set(assets) | {lead}
    news = sorted((n for n in items if focus_keys & set(n["_tags"]) and n["title"].lower() not in used),
                  key=lambda n: (n is story, max(n["_tags"].get(k, 0) for k in focus_keys), n["published"] or ""),
                  reverse=True)
    clean = [{k: v for k, v in n.items() if k != "_tags"} for n in news[:10]]
    currencies = set().union(*(CURRENCIES.get(k, set()) for k in focus_keys))

    def name(k):
        if k in LABELS:
            return LABELS[k]
        return data.get("fx", {}).get(k, {}).get("name") or data.get("crypto", {}).get(k, {}).get("name") or k
    focus = {
        "lead": lead, "label": name(lead),
        "assets": assets, "asset_names": {a: name(a) for a in assets},
        "story": {k: v for k, v in story.items() if k != "_tags"} if story else None,
        "news": clean,
        "links": [LINKS[p] for p in dict.fromkeys(pairs)],
        "currencies": sorted(currencies),
        "scores": {k: round(v, 2) for k, v in sorted(scores.items(), key=lambda kv: -kv[1])[:5]},
        "why": why[lead],
    }
    data["focus"] = focus
    return focus
