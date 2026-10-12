"""Turn the day's data into a grounded Shorts script with a graphic per scene.

Market briefs: focus.pick() chooses one lead story; research() writes an analyst note on what
happened and how it spreads to related crypto/forex/gold; write() turns that into a script about
that story only; fact_check() re-checks every claim against the data.
Gold outlook: a fixed scene plan built from gold.analyze(); the LLM only narrates it.
"""
import json
import random
import re

from . import seo
from .llm import generate_json

SCENE_TYPES = {
    "title": "opening card: a short headline (max 9 words) + a kicker (max 4 words)",
    "price": 'a coin\'s 7-day chart; needs "asset": one of the coin symbols in the data',
    "fx": 'a forex pair\'s 30-day chart; needs "asset": one of the FX pair codes in the data',
    "gold": "gold's (XAU/USD) 7-day chart",
    "board": "table of the assets in this brief with their % change",
    "news": 'one headline card; needs "source" and "headline" (your own max-12-word paraphrase)',
    "calendar": "table of today's high-impact economic events (only if there are any)",
}
GOLD_TYPES = {"gold_chart", "review", "bias", "liquidity", "scenarios", "drivers"}

# Opening lines with tension: a real number from the data + an open question the next scenes answer.
HOOKS = [
    'the move as a hard fact with its number, then a tension line the next scenes answer, e.g. '
    '"Ethereum just lost 5.7%. Here\'s who\'s selling." (only say "who" if a headline names them)',
    'the number first, then the question it raises, e.g. "Bitcoin dropped 4.2% overnight. One headline '
    'explains it." (only if a headline in the data does)',
    'the number set against what comes next on the calendar, e.g. "The euro slid 0.6% before today\'s '
    'ECB call."',
]
# Spoken disclaimer / goodbye phrases, cut out of the narration (the rest of a sentence stays). The
# disclaimer lives in the slide footers and the description, so the narration never speaks it.
SIGN_OFF = re.compile(r"[\s,;:\u2014\u2013-]*\b(?:(?:this|that|it)(?: is|[\u2019']s) )?(?:not financial advice|"
                      r"do your own research|thanks for watching|stay tuned|until next time|"
                      r"(?:like and )?\bsubscribe\b|see you (?:tomorrow|next time|soon|later|then|at the next \w+))",
                      re.I)
# Sentences that are only a goodbye ("That's your London brief.", "See you at the open.")
GOODBYE = re.compile(r"^\W*(?:that[\u2019']?s (?:your|all for)|see you|catch you|bye\b)", re.I)

SCHEMA = """{
  "title": "YouTube title, max 70 chars, include the date like 'Oct 7'",
  "scenes": [
    {"text": "narration (1-2 short spoken sentences)",
     "visual": {"type": "title|price|fx|gold|board|news|calendar", "...": "fields for that type"}}
  ],
  "description": "2-3 sentences summarising the brief",
  "tags": ["search phrase", "..."],
  "hashtags": ["#Bitcoin", "..."],
  "headlines_used": ["exact titles of the news items you referred to"],
  "thumbnail_hook": "2-4 word hook for the thumbnail"
}"""


def _models(cfg: dict) -> list[str]:
    return [cfg["llm"]["model"], *cfg["llm"].get("fallback_models", [])]


def _r(x, n=2):
    return round(x, n)


def _news_row(n: dict, body: bool = False) -> dict:
    row = {"source": n["source"], "title": n["title"], "summary": n["summary"][:200],
           "published": n["published"], "category": n["category"]}
    if body and n.get("body"):
        row["article_text"] = n["body"][:1200]
    return row


def brief_for_llm(data: dict, max_news: int = 30, focused: bool = False) -> dict:
    """Compact, number-rounded view of the data (no long price series).
    focused=True keeps only the brief's focus assets and the news about them."""
    focus = data.get("focus") or {}
    keep = set(focus.get("assets") or []) if focused else None
    crypto = {s: c for s, c in data.get("crypto", {}).items() if keep is None or s in keep}
    fx = {p: f for p, f in data.get("fx", {}).items() if keep is None or p in keep}
    gold = data.get("gold") if (keep is None or "XAU" in keep) else None
    out = {
        "date_utc": data["date_utc"], "weekday": data["weekday"], "weekend": data["weekend"],
        "crypto": {s: {"name": c["name"], "price_usd": _r(c["price"], 4 if c["price"] < 10 else 2),
                       "change_24h_pct": _r(c["change_24h"]), "change_7d_pct": _r(c["change_7d"]),
                       "high_24h": _r(c["high_24h"]), "low_24h": _r(c["low_24h"])}
                   for s, c in crypto.items()},
        "fx": {p: {"name": f["name"], "rate": _r(f["price"], 4 if f["price"] < 20 else 2),
                   "change_1d_pct": _r(f["change_1d"]), "change_30d_pct": _r(f["change_30d"]),
                   "rate_date": f["as_of"], "note": "daily central-bank reference rate"}
               for p, f in fx.items()},
        "calendar_today_utc": data.get("calendar", []),
    }
    if gold:
        out["gold"] = {"name": "Gold (XAU/USD)", "price_usd": _r(gold["price"], 1),
                       "change_24h_pct": _r(gold["change_24h"]), "change_7d_pct": _r(gold["change_7d"]),
                       "high_24h": _r(gold["high_24h"], 1), "low_24h": _r(gold["low_24h"], 1),
                       "note": "spot gold, live (hourly)"}
    if data.get("macro"):
        out["us_macro"] = data["macro"]
    if data.get("rate_expectations"):
        out["fed_rate_odds_headlines"] = data["rate_expectations"]
    if focused and focus:
        out["news"] = [_news_row(n, body=(i < 3)) for i, n in enumerate(focus.get("news", [])[:12])]
    else:
        out["news"] = [_news_row(n) for n in data.get("news", [])[:max_news]]
    return out


# ─── market brief ──────────────────────────────────────────────────────────

def research(cfg: dict, data: dict) -> dict:
    """Analyst note on the lead story: what happened, why (only from headlines), how it spreads."""
    focus = data["focus"]
    story = focus.get("story")
    prompt = f"""RESEARCH TASK. You are a senior crypto and forex market analyst preparing notes for a
~35-second news Short about ONE story. Work only from the material below.

LEAD: {focus['label']} (assets in this brief: {', '.join(focus['asset_names'].values())})
LEAD STORY: {json.dumps(_news_row(story, body=True), ensure_ascii=False) if story else "(no single story; lead is the price move)"}

DATA:
{json.dumps(brief_for_llm(data, focused=True), ensure_ascii=False, indent=1)}

TYPICAL MARKET RELATIONSHIPS (general knowledge you may cite with "usually"/"tends to"):
{chr(10).join('- ' + x for x in focus.get('links', [])) or '- (none)'}

Write notes:
- what_happened: 1-2 sentences, facts from the lead story / headlines with their source.
- why: causes ONLY if a headline or article text states them (with source); else [].
- impact: for each other asset in this brief, what it actually did in the data (number) and how
  it connects to the lead story: either a headline that says so, or a typical relationship
  marked "typical". Say plainly if an asset did NOT follow.
- context: facts from us_macro / fed_rate_odds_headlines ONLY if a headline ties them to this move
  (quote the source for odds); else [].
- watch: upcoming calendar events that matter for these assets (time GMT).
- angle: the one question this Short answers, max 12 words.

Return JSON: {{"what_happened": "...", "why": ["..."], "impact": [{{"asset": "...", "observed": "...",
"link": "...", "basis": "headline|typical|data"}}], "context": ["..."], "watch": ["..."], "angle": "..."}}"""
    return generate_json(prompt, _models(cfg), temperature=0.3)


def write(cfg: dict, data: dict, used_headlines: list[str], cover: dict, session: dict | None = None,
          note: dict | None = None) -> dict:
    ch, llm = cfg["channel"], cfg["llm"]
    focus = data.get("focus") or {}
    brief = brief_for_llm(data, focused=bool(focus))
    recent = "\n".join(f"- {h}" for h in used_headlines[-60:]) or "- (none)"
    types = "\n".join(f'- "{k}": {v}' for k, v in SCENE_TYPES.items()
                      if k != "gold" or brief.get("gold"))
    session = session or {}
    edition = (f"EDITION: the {session.get('label')} brief. {session.get('focus', '')}\n"
               if session.get("label") else "")
    since = (f"News below is only what came out since the previous brief ({data['news_since']}).\n"
             if data.get("news_since") else "")
    if focus:
        charts = ", ".join(f"{k} ({v})" for k, v in focus["asset_names"].items())
        topic = f"""ONE STORY: this Short is about {focus['label']} and how it spreads to related markets.
Assets in this brief (the only ones you may chart or name with numbers): {charts}.
Do not list or mention other coins or currency pairs.

ANALYST NOTES (built from the data; use them, they don't add new facts):
{json.dumps(note or {}, ensure_ascii=False, indent=1)}

Story arc: hook with the number → what happened (lead story) → why (only if a headline says) →
spread to 1-2 related assets (their actual numbers, the link) → what to watch next. Rates, inflation
or yields only when a headline says they are the cause. The last line loops back to the opening fact.
"""
    else:
        topic = ""
    follow = opening_chart(data, cover)
    names = {**{s: c["name"] for s, c in data.get("crypto", {}).items()},
             **{p: f["name"] for p, f in data.get("fx", {}).items()}, "XAU": "gold"}
    shown = cover.get("asset") if follow and cover.get("asset") else focus.get("lead")
    opening = (f"the {names.get(shown, focus.get('label', shown))} chart drawing in"
               if follow else "the board of the brief's assets")
    key = seo.primary(data)
    if key:
        seo_rules = f"""- title (max 70 chars): START with "{key[1]}" or "{key[0]}" (the search keyword must be in the
  first 40 characters), then the specific fact and the edition + date, e.g.
  "{key[1].title()}: Down 5% as Liquidations Hit $500M | London Open, Oct 8". No clickbait, no emojis.
- description: 2-3 sentences. The first sentence starts with "{key[1]}" and states the main fact
  with its number; the next ones name the related assets and the cause (if a headline gives it).
  Plain text, no hashtags, no links.
- tags: 8-12 phrases people search about this story (e.g. "{key[1].lower()}", "{key[0].lower()} news").
- hashtags: 2-3 specific ones (the asset first, e.g. "#{key[0].replace(' ', '')}")."""
    else:
        seo_rules = """- title: specific (name the asset and the move), include the date and the edition name
  (e.g. "| London Open, Oct 7"), no clickbait, no emojis.
- tags: 8-12 phrases people search (e.g. "bitcoin price today", "forex news today").
- hashtags: 2-3."""
    prompt = f"""You write a YouTube Short: a {llm['min_words']}-{llm['max_words']} word market brief.
Channel: {ch['niche']}
Audience: {ch['audience']}. Tone: {ch['tone']}.
{edition}{since}{topic}
TODAY'S DATA (the only facts you may use):
{json.dumps(brief, ensure_ascii=False, indent=1)}

Headlines already covered in earlier briefs (don't repeat them):
{recent}

Rules:
- Every number you say must come from the data above. Round naturally and say it the way it
  is spoken ("about sixty-two thousand four hundred dollars", "down two point one percent").
- Only explain WHY something moved if a headline in the data says so; otherwise just state the move.
- You may explain how markets are usually linked ("a stronger dollar usually weighs on gold"),
  worded as a general tendency, never as the cause of today's move unless a headline says so.
- Fed rate odds only from fed_rate_odds_headlines, naming the source ("according to CME FedWatch
  data cited by Reuters").
- Crypto and gold prices are live; forex rates are daily reference rates, so say "yesterday's close"
  or "the latest daily fix" for them, never "right now".
- If "weekend" is true, forex markets are closed: focus on crypto and the week ahead.
- If the calendar is empty, skip the calendar scene.
- The calendar has times, forecasts and previous values only, never results: don't state an
  actual figure unless a headline in the data reports it.
- No predictions, price targets, buy/sell calls or "this could explode". Neutral, factual.
- No spoken disclaimer and no sign-off: "not financial advice" is already on screen and in the
  description. No "that's your brief", "see you", "stay tuned". The last line loops back to the
  opening fact (e.g. "So that 5.7% drop came with...", restating the number), so the video can loop.
- First line (under 12 words) opens with {random.choice(HOOKS)}
- No greetings, no "in this video", no "like and subscribe".

OPENING CARD (also the video's thumbnail) — already designed from the data, it shows:
  {cover['facts']}
- Scene 1 uses visual "title" and its first sentence must state exactly that fact, so the
  viewer who clicked gets it straight away. The rest of the brief must answer the hook.
- "thumbnail_hook": 2-4 words, max 22 characters, written in capitals, that make people want
  the answer, e.g. "{cover['default_hook']}". It must be answered by this video. No predictions,
  no "moon", "buy", "sell", "will", "guaranteed", no emojis.

Structure: 5-6 scenes (about 35 seconds spoken). Scene 1 uses visual "title"; it shows the opening
card and then {opening}. Don't chart that asset again in later scenes. Pick a fitting visual for every
other scene from these types:
{types}

SEO:
{seo_rules}

Return JSON exactly in this shape:
{SCHEMA}"""
    return generate_json(prompt, _models(cfg), temperature=0.7)


def fact_check(cfg: dict, facts: dict, pkg: dict, extra_rules: str = "") -> tuple[str, dict, list]:
    llm = cfg["llm"]
    prompt = f"""You are a strict financial news editor. Check this Short script against the data.

DATA:
{json.dumps(facts, ensure_ascii=False, indent=1)}

SCRIPT:
{json.dumps(pkg, ensure_ascii=False, indent=1)}

1. Every number and claim in the narration, title and visuals must match the data (rounding is
   fine). Every "why" must be backed by a headline in the data. General market relationships
   worded as tendencies ("usually", "tends to") are fine. Fix anything that isn't backed.
2. Remove any buy/sell suggestion, price target or promise (also in "thumbnail_hook").{extra_rules}
3. Keep {llm['min_words']}-{llm['max_words']} words of narration and the same JSON shape.
4. verdict: "ok", "revised", or "reject" (only if the script is fundamentally wrong).

Return JSON: {{"issues": ["..."], "verdict": "ok|revised|reject", "package": <full package>}}"""
    res = generate_json(prompt, _models(cfg), temperature=0.1)
    revised = res.get("package") or pkg
    return res.get("verdict", "ok"), revised, res.get("issues", [])


def validate(cfg: dict, data: dict, pkg: dict) -> list[str]:
    problems = []
    scenes = pkg.get("scenes") or []
    if not 4 <= len(scenes) <= 7:
        problems.append(f"{len(scenes)} scenes")
    for i, s in enumerate(scenes):
        v = s.get("visual") or {}
        t = v.get("type")
        if not (s.get("text") or "").strip():
            problems.append(f"scene {i + 1}: no narration")
        if t not in SCENE_TYPES and t not in GOLD_TYPES:
            problems.append(f"scene {i + 1}: unknown visual {t!r}")
        elif t == "price" and v.get("asset") not in data["crypto"]:
            problems.append(f"scene {i + 1}: no price data for {v.get('asset')!r}")
        elif t == "fx" and v.get("asset") not in data["fx"]:
            problems.append(f"scene {i + 1}: no FX data for {v.get('asset')!r}")
        elif t in ("gold", "gold_chart") and not data.get("gold"):
            problems.append(f"scene {i + 1}: no gold data")
        elif t == "news" and not (v.get("headline") or "").strip():
            problems.append(f"scene {i + 1}: news card without headline")
    if len(scenes) > 1 and (scenes[-1].get("text") or "").strip() and not strip_sign_off(scenes[-1]["text"]):
        problems.append("last scene is only a sign-off")
    words = sum(len(s.get("text", "").split()) for s in scenes)
    lo, hi = cfg["llm"]["min_words"], cfg["llm"]["max_words"]
    if not lo - 30 <= words <= hi + 25:
        problems.append(f"{words} words (target {lo}-{hi})")
    if not (pkg.get("title") or "").strip():
        problems.append("missing title")
    return problems


def _chart_for(asset: str, data: dict) -> dict | None:
    if asset in data.get("crypto", {}):
        return {"type": "price", "asset": asset}
    if asset in data.get("fx", {}):
        return {"type": "fx", "asset": asset}
    if asset == "XAU" and data.get("gold"):
        return {"type": "gold"}
    return None


def opening_chart(data: dict, cover: dict | None = None) -> dict | None:
    """The chart that takes over from the opening card in scene 1: the cover's asset when the cover
    names one (move / level card; gold outlook card → gold chart), else the lead asset's chart (None if
    the lead has no chart of its own, e.g. the US dollar; the board is shown then)."""
    cover = cover or {}
    if cover.get("template") == "gold":
        return {"type": "gold_chart"} if data.get("gold_analysis") else _chart_for("XAU", data)
    chart = _chart_for(cover["asset"], data) if cover.get("asset") else None
    lead = (data.get("focus") or {}).get("lead")
    return chart or (_chart_for(lead, data) if lead else None)


def strip_sign_off(text: str) -> str:
    """The text without spoken disclaimer / goodbye phrases; sentences left empty or goodbye-only go."""
    out = []
    for part in re.split(r"(?<=[.!?])\s+", (text or "").strip()):
        rest = SIGN_OFF.sub("", part).strip()
        rest = re.sub(r"^[\s,;:\u2014\u2013-]+", "", rest)
        if not re.search(r"\w", rest) or GOODBYE.match(rest):
            continue
        if rest != part:
            rest = rest[0].upper() + rest[1:]
            if part[-1] in ".!?" and rest[-1] not in ".!?":
                rest += part[-1]
        out.append(rest)
    return " ".join(out)


def _clean_last_line(scenes: list[dict], log=print, can_drop: bool = True) -> None:
    """Cut a spoken disclaimer / goodbye from the last scene. An all-sign-off last scene is dropped if
    ≥ 4 scenes remain (can_drop), else emptied (fixed plans) or left for validate() to reject."""
    if len(scenes) < 2:
        return
    text = scenes[-1].get("text") or ""
    rest = strip_sign_off(text)
    if rest.split() == text.split():
        return
    if rest:
        scenes[-1]["text"] = rest
        log(f"Script: cut a sign-off from the last line: {text!r} -> {rest!r}")
    elif can_drop and len(scenes) - 1 >= 4:
        scenes.pop()
        log(f"Script: dropped a sign-off-only last scene: {text!r}")
    elif not can_drop:
        scenes[-1]["text"] = ""
        log(f"Script: the last scene was only a sign-off ({text!r}); left empty for validation")
    else:
        log(f"Script: the last scene is only a sign-off ({text!r}); too few scenes to drop it")


def fix_visuals(data: dict, pkg: dict, cover: dict | None = None, log=print) -> None:
    """Degrade gracefully instead of failing. Scene 1 is always the opening card (the thumbnail),
    followed by the cover's asset chart or else the lead's (`follow`, see opening_chart(); board if
    none), which later scenes don't repeat. A chart of an asset outside the brief's focus becomes a
    chart of an unused focus asset (or the board); unusable visuals become the board. A stray "outro"
    scene is dropped if it only signs off, else it becomes the board; sign-offs are cut from the last line."""
    scenes = pkg.get("scenes") or []
    for s in list(scenes[1:]):
        if (s.get("visual") or {}).get("type") == "outro":
            rest = strip_sign_off(s.get("text", ""))
            if len(rest.split()) < 3:
                scenes.remove(s)
                log(f"Script: dropped a stray outro scene: {s.get('text', '')!r}")
            else:
                s["text"], s["visual"] = rest, {"type": "board"}
                log(f"Script: stray outro scene turned into the board: {rest!r}")
    _clean_last_line(scenes, log)
    follow = opening_chart(data, cover)
    if scenes:
        scenes[0]["visual"] = {"type": "title", "follow": follow or {"type": "board"}}
    focus = set((data.get("focus") or {}).get("assets") or [])
    asset_of = {"price": lambda v: v.get("asset"), "fx": lambda v: v.get("asset"), "gold": lambda v: "XAU"}
    opened = asset_of[follow["type"]](follow) if follow and follow["type"] in asset_of else None
    shown = {asset_of[s["visual"]["type"]](s["visual"]) for s in scenes
             if (s.get("visual") or {}).get("type") in asset_of} | ({opened} if opened else set())
    for s in scenes[1:]:
        v = s.get("visual") or {}
        t = v.get("type")
        if t in asset_of:
            a = asset_of[t](v)
            if _chart_for(a, data) and (not focus or a in focus) and a != opened:
                continue
            spare = next((x for x in (data.get("focus") or {}).get("assets", [])
                          if x not in shown and _chart_for(x, data)), None)
            s["visual"] = _chart_for(spare, data) if spare else {"type": "board"}
            if spare:
                shown.add(spare)
        elif (t == "calendar" and not data["calendar"]) or t not in SCENE_TYPES:
            s["visual"] = {"type": "board"}


def make_script(cfg: dict, data: dict, used_headlines: list[str], cover: dict, session: dict | None = None,
                log=print) -> dict:
    note = None
    if data.get("focus"):
        log(f"Researching the lead story ({data['focus']['label']})...")
        try:
            note = research(cfg, data)
            log(f"Angle: {note.get('angle', '')}")
        except Exception as e:  # the brief can still be written from the data alone
            log(f"Research step failed ({e}); writing from the data only")
    facts = brief_for_llm(data)
    if data.get("focus"):
        facts["lead_story_article"] = (data["focus"].get("story") or {}).get("body", "")[:1200]
    for attempt in range(3):
        log("Writing the script...")
        pkg = write(cfg, data, used_headlines, cover, session, note)
        log(f"Draft: {pkg.get('title', '')}. Fact-checking against the data...")
        verdict, pkg, issues = fact_check(cfg, facts, pkg)
        log(f"Fact-check: {verdict}" + (f" ({len(issues)} fixes)" if issues else ""))
        fix_visuals(data, pkg, cover, log=log)
        problems = validate(cfg, data, pkg)
        if verdict != "reject" and not problems:
            pkg["fact_check"] = {"verdict": verdict, "issues": issues}
            if note:
                pkg["research"] = note
            return pkg
        log(f"Discarding draft: verdict={verdict} problems={problems}")
    raise RuntimeError("Could not produce a valid script in 3 attempts")


# ─── gold outlook ──────────────────────────────────────────────────────────

def gold_plan(data: dict, used_headlines: list[str]) -> list[dict]:
    """Fixed scene order for the daily gold outlook; each scene says what its narration covers."""
    a = data["gold_analysis"]
    plan = [{"id": "open", "visual": {"type": "title", "follow": {"type": "gold_chart"}},
             "covers": "the hook: state the opening-card fact (today's daily bias and the key level)"}]
    if a.get("review"):
        plan.append({"id": "review", "visual": {"type": "review"},
                     "covers": "how the previous outlook did, honestly (review)"})
    plan.append({"id": "bias", "visual": {"type": "bias"},
                 "covers": "where gold is now (price and 24h change, one short clause), then the bias for the next "
                           "hour (1H), the next 4 hours (4H) and the day, each with its main reason"})
    watch = None
    used = {h.lower() for h in used_headlines}
    story = next((n for n in data.get("news", []) if n["category"] == "gold" and n["title"].lower() not in used), None)
    if data.get("macro") or data.get("rate_expectations") or a.get("events_usd"):
        watch = {"id": "drivers", "visual": {"type": "drivers"},
                 "covers": "what to watch: today's USD events that can move gold (volatility risk, GMT time) and the "
                           "macro drivers (dollar, US 10-year and real yields, Fed rate odds headlines); last line "
                           "loops back to the key level from the opening"}
    elif story:
        watch = {"id": "news", "visual": {"type": "news", "source": story["source"], "headline": story["title"]},
                 "covers": f"what to watch: the gold headline from {story['source']}: \"{story['title']}\"; "
                           "last line loops back to the key level from the opening"}
    levels = {"id": "levels", "visual": {"type": "scenarios"},
              "covers": "the key levels: where liquidity rests above (buy-side, stops above highs) and below "
                        "(sell-side, stops below lows), then the if/then scenarios: above the bull trigger the next "
                        "objective, below the bear trigger the next objective"
                        + ("" if watch else "; last line loops back to the key level from the opening")}
    if len(plan) + 1 + (1 if watch else 0) < 4:  # too short: liquidity gets its own scene again
        plan.append({"id": "liquidity", "visual": {"type": "liquidity"},
                     "covers": "where liquidity rests: the nearest levels above (buy-side, stops above highs) and "
                               "below (sell-side, stops below lows), and any sweep today"})
        levels = dict(levels, covers="if/then scenarios: above the bull trigger the next objective, below the bear "
                                     "trigger the next objective"
                                     + ("" if watch else "; last line loops back to the key level from the opening"))
    plan.append(levels)
    if watch:
        plan.append(watch)
    return plan


def write_gold(cfg: dict, data: dict, plan: list[dict], cover: dict, used_headlines: list[str]) -> dict:
    ch, llm = cfg["channel"], cfg["llm"]
    facts = gold_facts(data)
    scenes = "\n".join(f'- "{p["id"]}": {p["covers"]}' for p in plan)
    recent = "\n".join(f"- {h}" for h in used_headlines[-30:]) or "- (none)"
    prompt = f"""You write a YouTube Short: a {llm['min_words']}-{llm['max_words']} word (about 35 seconds) DAILY GOLD OUTLOOK
(XAU/USD) for {data['weekday']}, {data['date_utc']}.
Channel: {ch['display_name']}. Audience: {ch['audience']}. Tone: a calm, precise market analyst.

ANALYSIS (rule-based, from hourly prices; the only numbers and calls you may use):
{json.dumps(facts, ensure_ascii=False, indent=1)}

Write narration for each scene, in this order (1-2 short spoken sentences each):
{scenes}

Rules:
- Every number and every bias must come from the analysis. The biases are rule-based reads, so
  present them as conditional ("bias is bearish while below forty-one forty-three"), never as
  certainty. Use "bias", "scenario", "if... then", "key level", "liquidity".
- Say gold prices the way traders do: "forty-one forty-three" for $4,143, "forty-one hundred" for
  $4,100. Dollar moves: "about ten dollars".
- Never say buy, sell, long, short, entry, stop loss, take profit, guaranteed, or "will" + a price.
- Explain liquidity simply: stop orders cluster above highs (buy-side) and below lows (sell-side);
  price often reaches for them.
- review: if the previous call did not play out, say so plainly.
- Fed rate odds only from fed_rate_odds_headlines, naming the source.
- Mention USD events today as volatility risk with their GMT time. No actual figures for them.
- Scene "open" must state exactly: {cover['facts']}, as a hook with tension (e.g. "Gold is bearish
  below forty-one forty-three. Here's where the stops sit.").
- No spoken disclaimer and no sign-off ("not financial advice" is on screen and in the description);
  no "that's your outlook", "see you". The last scene ends by looping back to the opening key level.
- No greetings, no "in this video", no "like and subscribe".

Headlines already covered (don't repeat):
{recent}

SEO:
- title: max 70 chars, START with "Gold Price Today" (search keyword first), then the daily bias,
  one key level and the date, e.g. "Gold Price Today: Bearish Below $4,143 | XAU/USD Oct 8". No hype.
- description: 2-3 sentences. The first starts with "Gold price today" and gives the price, the
  daily bias and the key level; then the 1H/4H read and the main driver. No hashtags or links.
- tags: 8-12 searches ("gold price today", "xauusd analysis", "gold forecast today", ...).
- hashtags: 2-3 (#Gold #XAUUSD ...).
- thumbnail_hook: 2-4 words, max 22 characters, capitals, e.g. "{cover['default_hook']}"; no "will",
  "buy", "sell", no emojis.

Return JSON: {{"title": "...", "scenes": [{{"id": "open", "text": "..."}}, ...], "description": "2-3 sentences",
"tags": ["..."], "hashtags": ["#Gold"], "headlines_used": ["exact titles you referred to"], "thumbnail_hook": "..."}}"""
    return generate_json(prompt, _models(cfg), temperature=0.6)


def gold_facts(data: dict) -> dict:
    out = {"gold_analysis": data["gold_analysis"], "us_macro": data.get("macro", {}),
           "fed_rate_odds_headlines": data.get("rate_expectations", []),
           "gold_news": [_news_row(n) for n in data.get("news", []) if n["category"] == "gold"][:8]}
    return out


GOLD_RULES = """
   Biases (1H / 4H / Daily) must match the analysis exactly and be worded as conditional reads.
   Remove "buy", "sell", "long", "short", "entry", "stop loss", "take profit", "guaranteed"."""


def _merge_plan(plan: list[dict], pkg: dict) -> dict:
    scenes = pkg.get("scenes") or []
    texts = {str(s.get("id")): (s.get("text") or "").strip() for s in scenes}
    if not any(p["id"] in texts for p in plan) and len(scenes) == len(plan):  # ids dropped: go by order
        texts = {p["id"]: (s.get("text") or "").strip() for p, s in zip(plan, scenes)}
    pkg["scenes"] = [{"id": p["id"], "text": texts.get(p["id"], ""), "visual": p["visual"]} for p in plan]
    return pkg


def make_gold_script(cfg: dict, data: dict, used_headlines: list[str], cover: dict, log=print) -> dict:
    plan = gold_plan(data, used_headlines)
    for attempt in range(3):
        log("Writing the gold outlook...")
        pkg = _merge_plan(plan, write_gold(cfg, data, plan, cover, used_headlines))
        log(f"Draft: {pkg.get('title', '')}. Fact-checking against the analysis...")
        verdict, checked, issues = fact_check(cfg, gold_facts(data), pkg, GOLD_RULES)
        pkg = _merge_plan(plan, checked)
        _clean_last_line(pkg["scenes"], log, can_drop=False)  # fixed plan: never drop a scene
        log(f"Fact-check: {verdict}" + (f" ({len(issues)} fixes)" if issues else ""))
        problems = validate(cfg, data, pkg)
        if verdict != "reject" and not problems:
            pkg["fact_check"] = {"verdict": verdict, "issues": issues}
            return pkg
        log(f"Discarding draft: verdict={verdict} problems={problems}")
    raise RuntimeError("Could not produce a valid gold script in 3 attempts")
