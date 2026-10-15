"""Triggered video (the `triggered` edition, kind: triggered): "why crypto just moved", topic-led, from one
trigger (autopilot/triggers.py) → narration from the trigger's fetched data only → a 16:9 YouTube video.
Dark until `triggers.enabled` (timed runs skip; manual runs make it).

    scene_plan(trigger)                  fixed shape: the move → the cause → recap
    facts(trigger)                       the only facts the narration may state (fetched numbers + headlines)
    write_script(cfg, trigger, plan, log)  Gemini narrates the plan; every scene narrated and
                                         rules.narration_problems; 3 failed attempts → RuntimeError
    render_slides(cfg, trigger, plan, layout, workdir)  one PNG per scene (lesson_slides LANDSCAPE / PORTRAIT)
    draw_move_chart(img, box, series, layout, accent, label)  the drawn line chart of a move (both shapes)
"""
from dataclasses import dataclass
from pathlib import Path

import yaml
from PIL import Image, ImageDraw

from autopilot import rules
from autopilot.lesson_slides import (BG, DISCLAIMER, FG, MUTED, Layout, _flow, _fmt_tick, _font, _heading, _ticks,
                                     _title_font)
from autopilot.llm import generate_json
from autopilot.script import _merge_plan, _models
from autopilot.slides import DOWN, PANEL, UP, _hex, _wrap

CHIP = "MARKET MOVE"
CATEGORY = "25"  # News & Politics (cfg triggers.category_id)


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


# ─── plan + narration ──────────────────────────────────────────────────────

def scene_plan(trigger: dict) -> list[dict]:
    label = trigger.get("label") or trigger.get("lead")
    cause = trigger.get("cause")
    return [
        {"id": "move", "visual": {"type": "move", "coin": trigger["lead"]},
         "covers": f"the hook: {label} moved {_pct(lead_move(trigger))} in the last 24 hours; say the size of the "
                   "move and promise to explain what actually happened, no greeting"},
        {"id": "cause", "visual": {"type": "cause"},
         "covers": ("the cause, from the headline: " + _clean(cause["title"])) if cause else
                   "no single headline explains the move: say so plainly and describe what the price data shows"},
        {"id": "recap", "visual": {"type": "recap"},
         "covers": "a short recap of the move and its cause, then: this is market data, not financial advice"},
    ]


def facts(trigger: dict) -> dict:
    """The only facts a triggered narration may state: the moves, the cause and the related headlines."""
    return {"moves": {s: {k: m.get(k) for k in ("name", "price", "change_24h", "change_7d")}
                      for s, m in (trigger.get("moves") or {}).items()},
            "cause": trigger.get("cause"), "headlines": trigger.get("headlines") or [],
            "market": trigger.get("market"), "window_hours": 24, "window_days": 7}


def _prompt(cfg: dict, trigger: dict, plan: list[dict]) -> str:
    ch = cfg.get("channel") or {}
    scenes = "\n".join(f'- "{p["id"]}": {p["covers"]}' for p in plan)
    return f"""You write the narration of a short YouTube market explainer: why crypto just moved.
Channel: {ch.get('display_name', 'CryptoFX Daily')}, a crypto data desk. Tone: calm, plain, neutral. No hype.

FETCHED DATA (the only facts you may state; round numbers sensibly):
{yaml.safe_dump(facts(trigger), allow_unicode=True, sort_keys=False)}
Write narration for each scene, in this order (several short spoken sentences each):
{scenes}

Rules:
- Topic-led: explain the cause and the move; never hype a coin.
- Every number and claim must come from the data above. No predictions, no advice, no price targets.
{rules.NARRATION_RULES}

Return JSON: {{"scenes": [{{"id": "{plan[0]['id']}", "text": "..."}}, ...]}}"""


def check_script(cfg: dict, plan: list[dict], scenes: list[dict]) -> list[str]:
    texts = {s["id"]: (s.get("text") or "").strip() for s in scenes}
    problems = [f"scene '{p['id']}': no narration" for p in plan if not texts.get(p["id"])]
    problems += [f"narration rule: {r}" for r in rules.narration_problems("\n".join(texts.get(p["id"], "")
                                                                                    for p in plan))]
    return problems


def write_script(cfg: dict, trigger: dict, plan: list[dict], log=print) -> dict:
    """{"scenes": [{id, text, visual}]} narrated by Gemini from the trigger's data; a draft with any problem
    (check_script) is discarded; RuntimeError after 3 failed attempts (the edition stops)."""
    problems: list[str] = []
    for attempt in range(1, 4):
        log(f"Writing the triggered narration ({trigger['id']}, attempt {attempt}/3)...")
        answer = generate_json(_prompt(cfg, trigger, plan), _models(cfg), temperature=0.6) or {}
        scenes = _merge_plan(plan, answer if isinstance(answer, dict) else {})["scenes"]
        problems = check_script(cfg, plan, scenes)
        if not problems:
            return {"scenes": scenes}
        log(f"Discarding draft: {'; '.join(problems)}")
    raise RuntimeError(f"Could not produce valid triggered narration in 3 attempts: {'; '.join(problems)}")


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
    y = _flow(d, [_heading(ctx, f"WHY {_clean(t.get('label')).upper()} MOVED"),
                  {"text": f"{_pct(move)} in 24 h", "size": 110, "title": True, "fill": UP if move >= 0 else DOWN,
                   "max_lines": 1}], L.content_box, L, who=f"{t['id']} move")
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


RENDERERS = {"move": slide_move, "cause": slide_cause, "recap": slide_recap}


def _ctx(cfg: dict, trigger: dict, layout: Layout) -> _Ctx:
    return _Ctx(cfg, trigger, layout, _hex(cfg["video"].get("accent", "FFD400")),
                cfg["channel"].get("display_name", "CryptoFX Daily").upper(), _footer(trigger))


def render_slides(cfg: dict, trigger: dict, plan: list[dict], layout: Layout, workdir: Path) -> list[dict]:
    """One PNG per plan scene in `layout`'s shape → [{"image", "reveal": None, "id"}] (render.build_video's
    slide shape). Unknown visual type → ValueError."""
    for s in plan:
        if (s.get("visual") or {}).get("type") not in RENDERERS:
            raise ValueError(f"unknown triggered visual type '{(s.get('visual') or {}).get('type')}' "
                             f"(scene '{s.get('id')}')")
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    ctx = _ctx(cfg, trigger, layout)
    out = []
    for i, s in enumerate(plan):
        img = RENDERERS[s["visual"]["type"]](ctx, s["visual"])
        path = workdir / f"triggered_{layout.name}_{i:02d}.png"
        img.save(path)
        out.append({"image": path, "reveal": None, "id": s["id"]})
    return out
