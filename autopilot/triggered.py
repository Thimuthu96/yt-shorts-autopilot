"""Triggered video (the `triggered` edition, kind: triggered): "why crypto just moved", topic-led, from one
trigger (autopilot/triggers.py) → narration from the trigger's fetched data only → a 16:9 YouTube video.
Dark until `triggers.enabled` (timed runs skip; manual runs make it).

    scene_plan(trigger)                  fixed shape: move (hook) → cause (the first payoff; the subscribe ask
                                         closes it) → coins (a drawn diagram: the cause → the 1-3 coins it moved,
                                         each part revealed as it is named) → context (7-day chart, total market
                                         cap) → watch (the related headlines; no predictions) → recap
    facts(trigger)                       the only facts the narration may state (fetched numbers + headlines)
    write_script(cfg, trigger, plan, log)  Gemini narrates the plan; checks (check_script): every scene narrated,
                                         word bounds (triggers.min_words-max_words ≈ 3-4 min), rules.narration_problems,
                                         the subscribe ask once at the end of the cause scene; 3 failed attempts →
                                         RuntimeError. The passing draft is fact-checked (script.fact_check vs
                                         facts(trigger)); a reject, a revised draft with problems or a spoken number
                                         no fetched value rounds to → RuntimeError at once (the edition stops)
    render_slides(cfg, trigger, plan, layout, workdir)  one PNG per scene (lesson_slides LANDSCAPE / PORTRAIT); the
                                         diagram scene adds base + steps for reveal.time_steps
    draw_move_chart(img, box, series, layout, accent, label)  the drawn line chart of a move (both shapes; epic 4's
                                         market Short reuses it)
"""
import copy
import json
import re
from dataclasses import dataclass
from pathlib import Path

import yaml
from PIL import Image, ImageDraw

from autopilot import diagrams, focus, rules
from autopilot.lesson_slides import (BG, DISCLAIMER, FG, MUTED, Layout, _flow, _fmt_tick, _font, _heading, _ticks,
                                     _title_font)
from autopilot.llm import generate_json
from autopilot.script import _merge_plan, _models, fact_check
from autopilot.slides import DOWN, PANEL, UP, _hex, _wrap

CHIP = "MARKET MOVE"
CATEGORY = "25"  # News & Politics (cfg triggers.category_id)
MIN_WORDS, MAX_WORDS = 420, 600  # ≈ 3-4 minutes (cfg triggers.min_words / max_words)
SUBSCRIBE_ASK = "If this was useful, subscribe for the next market explainer."  # cfg triggers.subscribe_ask
SUBSCRIBE = re.compile(r"\bsubscri[bp]\w*", re.I)
ASK_SCENE = "cause"  # the first payoff: the ask closes the explained cause, never the opening
NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")
ALIASES = {"ETH": ["Ether"], "BTC": [], "XRP": []}
TRIGGERED_RULES = """
3. This is a market explainer. The data above are its ONLY facts: every number must round from a value in
   it and every "why" must come from its headlines. No predictions, targets, advice, dates or clock times.
   Keep every scene id and the words that name each diagram part."""


def _clean(text) -> str:
    return " ".join(str(text or "").split())


def _pct(v: float, dec: int = 1) -> str:
    return f"{'+' if v >= 0 else '−'}{abs(v):.{dec}f}%"


def lead_move(trigger: dict) -> float:
    """The headline move: the lead coin's 24 h change (the total market cap's for a market-wide trigger)."""
    m = (trigger.get("moves") or {}).get(trigger.get("lead")) or {}
    if m.get("change_24h") is not None:
        return float(m["change_24h"])
    return float((trigger.get("market") or {}).get("total_cap_change_24h") or 0.0)


def chart_coin(trigger: dict) -> str | None:
    """The coin whose chart shows the move: the lead, else the first coin with a series."""
    moves = trigger.get("moves") or {}
    for s in [trigger.get("lead")] + list(trigger.get("coins") or []):
        if len((moves.get(s) or {}).get("series") or []) >= 2:
            return s
    return None


# ─── plan + narration ──────────────────────────────────────────────────────

def _cause_label(trigger: dict) -> str:
    cat = trigger.get("category")
    return focus.MAJOR_LABELS[cat].capitalize() if cat in focus.MAJOR_LABELS else "The news"


def diagram(trigger: dict) -> dict:
    """The coins scene's flow diagram: the cause → each coin it moved (label = name + 24 h move, drawn badge)."""
    nodes = [{"label": _cause_label(trigger), "say": ["headline", "news"]}]
    for i, sym in enumerate((trigger.get("coins") or [])[:3]):
        m = (trigger.get("moves") or {}).get(sym) or {}
        name = _clean(m.get("name")) or sym
        node = {"label": f"{name} {_pct(m['change_24h'])}" if m.get("change_24h") is not None else name,
                "arrow": "moved" if i == 0 else "and", "say": [name] + ALIASES.get(sym, [])}
        if re.fullmatch(r"[A-Z]{2,5}", sym):
            node["coin"] = sym
        nodes.append(node)
    return {"type": "flow", "nodes": nodes}


def scene_plan(trigger: dict) -> list[dict]:
    label = _clean(trigger.get("label") or trigger.get("lead"))
    cause = trigger.get("cause")
    coins = [((trigger.get("moves") or {}).get(s) or {}) for s in trigger.get("coins") or []]
    moved = ", ".join(f"{_clean(m.get('name'))} {_pct(m['change_24h'])}" for m in coins if m.get("change_24h") is not None)
    spec = diagram(trigger)
    problems = diagrams.validate(spec)
    if problems:
        raise ValueError(f"{trigger['id']} diagram: {'; '.join(problems)}")
    market = trigger.get("market") or {}
    others = [h for h in trigger.get("headlines") or [] if not cause or h["title"] != cause.get("title")]
    return [
        {"id": "move", "visual": {"type": "move", "coin": chart_coin(trigger)},
         "covers": f"the hook: {label} moved {_pct(lead_move(trigger))} in the last 24 hours; say the size of the "
                   "move and promise to explain what actually happened, no greeting"},
        {"id": "cause", "visual": {"type": "cause"},
         "covers": ("the cause, explained from the headline: " + _clean(cause["title"])
                    + (f" ({_clean(cause.get('summary'))})" if cause.get("summary") else "")) if cause else
                   "no single headline explains the move: say so plainly and describe what the price data shows"},
        {"id": "coins", "visual": {"type": "diagram", "diagram": spec},
         "covers": f"the coins this story moved: {moved}. The picture shows a diagram whose parts appear as they are "
                   "named: name them in this order, each in the sentence where it comes up, with these words: "
                   f"{diagrams.naming_order(spec)}"},
        {"id": "context", "visual": {"type": "context", "coin": chart_coin(trigger)},
         "covers": "context: the 7-day move of the coins" + (
             f" and the total crypto market cap's 24-hour change ({_pct(market['total_cap_change_24h'])})"
             if market.get("total_cap_change_24h") is not None else "")},
        {"id": "watch", "visual": {"type": "watch", "headlines": [h["title"] for h in others[:3]]},
         "covers": "what to watch next, only from these related headlines (no predictions, no levels): "
                   + ("; ".join(_clean(h["title"]) for h in others[:3]) or "the next headlines on this story")},
        {"id": "recap", "visual": {"type": "recap"},
         "covers": "a short recap of the move and its cause, then: this is market data, not financial advice"},
    ]


def facts(trigger: dict) -> dict:
    """The only facts a triggered narration may state: the moves, the cause, the headlines, the market cap."""
    return {"moves": {s: {k: m.get(k) for k in ("name", "price", "change_24h", "change_7d")}
                      for s, m in (trigger.get("moves") or {}).items()},
            "cause": trigger.get("cause"), "headlines": trigger.get("headlines") or [],
            "market": trigger.get("market"), "window_hours": 24, "window_days": 7}


def _bounds(cfg: dict) -> tuple[int, int]:
    tc = cfg.get("triggers") or {}
    return int(tc.get("min_words", MIN_WORDS)), int(tc.get("max_words", MAX_WORDS))


def subscribe_ask(cfg: dict) -> str:
    return _clean((cfg.get("triggers") or {}).get("subscribe_ask") or SUBSCRIBE_ASK)


def _prompt(cfg: dict, trigger: dict, plan: list[dict]) -> str:
    lo, hi = _bounds(cfg)
    ch = cfg.get("channel") or {}
    scenes = "\n".join(f'- "{p["id"]}": {p["covers"]}' for p in plan)
    return f"""You write the narration of a {lo}-{hi} word YouTube market explainer: why crypto just moved.
Channel: {ch.get('display_name', 'CryptoFX Daily')}, a crypto data desk. Tone: calm, plain, neutral. No hype.

FETCHED DATA (the only facts you may state; round numbers sensibly):
{yaml.safe_dump(facts(trigger), allow_unicode=True, sort_keys=False)}
Write narration for each scene, in this order (several short spoken sentences each):
{scenes}

Rules:
- Topic-led: explain the cause and the move it caused; never hype a coin.
- Every number and claim must come from the data above. No predictions, no advice, no price targets.
- No greetings, no "in this video", never ask viewers to subscribe (one short subscribe line is added for you
  after the cause).
- When a scene lists diagram parts, say each part's quoted words in that order, each in the sentence where
  that part comes up.
- "recap" ends: "This is market data, not financial advice."
{rules.NARRATION_RULES}

Return JSON: {{"scenes": [{{"id": "{plan[0]['id']}", "text": "..."}}, ...]}}"""


def _words(scenes: list[dict]) -> int:
    return sum(len((s.get("text") or "").split()) for s in scenes)


def _with_ask(cfg: dict, scenes: list[dict]) -> list[dict]:
    out = []
    for s in scenes:
        s = dict(s)
        if s.get("id") == ASK_SCENE and (s.get("text") or "").strip():
            s["text"] = f"{s['text'].strip()} {subscribe_ask(cfg)}"
        out.append(s)
    return out


def _without_ask(cfg: dict, scenes: list[dict]) -> list[dict]:
    ask = subscribe_ask(cfg)
    return [dict(s, text=_clean((s.get("text") or "").replace(ask, " "))) for s in scenes]


def check_script(cfg: dict, plan: list[dict], scenes: list[dict]) -> list[str]:
    """Deterministic problems ([] = usable): every scene narrated, word bounds, the narration rules, the
    subscribe ask exactly once at the end of the cause scene (no other subscribe mention)."""
    lo, hi = _bounds(cfg)
    texts = {s["id"]: (s.get("text") or "").strip() for s in scenes}
    problems = [f"scene '{p['id']}': no narration" for p in plan if not texts.get(p["id"])]
    words = _words(scenes)
    if not lo <= words <= hi:
        problems.append(f"{words} words (target {lo}-{hi})")
    problems += [f"narration rule: {r}" for r in rules.narration_problems("\n".join(texts.get(p["id"], "")
                                                                                    for p in plan))]
    ask = subscribe_ask(cfg)
    mentions = sum(len(SUBSCRIBE.findall(t)) for t in texts.values())
    if not texts.get(ASK_SCENE, "").endswith(ask) or mentions != len(SUBSCRIBE.findall(ask)):
        problems.append(f"subscribe ask: once, at the end of the '{ASK_SCENE}' scene only")
    return problems


def _values(obj) -> list[float]:
    out = []
    for m in NUMBER.finditer(json.dumps(obj, ensure_ascii=False)):
        try:
            out.append(abs(float(m.group(0).replace(",", ""))))
        except ValueError:
            pass
    return out


def unknown_numbers(text: str, known: dict) -> list[str]:
    """Spoken digit-numbers no fetched value rounds to: n with d decimals is known when a value is within half a
    unit of its last digit, or (for big numbers) within 0.5%."""
    have = _values(known)
    bad = []
    for m in NUMBER.finditer(text or ""):
        raw = m.group(0)
        n = float(raw.replace(",", ""))
        unit = 0.5 * 10 ** -(len(raw.split(".")[1]) if "." in raw else 0)
        if not any(abs(v - n) <= unit + 1e-9 or (n >= 100 and abs(v - n) <= 0.005 * v) for v in have):
            bad.append(raw)
    return list(dict.fromkeys(bad))


def write_script(cfg: dict, trigger: dict, plan: list[dict], log=print) -> dict:
    """{"scenes": [{id, text, visual}], "fact_check": {verdict, issues}} narrated by Gemini from the trigger's
    data, the ask closing the cause scene. A draft with any problem (check_script) is discarded; RuntimeError
    after 3 failed attempts. The passing draft is fact-checked; any failure → RuntimeError at once."""
    problems: list[str] = []
    for attempt in range(1, 4):
        log(f"Writing the triggered narration ({trigger['id']}, attempt {attempt}/3)...")
        answer = generate_json(_prompt(cfg, trigger, plan), _models(cfg), temperature=0.6) or {}
        scenes = _with_ask(cfg, _merge_plan(plan, answer if isinstance(answer, dict) else {})["scenes"])
        problems = check_script(cfg, plan, scenes)
        log(f"Draft: {_words(scenes)} words")
        if not problems:
            return _fact_checked(cfg, trigger, plan, scenes, log)
        log(f"Discarding draft: {'; '.join(problems)}")
    raise RuntimeError(f"Could not produce valid triggered narration in 3 attempts: {'; '.join(problems)}")


def _fact_checked(cfg: dict, trigger: dict, plan: list[dict], scenes: list[dict], log=print) -> dict:
    lo, hi = _bounds(cfg)
    fcfg = {**cfg, "llm": {**(cfg.get("llm") or {}), "min_words": lo, "max_words": hi}}
    known = facts(trigger)
    sent = {"title": _clean(trigger.get("label")),
            "scenes": [{"id": s["id"], "text": s["text"]} for s in _without_ask(cfg, scenes)]}
    log("Fact-checking the triggered narration against the fetched data...")
    verdict, checked, issues = fact_check(fcfg, known, sent, TRIGGERED_RULES)
    log(f"Fact-check: {verdict}" + (f" ({len(issues)} fixes)" if issues else ""))
    if verdict == "reject":
        raise RuntimeError(f"Triggered fact-check failed: verdict reject ({'; '.join(map(str, issues)) or 'no reason'})")
    revised = scenes
    if isinstance(checked, dict) and checked.get("scenes"):
        revised = _with_ask(cfg, _merge_plan(plan, copy.deepcopy(checked))["scenes"])
    problems = check_script(cfg, plan, revised)
    bad = unknown_numbers("\n".join(s.get("text") or "" for s in revised), known)
    if bad:
        problems.append("numbers not in the fetched data: " + ", ".join(bad))
    if problems:
        raise RuntimeError(f"Triggered fact-check failed: {'; '.join(problems)}")
    return {"scenes": revised, "fact_check": {"verdict": verdict, "issues": issues}}


# ─── slides ────────────────────────────────────────────────────────────────

@dataclass
class _Ctx:
    cfg: dict
    trigger: dict
    layout: Layout
    accent: tuple
    brand: str
    footer: str


def _footer(trigger: dict) -> str:
    return f"{DISCLAIMER} · Data: {', '.join(trigger.get('data_sources') or ['Coinbase'])}"


def _base(ctx: _Ctx):
    L = ctx.layout
    img = Image.new("RGB", (L.w, L.h), BG)
    d = ImageDraw.Draw(img)
    x0, x1 = L.content_box[0], L.content_box[2]
    d.text((x0, L.header_y), ctx.brand, font=_font(max(34, L.min_text), True), fill=ctx.accent)
    f = _font(L.min_text, True)
    cw, pad, ch = d.textlength(CHIP, font=f), round(L.min_text * 0.6), round(L.min_text * 1.5)
    d.rounded_rectangle([x1 - cw - 2 * pad, L.header_y, x1, L.header_y + ch], radius=ch // 2, fill=ctx.accent)
    d.text((x1 - cw - pad, L.header_y + ch / 2), CHIP, font=f, fill=BG, anchor="lm")
    d.line([(x0, L.rule_y), (x1, L.rule_y)], fill=PANEL, width=3)
    f = _font(L.min_text)
    lines = _wrap(d, ctx.footer, f, x1 - x0, L.footer_lines)
    lh = round(L.min_text * 1.3)
    y = L.footer_y - (len(lines) - 1) * lh
    for ln in lines:
        d.text(((L.w - d.textlength(ln, font=f)) / 2, y), ln, font=f, fill=MUTED)
        y += lh
    return img, d


def draw_move_chart(img: Image.Image, box, series: list[float], layout: Layout, accent: tuple,
                    label: str | None = None) -> dict:
    """A drawn line chart of `series` inside `box` (any shape): price ticks on the right, the line in green
    (up) or red (down) from first to last point, a dot on the last price, `label` top left.
    Fewer than 2 points → ValueError. Returns {"plot": (x0, y0, x1, y1), "last": (x, y)}."""
    pts = [float(v) for v in series or [] if v is not None]
    if len(pts) < 2:
        raise ValueError("a move chart needs at least 2 prices")
    d = ImageDraw.Draw(img)
    x0, y0, x1, y1 = box
    d.rounded_rectangle(box, radius=18, fill=BG, outline=PANEL, width=3)
    f = _font(layout.min_text)
    lo, hi = min(pts), max(pts)
    pad = (hi - lo) * 0.08 or abs(hi) * 0.01 or 1.0
    lo, hi = lo - pad, hi + pad
    ticks, dec = _ticks(lo, hi, 4)
    tw = max(d.textlength(_fmt_tick(t, dec), font=f) for t in ticks) if ticks else 0
    top = y0 + (round(layout.min_text * 1.8) if label else 24)
    px0, py0, px1, py1 = x0 + 24, top, x1 - 36 - tw, y1 - 24
    if label:
        d.text((x0 + 24, y0 + 14), label, font=_font(layout.min_text, True), fill=MUTED)

    def yv(v):
        return py1 - (v - lo) / (hi - lo) * (py1 - py0)
    for t in ticks:
        y = yv(t)
        d.line([(px0, y), (px1, y)], fill=PANEL, width=2)
        d.text((px1 + 14, y), _fmt_tick(t, dec), font=f, fill=MUTED, anchor="lm")
    colour = UP if pts[-1] >= pts[0] else DOWN
    step = (px1 - px0) / (len(pts) - 1)
    line = [(px0 + i * step, yv(v)) for i, v in enumerate(pts)]
    d.line(line, fill=colour, width=max(4, layout.min_text // 6), joint="curve")
    r = max(8, layout.min_text // 3)
    lx, ly = line[-1]
    d.ellipse([lx - r, ly - r, lx + r, ly + r], fill=colour)
    return {"plot": (px0, py0, px1, py1), "last": (lx, ly)}


def slide_move(ctx: _Ctx, v: dict) -> Image.Image:
    img, d = _base(ctx)
    L, t = ctx.layout, ctx.trigger
    x0, y0, x1, y1 = L.content_box
    m = (t.get("moves") or {}).get(v.get("coin")) or {}
    move = lead_move(t)
    what = "" if t.get("lead") in (t.get("moves") or {}) else "Market cap "
    y = _flow(d, [_heading(ctx, f"WHY {_clean(t.get('label')).upper()} MOVED"),
                  {"text": f"{what}{_pct(move)} in 24 h", "size": 110, "title": True,
                   "fill": UP if move >= 0 else DOWN, "max_lines": 1}], L.content_box, L, who=f"{t['id']} move")
    series = (m.get("series") or [])[-25:]
    if len(series) >= 2:
        draw_move_chart(img, (x0, y + 30, x1, y1), series, L, ctx.accent, label=f"{v.get('coin')} · last 24 h")
    return img


def slide_cause(ctx: _Ctx, v: dict) -> Image.Image:
    img, d = _base(ctx)
    cause = ctx.trigger.get("cause")
    items = [_heading(ctx, "WHAT HAPPENED")]
    if cause:
        items += [{"text": _clean(cause["title"]), "size": 76, "title": True, "fill": FG, "gap": 30, "max_lines": 4},
                  {"text": f"Source: {_clean(cause.get('source')) or 'news'}", "size": 40, "fill": MUTED, "keep": True}]
    else:
        items.append({"text": "No single headline explains this move", "size": 76, "title": True, "fill": FG,
                      "keep": True})
    _flow(d, items, ctx.layout.content_box, ctx.layout, valign="center", max_scale=1.2, who=f"{ctx.trigger['id']} cause")
    return img


def slide_recap(ctx: _Ctx, v: dict) -> Image.Image:
    img, d = _base(ctx)
    t = ctx.trigger
    items = [_heading(ctx, "RECAP")]
    for s in t.get("coins") or []:
        m = (t.get("moves") or {}).get(s)
        if m and m.get("change_24h") is not None:
            items.append({"text": f"{_clean(m['name'])} {_pct(m['change_24h'])}", "size": 56, "bold": True,
                          "fill": FG, "gap": 20, "bullet": "•", "bullet_fill": ctx.accent, "keep": True})
    items.append({"text": "Market data. Not financial advice.", "size": 40, "bold": True, "fill": MUTED,
                  "keep": True})
    _flow(d, items, ctx.layout.content_box, ctx.layout, valign="center", max_scale=1.2, who=f"{t['id']} recap")
    return img


def slide_diagram(ctx: _Ctx, v: dict, show=None) -> Image.Image:
    img, d = _base(ctx)
    L = ctx.layout
    x0, y0, x1, y1 = L.content_box
    y = _flow(d, [_heading(ctx, "WHAT IT MOVED")], L.content_box, L, who=f"{ctx.trigger['id']} coins")
    diagrams.draw(img, (x0, y + 20, x1, y1), v["diagram"], L, ctx.accent, show=show,
                  who=f"{ctx.trigger['id']} coins diagram")
    return img


def slide_context(ctx: _Ctx, v: dict) -> Image.Image:
    img, d = _base(ctx)
    L, t = ctx.layout, ctx.trigger
    x0, y0, x1, y1 = L.content_box
    m = (t.get("moves") or {}).get(v.get("coin")) or {}
    items = [_heading(ctx, "THE BIGGER PICTURE")]
    line = []
    if m.get("change_7d") is not None:
        line.append(f"{_clean(m.get('name'))} {_pct(m['change_7d'])} in 7 days")
    cap = (t.get("market") or {}).get("total_cap_change_24h")
    if cap is not None:
        line.append(f"Total market cap {_pct(cap)} in 24 h")
    if line:
        items.append({"text": " · ".join(line), "size": 52, "bold": True, "fill": FG, "max_lines": 2})
    y = _flow(d, items, L.content_box, L, who=f"{t['id']} context")
    series = m.get("series") or []
    if len(series) >= 2 and y1 - y > 200:
        draw_move_chart(img, (x0, y + 24, x1, y1), series, L, ctx.accent, label=f"{v.get('coin')} · last 7 days")
    return img


def slide_watch(ctx: _Ctx, v: dict) -> Image.Image:
    img, d = _base(ctx)
    items = [_heading(ctx, "WHAT TO WATCH")]
    for h in v.get("headlines") or ["The next headlines on this story"]:
        items.append({"text": _clean(h), "size": 50, "bold": True, "fill": FG, "gap": 22, "bullet": "•",
                      "bullet_fill": ctx.accent, "max_lines": 3})
    _flow(d, items, ctx.layout.content_box, ctx.layout, valign="center", max_scale=1.2,
          who=f"{ctx.trigger['id']} watch")
    return img


RENDERERS = {"move": slide_move, "cause": slide_cause, "diagram": slide_diagram, "context": slide_context,
             "watch": slide_watch, "recap": slide_recap}


def _ctx(cfg: dict, trigger: dict, layout: Layout) -> _Ctx:
    return _Ctx(cfg, trigger, layout, _hex(cfg["video"].get("accent", "FFD400")),
                cfg["channel"].get("display_name", "CryptoFX Daily").upper(), _footer(trigger))


def render_slides(cfg: dict, trigger: dict, plan: list[dict], layout: Layout, workdir: Path) -> list[dict]:
    """One PNG per plan scene in `layout`'s shape → [{"image", "reveal": None, "id"}] (render.build_video's
    slide shape); the diagram scene adds "base" + "steps" (diagrams.step_layers) for reveal.time_steps.
    Unknown visual type → ValueError."""
    for s in plan:
        if (s.get("visual") or {}).get("type") not in RENDERERS:
            raise ValueError(f"unknown triggered visual type '{(s.get('visual') or {}).get('type')}' "
                             f"(scene '{s.get('id')}')")
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    ctx = _ctx(cfg, trigger, layout)
    out = []
    for i, s in enumerate(plan):
        v = s["visual"]
        img = RENDERERS[v["type"]](ctx, v)
        stem = f"triggered_{layout.name}_{i:02d}"
        path = workdir / f"{stem}.png"
        img.save(path)
        slide = {"image": path, "reveal": None, "id": s["id"]}
        if v["type"] == "diagram":
            slide["base"], slide["steps"] = diagrams.step_layers(
                lambda show, v=v: slide_diagram(ctx, v, show=show), diagrams.steps(v["diagram"]), workdir, stem)
        out.append(slide)
    return out
