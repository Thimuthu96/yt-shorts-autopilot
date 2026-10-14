"""Crypto Basics (the `basics` edition, kind: basics): one beginner topic → narration of its approved
points → the same narration rendered 16:9 (YouTube) and 9:16 (Facebook). Dark until `basics.enabled`.

    sample_topic()                       the hand-written tracer topic (tests/basics/sample_topic.yaml)
    load_topics(path=TOPICS)             the owner-approved topic list (basics/topics.yaml; list order = queue)
    validate_topic(topic) -> [reason]    one topic's problems ([] = usable), one reason each: fields and types
                                         (unknown keys rejected), the question (a "?", ≤ 100 characters,
                                         rules.title_problems), the thumbnail (rules.thumbnail_text_problems,
                                         1-3 words), rules.narration_problems on the summary and every point's
                                         term and text, diagrams.validate on every point's diagram
    validate_topics(topics) -> ["<id>: <reason>"]  every topic's problems + duplicate ids / questions
                                         (questions compared case- and whitespace-insensitively)
    pick(topics, history) -> topic|None  the first `approved: true` topic (list order) that no uploaded
                                         kind: basics history entry (counting or not) has as its `topic`
    scene_plan(topic)                    hook → one scene per approved point → recap; a point's `diagram`
                                         (autopilot/diagrams.py) is validated here (problems → ValueError) and
                                         its parts' naming order goes into the scene's `covers`
    write_script(cfg, topic, plan, log)  Gemini narrates the plan; the fixed subscribe ask (subscribe_ask)
                                         is added at the end of the first point scene (the first payoff);
                                         checks (check_script): every scene narrated, word bounds
                                         (basics.min_words-max_words), rules.narration_problems, the ask once
                                         and only there; 3 failed attempts → RuntimeError. The passing draft is
                                         fact-checked (script.fact_check against facts(topic), its package
                                         merged back, then every spoken digit-number, small ones too, must
                                         be in the approved facts: unknown_numbers); a reject, a
                                         revised draft with problems or an unknown number → RuntimeError at
                                         once (the edition stops, no retry)
    facts(topic)                         the only facts: question, summary, approved points (term + text)
    render_slides(cfg, topic, plan, layout, workdir)  title + concept + recap slides in one lesson_slides
                                         layout (LANDSCAPE / PORTRAIT); the caption band is never drawn into.
                                         A point with a diagram: "KEY IDEA n OF m" + the term + the drawn
                                         diagram (the point text is spoken, not shown), plus "base" + "steps"
                                         (diagrams.step_layers) so reveal.time_steps fades each part in as the
                                         narration names it; without one: the text concept slide
    packaging_problems(topic)            the title (question verbatim: rules.title_problems, ≤ 100 chars) and the
                                         thumbnail text (1-3 words, rules.thumbnail_text_problems); [] = ok
    render_thumbnail(cfg, topic, path)   1280x720: brand + chip, the 1-3 thumbnail words, the first point's
                                         diagram (notes dropped), else a drawn coin icon
    chapters(plan, audio)                lesson_meta's chapter timing rule, named Intro / terms / Recap
    metadata(cfg, topic, chapters)       title = question verbatim, description (summary, key ideas, chapters,
                                         the disclosure line once, hashtags), tags, Facebook title + text

A topic: {id, question, summary, points: [{term, text, diagram?}]} (a basics/topics.yaml topic also carries
`thumbnail` and `approved`, and every point has a diagram). The narration may explain only its points.
The look follows lesson_slides (its public layouts and helpers, never changed) with a "CRYPTO BASICS"
header chip instead of the lesson's track label.
"""
import copy
import json
import re
from dataclasses import dataclass
from pathlib import Path

import yaml
from PIL import Image, ImageDraw

from autopilot import diagrams, rules
from autopilot.lesson_slides import BG, DISCLAIMER, FG, LANDSCAPE, MUTED, Layout, _flow, _font, _heading
from autopilot.llm import generate_json
from autopilot.script import _merge_plan, _models, fact_check
from autopilot.slides import PANEL, _hex, _wrap

SAMPLE = Path(__file__).resolve().parents[1] / "tests" / "basics" / "sample_topic.yaml"
TOPICS = Path(__file__).resolve().parents[1] / "basics" / "topics.yaml"
TOPIC_FIELDS = ("id", "question", "thumbnail", "summary", "points", "approved")
POINT_FIELDS = ("term", "text", "diagram")
SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")  # kebab-case
MAX_QUESTION = 100  # characters (YouTube's title limit)
THUMB_WORDS = 3  # packaging.md: 1-3 words on a Basics thumbnail
MIN_POINTS = 4  # Shorts material needs ≥ 5 segments (overview + one per point; autopilot/material.py)
MIN_WORDS, MAX_WORDS = 600, 900  # cfg basics.min_words / max_words
CHIP = "CRYPTO BASICS"
CATEGORY = "27"  # Education (cfg basics.category_id)
THUMB_SIZE = (1280, 720)
DIAGRAM_GAP = 44  # px between the term and the diagram
# the thumbnail's right column: taller than wide, so diagrams lay out stacked (flow / timeline down)
THUMB_COLUMN = Layout("thumb", 560, 720, (720, 720), (0, 0, 560, 720), min_text=24)
SUBSCRIBE_ASK = "If this helped, subscribe for the next Crypto Basics explainer."  # cfg basics.subscribe_ask
SUBSCRIBE = re.compile(r"\bsubscri[bp]\w*", re.I)  # subscribe(d/r/rs/ing), subscription(s)
NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")
ASK_SCENE = "point_1"  # the first payoff: the ask closes the first explained point, never the opening
BASICS_RULES = """
3. This is a beginner explainer. The data above are its ONLY approved facts: every claim must follow from
   them. Remove any number, date, name, product, company or claim the approved points do not state. Keep
   the plain, neutral data-desk tone; no first person, advice, predictions or prices.
   Keep every scene id and the words that name each diagram part."""


def sample_topic() -> dict:
    """The tracer topic: {id, question, summary, points: [{term, text}]}."""
    return yaml.safe_load(SAMPLE.read_text(encoding="utf-8"))


def _clean(text: str) -> str:
    return " ".join(str(text or "").split())


# ─── topic list (basics/topics.yaml) ───────────────────────────────────────

def load_topics(path: Path = TOPICS) -> list:
    """The `topics:` list of basics/topics.yaml, in file order (= the queue). Not validated here."""
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("topics"), list):
        raise ValueError(f"{path}: needs a top-level `topics:` list")
    return data["topics"]


def _is_text(v) -> bool:
    return isinstance(v, str) and bool(v.strip())


def _text_problem(field: str, v) -> str | None:
    """Why `v` can't be the text of `field` (None = it can): a wrong type names its value, "" is empty."""
    if not isinstance(v, str):
        return f"{field} must be non-empty text (got {v!r})"
    return None if v.strip() else f"empty {field}"


def _point_problems(n: int, p) -> list[str]:
    where = f"point {n}"
    if not isinstance(p, dict):
        return [f"{where}: must be a mapping"]
    out = []
    unknown = sorted(set(map(str, p)) - set(POINT_FIELDS))
    if unknown:
        out.append(f"{where}: unknown key(s) {', '.join(unknown)}")
    for f in POINT_FIELDS:
        if f not in p:
            out.append(f"{where}: missing field '{f}'")
    for f in ("term", "text"):
        if f in p:
            if _text_problem(f, p[f]):
                out.append(f"{where}: {_text_problem(f, p[f])}")
            else:
                out += [f"{where} {f}: {r}" for r in rules.narration_problems(_clean(p[f]))]
    if "diagram" in p:
        out += [f"{where} diagram: {r}" for r in diagrams.validate(p["diagram"])]
    return out


def validate_topic(topic) -> list[str]:
    """Every problem with one basics/topics.yaml topic, one reason each ([] = usable)."""
    if not isinstance(topic, dict):
        return ["topic must be a mapping"]
    out = []
    unknown = sorted(set(map(str, topic)) - set(TOPIC_FIELDS))
    if unknown:
        out.append(f"unknown key(s) {', '.join(unknown)}")
    for f in TOPIC_FIELDS:
        if f not in topic:
            out.append(f"missing field '{f}'")
    if "id" in topic and not (isinstance(topic["id"], str) and SLUG.fullmatch(topic["id"])):
        out.append(f"id {topic['id']!r} is not a kebab-case slug (lowercase letters and digits joined by -)")
    if "question" in topic:
        q = topic["question"]
        if _text_problem("question", q):
            out.append(_text_problem("question", q))
        else:
            q = _clean(q)
            if "?" not in q:
                out.append(f"question {q!r} is not a question (no \"?\")")
            if len(q) > MAX_QUESTION:
                out.append(f"question is {len(q)} characters (at most {MAX_QUESTION})")
            out += [f"question {r}" for r in rules.title_problems(q)]
    if "thumbnail" in topic:
        t = topic["thumbnail"]
        if _text_problem("thumbnail", t):
            out.append(_text_problem("thumbnail", t))
        else:
            out += [r if r.startswith("thumbnail") else f"thumbnail {r}"
                    for r in rules.thumbnail_text_problems(_clean(t), max_words=THUMB_WORDS)]
    if "summary" in topic:
        if _text_problem("summary", topic["summary"]):
            out.append(_text_problem("summary", topic["summary"]))
        else:
            out += [f"summary {r}" for r in rules.narration_problems(_clean(topic["summary"]))]
    if "points" in topic:
        points = topic["points"]
        if not isinstance(points, list) or not points:
            out.append("points must be a non-empty list")
        else:
            if len(points) < MIN_POINTS:
                out.append(f"{len(points)} points (at least {MIN_POINTS}: the Shorts material needs "
                           f"{MIN_POINTS + 1} segments, an overview and one per point)")
            for n, p in enumerate(points, 1):
                out += _point_problems(n, p)
    if "approved" in topic and not isinstance(topic["approved"], bool):
        out.append(f"approved must be true or false (got {topic['approved']!r})")
    return out


def validate_topics(topics) -> list[str]:
    """Every problem of the topic list as "<id>: <reason>" ([] = usable): each topic's validate_topic
    reasons, then a repeated id or question (case- and whitespace-insensitive) on the later topic."""
    if not isinstance(topics, list):
        return ["topics must be a list"]
    out, ids, questions = [], set(), {}
    for i, t in enumerate(topics):
        tid = t.get("id") if isinstance(t, dict) and _is_text(t.get("id")) else f"#{i + 1}"
        out += [f"{tid}: {r}" for r in validate_topic(t)]
        if not isinstance(t, dict):
            continue
        if _is_text(t.get("id")):
            if t["id"] in ids:
                out.append(f"{tid}: duplicate id")
            ids.add(t["id"])
        if _is_text(t.get("question")):
            key = _clean(t["question"]).lower()
            if key in questions:
                first, n = questions[key]  # the earlier topic; by list position when it shares this id
                out.append(f"{tid}: duplicate question (same as {first if first != tid else f'#{n}'})")
            else:
                questions[key] = (tid, i + 1)
    return out


def pick(topics: list, history) -> dict | None:
    """The next topic to publish: the first in list order with `approved: true` whose id no uploaded
    (`history.uploaded()`, an autopilot.history.History) kind: basics entry has as its `topic`, counting
    or not. None = nothing approved is left. Same inputs → same answer."""
    published = {v["topic"] for v in history.uploaded() if v.get("kind") == "basics" and v.get("topic")}
    for t in topics:
        if isinstance(t, dict) and t.get("approved") is True and t.get("id") not in published:
            return t
    return None


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
        visual = {"type": "concept", "n": n, "of": len(points), "term": _clean(p["term"]), "text": _clean(p["text"])}
        covers = f"approved point {n}, \"{_clean(p['term'])}\": {_clean(p['text'])}"
        if p.get("diagram") is not None:
            problems = diagrams.validate(p["diagram"])
            if problems:
                raise ValueError(f"{topic.get('id')} point {n} diagram: {'; '.join(problems)}")
            visual["diagram"] = copy.deepcopy(p["diagram"])
            covers = covers.rstrip(".") + (". The picture shows a diagram whose parts appear as they are named: name them in this "
                       f"order, each in the sentence where it comes up, with these words: "
                       f"{diagrams.naming_order(p['diagram'])}")
        plan.append({"id": f"point_{n}", "term": _clean(p["term"]), "visual": visual, "covers": covers})
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
- No greetings, no "in this video", no "like and subscribe", never ask viewers to subscribe (one short
  subscribe line is added for you after the first point).
- When a scene lists diagram parts, say each part's quoted words in that order, each in the sentence
  where that part comes up (the picture shows each part as it is named).
{rules.NARRATION_RULES}

Return JSON: {{"scenes": [{{"id": "{plan[0]['id']}", "text": "..."}}, ...]}}"""


def _words(scenes: list[dict]) -> int:
    return sum(len((s.get("text") or "").split()) for s in scenes)


def subscribe_ask(cfg: dict) -> str:
    """The one short spoken subscribe ask (cfg basics.subscribe_ask, else SUBSCRIBE_ASK)."""
    return _clean((cfg.get("basics") or {}).get("subscribe_ask") or SUBSCRIBE_ASK)


def _ask_scene(plan: list[dict]) -> str:
    """The scene the ask closes: the first point (the first payoff), else the first scene after the hook."""
    ids = [p["id"] for p in plan]
    return ASK_SCENE if ASK_SCENE in ids else ids[min(1, len(ids) - 1)]


def _with_ask(cfg: dict, plan: list[dict], scenes: list[dict]) -> list[dict]:
    """The scenes with the subscribe ask appended to the first payoff scene's narration (copies)."""
    where = _ask_scene(plan)
    out = []
    for s in scenes:
        s = dict(s)
        if s.get("id") == where and (s.get("text") or "").strip():
            s["text"] = f"{s['text'].strip()} {subscribe_ask(cfg)}"
        out.append(s)
    return out


def _without_ask(cfg: dict, scenes: list[dict]) -> list[dict]:
    ask = subscribe_ask(cfg)
    return [dict(s, text=_clean((s.get("text") or "").replace(ask, " "))) for s in scenes]


def facts(topic: dict) -> dict:
    """The only facts a Basics narration may state: the question, the summary and the approved points."""
    return {"question": _clean(topic.get("question")), "summary": _clean(topic.get("summary")),
            "points": [{"term": _clean(p.get("term")), "text": _clean(p.get("text"))}
                       for p in topic.get("points") or []]}


def _values(text: str) -> list[float]:
    out = []
    for m in NUMBER.finditer(text or ""):
        try:
            out.append(float(m.group(0).replace(",", "")))
        except ValueError:
            pass
    return out


def unknown_numbers(text: str, known: dict) -> list[str]:
    """Every digit-number spoken in `text` (small ones too) whose value the approved facts don't hold."""
    have = set(_values(json.dumps(known, ensure_ascii=False)))
    return list(dict.fromkeys(m.group(0) for m in NUMBER.finditer(text or "")
                              if float(m.group(0).replace(",", "")) not in have))


def check_script(cfg: dict, plan: list[dict], scenes: list[dict]) -> list[str]:
    """Deterministic problems with a narration ([] = usable): every scene narrated, word bounds,
    the shared data-desk narration rules, and the subscribe ask exactly once, at the end of the first
    payoff scene (no other subscribe mention anywhere)."""
    lo, hi = _bounds(cfg)
    texts = {s["id"]: (s.get("text") or "").strip() for s in scenes}
    problems = [f"scene '{p['id']}': no narration" for p in plan if not texts.get(p["id"])]
    words = _words(scenes)
    if not lo <= words <= hi:
        problems.append(f"{words} words (target {lo}-{hi})")
    problems += [f"narration rule: {r}" for r in rules.narration_problems("\n".join(texts.get(p["id"], "")
                                                                                    for p in plan))]
    ask, where = subscribe_ask(cfg), _ask_scene(plan)
    mentions = {p["id"]: len(SUBSCRIBE.findall(texts.get(p["id"], ""))) for p in plan}
    if not texts.get(where, "").endswith(ask) or sum(mentions.values()) != len(SUBSCRIBE.findall(ask)):
        others = [k for k, n in mentions.items() if n and k != where]
        problems.append("subscribe ask: once, at the end of the first payoff scene "
                        f"('{where}') only" + (f" (also in {', '.join(others)})" if others else ""))
    return problems


def _draft(cfg: dict, topic: dict, plan: list[dict], answer: dict) -> list[dict]:
    """A writer's (or fact-checker's) answer merged onto the plan, terms carried, the ask added."""
    pkg = _merge_plan(plan, answer if isinstance(answer, dict) else {})
    for s, p in zip(pkg["scenes"], plan):
        if p.get("term"):
            s["term"] = p["term"]
    return _with_ask(cfg, plan, pkg["scenes"])


def write_script(cfg: dict, topic: dict, plan: list[dict], log=print) -> dict:
    """{"scenes": [{id, text, visual, term?}], "fact_check": {verdict, issues}} narrated by Gemini from the
    topic's approved points, with the subscribe ask closing the first payoff scene. A draft with any
    problem (check_script) is discarded; RuntimeError after 3 failed attempts. The first passing draft is
    fact-checked: a reject, a revised draft with problems or a spoken number the approved facts don't hold
    → RuntimeError at once (no retry: the edition stops)."""
    problems: list[str] = []
    for attempt in range(1, 4):
        log(f"Writing the Basics narration ({topic['id']}, attempt {attempt}/3)...")
        scenes = _draft(cfg, topic, plan, generate_json(_prompt(cfg, topic, plan), _models(cfg), temperature=0.6) or {})
        problems = check_script(cfg, plan, scenes)
        log(f"Draft: {_words(scenes)} words")
        if not problems:
            return _fact_checked(cfg, topic, plan, scenes, log)
        log(f"Discarding draft: {'; '.join(problems)}")
    raise RuntimeError(f"Could not produce valid Basics narration in 3 attempts: {'; '.join(problems)}")


def _fact_checked(cfg: dict, topic: dict, plan: list[dict], scenes: list[dict], log=print) -> dict:
    """script.fact_check against the approved facts (the ask is not sent), then the deterministic checks
    again and the number check; any failure → RuntimeError ("Basics fact-check failed: …")."""
    lo, hi = _bounds(cfg)
    fcfg = {**cfg, "llm": {**(cfg.get("llm") or {}), "min_words": lo, "max_words": hi}}
    known = facts(topic)
    sent = {"title": known["question"],
            "scenes": [{"id": s["id"], "text": s["text"]} for s in _without_ask(cfg, scenes)]}
    log("Fact-checking the Basics narration against the topic's approved points...")
    verdict, checked, issues = fact_check(fcfg, known, sent, BASICS_RULES)
    log(f"Fact-check: {verdict}" + (f" ({len(issues)} fixes)" if issues else ""))
    if verdict == "reject":
        raise RuntimeError(f"Basics fact-check failed: verdict reject ({'; '.join(map(str, issues)) or 'no reason'})")
    revised = _draft(cfg, topic, plan, checked) if isinstance(checked, dict) and checked.get("scenes") else scenes
    problems = check_script(cfg, plan, revised)
    bad = unknown_numbers("\n".join(s.get("text") or "" for s in revised), known)
    if bad:
        problems.append("numbers not in the approved points: " + ", ".join(bad))
    if problems:
        raise RuntimeError(f"Basics fact-check failed: {'; '.join(problems)}")
    return {"scenes": revised, "fact_check": {"verdict": verdict, "issues": issues}}


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


def slide_concept(ctx: _Ctx, v: dict, show=None) -> Image.Image:
    """With a diagram: the heading, the term and the diagram under them (`show` = the diagram parts painted,
    None = all; the layout is the same for every `show`). Without: heading, term and the point text."""
    img, d = _base(ctx)
    who = f"{ctx.topic['id']} point {v['n']}"
    if v.get("diagram"):
        L = ctx.layout
        x0, y0, x1, y1 = L.content_box
        y = _flow(d, [_heading(ctx, f"KEY IDEA {v['n']} OF {v['of']}"),
                      {"text": v["term"], "size": 88, "title": True, "fill": FG, "max_lines": 2}],
                  L.content_box, L, who=who)
        diagrams.draw(img, (x0, y + DIAGRAM_GAP, x1, y1), v["diagram"], L, ctx.accent, show=show,
                      who=f"{who} diagram")
        return img
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
    slide shape; no draw-in). A concept scene with a diagram adds "base" (no part painted) and "steps"
    ([{key, name, names, layers}], diagrams.step_layers) for reveal.time_steps; its "image" is the full slide
    (= base + every layer). Unknown visual type → ValueError."""
    for s in plan:
        if (s.get("visual") or {}).get("type") not in RENDERERS:
            raise ValueError(f"unknown Basics visual type '{(s.get('visual') or {}).get('type')}' (scene '{s.get('id')}')")
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    ctx = _ctx(cfg, topic, layout)
    out = []
    for i, s in enumerate(plan):
        v = s["visual"]
        img = RENDERERS[v["type"]](ctx, v)
        stem = f"basics_{layout.name}_{i:02d}"
        path = workdir / f"{stem}.png"
        img.save(path)
        slide = {"image": path, "reveal": None, "id": s["id"]}
        if v["type"] == "concept" and v.get("diagram"):
            slide["base"], slide["steps"] = diagrams.step_layers(
                lambda show, v=v: slide_concept(ctx, v, show=show), diagrams.steps(v["diagram"]), workdir, stem)
        out.append(slide)
    return out


# ─── packaging (packaging.md, Basics row) ──────────────────────────────────

def packaging_problems(topic: dict) -> list[str]:
    """Why this topic can't be packaged ([] = it can): the title (the question verbatim) breaks
    rules.title_problems or is over 100 characters; the thumbnail text is missing or not 1-3 clean words."""
    title = _clean(topic.get("question"))
    out = [f"title {r}" for r in rules.title_problems(title)] if title else ["title: missing question"]
    if len(title) > MAX_QUESTION:
        out.append(f"title is {len(title)} characters (at most {MAX_QUESTION})")
    words = _clean(topic.get("thumbnail"))
    if not words:
        out.append("thumbnail: missing thumbnail text")
    else:
        out += [r if r.startswith("thumbnail") else f"thumbnail {r}"
                for r in rules.thumbnail_text_problems(words, max_words=THUMB_WORDS)]
    return out


def _check_packaging(topic: dict) -> None:
    problems = packaging_problems(topic)
    if problems:
        raise ValueError(f"Basics packaging ({topic.get('id')}): {'; '.join(problems)}")


def _thumb_icon(topic: dict) -> str:
    """The coin of the fallback icon: the first coin badge in the topic's diagrams, else BTC."""
    found = re.findall(r"'coin': '([A-Z]{2,5})'", repr([p.get("diagram") for p in topic.get("points") or []]))
    return found[0] if found else "BTC"


def render_thumbnail(cfg: dict, topic: dict, path: Path, log=print) -> Path:
    """The 1280x720 Basics thumbnail: brand + CRYPTO BASICS chip, the topic's 1-3 thumbnail words large on the
    left, and one clean drawing on the right: the first point's diagram (notes dropped) when it fits, else a
    drawn coin badge. Bad thumbnail text or title → ValueError (packaging_problems)."""
    from autopilot.thumbnail import GRID, _fit, _mini_logo
    from autopilot.slides import DOWN, UP
    _check_packaging(topic)
    W, H = THUMB_SIZE
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

    # the 1-3 words, left column, as large as they fit (one word a line)
    from autopilot.lesson_slides import _title_font
    words = _clean(topic["thumbnail"]).upper().split()
    col_x, col_w, top, bottom = 56, 580, 130, H - 50
    size = 190
    while True:
        f = _title_font(size)
        if max(d.textlength(w, font=f) for w in words) <= col_w and len(words) * size * 1.02 <= bottom - top:
            break
        size -= 6
        if size < 48:  # a word too long to read on a thumbnail: a packaging problem, never drawn over the column
            raise ValueError(f"Basics packaging ({topic.get('id')}): thumbnail text {topic['thumbnail']!r} "
                             "is too wide for the thumbnail")
    y = top + (bottom - top - len(words) * round(size * 1.02)) // 2
    for i, w in enumerate(words):
        d.text((col_x, y), w, font=f, fill=accent if i == len(words) - 1 else FG)
        y += round(size * 1.02)

    # one clean drawing, right column
    box = (676, 140, 1236, 640)
    d.rounded_rectangle(box, radius=22, fill=BG, outline=PANEL, width=3)
    inner = (box[0] + 20, box[1] + 20, box[2] - 20, box[3] - 20)
    first = next((p.get("diagram") for p in topic.get("points") or [] if p.get("diagram")), None)
    drawn = False
    if first:
        spec = {k: v for k, v in copy.deepcopy(first).items() if k != "notes"}
        layer = img.copy()
        try:
            diagrams.draw(layer, inner, spec, THUMB_COLUMN, accent, who=f"{topic.get('id')} thumbnail")
            img.paste(layer)
            drawn = True
        except ValueError as e:
            log(f"Basics thumbnail: diagram doesn't fit ({e}); using a coin icon")
    if not drawn:
        coin = _thumb_icon(topic)
        size = min(inner[2] - inner[0], inner[3] - inner[1]) - 60
        cx, cy = (inner[0] + inner[2]) // 2, (inner[1] + inner[3]) // 2
        fi = _fit(coin, lambda s_: _title_font(s_), round(size * 0.7), round(size * 0.36), 40)
        diagrams._paint(ImageDraw.Draw(img), diagrams._badge(cx, cy, size, coin, fi, accent))
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, "JPEG", quality=92)
    return path


def chapters(plan: list[dict], audio: list[dict]) -> list[dict]:
    """Chapters from the scene timings (lesson_meta.chapters' rule: each ≥ 10 s, short scenes merge into the
    previous chapter), named Intro / each point's term / Recap → [{start, time, title, scenes}]."""
    from autopilot import lesson_meta
    names = {"hook": "Intro", "recap": "Recap"}
    names.update({p["id"]: p["term"] for p in plan if p.get("term")})
    out = lesson_meta.chapters(plan, audio, [])
    for c in out:
        c["title"] = names.get(c["scenes"][0], c["title"])
    return out


# ─── metadata ──────────────────────────────────────────────────────────────

HASHTAGS = ["#CryptoBasics", "#CryptoForBeginners", "#Crypto"]
COIN_HASHTAGS = {"bitcoin": "#Bitcoin", "ethereum": "#Ethereum"}
MAX_HASHTAGS = 5
MIN_CHAPTERS = 3  # YouTube shows chapters only with at least 3 (first at 0:00, each ≥ 10 s)
MAX_DESCRIPTION = 4900  # YouTube allows 5000


def hashtags(topic: dict) -> list[str]:
    q = _clean(topic.get("question")).lower()
    return (HASHTAGS + [h for w, h in COIN_HASHTAGS.items() if w in q])[:MAX_HASHTAGS]


def _tags(topic: dict) -> list[str]:
    q = re.sub(r"\s*\(.*?\)\s*", " ", _clean(topic.get("question"))).strip(" ?").lower()
    seeds = [q, "crypto basics", "crypto explained", "crypto for beginners"]
    seeds += [_clean(p.get("term")).lower() for p in topic.get("points") or []]
    tags, seen, total = [], set(), 0
    for t in seeds:
        t = re.sub(r"[<>,]", "", t).strip()
        cost = len(t) + (2 if " " in t else 0) + 1  # YouTube counts quotes + separator
        if t and t not in seen and total + cost <= 480:
            seen.add(t)
            tags.append(t)
            total += cost
    return tags


def metadata(cfg: dict, topic: dict, chapters: list[dict] | None = None, log=print) -> dict:
    """{title, description, tags, category_id, fb_title, fb_description} (packaging.md, Basics row): the title
    is the search question verbatim (packaging_problems → ValueError); YouTube description = summary → key
    ideas → chapters (≥ 3) → the disclosure line exactly once → hashtags (the body is cut, never that tail);
    Facebook = summary → key ideas → the disclosure line exactly once → hashtags."""
    _check_packaging(topic)
    title = _clean(topic["question"])
    line = rules.disclosure(cfg, "basics")
    about = rules.without_disclosure(_clean(topic.get("summary")), line)
    ideas = "Key ideas:\n" + "\n".join(f"• {_clean(p['term'])}" for p in topic.get("points") or [])
    tags = " ".join(hashtags(topic))
    parts = [about, ideas]
    chapters = chapters or []
    if len(chapters) >= MIN_CHAPTERS:
        parts.append("Chapters:\n" + "\n".join(f"{c['time']} {_clean(c['title'])}" for c in chapters))
    elif chapters:
        log(f"No chapters in the description: only {len(chapters)} (YouTube needs {MIN_CHAPTERS})")
    tail = "\n\n".join(("⚠️ " + line, tags))
    body = "\n\n".join(p for p in parts if p)
    room = MAX_DESCRIPTION - len(tail) - 2
    if len(body) > room:  # cut at a line break, so no half chapter line is left
        body = body[:room].rsplit("\n", 1)[0] if "\n" in body[:room] else body[:room]
    body = body.rstrip()
    fb = "\n\n".join(p for p in (about, ideas, "⚠️ " + line, tags) if p)
    return {"title": title, "description": body + "\n\n" + tail, "tags": _tags(topic),
            "category_id": str((cfg.get("basics") or {}).get("category_id") or CATEGORY),
            "fb_title": title, "fb_description": fb}
