"""Crypto Basics (the `basics` edition, kind: basics): one beginner topic → narration of its approved
points → the same narration rendered 16:9 (YouTube) and 9:16 (Facebook). Dark until `basics.enabled`.

    sample_topic()                       the hand-written tracer topic (tests/basics/sample_topic.yaml)
    scene_plan(topic)                    hook → one scene per approved point → recap
    write_script(cfg, topic, plan, log)  Gemini narrates the plan; checks: every scene narrated, word
                                         bounds (basics.min_words-max_words), rules.narration_problems;
                                         3 failed attempts → RuntimeError (the edition stops)
    render_slides(cfg, topic, plan, layout, workdir)  title + concept + recap slides in one lesson_slides
                                         layout (LANDSCAPE / PORTRAIT); the caption band is never drawn into
    render_thumbnail(cfg, topic, path)   the 16:9 title slide as a 1280x720 JPEG (placeholder until entry 6)
    metadata(cfg, topic)                 title, description (summary + the disclosure line once), tags

A topic: {id, question, summary, points: [{term, text}]}. The narration may explain only its points.
The look follows lesson_slides (its public layouts and helpers, never changed) with a "CRYPTO BASICS"
header chip instead of the lesson's track label.
"""
from dataclasses import dataclass
from pathlib import Path

import yaml
from PIL import Image, ImageDraw

from autopilot import rules
from autopilot.lesson_slides import BG, DISCLAIMER, FG, LANDSCAPE, MUTED, Layout, _flow, _font, _heading
from autopilot.llm import generate_json
from autopilot.script import _merge_plan, _models
from autopilot.slides import PANEL, _hex, _wrap

SAMPLE = Path(__file__).resolve().parents[1] / "tests" / "basics" / "sample_topic.yaml"
MIN_WORDS, MAX_WORDS = 600, 900  # cfg basics.min_words / max_words
CHIP = "CRYPTO BASICS"
CATEGORY = "27"  # Education (cfg basics.category_id)
THUMB_SIZE = (1280, 720)


def sample_topic() -> dict:
    """The tracer topic: {id, question, summary, points: [{term, text}]}."""
    return yaml.safe_load(SAMPLE.read_text(encoding="utf-8"))


def _clean(text: str) -> str:
    return " ".join(str(text or "").split())


def scene_plan(topic: dict) -> list[dict]:
    """Fixed shape: hook (title slide), one concept scene per approved point (in order), recap.
    Each scene says what its narration covers; a point scene carries its `term` (voice.paced pause)."""
    points = topic.get("points") or []
    if not points:
        raise ValueError(f"{topic.get('id')}: a Basics topic needs at least one point")
    plan = [{"id": "hook", "visual": {"type": "title"},
             "covers": f"the hook: ask \"{_clean(topic['question'])}\" in plain words and say why a beginner "
                       "meets it; promise a simple explanation, no greeting"}]
    for n, p in enumerate(points, 1):
        plan.append({"id": f"point_{n}", "term": _clean(p["term"]),
                     "visual": {"type": "concept", "n": n, "of": len(points), "term": _clean(p["term"]),
                                "text": _clean(p["text"])},
                     "covers": f"approved point {n}, \"{_clean(p['term'])}\": {_clean(p['text'])}"})
    plan.append({"id": "recap", "visual": {"type": "recap", "terms": [_clean(p["term"]) for p in points]},
                 "covers": "a short recap of the points above in a few short sentences, then: "
                           "this is education, not financial advice"})
    return plan


# ─── narration ─────────────────────────────────────────────────────────────

def _bounds(cfg: dict) -> tuple[int, int]:
    bc = cfg.get("basics") or {}
    return int(bc.get("min_words", MIN_WORDS)), int(bc.get("max_words", MAX_WORDS))


def _prompt(cfg: dict, topic: dict, plan: list[dict]) -> str:
    lo, hi = _bounds(cfg)
    ch = cfg.get("channel") or {}
    approved = {"question": _clean(topic["question"]), "summary": _clean(topic.get("summary")),
                "points": [{"term": _clean(p["term"]), "text": _clean(p["text"])} for p in topic["points"]]}
    scenes = "\n".join(f'- "{p["id"]}": {p["covers"]}' for p in plan)
    return f"""You write the narration of a {lo}-{hi} word CRYPTO BASICS explainer video: "{approved['question']}".
Channel: {ch.get('display_name', 'CryptoFX Daily')}, a crypto data desk. Audience: beginners.
Tone: calm, plain and neutral, like a data desk explaining a term. No hype.

APPROVED POINTS (the only things you may explain):
{yaml.safe_dump(approved, allow_unicode=True, sort_keys=False)}
Write narration for each scene, in this order (several short spoken sentences each):
{scenes}

Rules:
- Explain only the approved points above. Add no other fact, number, product, company, date or claim.
- Short sentences (under 20 words), one idea per sentence, plain words; explain each term the first
  time it is used.
- No numbers at all, no predictions, no advice, no performance claims, no prices.
- "recap" says: "This is education, not financial advice."
- No greetings, no "in this video", no "like and subscribe".
{rules.NARRATION_RULES}

Return JSON: {{"scenes": [{{"id": "{plan[0]['id']}", "text": "..."}}, ...]}}"""


def _words(scenes: list[dict]) -> int:
    return sum(len((s.get("text") or "").split()) for s in scenes)


def check_script(cfg: dict, plan: list[dict], scenes: list[dict]) -> list[str]:
    """Deterministic problems with a narration ([] = usable): every scene narrated, word bounds,
    the shared data-desk narration rules."""
    lo, hi = _bounds(cfg)
    texts = {s["id"]: (s.get("text") or "").strip() for s in scenes}
    problems = [f"scene '{p['id']}': no narration" for p in plan if not texts.get(p["id"])]
    words = _words(scenes)
    if not lo <= words <= hi:
        problems.append(f"{words} words (target {lo}-{hi})")
    problems += [f"narration rule: {r}" for r in rules.narration_problems("\n".join(texts.get(p["id"], "")
                                                                                    for p in plan))]
    return problems


def write_script(cfg: dict, topic: dict, plan: list[dict], log=print) -> dict:
    """{"scenes": [{id, text, visual, term?}]} narrated by Gemini from the topic's approved points.
    A draft with any problem (check_script) is discarded; RuntimeError after 3 failed attempts."""
    problems: list[str] = []
    for attempt in range(1, 4):
        log(f"Writing the Basics narration ({topic['id']}, attempt {attempt}/3)...")
        pkg = _merge_plan(plan, generate_json(_prompt(cfg, topic, plan), _models(cfg), temperature=0.6) or {})
        for s, p in zip(pkg["scenes"], plan):
            if p.get("term"):
                s["term"] = p["term"]
        problems = check_script(cfg, plan, pkg["scenes"])
        log(f"Draft: {_words(pkg['scenes'])} words")
        if not problems:
            return {"scenes": pkg["scenes"]}
        log(f"Discarding draft: {'; '.join(problems)}")
    raise RuntimeError(f"Could not produce valid Basics narration in 3 attempts: {'; '.join(problems)}")


# ─── slides ────────────────────────────────────────────────────────────────

@dataclass
class _Ctx:
    cfg: dict
    topic: dict
    layout: Layout
    accent: tuple
    brand: str


def _base(ctx: _Ctx):
    """Ground, brand line, the CRYPTO BASICS chip, divider and the disclaimer footer (as lesson_slides)."""
    L = ctx.layout
    img = Image.new("RGB", (L.w, L.h), BG)
    d = ImageDraw.Draw(img)
    x0, x1 = L.content_box[0], L.content_box[2]
    d.text((x0, L.header_y), ctx.brand, font=_font(max(34, L.min_text), True), fill=ctx.accent)
    f = _font(L.min_text, True)
    cw, pad = d.textlength(CHIP, font=f), round(L.min_text * 0.6)
    ch = round(L.min_text * 1.5)
    d.rounded_rectangle([x1 - cw - 2 * pad, L.header_y, x1, L.header_y + ch], radius=ch // 2, fill=ctx.accent)
    d.text((x1 - cw - pad, L.header_y + ch / 2), CHIP, font=f, fill=BG, anchor="lm")
    d.line([(x0, L.rule_y), (x1, L.rule_y)], fill=PANEL, width=3)
    f = _font(L.min_text)
    lines = _wrap(d, DISCLAIMER, f, x1 - x0, L.footer_lines)
    lh = round(L.min_text * 1.3)
    y = L.footer_y - (len(lines) - 1) * lh
    for ln in lines:
        d.text(((L.w - d.textlength(ln, font=f)) / 2, y), ln, font=f, fill=MUTED)
        y += lh
    return img, d


def slide_title(ctx: _Ctx, v: dict) -> Image.Image:
    img, d = _base(ctx)
    q = _clean(ctx.topic["question"])
    hero, _, sub = q.partition(" (")
    items = [{"text": hero, "size": 150, "title": True, "fill": FG, "gap": 26, "max_lines": 4}]
    if sub.strip(" )"):
        items.append({"text": sub.strip(" )"), "size": 60, "bold": True, "fill": ctx.accent, "max_lines": 2})
    _flow(d, items, ctx.layout.content_box, ctx.layout, valign="center", max_scale=1.3, who=f"{ctx.topic['id']} title")
    return img


def slide_concept(ctx: _Ctx, v: dict) -> Image.Image:
    img, d = _base(ctx)
    items = [_heading(ctx, f"KEY IDEA {v['n']} OF {v['of']}"),
             {"text": v["term"], "size": 100, "title": True, "fill": FG, "gap": 30, "max_lines": 2},
             {"text": v["text"], "size": 48, "fill": FG, "keep": True}]
    _flow(d, items, ctx.layout.content_box, ctx.layout, valign="center", max_scale=1.3,
          who=f"{ctx.topic['id']} point {v['n']}")
    return img


def slide_recap(ctx: _Ctx, v: dict) -> Image.Image:
    img, d = _base(ctx)
    items = [_heading(ctx, "RECAP")]
    items += [{"text": t, "size": 50, "bold": True, "fill": FG, "gap": 22, "bullet": "•", "bullet_fill": ctx.accent,
               "keep": True} for t in v.get("terms") or []]
    items.append({"text": "Education only. Not financial advice.", "size": 40, "bold": True, "fill": MUTED,
                  "gap": 0, "keep": True})
    _flow(d, items, ctx.layout.content_box, ctx.layout, valign="center", max_scale=1.3, who=f"{ctx.topic['id']} recap")
    return img


RENDERERS = {"title": slide_title, "concept": slide_concept, "recap": slide_recap}


def _ctx(cfg: dict, topic: dict, layout: Layout) -> _Ctx:
    return _Ctx(cfg, topic, layout, _hex(cfg["video"].get("accent", "FFD400")),
                cfg["channel"].get("display_name", "CryptoFX Daily").upper())


def render_slides(cfg: dict, topic: dict, plan: list[dict], layout: Layout, workdir: Path) -> list[dict]:
    """One PNG per plan scene in `layout`'s shape → [{"image", "reveal": None, "id"}] (render.build_video's
    slide shape; no draw-in). Unknown visual type → ValueError."""
    for s in plan:
        if (s.get("visual") or {}).get("type") not in RENDERERS:
            raise ValueError(f"unknown Basics visual type '{(s.get('visual') or {}).get('type')}' (scene '{s.get('id')}')")
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    ctx = _ctx(cfg, topic, layout)
    out = []
    for i, s in enumerate(plan):
        img = RENDERERS[s["visual"]["type"]](ctx, s["visual"])
        path = workdir / f"basics_{layout.name}_{i:02d}.png"
        img.save(path)
        out.append({"image": path, "reveal": None, "id": s["id"]})
    return out


def render_thumbnail(cfg: dict, topic: dict, path: Path) -> Path:
    """The 16:9 title slide scaled to a 1280x720 JPEG (a placeholder; thumbnail design is entry 6)."""
    img = slide_title(_ctx(cfg, topic, LANDSCAPE), {"type": "title"}).resize(THUMB_SIZE, Image.LANCZOS)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, "JPEG", quality=92)
    return path


# ─── metadata ──────────────────────────────────────────────────────────────

def metadata(cfg: dict, topic: dict) -> dict:
    """{title, description, tags, category_id, fb_title, fb_description}: the topic's question as the
    title; description = the short summary + the disclosure line exactly once (rules.disclosure)."""
    line = rules.disclosure(cfg, "basics")
    about = rules.without_disclosure(_clean(topic.get("summary")), line)
    description = "\n\n".join(p for p in (about, line) if p)
    tags: list[str] = []
    for t in ("crypto basics", "crypto explained", *(_clean(p["term"]).lower() for p in topic.get("points") or [])):
        if t and t not in tags:
            tags.append(t)
    title = _clean(topic["question"])[:100]
    return {"title": title, "description": description, "tags": tags,
            "category_id": str((cfg.get("basics") or {}).get("category_id") or CATEGORY),
            "fb_title": title, "fb_description": description}
