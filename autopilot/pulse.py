"""Market-pulse material (epic-shorts-reach entry 6.1): Shorts material built from the day's fetched data alone, no
long video. Fetches Coinbase prices, crypto headlines and the CoinGecko overview (triggers.fetch), picks the lead
coin, finds its cause and headlines, snapshots the numbers as fetched (each coin's series kept) and writes
data/material/pulse-<YYYY-MM-DD>-<slot>.json in the market material format (autopilot/material.py, source kind
"pulse"). Deterministic: no LLM call. A quiet market writes nothing and says why.

    pick_lead(data, overview, cfg, used, log) -> {lead, coins, moves, cause, headlines, market, data_sources} | None
                                     candidates: BTC and ETH (triggers.coin_moves: Coinbase first, else CoinGecko) +
                                     the first non-major coin through the coin gate (triggers.coin_gate, rule 3's
                                     gate unchanged: top-50, ±coin_pct% in 24 h AND a crypto headline naming it);
                                     the lead = the biggest |24 h move|. Major lead → triggers.cause_for (the
                                     headlines in `used` skipped only when given) + triggers.related_coins; gated lead
                                     → its story is the cause, coins = it + the coins that story names (1-3 coins).
                                     None = no price data
    build(data, overview, now, slot, cfg, used, related, log) -> (material | None, reason)
                                     no price data → (None, "no price data"); |lead move| < pulse.quiet_move_pct with no
                                     cause → (None, "quiet market: …"); material.build_pulse failing material.validate →
                                     (None, "invalid pulse material: <problems>"); else (material, what it holds)
    make(cfg, root, slot, now, log, fetch, related, used) -> (path | None, reason)
                                     fetch + build + material.write (a second build for the same date + slot merges
                                     into the existing file); the builder the pulse Short (6.2) calls:
                                     main.make_pulse passes the latest long video (shorts.latest_long) as `related`
                                     and loads the written file; a None path → the concept fallback
"""
from datetime import datetime
from pathlib import Path

from autopilot import material, triggers

QUIET_MOVE_PCT = 1.5  # cfg pulse.quiet_move_pct: a smaller lead move with no story = a quiet market


def _quiet(cfg: dict | None) -> float:
    return float(((cfg or {}).get("pulse") or {}).get("quiet_move_pct", QUIET_MOVE_PCT))


def _moved(m: dict) -> bool:
    return m.get("change_24h") is not None or m.get("change_7d") is not None


def pick_lead(data: dict, overview: dict | None, cfg: dict | None = None, used: list[str] | None = None,
              log=print) -> dict | None:
    """The lead coin, its cause, coins, moves and headlines (see the module doc); None without price data."""
    pct = float(((cfg or {}).get("triggers") or {}).get("coin_pct", triggers.COIN_PCT))
    cands = {s: m for s, m in triggers.coin_moves(data, overview, list(triggers.MAJOR_COINS)).items()
             if m.get("change_24h") is not None}
    gated = None
    for sym, _c, story in triggers.coin_gate(data, overview, pct, log, outcome="not a pulse lead"):
        if sym in triggers.MAJOR_COINS:
            continue
        move = triggers.coin_moves(data, overview, [sym]).get(sym) or {}
        if move.get("change_24h") is not None:
            gated, cands[sym] = (sym, story), move
            break
    if not cands:
        return None
    lead = max(cands, key=lambda s: abs(cands[s]["change_24h"]))
    if gated and lead == gated[0]:
        cause = gated[1]
        coins = [lead] + [x for x in triggers.named_coins(cause["title"], data, overview) if x != lead]
    else:
        cause = triggers.cause_for(data, lead, used)
        coins = [lead] + [x for x in triggers.related_coins(data, lead) if x != lead]
    moves = {s: m for s, m in triggers.coin_moves(data, overview, coins[:triggers.MAX_COINS]).items() if _moved(m)}
    moves.setdefault(lead, cands[lead])
    coins = [lead] + [s for s in coins[:triggers.MAX_COINS] if s in moves and s != lead]
    moves = {s: moves[s] for s in coins}
    cause = triggers._story_row(cause)
    sources = sorted({m.get("source") or "Coinbase" for m in moves.values()} | ({"CoinGecko"} if overview else set()))
    return {"lead": lead, "coins": coins, "moves": moves, "cause": cause,
            "headlines": triggers.headlines(data, coins, cause), "market": triggers._market(overview),
            "data_sources": sources}


def build(data: dict, overview: dict | None, now: datetime, slot: str, cfg: dict | None = None,
          used: list[str] | None = None, related: str | None = None, log=print) -> tuple[dict | None, str]:
    """(pulse material, reason) or (None, why there is none); see the module doc."""
    picked = pick_lead(data or {}, overview, cfg, used, log)
    if picked is None:
        why = "no price data"
        log(f"Pulse: no material ({why}: no 24 h move for BTC, ETH or a coin through the coin gate)")
        return None, why
    lead = picked["lead"]
    m = picked["moves"][lead]
    name, move, quiet = m.get("name") or lead, m["change_24h"], _quiet(cfg)
    if abs(move) < quiet and picked["cause"] is None:
        why = f"quiet market: {name} {move:+.2f}% in 24 h (under {quiet:g}%) and no story behind it"
        log(f"Pulse: no material ({why})")
        return None, why
    out = material.build_pulse(picked, now, slot, related)
    problems = material.validate(out)
    if problems:
        why = "invalid pulse material: " + "; ".join(problems)
        log(f"Pulse: no material ({why})")
        return None, why
    cause = (picked["cause"] or {}).get("title")
    why = (f"pulse material: {name} {move:+.2f}% in 24 h, coins {', '.join(picked['coins'])}, "
           + (f"cause: {cause}" if cause else "no matching story") + f", data {', '.join(picked['data_sources'])}")
    log(f"Pulse: {why}")
    return out, why


def make(cfg: dict, root: Path, slot: str, now: datetime | None = None, log=print, fetch=triggers.fetch,
         related: str | None = None, used: list[str] | None = None) -> tuple[Path | None, str]:
    """Fetch, build and write today's pulse material for `slot` → (data/material/pulse-<date>-<slot>.json, reason),
    or (None, why there is none: nothing written)."""
    now = triggers._now(now)
    data, overview = fetch(cfg, log=log)
    m, why = build(data, overview, now, slot, cfg, used=used, related=related, log=log)
    if m is None:
        return None, why
    path = material.write(m, root)
    log(f"Pulse: wrote {path.name}")
    return path, why
