"""Standalone Shorts (epic-standalone-shorts, kind: short): an original 30-40 second vertical piece with its own hook
and script, written from one segment of a long video's Shorts material (autopilot/material.py). Dark until
`shorts.enabled`: timed short_a / short_b runs log and skip; manual runs make and publish.

    load_materials(root, log)            every valid data/material/*.json (invalid files logged and skipped)
    key(m)                               "<source kind>-<source id>" (what a Short's history entry names)
    used_segments(history)               {(material key, segment id)} already used by published Shorts
    pick_concept(materials, history)     (material, segment) of the oldest Basics / Lesson material with an
                                         unused segment, else None
    opening_problems(text)               a subscribe ask in the first sentence → [reason] (narration-rules.md)
    check_script(cfg, pkg, known)        deterministic problems: every scene narrated, word bounds, narration
                                         rules, no subscribe ask in the opening, spoken numbers in the facts
    write_concept(cfg, m, seg, log)      Gemini writes {hook, scenes: hook / explain / payoff}; 3 attempts
    render_slides(cfg, m, seg, pkg, wd)  9:16: the hook card (frame 0, `cover`) → the term, the segment's diagram
                                         with step reveal (diagrams.step_layers) or its fact, the payoff card
    metadata(cfg, m, seg, pkg)           title = hook, description, tags; reel_caption(meta, cfg) for Facebook
"""
import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw

from autopilot import diagrams, material, rules
from autopilot.basics import unknown_numbers as _concept_unknown
from autopilot.lesson_slides import BG, FG, MUTED, PORTRAIT, Layout, _flow, _font
from autopilot.llm import generate_json
from autopilot.script import _models
from autopilot.slides import PANEL, _hex, _wrap

MIN_WORDS, MAX_WORDS = 70, 105  # cfg shorts.min_words / max_words: 30-40 s at +0%
SCENES = ("hook", "explain", "payoff")
CONCEPT_SOURCES = ("basics", "lesson")
CHIPS = {"basics": "CRYPTO BASICS", "lesson": "TRADING LESSON", "triggered": "WHY IT MOVED", "recap": "WEEKLY RECAP"}
DISCLAIMER = "Education only · Not financial advice"
SUBSCRIBE_OPEN = re.compile(r"\bsubscri[bp]\w*|\bhit the (?:bell|like)\b|\blike and (?:share|follow)\b|"
                            r"\bfollow (?:us|the channel|for more)\b|\bturn on (?:the )?notifications?\b", re.I)
_SENTENCE = re.compile(r"(?<=[.!?])\s+")
DIAGRAM_GAP = 44


def _clean(text) -> str:
    return " ".join(str(text or "").split())


def _log(msg):
    print(msg)


# ─── material ──────────────────────────────────────────────────────────────

def key(m: dict) -> str:
    return f"{m['source']['kind']}-{m['source']['id']}"


def load_materials(root: Path, log=_log) -> list[dict]:
    out = []
    for p in sorted((Path(root) / material.FOLDER).glob("*.json")):
        try:
            m = material.load(p)
            problems = material.validate(m)
        except Exception as e:
            problems = [str(e)]
        if problems:
            log(f"Shorts: material {p.name} skipped: {'; '.join(problems)}")
            continue
        out.append(m)
    return out


def _published(m: dict) -> str:
    return str(m.get("published_at") or "")


def _shorts(history) -> list[dict]:
    return [v for v in history.uploaded() if v.get("kind") == "short"]


def used_segments(history) -> set[tuple[str, str]]:
    return {(v.get("material"), v.get("segment")) for v in _shorts(history) if v.get("material")}


def pick_concept(materials: list[dict], history) -> tuple[dict, dict] | None:
    """The oldest Basics / Lesson material's first unused segment (concept segments before the overview)."""
    used = used_segments(history)
    for m in sorted((m for m in materials if m["source"]["kind"] in CONCEPT_SOURCES), key=_published):
        segs = sorted(m["segments"], key=lambda s: s.get("kind") != "concept")
        for s in segs:
            if (key(m), s["id"]) not in used:
                return m, s
    return None


# ─── script ────────────────────────────────────────────────────────────────

def _bounds(cfg: dict) -> tuple[int, int]:
    sc = cfg.get("shorts") or {}
    return int(sc.get("min_words", MIN_WORDS)), int(sc.get("max_words", MAX_WORDS))


def first_sentence(text: str) -> str:
    parts = _SENTENCE.split(_clean(text), maxsplit=1)
    return parts[0] if parts else ""


def opening_problems(text: str) -> list[str]:
    """A Short never opens with a subscribe ask (narration-rules.md, Delivery): the first sentence is checked."""
    m = SUBSCRIBE_OPEN.search(first_sentence(text))
    return [f'subscribe ask in the opening: "{m.group(0)}"'] if m else []


def _words(scenes: list[dict]) -> int:
    return sum(len((s.get("text") or "").split()) for s in scenes)


def check_script(cfg: dict, pkg: dict, known: dict, unknown=_concept_unknown) -> list[str]:
    lo, hi = _bounds(cfg)
    scenes = pkg.get("scenes") or []
    texts = {s.get("id"): _clean(s.get("text")) for s in scenes}
    out = [f"scene '{k}': no narration" for k in SCENES if not texts.get(k)]
    if not _clean(pkg.get("hook")):
        out.append("no hook")
    n = _words(scenes)
    if not lo <= n <= hi:
        out.append(f"{n} words (target {lo}-{hi})")
    spoken = " ".join(texts.get(k, "") for k in SCENES)
    out += [f"narration rule: {r}" for r in rules.narration_problems(spoken)]
    out += opening_problems(spoken)
    bad = unknown(spoken, known)
    if bad:
        out.append("numbers not in the material: " + ", ".join(bad))
    return out


def _parse(answer) -> dict:
    a = answer if isinstance(answer, dict) else {}
    got = {s.get("id"): _clean(s.get("text")) for s in a.get("scenes") or [] if isinstance(s, dict)}
    return {"hook": _clean(a.get("hook")), "card": _clean(a.get("card")),
            "scenes": [{"id": k, "text": got.get(k, "")} for k in SCENES]}


def _concept_prompt(cfg: dict, m: dict, seg: dict, problems: list[str]) -> str:
    lo, hi = _bounds(cfg)
    ch = cfg.get("channel") or {}
    src = {"episode": m["source"]["title"], "term": seg["term"], "facts": seg["facts"],
           "episode_narration": seg["narration"], "hook_ideas": seg["hooks"]}
    redo = ("\nYour last draft was rejected: " + "; ".join(problems) + "\n") if problems else ""
    return f"""You write a NEW standalone YouTube Short ({lo}-{hi} words, 30-40 seconds) for
{ch.get('display_name', 'CryptoFX Daily')}, a crypto data desk. It explains ONE idea from a longer episode, with its
own hook and its own wording: never copy the episode narration's sentences.

SOURCE (the only facts you may state):
{json.dumps(src, ensure_ascii=False, indent=1)}

Write three scenes:
- "hook": one curiosity question or tension line about the idea (the first sentence is the hook).
- "explain": the idea in short, plain sentences; name each part of the picture as it comes up.
- "payoff": the one thing to remember, looping back to the hook.
Rules:
- Only the facts above. No other number, product, company, date or claim; no prices, predictions or advice.
- Never ask viewers to subscribe, like or follow, and above all never in the opening.
- No greetings, no "in this video", no sign-off.
- "hook" (the title): a question of 60 characters or fewer, no date, no hashtag, no hype words.
{rules.NARRATION_RULES}{redo}
Return JSON: {{"hook": "...", "scenes": [{{"id": "hook", "text": "..."}}, {{"id": "explain", "text": "..."}},
{{"id": "payoff", "text": "..."}}]}}"""


def concept_facts(m: dict, seg: dict) -> dict:
    return {"term": seg["term"], "facts": seg["facts"], "narration": seg["narration"], "title": m["source"]["title"]}


def write_concept(cfg: dict, m: dict, seg: dict, log=_log) -> dict:
    """{hook, card, scenes} for a concept Short of `seg`; a draft with any check_script problem is discarded
    (its problems are sent back); RuntimeError after 3 attempts."""
    problems: list[str] = []
    known = concept_facts(m, seg)
    for attempt in range(1, 4):
        log(f"Writing the Short script ({key(m)} · {seg['id']}, attempt {attempt}/3)...")
        pkg = _parse(generate_json(_concept_prompt(cfg, m, seg, problems), _models(cfg), temperature=0.8))
        problems = check_script(cfg, pkg, known)
        if not problems:
            for s in pkg["scenes"]:
                if s["id"] == "explain":
                    s["term"] = seg["term"]
            log(f"Short script: {_words(pkg['scenes'])} words · hook: {pkg['hook']}")
            return pkg
        log(f"Discarding Short draft: {'; '.join(problems)}")
    raise RuntimeError(f"Could not write a valid Short in 3 attempts: {'; '.join(problems)}")


# ─── slides (9:16) ─────────────────────────────────────────────────────────

@dataclass
class _Ctx:
    cfg: dict
    layout: Layout
    accent: tuple
    brand: str
    chip: str
    footer: str


def _ctx(cfg: dict, m: dict, layout: Layout = PORTRAIT) -> _Ctx:
    return _Ctx(cfg, layout, _hex(cfg["video"].get("accent", "FFD400")),
                cfg["channel"].get("display_name", "CryptoFX Daily").upper(),
                CHIPS.get(m["source"]["kind"], "CRYPTO"), DISCLAIMER)


def _base(ctx: _Ctx):
    L = ctx.layout
    img = Image.new("RGB", (L.w, L.h), BG)
    d = ImageDraw.Draw(img)
    x0, x1 = L.content_box[0], L.content_box[2]
    d.text((x0, L.header_y), ctx.brand, font=_font(max(34, L.min_text), True), fill=ctx.accent)
    f = _font(L.min_text, True)
    cw, pad, ch = d.textlength(ctx.chip, font=f), round(L.min_text * 0.6), round(L.min_text * 1.5)
    d.rounded_rectangle([x1 - cw - 2 * pad, L.header_y, x1, L.header_y + ch], radius=ch // 2, fill=ctx.accent)
    d.text((x1 - cw - pad, L.header_y + ch / 2), ctx.chip, font=f, fill=BG, anchor="lm")
    d.line([(x0, L.rule_y), (x1, L.rule_y)], fill=PANEL, width=3)
    f = _font(L.min_text)
    lines = _wrap(d, ctx.footer, f, x1 - x0, L.footer_lines)
    lh = round(L.min_text * 1.3)
    y = L.footer_y - (len(lines) - 1) * lh
    for ln in lines:
        d.text(((L.w - d.textlength(ln, font=f)) / 2, y), ln, font=f, fill=MUTED)
        y += lh
    return img, d


def hook_card(ctx: _Ctx, text: str) -> Image.Image:
    """Frame 0: the hook in huge type on the channel ground (no captions over it)."""
    img, d = _base(ctx)
    L = ctx.layout
    x0, y0, x1, y1 = L.content_box
    _flow(d, [{"text": _clean(text).upper(), "size": 190, "title": True, "fill": FG, "gap": 40, "max_lines": 5},
              {"text": "▬▬▬", "size": 60, "bold": True, "fill": ctx.accent, "max_lines": 1}],
          (x0, y0, x1, y1), L, valign="center", max_scale=1.0, who="hook card")
    return img


def term_slide(ctx: _Ctx, term: str, sub: str = "") -> Image.Image:
    img, d = _base(ctx)
    items = [{"text": term, "size": 130, "title": True, "fill": FG, "gap": 30, "max_lines": 3}]
    if sub:
        items.append({"text": sub, "size": 56, "bold": True, "fill": ctx.accent, "max_lines": 3})
    _flow(d, items, ctx.layout.content_box, ctx.layout, valign="center", max_scale=1.2, who="term slide")
    return img


def diagram_slide(ctx: _Ctx, term: str, spec: dict, show=None) -> Image.Image:
    img, d = _base(ctx)
    L = ctx.layout
    x0, y0, x1, y1 = L.content_box
    y = _flow(d, [{"text": term, "size": 88, "title": True, "fill": FG, "max_lines": 2}], L.content_box, L,
              who="Short diagram heading")
    diagrams.draw(img, (x0, y + DIAGRAM_GAP, x1, y1), spec, L, ctx.accent, show=show, who="Short diagram")
    return img


def text_slide(ctx: _Ctx, heading: str, text: str) -> Image.Image:
    img, d = _base(ctx)
    _flow(d, [{"text": heading, "size": 48, "bold": True, "fill": ctx.accent, "gap": 34, "max_lines": 1},
              {"text": text, "size": 64, "bold": True, "fill": FG, "max_lines": 9}],
          ctx.layout.content_box, ctx.layout, valign="center", max_scale=1.2, who="Short text slide")
    return img


def _cover(ctx: _Ctx, card_text: str, follow_img: Image.Image, workdir: Path) -> tuple[dict, Path]:
    card = workdir / "thumbnail.jpg"
    hook_card(ctx, card_text).save(card, quality=92)
    follow = workdir / "short_01_follow.png"
    follow_img.save(follow)
    return {"image": card, "cover": True, "follow": {"image": follow, "reveal": None}, "reveal": None,
            "id": "hook"}, card


def render_slides(cfg: dict, m: dict, seg: dict, pkg: dict, workdir: Path) -> tuple[list[dict], Path]:
    """The concept Short's slides (one per scene) → (slides, hook card path = the thumbnail / Reel cover)."""
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    ctx = _ctx(cfg, m)
    cover, card = _cover(ctx, pkg.get("card") or pkg["hook"], term_slide(ctx, seg["term"]), workdir)
    out = [cover]
    path = workdir / "short_02.png"
    if seg.get("diagram"):
        spec = seg["diagram"]
        diagram_slide(ctx, seg["term"], spec).save(path)
        slide = {"image": path, "reveal": None, "id": "explain"}
        slide["base"], slide["steps"] = diagrams.step_layers(
            lambda show: diagram_slide(ctx, seg["term"], spec, show=show), diagrams.steps(spec), workdir, "short_02")
    else:
        text_slide(ctx, seg["term"].upper(), seg["facts"][0]).save(path)
        slide = {"image": path, "reveal": None, "id": "explain"}
    out.append(slide)
    path = workdir / "short_03.png"
    text_slide(ctx, "REMEMBER", seg["facts"][0]).save(path)
    out.append({"image": path, "reveal": None, "id": "payoff"})
    return out, card


# ─── packaging ─────────────────────────────────────────────────────────────

def hashtags(m: dict, seg: dict | None = None) -> list[str]:
    tags = ["#Crypto", "#CryptoBasics" if m["source"]["kind"] == "basics" else "#Trading"]
    text = " ".join([m["source"]["title"], (seg or {}).get("term", "")]).lower()
    for word, tag in (("bitcoin", "#Bitcoin"), ("ethereum", "#Ethereum"), ("ether", "#Ethereum")):
        if word in text and tag not in tags:
            tags.append(tag)
    return tags[:4] + ["#Shorts"]


def metadata(cfg: dict, m: dict, seg: dict, pkg: dict) -> dict:
    line = rules.disclosure(cfg, "shorts")
    body = rules.without_disclosure(_clean(" ".join(s["text"] for s in pkg["scenes"] if s["id"] == "payoff")), line)
    tags = hashtags(m, seg)
    description = "\n\n".join(p for p in (pkg["hook"], body, f"From: {m['source']['title']}", "⚠️ " + line,
                                          " ".join(tags)) if p)
    return {"title": pkg["hook"], "description": description,
            "tags": [t.lstrip("#") for t in tags if t != "#Shorts"] + [seg["term"]]}


def reel_caption(meta: dict, cfg: dict) -> str:
    """The Facebook Reel caption from the same metadata (no #Shorts)."""
    return "\n\n".join(p for p in meta["description"].replace(" #Shorts", "").split("\n\n") if p).strip()


def now_iso(now: datetime) -> str:
    return now.isoformat(timespec="seconds")
