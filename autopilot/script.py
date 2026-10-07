"""Turn the day's data into a grounded Shorts script with a graphic per scene."""
import json
import random

from .llm import generate_json

SCENE_TYPES = {
    "title": "opening card: a short headline (max 9 words) + a kicker (max 4 words)",
    "price": 'a coin\'s 7-day chart; needs "asset": one of the coin symbols in the data',
    "fx": 'a forex pair\'s 30-day chart; needs "asset": one of the FX pair codes in the data',
    "board": "table of all coins and FX pairs with their % change",
    "news": 'one headline card; needs "source" and "headline" (your own max-12-word paraphrase)',
    "calendar": "table of today's high-impact economic events (only if there are any)",
    "outro": "closing card with the not-financial-advice note",
}

HOOKS = [
    "the single biggest move of the day, stated with its number",
    "a question about why something moved, answered right away",
    "what traders are watching today and why it matters",
]

SCHEMA = """{
  "title": "YouTube title, max 70 chars, include the date like 'Oct 7'",
  "scenes": [
    {"text": "narration (1-2 short spoken sentences)",
     "visual": {"type": "title|price|fx|board|news|calendar|outro", "...": "fields for that type"}}
  ],
  "description": "2-3 sentences summarising the brief",
  "tags": ["search phrase", "..."],
  "hashtags": ["#Bitcoin", "..."],
  "headlines_used": ["exact titles of the news items you referred to"],
  "thumbnail_hook": "2-4 word hook for the thumbnail"
}"""


def brief_for_llm(data: dict, max_news: int = 30) -> dict:
    """Compact, number-rounded view of the data (no long price series)."""
    def r(x, n=2):
        return round(x, n)
    return {
        "date_utc": data["date_utc"], "weekday": data["weekday"], "weekend": data["weekend"],
        "crypto": {s: {"name": c["name"], "price_usd": r(c["price"], 4 if c["price"] < 10 else 2),
                       "change_24h_pct": r(c["change_24h"]), "change_7d_pct": r(c["change_7d"]),
                       "high_24h": r(c["high_24h"]), "low_24h": r(c["low_24h"])}
                   for s, c in data["crypto"].items()},
        "fx": {p: {"name": f["name"], "rate": r(f["price"], 4 if f["price"] < 20 else 2),
                   "change_1d_pct": r(f["change_1d"]), "change_30d_pct": r(f["change_30d"]),
                   "rate_date": f["as_of"], "note": "daily central-bank reference rate"}
               for p, f in data["fx"].items()},
        "calendar_today_utc": data["calendar"],
        "news": [{"source": n["source"], "title": n["title"], "summary": n["summary"][:200],
                  "published": n["published"], "category": n["category"]}
                 for n in data["news"][:max_news]],
    }


def write(cfg: dict, data: dict, used_headlines: list[str], cover: dict, session: dict | None = None) -> dict:
    ch, llm = cfg["channel"], cfg["llm"]
    brief = brief_for_llm(data)
    recent = "\n".join(f"- {h}" for h in used_headlines[-60:]) or "- (none)"
    types = "\n".join(f'- "{k}": {v}' for k, v in SCENE_TYPES.items())
    session = session or {}
    edition = (f"EDITION: the {session.get('label')} brief. {session.get('focus', '')}\n"
               if session.get("label") else "")
    since = (f"News below is only what came out since the previous brief ({data['news_since']}).\n"
             if data.get("news_since") else "")
    prompt = f"""You write a YouTube Short: a {llm['min_words']}-{llm['max_words']} word market brief.
Channel: {ch['niche']}
Audience: {ch['audience']}. Tone: {ch['tone']}.
{edition}{since}

TODAY'S DATA (the only facts you may use):
{json.dumps(brief, ensure_ascii=False, indent=1)}

Headlines already covered in earlier briefs (don't repeat them):
{recent}

Rules:
- Every number you say must come from the data above. Round naturally and say it the way it
  is spoken ("about sixty-two thousand four hundred dollars", "down two point one percent").
- Only explain WHY something moved if a headline in the data says so; otherwise just state the move.
- Crypto prices are live; forex rates are daily reference rates, so say "yesterday's close"
  or "the latest daily fix" for them, never "right now".
- If "weekend" is true, forex markets are closed: focus on crypto and the week ahead.
- If the calendar is empty, skip the calendar scene.
- The calendar has times, forecasts and previous values only, never results: don't state an
  actual figure unless a headline in the data reports it.
- No predictions, price targets, buy/sell calls or "this could explode". Neutral, factual.
  End with a short spoken note that this is not financial advice.
- First line (under 12 words) opens with {random.choice(HOOKS)}.
- No greetings, no "in this video", no "like and subscribe".

OPENING CARD (also the video's thumbnail) — already designed from the data, it shows:
  {cover['facts']}
- Scene 1 uses visual "title" and its first sentence must state exactly that fact, so the
  viewer who clicked gets it straight away. The rest of the brief must answer the hook.
- "thumbnail_hook": 2-4 words, max 22 characters, written in capitals, that make people want
  the answer, e.g. "{cover['default_hook']}". It must be answered by this video. No predictions,
  no "moon", "buy", "sell", "will", "guaranteed", no emojis.

Structure: 6-9 scenes. Scene 1 uses visual "title"; the last uses "outro". Pick a fitting
visual for every scene from these types:
{types}

SEO:
- title: specific (name the asset and the move), include the date and the edition name
  (e.g. "| London Open, Oct 7"), no clickbait, no emojis.
- tags: 8-12 phrases people search (e.g. "bitcoin price today", "forex news today").
- hashtags: 2-3.

Return JSON exactly in this shape:
{SCHEMA}"""
    models = [llm["model"], *llm.get("fallback_models", [])]
    pkg = generate_json(prompt, models, temperature=0.7)
    return pkg


def fact_check(cfg: dict, data: dict, pkg: dict) -> tuple[str, dict, list]:
    llm = cfg["llm"]
    prompt = f"""You are a strict financial news editor. Check this Short script against the data.

DATA:
{json.dumps(brief_for_llm(data), ensure_ascii=False, indent=1)}

SCRIPT:
{json.dumps(pkg, ensure_ascii=False, indent=1)}

1. Every number and claim in the narration, title and visuals must match the data (rounding is
   fine). Every "why" must be backed by a headline in the data. Fix anything that isn't.
2. Remove any prediction, price target, or buy/sell suggestion (also in "thumbnail_hook").
3. Keep {llm['min_words']}-{llm['max_words']} words of narration and the same JSON shape.
4. verdict: "ok", "revised", or "reject" (only if the script is fundamentally wrong).

Return JSON: {{"issues": ["..."], "verdict": "ok|revised|reject", "package": <full package>}}"""
    models = [llm["model"], *llm.get("fallback_models", [])]
    res = generate_json(prompt, models, temperature=0.1)
    revised = res.get("package") or pkg
    return res.get("verdict", "ok"), revised, res.get("issues", [])


def validate(cfg: dict, data: dict, pkg: dict) -> list[str]:
    problems = []
    scenes = pkg.get("scenes") or []
    if not 4 <= len(scenes) <= 11:
        problems.append(f"{len(scenes)} scenes")
    for i, s in enumerate(scenes):
        v = s.get("visual") or {}
        t = v.get("type")
        if not (s.get("text") or "").strip():
            problems.append(f"scene {i + 1}: no narration")
        if t not in SCENE_TYPES:
            problems.append(f"scene {i + 1}: unknown visual {t!r}")
        elif t == "price" and v.get("asset") not in data["crypto"]:
            problems.append(f"scene {i + 1}: no price data for {v.get('asset')!r}")
        elif t == "fx" and v.get("asset") not in data["fx"]:
            problems.append(f"scene {i + 1}: no FX data for {v.get('asset')!r}")
        elif t == "news" and not (v.get("headline") or "").strip():
            problems.append(f"scene {i + 1}: news card without headline")
    words = sum(len(s.get("text", "").split()) for s in scenes)
    lo, hi = cfg["llm"]["min_words"], cfg["llm"]["max_words"]
    if not lo - 30 <= words <= hi + 25:
        problems.append(f"{words} words (target {lo}-{hi})")
    if not (pkg.get("title") or "").strip():
        problems.append("missing title")
    return problems


def fix_visuals(data: dict, pkg: dict) -> None:
    """Degrade gracefully instead of failing: unusable visuals become a market board.
    Scene 1 is always the opening card (the thumbnail)."""
    scenes = pkg.get("scenes") or []
    if scenes:
        scenes[0]["visual"] = {"type": "title"}
    for s in scenes:
        v = s.get("visual") or {}
        t = v.get("type")
        if (t == "price" and v.get("asset") not in data["crypto"]) or \
           (t == "fx" and v.get("asset") not in data["fx"]) or \
           (t == "calendar" and not data["calendar"]) or t not in SCENE_TYPES:
            s["visual"] = {"type": "board"}


def make_script(cfg: dict, data: dict, used_headlines: list[str], cover: dict, session: dict | None = None,
                log=print) -> dict:
    for attempt in range(3):
        log("Writing the script...")
        pkg = write(cfg, data, used_headlines, cover, session)
        log(f"Draft: {pkg.get('title', '')}. Fact-checking against the data...")
        verdict, pkg, issues = fact_check(cfg, data, pkg)
        log(f"Fact-check: {verdict}" + (f" ({len(issues)} fixes)" if issues else ""))
        fix_visuals(data, pkg)
        problems = validate(cfg, data, pkg)
        if verdict != "reject" and not problems:
            pkg["fact_check"] = {"verdict": verdict, "issues": issues}
            return pkg
        log(f"Discarding draft: verdict={verdict} problems={problems}")
    raise RuntimeError("Could not produce a valid script in 3 attempts")
