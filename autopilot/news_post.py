"""Facebook news image posts: one important story that moves crypto / forex (rate decisions,
central-bank speeches and statements, war and geopolitics, tariffs, regulation, macro data…).

pick_story()  scores the last 48 h of headlines (topic weight + multi-outlet coverage + recency),
              skips stories earlier Facebook posts used, and never comes back empty.
write_post()  Gemini writes the card text (kicker, 2-3 line headline, subline), the caption and a
              symbolic image prompt; script.fact_check() checks it against the story; numbers are
              verified against the facts. Any failure → a deterministic post from the story itself.
caption()     the final Facebook caption: hook first, source named, key numbers from fetched data,
              disclaimer, ≤5 hashtags, no links.
"""
import json
import re
from datetime import datetime, timezone

from . import focus, seo, thumbnail
from .facebook import clean_text, fb_hashtags, strip_hashtags
from .llm import generate_json
from .script import _models, _news_row, fact_check

# topic: (regex, kicker, hashtags)
TOPICS = {
    "rates": (r"rate (decision|cut|hike|hold|pause)s?|(cuts?|hikes?|holds?|raises?|lowers?|keeps?) "
              r"(interest )?rates|interest rates?|basis points?|\bbps\b|policy rate|monetary policy|\bfomc\b",
              "INTEREST RATES", ["#InterestRates"]),
    "central_bank": (r"\bfed\b|federal reserve|powell|\becb\b|lagarde|bank of (england|japan|canada)|\bboe\b|"
                     r"\bboj\b|\bsnb\b|\brba\b|\bpboc\b|central bank|\bminutes\b|\bspeech\b",
                     "CENTRAL BANKS", ["#Fed"]),
    "geopolitics": (r"\bwars?\b|missile|airstrike|\battacks?\b|invasion|invade|sanction|conflict|ceasefire|"
                    r"military|troops|nuclear|geopolitic|middle east|ukraine|russia|israel|\biran\b|taiwan|"
                    r"houthi|red sea", "GEOPOLITICS", ["#Geopolitics"]),
    "tariffs": (r"tariff|trade war|trade deal|trade talks|export (ban|control)s?|import dut|customs dut",
                "TRADE & TARIFFS", ["#Tariffs"]),
    "regulation": (r"\bsec\b|\bcftc\b|regulat|stablecoin|lawsuit|legislation|\bbill\b|congress|senate|\bmica\b|"
                   r"licen[cs]e|crackdown|\bban(s|ned)?\b", "REGULATION", ["#CryptoRegulation"]),
    "macro": (r"\bcpi\b|inflation|\bgdp\b|payrolls|jobs report|unemployment|jobless|\bpmi\b|retail sales|"
              r"\bpce\b|recession|treasury yields?|bond yields?", "MACRO DATA", ["#Economy"]),
    "crypto": (r"bitcoin|\bbtc\b|\bether(eum)?\b|crypto|solana|\bxrp\b|\betfs?\b", "CRYPTO", ["#Crypto"]),
    "gold": (r"\bgold\b|bullion|\bxau", "GOLD", ["#Gold"]),
    "fx": (r"\bdollar\b|\beuro\b|\byen\b|\bpound\b|sterling|forex|currenc|\bfx\b", "FOREX", ["#Forex"]),
}
_TRX = {k: re.compile(v[0], re.I) for k, v in TOPICS.items()}
DEFAULT_WEIGHTS = {"rates": 1.0, "central_bank": 0.85, "geopolitics": 0.9, "tariffs": 0.9, "regulation": 0.8,
                   "macro": 0.8, "crypto": 0.5, "gold": 0.5, "fx": 0.5}

# symbolic backgrounds when Gemini gives no image prompt (never the real event, people or text)
SCENES = {
    "rates": "a grand neoclassical central bank building with tall stone columns at dusk, warm golden light, "
             "dramatic clouds",
    "central_bank": "an empty wood-panelled meeting room with a long polished table and a single microphone, "
                    "soft dramatic light",
    "geopolitics": "a world map spread on a dark table lit by a single lamp, chess pieces standing on it, "
                   "tense moody atmosphere",
    "tariffs": "stacked shipping containers at a busy port at night, cranes silhouetted, orange harbour lights",
    "regulation": "a judge's gavel on a dark desk beside a glowing golden coin, blurred courthouse columns behind",
    "macro": "a financial district skyline at blue hour, glowing office windows, light trails on the streets",
    "crypto": "a glowing golden coin with circuit patterns on a dark reflective surface, blue and amber light",
    "gold": "stacked gold bars in a dark vault, warm reflections, shallow depth of field",
    "fx": "a vintage brass balance scale on a dark desk with coins on both pans, dramatic side light",
    "markets": "abstract glowing market chart lines over a dark city skyline at night",
}

_BANNED_RX = re.compile(r"\b(" + "|".join(re.escape(w.lower()) for w in thumbnail.BANNED if w.isalnum()) + r")\b",
                        re.I)


# ─── picking the story ─────────────────────────────────────────────────────

def topics(item: dict) -> dict:
    """{topic: 1.0 if in the title, 0.5 if only in the summary}"""
    title, rest = item.get("title", ""), f"{item.get('summary', '')} {item.get('body', '')[:400]}"
    out = {}
    for k, rx in _TRX.items():
        if rx.search(title):
            out[k] = 1.0
        elif rx.search(rest):
            out[k] = 0.5
    return out


def _similar(a: str, b: str) -> bool:
    wa, wb = focus._words(a), focus._words(b)
    if not wa or not wb:
        return a.strip().lower() == b.strip().lower()
    shared = len(wa & wb)
    ratio = shared / min(len(wa), len(wb))
    return (shared >= 3 and ratio >= 0.5) or ratio >= 0.75  # the same story told by another outlet


def _age_hours(n: dict, now: datetime) -> float:
    try:
        return (now - datetime.fromisoformat(n["published"])).total_seconds() / 3600
    except (KeyError, TypeError, ValueError):
        return 24.0


def pick_story(data: dict, fb_used: list[str], video_used: list[str] | None = None, cfg: dict | None = None,
               last_topic: str | None = None, now: datetime | None = None, log=print) -> dict:
    """The most important story not used by an earlier Facebook post. Tiers: fresh (≤ fresh_hours)
    → anything in the 48 h window → any story at all (never skips while there is news)."""
    np_cfg = (cfg or {}).get("news_posts") or {}
    weights = DEFAULT_WEIGHTS | (np_cfg.get("topic_weights") or {})
    fresh_h = float(np_cfg.get("fresh_hours", 12))
    window_h = float(np_cfg.get("news_hours", 48))
    now = now or datetime.now(timezone.utc)
    items = [n for n in data.get("news", []) if n.get("title")]
    if not items:
        raise RuntimeError("No news to post about")
    used = [h for h in fb_used if h]
    video = {h.lower() for h in (video_used or [])}

    scored = []
    for n in items:
        age = _age_hours(n, now)
        t = topics(n)
        if t:
            main = max(t, key=lambda k: weights.get(k, 0.3) * t[k])
            topic_score = weights.get(main, 0.3) * t[main] + 0.15 * min(len(t) - 1, 2)
        else:
            main, topic_score = "markets", 0.3
        cover = [m for m in items if m is not n and len(focus._words(m["title"]) & focus._words(n["title"])) >= 2]
        recency = 1.0 if age < 3 else 0.7 if age < 6 else 0.4 if age < 12 else 0.15 if age < 24 else 0.0
        assets = [a for a, s in focus.tag(n).items() if s >= 1.0]
        detail = 0.15 if n.get("body") or len(n.get("summary", "")) > len(n["title"]) + 30 else 0.0
        score = (topic_score + 0.35 * min(len(cover), 5) + recency + (0.3 if assets else 0.0) + detail
                 - (0.5 if n["title"].lower() in video else 0.0) - (0.3 if main == last_topic else 0.0))
        scored.append({"item": n, "score": score, "age": age, "topic": main, "topics": sorted(t),
                       "assets": assets, "coverage": cover,
                       "used": any(_similar(n["title"], u) for u in used)})

    tiers = [("fresh", [s for s in scored if s["age"] <= fresh_h and not s["used"]]),
             ("not used yet", [s for s in scored if s["age"] <= window_h and not s["used"]]),
             ("best available (all recent stories were used)",
              [s for s in scored if not (used and _similar(s["item"]["title"], used[-1]))] or scored)]
    # stories whose own title has hype / prediction words only as a last resort (never skip a post)
    calm = [(name, [s for s in pool if not _BANNED_RX.search(s["item"]["title"])]) for name, pool in tiers]
    tier, pool = next((name, pool) for name, pool in calm + tiers if pool)
    best = max(pool, key=lambda s: s["score"])
    n = best["item"]
    story = {k: v for k, v in n.items() if not k.startswith("_")}
    story.update({"topic": best["topic"], "topics": best["topics"], "assets": best["assets"],
                  "score": round(best["score"], 2), "tier": tier,
                  "coverage": [{"source": m["source"], "title": m["title"]} for m in best["coverage"][:5]]})
    log(f"News post story ({tier}, {best['topic']}, score {best['score']:.2f}): {n['source']}: {n['title']}")
    return story


# ─── writing the post ──────────────────────────────────────────────────────

def chart_assets(story: dict, data: dict) -> list[str]:
    """Tracked assets the story names (title first), with price data, at most 3."""
    tags = focus.tag(story)
    have = set(data.get("crypto", {})) | set(data.get("fx", {})) | ({"XAU"} if data.get("gold") else set())
    out = sorted((a for a in tags if a in have), key=lambda a: -tags[a])
    if not out and "USD" in tags:
        out = [a for a in focus.RELATED["USD"] if a in have][:2]
    return out[:3]


def key_numbers(story: dict, data: dict) -> list[str]:
    assets = chart_assets(story, data)
    if not assets:
        return []
    return seo.key_numbers({**data, "kind": "market", "focus": {"assets": assets}})


def facts_for(story: dict, data: dict) -> dict:
    return {"date_utc": data.get("date_utc"), "weekday": data.get("weekday"),
            "story": _news_row(story, body=True),
            "same_story_elsewhere": story.get("coverage", []),
            "key_numbers": key_numbers(story, data),
            "calendar_next_24h_gmt": data.get("calendar", [])[:6],
            "us_macro": data.get("macro", {}),
            "fed_rate_odds_headlines": data.get("rate_expectations", [])}


POST_RULES = """
   This is a Facebook IMAGE POST, not a video script: "headline" is a list of 2-3 short card lines,
   "caption" is the post text. There is no narration; ignore any word count for narration and keep
   the caption 50-160 words. Every number in "headline", "subline" and "caption" must be in the data.
   Remove predictions, hype and the words buy, sell, moon, guaranteed, will (about prices).
   "image_prompt" must describe a symbolic scene with no text, logos or real people; keep it as is
   if it already does."""


def _prompt(cfg: dict, story: dict, facts: dict) -> str:
    ch = cfg["channel"]
    banned = ", ".join(sorted(w.lower() for w in thumbnail.BANNED))
    return f"""You write ONE Facebook image post for {ch.get('display_name', 'CryptoFX Daily')}, a crypto & forex
market news page. Audience: {ch['audience']}. Tone: {ch['tone']}.
The post is about this one story only: {story['source']}: "{story['title']}"

FACTS (the only facts and numbers you may use):
{json.dumps(facts, ensure_ascii=False, indent=1)}

Write:
- "kicker": 1-3 words in capitals naming the topic, e.g. "RATE DECISION", "TRADE WAR", "FED SPEECH", "SEC".
- "headline": 2 or 3 short lines in capitals, max 18 characters per line, max 8 words in total, that
  state the news itself (who did what), e.g. ["FED HOLDS", "RATES STEADY"]. A number only if it is in the facts.
- "accent_line": the index (0-based) of the headline line that carries the key fact (shown in colour).
- "subline": one plain sentence, max 90 characters, with the most important detail.
- "caption": 60-130 words of plain text in 2-4 short paragraphs separated by blank lines. The first
  sentence (max 120 characters) is the hook: the news itself, clear and specific. Then what happened,
  naming the source ("according to {story['source']}"); why only if the story or the other coverage
  says so; which markets it matters for (crypto, the US dollar, gold, a currency) worded as general
  tendencies ("usually", "tends to") unless the story itself states the effect; and what to watch
  next from the calendar if it is relevant. Use the words people search for (e.g. "Fed rate decision",
  "Bitcoin price", "US tariffs"). No hashtags, no links, no emojis.
- "hashtags": 3-5 specific hashtags.
- "image_prompt": max 40 words describing a symbolic background scene for the card: objects, places,
  light and mood that fit the story (e.g. "a grand stone central bank building at dusk, golden light,
  storm clouds"). Never text, letters, numbers, logos, flags with emblems, real or recognisable people,
  or a realistic depiction of the actual event.

Rules: every number must be in the facts (rounding is fine). "Why" only if a headline or article text
says so. No predictions, price targets, buy/sell calls or hype; never use: {banned}. Neutral and factual.

Return JSON: {{"kicker": "...", "headline": ["...", "..."], "accent_line": 1, "subline": "...",
"caption": "...", "hashtags": ["#..."], "image_prompt": "..."}}"""


_NUM = re.compile(r"(\$|€|£)?(\d[\d,]*(?:\.\d+)?)\s?(%|k\b|m\b|b\b|bn\b|billion|million|trillion|thousand|bps?\b)?",
                  re.I)
_SCALE = {"k": 1e3, "thousand": 1e3, "m": 1e6, "million": 1e6, "b": 1e9, "bn": 1e9, "billion": 1e9,
          "trillion": 1e12}


def _numbers(text: str) -> list[tuple[float, bool]]:
    """[(value, is_bare_small_int)] for every number in the text, with K/M/B scaling applied."""
    out = []
    for cur, num, unit in _NUM.findall(text or ""):
        try:
            v = float(num.replace(",", ""))
        except ValueError:
            continue
        scale = _SCALE.get((unit or "").lower(), 1)
        out.append((v * scale, not cur and not unit and v == int(v) and v <= 10))
        if scale != 1:
            out.append((v, False))
    return out


def unverified_numbers(text: str, facts: dict) -> list[float]:
    known = [v for v, _ in _numbers(json.dumps(facts, ensure_ascii=False))]
    bad = []
    for v, small in _numbers(text):
        if small:
            continue
        if not any(abs(v - f) <= max(0.012 * abs(f), 0.051) for f in known):
            bad.append(v)
    return bad


def _card_ok(lines: list[str], kicker: str, subline: str) -> bool:
    if not 2 <= len(lines) <= 3 or any(not ln or len(ln) > 22 for ln in lines):
        return False
    words = " ".join(lines + [kicker, subline]).upper().replace("’", "'")
    return not any(w.strip("?!.,:;'\"") in thumbnail.BANNED for w in words.split())


def _drop_banned(text: str) -> str:
    """Remove sentences with hype / prediction words from a caption."""
    paras = []
    for para in re.split(r"\n\s*\n", text or ""):
        sents = re.split(r"(?<=[.!?])\s+", para.strip())
        keep = [s for s in sents if s and not _BANNED_RX.search(s) and "now!" not in s.lower()]
        if keep:
            paras.append(" ".join(keep))
    return "\n\n".join(paras)


def _shorten(title: str) -> str:
    """The story's main clause, for a headline that fits the card."""
    t = re.sub(r"\s+", " ", title.replace('"', "").replace("“", "").replace("”", "")).strip()
    if len(t) <= 66:
        return t
    for sep in (": ", " - ", " — ", "; ", ", ", " as ", " after ", " amid ", " while ", " despite "):
        head = t.split(sep, 1)[0]
        if sep in t and len(head.split()) >= 3 and len(head) <= 66:
            return head
    words, out = t.split(), ""
    for w in words:
        if len(out) + len(w) + 1 > 62:
            break
        out = f"{out} {w}".strip()
    return out + "…"


def _balanced(words: list[str], n: int) -> list[str]:
    """Split words into n lines with the shortest possible longest line."""
    best = None
    for cuts in ([(i,) for i in range(1, len(words))] if n == 2 else
                 [(i, j) for i in range(1, len(words) - 1) for j in range(i + 1, len(words))]):
        bounds = (0, *cuts, len(words))
        lines = [" ".join(words[a:b]) for a, b in zip(bounds, bounds[1:])]
        if best is None or max(map(len, lines)) < max(map(len, best)):
            best = lines
    return best


def wrap_headline(text: str) -> list[str]:
    """2-3 upper-case lines of similar length (render_card shrinks the font for long lines)."""
    words = text.upper().split()
    if len(words) < 2:
        return words or ["MARKET NEWS"]
    for width in (14, 16, 18, 20, 22, 24, 26):
        lines, cur = [], ""
        for w in words:
            if cur and len(cur) + 1 + len(w) > width:
                lines.append(cur)
                cur = w
            else:
                cur = f"{cur} {w}".strip()
        if cur:
            lines.append(cur)
        if len(lines) <= 3:
            break
    if len(lines) == 1:
        return _balanced(words, 2)
    return lines if len(lines) <= 3 else _balanced(words, 3)


def fallback_post(story: dict, data: dict) -> dict:
    """A plain, safe post built only from the story (used when Gemini fails or isn't trusted)."""
    title = clean_text(story["title"])
    lines = wrap_headline(_shorten(title))
    summary = clean_text(story.get("body") or story.get("summary") or "")
    detail = ""
    if summary and not _similar(summary[:len(title) + 40], title):
        first = re.split(r"(?<=[.!?])\s+", summary)[:2]
        detail = _drop_banned(" ".join(first)[:320])
    others = list(dict.fromkeys(c["source"] for c in story.get("coverage", []) if c["source"] != story["source"]))
    body = [title if title.endswith((".", "?", "!")) else title + "."]
    if detail:
        body.append(detail)
    body = [_drop_banned("\n\n".join(body))]  # no hype / prediction sentences, even in a source's title
    body.append(f"Reported by {story['source']}" + (f", also covered by {', '.join(others[:3])}" if others else "")
                + ".")
    body = [b for b in body if b]
    # the card already names the source, so the subline only carries a real detail
    sub = detail.split(". ")[0].rstrip(".") if detail and len(detail.split(". ")[0]) <= 90 else ""
    return {"kicker": TOPICS.get(story.get("topic"), ("", "MARKET NEWS"))[1], "headline": lines,
            "accent_line": len(lines) - 1, "subline": sub, "caption": "\n\n".join(body), "hashtags": [],
            "image_prompt": SCENES.get(story.get("topic"), SCENES["markets"]), "writer": "fallback"}


def write_post(cfg: dict, data: dict, story: dict, log=print) -> dict:
    """Card text + caption + image prompt, fact-checked; falls back to fallback_post() piece by piece."""
    facts = facts_for(story, data)
    base = fallback_post(story, data)
    try:
        pkg = generate_json(_prompt(cfg, story, facts), _models(cfg), temperature=0.6)
        small = cfg | {"llm": cfg["llm"] | {"min_words": 50, "max_words": 160}}
        verdict, checked, issues = fact_check(small, facts, pkg, POST_RULES)
        log(f"News post fact-check: {verdict}" + (f" ({len(issues)} fixes)" if issues else ""))
        if verdict == "reject":
            raise RuntimeError(f"fact-check rejected the post: {issues[:3]}")
        pkg = checked if isinstance(checked, dict) else pkg
    except Exception as e:  # never skip a post: write it from the story itself
        log(f"News post writer failed ({str(e)[:200]}); using the story's own headline")
        return base | {"fact_check": {"verdict": "fallback", "error": str(e)[:300]}}

    post = dict(base, writer="gemini", fact_check={"verdict": verdict, "issues": issues})
    lines = [re.sub(r"\s+", " ", str(x)).strip().upper().replace("’", "'") for x in (pkg.get("headline") or [])]
    kicker = re.sub(r"\s+", " ", str(pkg.get("kicker") or "")).strip().upper()[:28]
    subline = clean_text(str(pkg.get("subline") or ""))[:110]
    card_text = " ".join(lines + [subline])
    bad = unverified_numbers(card_text, facts)
    if _card_ok(lines, kicker, subline) and not bad:
        try:
            acc = int(pkg.get("accent_line", len(lines) - 1))
        except (TypeError, ValueError):
            acc = len(lines) - 1
        post.update(headline=lines, kicker=kicker or base["kicker"], subline=subline,
                    accent_line=min(max(acc, 0), len(lines) - 1))
    else:
        log(f"Card text from Gemini not used ({'numbers not in the data: ' + str(bad) if bad else 'length/words'}); "
            "using the story's headline")
    cap = _drop_banned(clean_text(str(pkg.get("caption") or "")))
    bad = unverified_numbers(cap, facts)
    if len(cap.split()) >= 25 and not bad:
        post["caption"] = cap
    else:
        log(f"Caption from Gemini not used ({'numbers not in the data: ' + str(bad) if bad else 'too short'})")
    post["hashtags"] = [str(h) for h in (pkg.get("hashtags") or [])][:6]
    prompt = clean_text(str(pkg.get("image_prompt") or ""))
    if 4 <= len(prompt.split()) <= 70:
        post["image_prompt"] = prompt
    return post


def hashtags(post: dict, story: dict, data: dict, limit: int = 5) -> list[str]:
    tags = list(TOPICS.get(story.get("topic"), ("", "", []))[2])
    for a in chart_assets(story, data):
        tags += seo.HASHTAGS.get(a, [])[:1]
    tags += post.get("hashtags", [])
    tags += ["#CryptoNews" if story.get("topic") in ("crypto", "regulation") else "#MarketNews"]
    return fb_hashtags(tags, limit)


def caption(post: dict, story: dict, data: dict, cfg: dict, ai_image: bool = False) -> str:
    """Hook first (Facebook shows ~280 characters before "See more"), then the body, the source,
    key numbers from the fetched data, what's next, disclaimer and ≤5 hashtags. No links."""
    np_cfg = cfg.get("news_posts") or {}
    parts = [clean_text(post["caption"])]
    if story["source"].lower() not in parts[0].lower():
        parts.append(f"Source: {story['source']}.")
    numbers = key_numbers(story, data)
    if numbers:
        parts.append("Market check:\n" + "\n".join(numbers))
    cur = set().union(*(focus.CURRENCIES.get(a, set()) for a in chart_assets(story, data))) or {"USD"}
    now = datetime.now(timezone.utc)

    def ahead(e):
        try:
            return datetime.fromisoformat(e["datetime"]) >= now
        except (KeyError, TypeError, ValueError):
            return False
    evs = [e for e in data.get("calendar", []) if e.get("currency") in cur and ahead(e)][:2]
    if evs:
        parts.append("Coming up (GMT):\n" + "\n".join(f"• {e['time_utc']} {e['currency']} {e['event']}" for e in evs))
    disclaimer = " ".join(str(np_cfg.get("disclaimer") or cfg.get("upload", {}).get("disclaimer") or "").split())
    if disclaimer:
        parts.append("⚠️ " + disclaimer)
    if ai_image:
        parts.append("Image: AI illustration, not a photo of the event.")
    tags = " ".join(hashtags(post, story, data, int((cfg.get("facebook") or {}).get("max_hashtags", 5))))
    parts = [strip_hashtags(p) for p in parts]  # the only hashtags are the ≤5 in the tag line
    return "\n\n".join(p for p in parts if p).strip() + ("\n\n" + tags if tags else "")
