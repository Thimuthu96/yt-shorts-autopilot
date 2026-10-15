"""Trigger engine (CAP-4, epic-volatility-videos): watches the market and fires a trigger for a topic-led
"why crypto just moved" video (the `triggered` edition in main.py). Dark until `triggers.enabled: true`.
Deterministic: no LLM call; light imports only (the poll job installs no ffmpeg / Pillow).

A trigger (JSON, also the fixture format of `main.py --session triggered --trigger <path>`):

    {"id": "20261015-0930-r1-btc", "rule": 1, "rule_name": "BTC or ETH ±5% in 24 h",
     "fired_utc": ISO, "due_utc": ISO,
     "lead": "BTC", "label": "Bitcoin", "coins": ["BTC", "ETH"],          1-3 coins, the lead first
     "moves": {"BTC": {"name", "price", "change_24h", "change_7d", "series", "series_times", "source"}},
     "cause": {"title", "source", "published", "summary"} | None,          the story behind the move
     "headlines": [{"title", "source", "published"}],                       ≤ 5 related crypto stories
     "market": {"total_cap_usd", "total_cap_change_24h", "source"} | None, CoinGecko's overview when fetched
     "data_sources": ["Coinbase", "CoinGecko"], "key": "r1:BTC:<cause>"}  key = the same cause, for dedupe

    evaluate(data, overview=None, now=None, log) -> [trigger]  every rule that fires now (rule 1: BTC or ETH
                                     moves ±5% or more in 24 h); data = sources-style {crypto, news}
    load(ref, root) -> trigger       `ref` = a fixture path: a trigger JSON ({"trigger": …} or a trigger), or
                                     market data ({crypto, news, overview?}) whose first firing trigger is used
"""
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from autopilot import focus

RULE_NAMES = {1: "BTC or ETH ±5% in 24 h"}
MAJOR_COINS = ("BTC", "ETH")  # rule 1
MOVE_PCT = 5.0  # rule 1 threshold (cfg triggers.move_pct)
MAX_COINS = 3
MAX_HEADLINES = 5


def _now(now: datetime | None) -> datetime:
    return (now or datetime.now(timezone.utc)).astimezone(timezone.utc)


def _iso(t: datetime) -> str:
    return t.astimezone(timezone.utc).isoformat(timespec="seconds")


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-")[:40]


def _round(v):
    return None if v is None else float(f"{float(v):.6g}")


def _story_row(n: dict | None) -> dict | None:
    if not n:
        return None
    return {"title": n.get("title", ""), "source": n.get("source", ""), "published": n.get("published") or "",
            "summary": " ".join(str(n.get("summary") or "").split())[:400]}


def _tagged(data: dict) -> list[dict]:
    return [dict(n, _tags=focus.tag(n)) for n in data.get("news") or []]


def cause_for(data: dict, lead: str, used: list[str] | None = None) -> dict | None:
    """The story behind `lead`'s move: the crypto-only focus.pick's story when it leads with `lead`, else
    focus's story rule for that coin (named in the title, covered by several outlets, recent)."""
    picked = focus.pick(dict(data), used_headlines=used)
    if picked.get("lead") == lead and picked.get("story"):
        return picked["story"]
    story = focus._story(_tagged(data), lead, {h.lower() for h in used or []})
    return {k: v for k, v in story.items() if k != "_tags"} if story else None


def related_coins(data: dict, lead: str) -> list[str]:
    """The lead + the related coins (focus.RELATED) with price data that moved most: 1-3 coins."""
    crypto = data.get("crypto") or {}
    rel = [a for a in focus.RELATED.get(lead, []) if a in crypto]
    rel.sort(key=lambda a: abs(crypto[a].get("change_24h") or 0), reverse=True)
    return ([lead] if lead in crypto else []) + rel[:MAX_COINS - 1]


def snapshot(data: dict, coins: list[str], source: str = "Coinbase") -> dict:
    """The fetched numbers a triggered video may speak, per coin (series kept for its charts)."""
    out = {}
    for sym in coins:
        c = (data.get("crypto") or {}).get(sym)
        if not c:
            continue
        out[sym] = {"name": c.get("name") or focus.LABELS.get(sym, sym), "price": _round(c.get("price")),
                    "change_24h": _round(c.get("change_24h")), "change_7d": _round(c.get("change_7d")),
                    "series": [_round(x) for x in c.get("series") or []],
                    "series_times": list(c.get("series_times") or []), "source": c.get("source") or source}
    return out


def headlines(data: dict, coins: list[str], cause: dict | None) -> list[dict]:
    """The cause first, then other stories naming one of the coins (newest first), ≤ MAX_HEADLINES."""
    rows = [n for n in _tagged(data) if set(coins) & set(n["_tags"])]
    rows.sort(key=lambda n: n.get("published") or "", reverse=True)
    out, seen = [], set()
    for n in ([cause] if cause else []) + rows:
        t = (n.get("title") or "").strip()
        if t and t.lower() not in seen:
            seen.add(t.lower())
            out.append({"title": t, "source": n.get("source", ""), "published": n.get("published") or ""})
    return out[:MAX_HEADLINES]


def _market(overview: dict | None) -> dict | None:
    if not overview:
        return None
    return {"total_cap_usd": _round(overview.get("total_cap_usd")),
            "total_cap_change_24h": _round(overview.get("total_cap_change_24h")),
            "source": overview.get("source") or "CoinGecko", "credit": overview.get("credit") or ""}


def make_trigger(rule: int, lead: str, coins: list[str], cause: dict | None, data: dict, now: datetime,
                 overview: dict | None = None, moves: dict | None = None, label: str | None = None) -> dict:
    moves = moves if moves is not None else snapshot(data, coins)
    sources = sorted({m.get("source", "Coinbase") for m in moves.values()} | ({"CoinGecko"} if overview else set()))
    cause = _story_row(cause)
    return {"id": f"{now:%Y%m%d-%H%M}-r{rule}-{_slug(lead)}", "rule": rule, "rule_name": RULE_NAMES[rule],
            "fired_utc": _iso(now), "due_utc": _iso(now), "lead": lead,
            "label": label or (moves.get(lead) or {}).get("name") or focus.LABELS.get(lead, lead),
            "coins": [c for c in coins if c in moves][:MAX_COINS] or coins[:MAX_COINS], "moves": moves,
            "cause": cause, "headlines": headlines(data, coins, cause), "market": _market(overview),
            "data_sources": sources,
            "key": f"r{rule}:{lead}:{_slug((cause or {}).get('title') or 'no-story')}"}


def evaluate(data: dict, overview: dict | None = None, now: datetime | None = None, cfg: dict | None = None,
             used: list[str] | None = None, log=print) -> list[dict]:
    """Every trigger that fires on this data, strongest rule first (rule 1 only for now)."""
    now = _now(now)
    tc = (cfg or {}).get("triggers") or {}
    pct = float(tc.get("move_pct", MOVE_PCT))
    crypto = data.get("crypto") or {}
    out = []
    big = [s for s in MAJOR_COINS if s in crypto and abs(crypto[s].get("change_24h") or 0) >= pct]
    if big:
        lead = max(big, key=lambda s: abs(crypto[s]["change_24h"]))
        cause = cause_for(data, lead, used)
        coins = list(dict.fromkeys(big + related_coins(data, lead)))
        coins = [lead] + [c for c in coins if c != lead]
        out.append(make_trigger(1, lead, coins[:MAX_COINS], cause, data, now, overview))
        log(f"Trigger rule 1: {lead} {crypto[lead]['change_24h']:+.2f}% in 24 h"
            + (f" · cause: {cause['title']}" if cause else " · no matching story"))
    return out


def load(ref: str, root: Path | None = None, now: datetime | None = None) -> dict:
    """A trigger from a fixture path (a trigger JSON, {"trigger": …}, or market data that fires).
    Unknown / nothing fires → ValueError."""
    path = Path(ref)
    if not path.exists() and root is not None:
        path = Path(root) / ref
    if not path.is_file():
        raise ValueError(f"trigger '{ref}' is not a fixture file")
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, dict) and isinstance(raw.get("trigger"), dict):
        raw = raw["trigger"]
    if isinstance(raw, dict) and raw.get("rule") and raw.get("id"):
        return raw
    if isinstance(raw, dict) and ("crypto" in raw or "news" in raw):
        when = raw.get("now")
        fired = evaluate(raw, raw.get("overview"), datetime.fromisoformat(when) if when else now, log=lambda m: None)
        if not fired:
            raise ValueError(f"the fixture {path.name} fires no trigger")
        return fired[0]
    raise ValueError(f"{path.name} is neither a trigger nor market data")
