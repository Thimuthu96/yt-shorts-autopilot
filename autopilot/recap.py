"""Saturday recap (the `recap` edition, kind: recap, CAP-5): "This Week in Crypto: What Moved and Why", 16:9 on
YouTube only, Sat 15:00. Runs only when no triggered video published that ISO week (UTC); otherwise it logs the
skip. Dark until `recap.enabled: true` (timed runs skip; manual runs make it). Reuses autopilot/triggered.py's
slides, move chart, number check and credits.

    fetch(cfg, log) -> (data, overview)  Coinbase 7-day candles, a week of crypto headlines, the CoinGecko overview
    week_has_triggered(history, now)     an uploaded kind: triggered video (simulated ones never count) this ISO week
    build(data, overview, now) -> recap  the week's 2-3 biggest 7-day moves (Coinbase coins, then CoinGecko's top 50;
                                         stablecoins left out), each with its headline cause (a crypto headline
                                         naming the coin) or none; fewer than 2 moves → ValueError
    scene_plan(recap)                    hook (the board) → one scene per move (its 7-day chart + cause; the
                                         subscribe ask closes the first, the first payoff) → market (total cap,
                                         with an overview) → watch (related headlines) → recap
    write_script(cfg, recap, plan, log)  as triggered.write_script: word bounds recap.min_words-max_words (≈ 4-5 min),
                                         narration rules, the ask once, 3 attempts; fact-check + number check stop it
    render_slides / render_thumbnail (the 2-3 moves as a mini board) / metadata (fixed title, the moves and their
                                         causes, credits incl. "Data provided by CoinGecko" once when used, the
                                         disclosure line once, hashtags)
"""
import copy
import re
from datetime import datetime, timezone
from pathlib import Path

import yaml
from PIL import Image, ImageDraw

from autopilot import diagrams, focus, rules, triggered, triggers
from autopilot.lesson_slides import BG, FG, Layout, _flow, _font, _heading, _title_font
from autopilot.llm import generate_json
from autopilot.script import _merge_plan, _models, fact_check
from autopilot.slides import DOWN, PANEL, UP, _hex

TITLE = "This Week in Crypto: What Moved and Why"
THUMB_WORDS = "THIS WEEK"
CHIP = "WEEKLY RECAP"
MIN_WORDS, MAX_WORDS = 560, 750  # ≈ 4-5 minutes (cfg recap.min_words / max_words)
SUBSCRIBE_ASK = "If this recap helps, subscribe for next week's."  # cfg recap.subscribe_ask
ASK_SCENE = "move_1"
MAX_MOVES = 3
RECAP_RULES = triggered.TRIGGERED_RULES.replace("market explainer", "weekly market recap")


def _clean(text) -> str:
    return " ".join(str(text or "").split())


def _pct(v: float) -> str:
    return triggered._pct(v)


# ─── data ──────────────────────────────────────────────────────────────────

def fetch(cfg: dict, log=print) -> tuple[dict, dict | None]:
    from autopilot import sources
    feeds = {k: v for k, v in sources.DEFAULT_FEEDS.items() if k in ("crypto", "regulation")}
    data = {"crypto": sources.fetch_crypto(log=log), "news": sources.fetch_news(feeds, hours=24 * 7, log=log)}
    for n in data["news"]:
        n.setdefault("category", "crypto")
    return data, sources.fetch_market_overview(log=log)


def week_of(t: datetime) -> str:
    y, w, _ = t.astimezone(timezone.utc).isocalendar()
    return f"{y}-W{w:02d}"


def week_has_triggered(history, now: datetime) -> bool:
    return any(week_of(t) == week_of(now) for t in triggers.published(history).values())


def _cause(data: dict, overview: dict | None, sym: str, name: str) -> dict | None:
    rx = triggers._coin_rx(sym, name)
    tagged = [n for n in data.get("news") or [] if (n.get("title") or "").strip()]
    hits = [n for n in tagged if focus.tag(n).get(sym, 0) >= 1.0 or rx.search(n["title"])]
    if not hits:
        return None
    best = max(hits, key=lambda n: (sum(1 for m in tagged if m is not n and
                                        len(focus._words(m["title"]) & focus._words(n["title"])) >= 2),
                                    n.get("published") or ""))
    return triggers._story_row(best)


def build(data: dict, overview: dict | None, now: datetime | None = None) -> dict:
    now = triggers._now(now)
    cands = {}
    for sym, c in (data.get("crypto") or {}).items():
        if c.get("change_7d") is not None:
            cands[sym] = {"name": c.get("name") or sym, "price": triggers._round(c.get("price")),
                          "change_7d": triggers._round(c["change_7d"]), "change_24h": triggers._round(c.get("change_24h")),
                          "series": [triggers._round(x) for x in c.get("series") or []], "source": "Coinbase"}
    for sym, c in triggers._overview_coins(overview).items():
        if sym not in cands and c.get("change_7d") is not None:
            cands[sym] = {"name": c.get("name") or sym, "price": triggers._round(c.get("price")),
                          "change_7d": triggers._round(c["change_7d"]), "change_24h": triggers._round(c.get("change_24h")),
                          "series": [triggers._round(x) for x in c.get("sparkline") or []], "source": "CoinGecko"}
    coins = sorted(cands, key=lambda s: -abs(cands[s]["change_7d"]))[:MAX_MOVES]
    if len(coins) < 2:
        raise ValueError(f"only {len(coins)} coin(s) with a 7-day move; a recap needs at least 2")
    moves = {s: cands[s] for s in coins}
    causes = {s: _cause(data, overview, s, moves[s]["name"]) for s in coins}
    seen, heads = set(), []
    for n in sorted(data.get("news") or [], key=lambda n: n.get("published") or "", reverse=True):
        if n.get("title") and n["title"].lower() not in seen and set(coins) & set(focus.tag(n)):
            seen.add(n["title"].lower())
            heads.append({"title": n["title"], "source": n.get("source", ""), "published": n.get("published") or ""})
    sources = sorted({m["source"] for m in moves.values()} | ({"CoinGecko"} if overview else set()))
    return {"id": f"recap-{week_of(now)}", "week": week_of(now), "label": "Crypto", "lead": coins[0], "coins": coins,
            "moves": moves, "causes": causes, "headlines": heads[:5], "market": triggers._market(overview),
            "data_sources": sources}


# ─── plan + narration ──────────────────────────────────────────────────────

def scene_plan(recap: dict) -> list[dict]:
    moves = recap["moves"]
    board = ", ".join(f"{moves[s]['name']} {_pct(moves[s]['change_7d'])}" for s in recap["coins"])
    plan = [{"id": "hook", "visual": {"type": "board"},
             "covers": f"the hook: this week in crypto, the biggest 7-day moves were {board}; promise what moved and "
                       "why, no greeting"}]
    for i, s in enumerate(recap["coins"], 1):
        c = recap["causes"].get(s)
        plan.append({"id": f"move_{i}", "visual": {"type": "week_move", "coin": s},
                     "covers": f"{moves[s]['name']} moved {_pct(moves[s]['change_7d'])} over 7 days; "
                               + (f"the cause, from the headline: {_clean(c['title'])}" if c else
                                  "no single headline explains it: say so plainly and describe the price data")})
    market = recap.get("market") or {}
    if market.get("total_cap_change_24h") is not None:
        plan.append({"id": "market", "visual": {"type": "context", "coin": recap["coins"][0]},
                     "covers": "the wider market: the total crypto market cap changed "
                               f"{_pct(market['total_cap_change_24h'])} in the last 24 hours"})
    causes = {(c or {}).get("title") for c in recap["causes"].values()}
    others = [h for h in recap.get("headlines") or [] if h["title"] not in causes]
    plan.append({"id": "watch", "visual": {"type": "watch", "headlines": [h["title"] for h in others[:3]]},
                 "covers": "what to watch next week, only from these headlines (no predictions, no levels): "
                           + ("; ".join(_clean(h["title"]) for h in others[:3]) or "the next headlines on these coins")})
    plan.append({"id": "recap", "visual": {"type": "recap"},
                 "covers": "a short recap of the week's moves and their causes, then: this is market data, not "
                           "financial advice"})
    return plan


def facts(recap: dict) -> dict:
    return {"moves": {s: {k: m.get(k) for k in ("name", "price", "change_7d", "change_24h")}
                      for s, m in recap["moves"].items()},
            "causes": recap.get("causes"), "headlines": recap.get("headlines") or [], "market": recap.get("market"),
            "window_days": 7, "window_hours": 24}


def _bounds(cfg: dict) -> tuple[int, int]:
    rc = cfg.get("recap") or {}
    return int(rc.get("min_words", MIN_WORDS)), int(rc.get("max_words", MAX_WORDS))


def subscribe_ask(cfg: dict) -> str:
    return _clean((cfg.get("recap") or {}).get("subscribe_ask") or SUBSCRIBE_ASK)


def _prompt(cfg: dict, recap: dict, plan: list[dict]) -> str:
    lo, hi = _bounds(cfg)
    ch = cfg.get("channel") or {}
    scenes = "\n".join(f'- "{p["id"]}": {p["covers"]}' for p in plan)
    return f"""You write the narration of a {lo}-{hi} word YouTube WEEKLY CRYPTO RECAP: what moved this week and why.
Channel: {ch.get('display_name', 'CryptoFX Daily')}, a crypto data desk. Tone: calm, plain, neutral. No hype.

FETCHED DATA (the only facts you may state; round numbers sensibly):
{yaml.safe_dump(facts(recap), allow_unicode=True, sort_keys=False)}
Write narration for each scene, in this order (several short spoken sentences each):
{scenes}

Rules:
- Every number and claim must come from the data above. No predictions, no advice, no price targets.
- No greetings, no "in this video", never ask viewers to subscribe (one short subscribe line is added for you
  after the first move).
- "recap" ends: "This is market data, not financial advice."
{rules.NARRATION_RULES}

Return JSON: {{"scenes": [{{"id": "{plan[0]['id']}", "text": "..."}}, ...]}}"""


def _with_ask(cfg: dict, scenes: list[dict]) -> list[dict]:
    return [dict(s, text=f"{s['text'].strip()} {subscribe_ask(cfg)}") if s.get("id") == ASK_SCENE
            and (s.get("text") or "").strip() else dict(s) for s in scenes]


def check_script(cfg: dict, plan: list[dict], scenes: list[dict]) -> list[str]:
    lo, hi = _bounds(cfg)
    texts = {s["id"]: (s.get("text") or "").strip() for s in scenes}
    problems = [f"scene '{p['id']}': no narration" for p in plan if not texts.get(p["id"])]
    words = triggered._words(scenes)
    if not lo <= words <= hi:
        problems.append(f"{words} words (target {lo}-{hi})")
    problems += [f"narration rule: {r}" for r in rules.narration_problems("\n".join(texts.get(p["id"], "")
                                                                                    for p in plan))]
    ask = subscribe_ask(cfg)
    mentions = sum(len(triggered.SUBSCRIBE.findall(t)) for t in texts.values())
    if not texts.get(ASK_SCENE, "").endswith(ask) or mentions != len(triggered.SUBSCRIBE.findall(ask)):
        problems.append(f"subscribe ask: once, at the end of the '{ASK_SCENE}' scene only")
    return problems


def write_script(cfg: dict, recap: dict, plan: list[dict], log=print) -> dict:
    problems: list[str] = []
    for attempt in range(1, 4):
        log(f"Writing the recap narration ({recap['id']}, attempt {attempt}/3)...")
        answer = generate_json(_prompt(cfg, recap, plan), _models(cfg), temperature=0.6) or {}
        scenes = _with_ask(cfg, _merge_plan(plan, answer if isinstance(answer, dict) else {})["scenes"])
        problems = check_script(cfg, plan, scenes)
        log(f"Draft: {triggered._words(scenes)} words")
        if problems:
            log(f"Discarding draft: {'; '.join(problems)}")
            continue
        lo, hi = _bounds(cfg)
        fcfg = {**cfg, "llm": {**(cfg.get("llm") or {}), "min_words": lo, "max_words": hi}}
        ask = subscribe_ask(cfg)
        sent = {"title": TITLE, "scenes": [{"id": s["id"], "text": _clean(s["text"].replace(ask, " "))} for s in scenes]}
        log("Fact-checking the recap narration against the fetched data...")
        verdict, checked, issues = fact_check(fcfg, facts(recap), sent, RECAP_RULES)
        if verdict == "reject":
            raise RuntimeError(f"Recap fact-check failed: verdict reject ({'; '.join(map(str, issues)) or 'no reason'})")
        if isinstance(checked, dict) and checked.get("scenes"):
            scenes = _with_ask(cfg, _merge_plan(plan, copy.deepcopy(checked))["scenes"])
        problems = check_script(cfg, plan, scenes)
        bad = triggered.unknown_numbers("\n".join(s.get("text") or "" for s in scenes), facts(recap))
        if bad:
            problems.append("numbers not in the fetched data: " + ", ".join(bad))
        if problems:
            raise RuntimeError(f"Recap fact-check failed: {'; '.join(problems)}")
        return {"scenes": scenes, "fact_check": {"verdict": verdict, "issues": issues}}
    raise RuntimeError(f"Could not produce valid recap narration in 3 attempts: {'; '.join(problems)}")


# ─── slides ────────────────────────────────────────────────────────────────

def _ctx(cfg: dict, recap: dict, layout: Layout):
    ctx = triggered._ctx(cfg, recap, layout)
    ctx.chip = CHIP
    return ctx


_base = triggered._base


def slide_board(ctx, v: dict) -> Image.Image:
    img, d = _base(ctx)
    r = ctx.trigger
    items = [_heading(ctx, "THIS WEEK IN CRYPTO")]
    for s in r["coins"]:
        m = r["moves"][s]
        items.append({"text": f"{m['name']} {_pct(m['change_7d'])}", "size": 96, "title": True, "gap": 18,
                      "fill": UP if m["change_7d"] >= 0 else DOWN, "keep": True})
    items.append({"text": "7-day moves", "size": 40, "bold": True, "fill": FG, "keep": True})
    _flow(d, items, ctx.layout.content_box, ctx.layout, valign="center", max_scale=1.1, who=f"{r['id']} board")
    return img


def slide_week_move(ctx, v: dict) -> Image.Image:
    img, d = _base(ctx)
    L, r = ctx.layout, ctx.trigger
    x0, y0, x1, y1 = L.content_box
    m = r["moves"][v["coin"]]
    c = r["causes"].get(v["coin"])
    items = [_heading(ctx, f"{_clean(m['name']).upper()} {_pct(m['change_7d'])} IN 7 DAYS"),
             {"text": _clean(c["title"]) if c else "No single headline explains this move", "size": 56, "title": True,
              "fill": FG, "max_lines": 2}]
    y = _flow(d, items, L.content_box, L, who=f"{r['id']} {v['coin']}")
    if len(m.get("series") or []) >= 2 and y1 - y > 200:
        triggered.draw_move_chart(img, (x0, y + 24, x1, y1), m["series"], L, ctx.accent,
                                  label=f"{v['coin']} · last 7 days")
    return img


def _context(ctx, v: dict) -> Image.Image:
    img, d = _base(ctx)
    cap = (ctx.trigger.get("market") or {}).get("total_cap_change_24h")
    items = [_heading(ctx, "THE WIDER MARKET"),
             {"text": f"Total market cap {_pct(cap)} in 24 h", "size": 96, "title": True,
              "fill": UP if (cap or 0) >= 0 else DOWN, "keep": True}]
    _flow(d, items, ctx.layout.content_box, ctx.layout, valign="center", who=f"{ctx.trigger['id']} market")
    return img


def _recap(ctx, v):
    r = ctx.trigger
    img, d = _base(ctx)
    items = [_heading(ctx, "RECAP")]
    for s in r["coins"]:
        items.append({"text": f"{r['moves'][s]['name']} {_pct(r['moves'][s]['change_7d'])} (7 days)", "size": 56,
                      "bold": True, "fill": FG, "gap": 20, "bullet": "•", "bullet_fill": ctx.accent, "keep": True})
    items.append({"text": "Market data. Not financial advice.", "size": 40, "bold": True, "fill": FG, "keep": True})
    _flow(d, items, ctx.layout.content_box, ctx.layout, valign="center", max_scale=1.2, who=f"{r['id']} recap")
    return img


RENDERERS = {"board": slide_board, "week_move": slide_week_move, "context": _context, "watch": triggered.slide_watch,
             "recap": _recap}


def render_slides(cfg: dict, recap: dict, plan: list[dict], layout: Layout, workdir: Path) -> list[dict]:
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    ctx = _ctx(cfg, recap, layout)
    out = []
    for i, s in enumerate(plan):
        t = (s.get("visual") or {}).get("type")
        if t not in RENDERERS:
            raise ValueError(f"unknown recap visual type '{t}' (scene '{s.get('id')}')")
        path = workdir / f"recap_{layout.name}_{i:02d}.png"
        RENDERERS[t](ctx, s["visual"]).save(path)
        out.append({"image": path, "reveal": None, "id": s["id"]})
    return out


# ─── packaging (packaging.md, Recap row) ───────────────────────────────────

def packaging_problems() -> list[str]:
    return triggered.packaging_problems(TITLE, THUMB_WORDS)


def render_thumbnail(cfg: dict, recap: dict, path: Path) -> Path:
    """1280x720: brand + WEEKLY RECAP chip, "THIS WEEK" and the 2-3 moves as a mini board (drawn badge, name,
    % in green / red)."""
    from autopilot.thumbnail import GRID, _fit, _mini_logo
    W, H = triggered.THUMB_SIZE
    accent = _hex(cfg["video"].get("accent", "FFD400"))
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    for x in range(0, W, 64):
        d.rectangle([x, 0, x + 1, H], fill=GRID)
    for y in range(0, H, 64):
        d.rectangle([0, y, W, y + 1], fill=GRID)
    _mini_logo(img, 44, 30, 64, accent, [UP, DOWN, UP])
    d.text((120, 62), cfg["channel"].get("display_name", "CryptoFX Daily"), font=_font(34, True), fill=FG, anchor="lm")
    fc = _font(28, True)
    cw = d.textlength(CHIP, font=fc)
    d.rounded_rectangle([W - 48 - cw - 44, 36, W - 48, 88], radius=26, fill=accent)
    d.text((W - 48 - cw - 22, 62), CHIP, font=fc, fill=BG, anchor="lm")
    f = _title_font(120)
    y = 140
    for w in THUMB_WORDS.split():
        d.text((56, y), w, font=f, fill=FG)
        y += 124
    rows = recap["coins"][:3]
    top, rh = 130, (H - 160) // max(len(rows), 1)
    for i, s in enumerate(rows):
        m = recap["moves"][s]
        cy = top + i * rh + rh // 2
        d.rounded_rectangle([600, cy - rh // 2 + 10, W - 48, cy + rh // 2 - 10], radius=20, fill=PANEL)
        bs = min(130, rh - 40)
        tick = s if re.fullmatch(r"[A-Z]{2,5}", s) else s[:5].upper()
        fi = _fit(tick, lambda s_: _title_font(s_), round(bs * 0.75), round(bs * 0.4), 24)
        diagrams._paint(d, diagrams._badge(600 + 30 + bs // 2, cy, bs, tick, fi, accent))
        pct = _pct(m["change_7d"]).replace("−", "-")
        d.text((W - 80, cy), pct, font=_fit(pct, lambda s_: _title_font(s_), 330, 110, 40),
               fill=UP if m["change_7d"] >= 0 else DOWN, anchor="rm")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, "JPEG", quality=92)
    return path


def metadata(cfg: dict, recap: dict) -> dict:
    problems = packaging_problems()
    if problems:
        raise ValueError(f"Recap packaging: {'; '.join(problems)}")
    line = rules.disclosure(cfg, "recap")
    rows = []
    for s in recap["coins"]:
        m, c = recap["moves"][s], recap["causes"].get(s)
        rows.append(f"• {_clean(m['name'])}: {_pct(m['change_7d'])} over 7 days"
                    + (f". Why: {_clean(c['title'])}" + (f" ({_clean(c.get('source'))})" if c.get("source") else "")
                       if c else ""))
    parts = ["The week's biggest crypto moves and the headlines behind them.", "What moved:\n" + "\n".join(rows)]
    heads = [f"• {_clean(h['title'])}" for h in recap.get("headlines") or []]
    if heads:
        parts.append("Headlines:\n" + "\n".join(heads))
    body = "\n\n".join(rules.without_disclosure(p, line) for p in parts)
    tags_ = ["#Crypto", "#CryptoNews"] + [triggered.COIN_HASHTAGS[c] for c in recap["coins"] if c in triggered.COIN_HASHTAGS]
    tail = "\n\n".join(["\n".join(triggered.credits(recap)), "⚠️ " + line, " ".join(tags_[:5])])
    room = triggered.MAX_DESCRIPTION - len(tail) - 2
    if len(body) > room:
        body = body[:room].rsplit("\n", 1)[0]
    tags = ["this week in crypto", "crypto weekly recap", "crypto news"] + \
        [_clean(recap["moves"][c]["name"]).lower() for c in recap["coins"]]
    return {"title": TITLE, "description": body.rstrip() + "\n\n" + tail, "tags": tags,
            "category_id": str((cfg.get("recap") or {}).get("category_id") or triggered.CATEGORY),
            "thumbnail_text": THUMB_WORDS}
