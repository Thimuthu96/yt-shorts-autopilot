"""Topic selection, script writing and fact-check pass."""
import json
import random

from .llm import generate_json

HOOK_STYLES = [
    "a surprising claim that challenges what the viewer assumes",
    "a direct question the viewer has probably wondered about",
    "a common belief, then immediately say it's wrong",
    "a vivid 'imagine...' moment the viewer can picture",
    "a startling but accurate comparison (no invented numbers)",
]

ENDINGS = [
    "a twist fact that makes the viewer want to rewatch",
    "a quick question inviting viewers to comment their own example",
    "a callback to the opening line that lands the answer",
]

PACKAGE_SCHEMA = """{
  "title": "string, under 60 characters",
  "scenes": [
    {"text": "narration for this scene (1-2 short sentences)",
     "visual": "stock footage search query, 2-4 concrete visual words",
     "visual_alt": "a different backup query"}
  ],
  "description": "2-3 sentences",
  "tags": ["search phrase", "..."],
  "hashtags": ["#example", "..."]
}"""


def pick_topic(cfg: dict, recent_topics: list[str]) -> dict:
    ch, llm = cfg["channel"], cfg["llm"]
    covered = "\n".join(f"- {t}" for t in recent_topics[-150:]) or "- (nothing yet)"
    prompt = f"""You plan videos for a YouTube Shorts channel.
Channel niche: {ch['niche']}
Audience: {ch['audience']}

Already covered — do NOT repeat these or anything that overlaps closely:
{covered}

Propose {llm['ideas_per_round']} fresh ideas. Each must be one specific question a curious
viewer would want answered in under a minute. Base them on well-established facts only:
no speculation, no news or current events, no medical, legal or financial advice.
Mix sub-topics (food, body, home, weather, materials, animals, sound, light...).

Return JSON: {{"ideas": [{{"topic": "the question", "angle": "the surprising part of the answer",
"confidence": 1-10 (how sure you are the core facts are textbook-solid)}}]}}"""
    ideas = generate_json(prompt, llm["model"], temperature=1.0).get("ideas", [])
    covered_lower = {t.lower() for t in recent_topics}
    ideas = [i for i in ideas if i.get("topic") and i["topic"].lower() not in covered_lower]
    if not ideas:
        raise RuntimeError("No usable topic ideas returned")
    ideas.sort(key=lambda i: i.get("confidence", 0), reverse=True)
    return random.choice(ideas[:3])


def write_package(cfg: dict, idea: dict) -> dict:
    ch, llm = cfg["channel"], cfg["llm"]
    prompt = f"""Write a YouTube Short.
Topic: {idea['topic']}
Surprising angle: {idea.get('angle', '')}
Channel niche: {ch['niche']}
Audience: {ch['audience']}. Tone: {ch['tone']}.

Narration rules:
- {llm['min_words']}-{llm['max_words']} words in total across all scenes. Spoken English, short sentences.
- First sentence (under 12 words) opens with {random.choice(HOOK_STYLES)}.
- No "in this video", no greetings, no "like and subscribe".
- Explain the actual mechanism in plain words, with one concrete everyday example.
- End with {random.choice(ENDINGS)}.
- Only state facts you are confident are accurate. Never invent statistics, studies, names or quotes.
- Write numbers the way they are spoken ("twenty percent", not "20%").

Structure: split the narration into 5-8 scenes. For each scene give a stock-footage search
query made of concrete, filmable things (e.g. "frozen lake skater", not "friction concept"),
plus a different backup query.

SEO:
- title: under 60 characters, specific and curiosity-driving, but the video must fully deliver
  on it. No ALL CAPS words, no emojis, no misleading claims.
- description: 2-3 sentences summarising the answer, with natural search keywords.
- tags: 8-12 phrases people would actually type into YouTube search.
- hashtags: 2-3, each starting with #, no spaces.

Return JSON exactly in this shape:
{PACKAGE_SCHEMA}"""
    pkg = generate_json(prompt, llm["model"], temperature=0.9)
    pkg["topic"] = idea["topic"]
    return pkg


def fact_check(cfg: dict, pkg: dict) -> tuple[str, dict, list]:
    llm = cfg["llm"]
    prompt = f"""You are a strict science fact-checking editor for a YouTube Shorts channel.
Review this video package:
{json.dumps(pkg, ensure_ascii=False, indent=2)}

1. List every factual claim in the narration and mark it "solid", "shaky" or "wrong".
2. If any claim is shaky or wrong, rewrite that scene so it is accurate, or remove the claim.
   Keep the narration between {llm['min_words']} and {llm['max_words']} words and keep the same JSON shape.
3. Make sure the narration actually answers what the title promises; fix the title if not.
4. verdict: "ok" if nothing changed, "revised" if you fixed things, "reject" only if the
   core premise of the video is false.

Return JSON: {{"claims": [{{"claim": "...", "status": "solid|shaky|wrong"}}],
"verdict": "ok|revised|reject", "package": <the full package, revised if needed>}}"""
    res = generate_json(prompt, llm["model"], temperature=0.2)
    verdict = res.get("verdict", "ok")
    revised = res.get("package") or pkg
    revised["topic"] = pkg["topic"]
    return verdict, revised, res.get("claims", [])


def validate(cfg: dict, pkg: dict) -> list[str]:
    problems = []
    scenes = pkg.get("scenes") or []
    if not 3 <= len(scenes) <= 10:
        problems.append(f"{len(scenes)} scenes")
    for i, s in enumerate(scenes):
        if not (s.get("text") or "").strip() or not (s.get("visual") or "").strip():
            problems.append(f"scene {i + 1} missing text or visual")
    words = sum(len(s.get("text", "").split()) for s in scenes)
    lo, hi = cfg["llm"]["min_words"], cfg["llm"]["max_words"]
    if not lo - 25 <= words <= hi + 20:
        problems.append(f"{words} words (target {lo}-{hi})")
    if not (pkg.get("title") or "").strip():
        problems.append("missing title")
    return problems


def make_package(cfg: dict, recent_topics: list[str], forced_topic: str | None = None,
                 log=print) -> dict:
    """Return a fact-checked package, retrying with new topics if needed."""
    tried = list(recent_topics)
    for attempt in range(3):
        idea = {"topic": forced_topic, "angle": ""} if forced_topic else pick_topic(cfg, tried)
        log(f"Topic: {idea['topic']}")
        pkg = write_package(cfg, idea)
        verdict, pkg, claims = fact_check(cfg, pkg)
        log(f"Fact-check verdict: {verdict} ({len(claims)} claims checked)")
        problems = validate(cfg, pkg)
        if verdict != "reject" and not problems:
            pkg["fact_check"] = {"verdict": verdict, "claims": claims}
            return pkg
        log(f"Discarding package: verdict={verdict} problems={problems}")
        tried.append(idea["topic"])
        forced_topic = None
    raise RuntimeError("Could not produce a valid package in 3 attempts")
