"""Lesson narration: free Gemini narrates `lessons.scene_plan` scene by scene from the episode's
approved key points, its glossary definitions and the examples' facts only.

    lesson_facts()        the only inputs the writer sees (title, key points, glossary, examples' facts)
    write_lesson()        one Gemini call → {"scenes": [{"id", "text"}]}
    script.fact_check()   with LESSON_RULES and a cfg copy holding the lesson word bounds (550-700)
    check_lesson()        deterministic: every scene narrated, word bounds, banned words/claims,
                          numbers backed by the facts, disclaimer, ICT non-affiliation (track 4)
    make_lesson_script()  up to 3 attempts, like script.make_gold_script

Live sample (needs GEMINI_API_KEY; sample curriculum + fixture candles, no market data):
    python -m autopilot.lesson_script
"""
import json
import re
import sys
from pathlib import Path

from autopilot import detectors  # noqa: F401  (registers the detectors, so their glossary keys are known)
from autopilot import lessons
from autopilot.llm import generate_json
from autopilot.news_post import unverified_numbers
from autopilot.script import _merge_plan, _models, fact_check

MIN_WORDS, MAX_WORDS = 550, 700
DISCLAIMER = "This is education, not financial advice."
NON_AFFILIATION = "This channel is not affiliated with The Inner Circle Trader."
ICT_TRACK = 4

# case-insensitive; "buy-side" / "sell-side" (liquidity) are allowed terms
BANNED = [re.compile(p, re.I) for p in (
    r"\bbuy\b(?![- ]side)", r"\bsell\b(?![- ]side)", r"\bentr(?:y|ies)\b", r"\bstop[- ]loss",
    r"\btake[- ]profit", r"\btarget", r"\bwin[- ]?rate", r"\bguarantee", r"\bprofit",
    r"\bwill (?:reach|hit|go|drop|rise)\b",
)]
DASHES = re.compile("[\u2010-\u2015\u2212]")  # Unicode hyphens / dashes / minus → "-" before matching

# times and dates are not numbers a viewer is told: dropped from the facts for the number check, and
# spoken dates / clock times are taken out of the narration before it (else "2026-09-05" backs 9, 5, 2026)
TIME_KEYS = {"t", "t1", "t2", "swing_t", "date", "start", "end"}
_MONTHS = ("jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|"
           "sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?")
SPOKEN_TIME = re.compile(
    r"\b\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2})?(?:[+-]\d{2}:\d{2}|Z)?)?"
    r"|\b\d{1,2}:\d{2}\b"
    rf"|\b(?:{_MONTHS})\.? \d{{1,2}}(?:st|nd|rd|th)?\b(?:,? \d{{4}}\b)?"
    rf"|\b\d{{1,2}}(?:st|nd|rd|th)? (?:of )?(?:{_MONTHS})\b(?:,? \d{{4}}\b)?", re.I)

# spoken dates beyond SPOKEN_TIME: years 2010-2039, month names ("may"/"march" excluded: ordinary words), UTC
SPOKEN_DATE_WORDS = re.compile(r"\b20[1-3]\d\b|\b(?:january|february|april|june|july|august|september|"
                               r"october|november|december|sept?|oct|nov|dec)\b|\butc\b|\bgmt\b", re.I)

LESSON_RULES = """
   This is a trading LESSON, not a news brief. DATA holds the episode's approved key points, its
   glossary definitions and historical examples. The narration may teach only those key points and
   definitions: remove any other concept, indicator, pattern or strategy. Examples are historical,
   told in the past tense from their facts only. Remove any date, day, month, year or clock time.
   Keep sentences short and simple. Remove "buy" / "sell" (except "buy-side" /
   "sell-side" liquidity), "entry", "stop loss", "take profit", "target", "win rate", "profit",
   "guaranteed", predictions ("will reach / hit / go / drop / rise") and performance claims.
   Keep each scene's "id". The "recap" scene must keep: "This is education, not financial advice." """
ICT_RULE = f"""
   The "recap" scene must also keep: "{NON_AFFILIATION}" """


def _glossary_keys(entry: dict) -> list[str]:
    keys = list(entry.get("concepts") or [])
    det = lessons.DETECTORS.get(entry.get("detector")) if isinstance(entry.get("detector"), str) else None
    if det:
        keys += [k for k in det.glossary_keys() if k not in keys]
    return keys


def lesson_facts(entry: dict, glossary: dict, examples: list[dict]) -> dict:
    """Everything the narration may use: title, key points, glossary entries for the entry's concepts
    and detector keys, and each example's chart name and facts. No dates or times (they are hard to follow
    when spoken, owner 2026-10-10), no candles, no drawing."""
    terms = {k: {"term": glossary[k].get("term", k), "definition": glossary[k].get("definition", "")}
             for k in _glossary_keys(entry) if k in glossary}
    return {
        "title": entry["title"],
        "key_points": list(entry["key_points"]),
        "glossary": terms,
        "examples": [{"scene": f"example_{n}", "chart": lessons.spoken_chart(ex), "facts": _no_times(ex["facts"])}
                     for n, ex in enumerate(examples[:2], 1)],
    }


def _affiliated(entry: dict, plan: list[dict]) -> bool:
    recap = next((p for p in plan if p["id"] == "recap"), None)
    return entry.get("track") == ICT_TRACK or bool(recap and recap["visual"].get("non_affiliation"))


def write_lesson(cfg: dict, entry: dict, glossary: dict, plan: list[dict], examples: list[dict]) -> dict:
    ch = cfg.get("channel") or {}
    facts = lesson_facts(entry, glossary, examples)
    scenes = "\n".join(f'- "{p["id"]}": {p["covers"]}' for p in plan)
    ict = (f'\n- "recap" also says: "{NON_AFFILIATION}"' if _affiliated(entry, plan) else "")
    prompt = f"""You write the narration of a {MIN_WORDS}-{MAX_WORDS} word TRADING LESSON video: "{entry['title']}".
Channel: {ch.get('display_name', 'CryptoFX Daily')}. Audience: traders who want to learn this concept.
Tone: a friendly, patient teacher. The viewer should finish the video able to spot the concept themselves.

FACTS (the approved key points, glossary definitions and historical examples; the only things you may teach or quote):
{json.dumps(facts, ensure_ascii=False, indent=1)}

Write narration for each scene, in this order (2-6 spoken sentences each):
{scenes}

Rules:
- Teach only the key points and the glossary definitions above. Add no other concept, indicator,
  pattern or strategy.
- Keep it easy to follow: short sentences (under 20 words), one idea per sentence, plain words.
  Explain each term in simple words the first time you use it.
- The examples are historical examples on the chart the viewer is looking at. Describe each in the
  past tense from its facts only, in the scene with the same id. Call it by its chart, e.g. "on this
  Bitcoin hourly chart", and guide the eye: "first look at…", "then notice…".
- Never say a date, day, month, year or clock time.
- Avoid reading prices. Use at most one price per example, rounded, and only if it helps;
  otherwise say "the last high", "that level". No other numbers.
- No predictions, no advice, no performance claims. Never say buy, sell, entry, stop loss, take
  profit, target, win rate, profit, guaranteed, or "will" + reach / hit / go / drop / rise.
  "Buy-side" and "sell-side" liquidity are allowed terms.
- "recap" ends with: "{DISCLAIMER}"{ict}
- No greetings, no "in this video", no "like and subscribe".

Return JSON: {{"scenes": [{{"id": "{plan[0]['id']}", "text": "..."}}, ...]}}"""
    return generate_json(prompt, _models(cfg), temperature=0.6)


def _no_times(v):
    """The facts without time / date fields or ISO date strings (prices and other values kept)."""
    if isinstance(v, dict):
        return {k: _no_times(x) for k, x in v.items() if k not in TIME_KEYS}
    if isinstance(v, list):
        return [_no_times(x) for x in v]
    if isinstance(v, str):
        return SPOKEN_TIME.sub(" ", v)
    return v


def _fmt(v: float) -> str:
    """A number as spoken: thousands separators, up to 2 decimals, no exponent."""
    return f"{v:,.2f}".rstrip("0").rstrip(".")


def _words(pkg: dict) -> int:
    return sum(len((s.get("text") or "").split()) for s in pkg.get("scenes") or [])


def check_lesson(pkg: dict, entry: dict, plan: list[dict], facts: dict) -> list[str]:
    """Deterministic problems with a narration package ([] = usable)."""
    problems = []
    texts = {str(s.get("id")): (s.get("text") or "").strip() for s in pkg.get("scenes") or []}
    for p in plan:
        if not texts.get(p["id"]):
            problems.append(f"scene '{p['id']}': no narration")
    words = sum(len(texts.get(p["id"], "").split()) for p in plan)
    if not MIN_WORDS <= words <= MAX_WORDS:
        problems.append(f"{words} words (target {MIN_WORDS}-{MAX_WORDS})")
    narration = DASHES.sub("-", "\n".join(texts.get(p["id"], "") for p in plan))
    said = [m.group(0) for rx in (SPOKEN_TIME, SPOKEN_DATE_WORDS) for m in rx.finditer(narration)]
    if said:
        problems.append("says a date or time: " + ", ".join(dict.fromkeys(s.strip() for s in said)))
    hits = []
    for rx in BANNED:
        hits += [m.group(0) for m in rx.finditer(narration)]
    if hits:
        problems.append("banned wording: " + ", ".join(dict.fromkeys(h.lower() for h in hits)))
    # numbers may come from the facts or the scene list the writer was given (e.g. next episode title)
    known = _no_times({"facts": facts, "covers": [p["covers"] for p in plan]})
    bad = unverified_numbers(SPOKEN_DATE_WORDS.sub(" ", SPOKEN_TIME.sub(" ", narration)), known)  # dates: own problem
    if bad:
        problems.append("numbers not in the facts: " + ", ".join(_fmt(v) for v in dict.fromkeys(bad)))
    recap = texts.get("recap", "").lower().replace("’", "'")
    if "not financial advice" not in recap:
        problems.append("recap lacks the disclaimer (\"not financial advice\")")
    if _affiliated(entry, plan) and not ("not affiliated" in recap and "inner circle trader" in recap):
        problems.append("recap lacks the non-affiliation line (The Inner Circle Trader)")
    return problems


def _for_check(pkg: dict) -> dict:
    """What fact_check sees: the narration only (the example visuals carry candles)."""
    return {"title": pkg.get("title", ""), "scenes": [{"id": s["id"], "text": s["text"]} for s in pkg["scenes"]]}


def make_lesson_script(cfg: dict, entry: dict, glossary: dict, plan: list[dict], examples: list[dict],
                       log=print) -> dict:
    """Narration package {"scenes": [{id, text, visual}], "fact_check": {verdict, issues}}; RuntimeError
    with the last problems after 3 failed attempts."""
    lcfg = {**cfg, "llm": {**cfg["llm"], "min_words": MIN_WORDS, "max_words": MAX_WORDS}}
    facts = lesson_facts(entry, glossary, examples)
    rules = LESSON_RULES + (ICT_RULE if _affiliated(entry, plan) else "")
    problems = []
    for attempt in range(1, 4):
        log(f"Writing the lesson narration ({entry['id']}, attempt {attempt}/3)...")
        pkg = _merge_plan(plan, write_lesson(cfg, entry, glossary, plan, examples))
        pkg["title"] = entry["title"]
        log(f"Draft: {_words(pkg)} words. Fact-checking against the key points and examples...")
        verdict, checked, issues = fact_check(lcfg, facts, _for_check(pkg), rules)
        pkg = _merge_plan(plan, checked if isinstance(checked, dict) else {})
        pkg["title"] = entry["title"]
        log(f"Fact-check: {verdict}" + (f" ({len(issues)} fixes)" if issues else ""))
        problems = check_lesson(pkg, entry, plan, facts)
        if verdict != "reject" and not problems:
            pkg["fact_check"] = {"verdict": verdict, "issues": issues}
            return pkg
        if verdict == "reject":
            problems = ["fact-check verdict: reject"] + problems
        log(f"Discarding draft: {'; '.join(problems)}")
    raise RuntimeError(f"Could not produce valid lesson narration in 3 attempts: {'; '.join(problems)}")


# ─── live sample ───────────────────────────────────────────────────────────

def sample_inputs() -> tuple[dict, dict, dict, dict | None]:
    """(entry, glossary, price history, next entry) for the sample `bos-vs-choch` episode: tests/lessons/
    curriculum and glossary, fixture candles shaped like lesson_data.fetch_history's answer."""
    root = Path(__file__).resolve().parents[1] / "tests" / "lessons"
    curriculum = lessons.load_curriculum(root / "curriculum.yaml")
    i = next(n for n, e in enumerate(curriculum) if e["id"] == "bos-vs-choch")
    glossary = lessons.load_glossary(root / "glossary.yaml")

    def candles(name):
        return json.loads((root / "candles" / f"{name}.json").read_text(encoding="utf-8"))
    history = {"BTC/USD": {"1H": candles("downtrend_bos_choch")}, "ETH/USD": {"1H": candles("downtrend_hl_choch")}}
    return curriculum[i], glossary, history, (curriculum[i + 1] if i + 1 < len(curriculum) else None)


def sample_episode() -> tuple[dict, dict, list[dict], list[dict]]:
    """(entry, glossary, plan, examples) for the sample `bos-vs-choch` episode: tests/lessons/ curriculum
    and glossary, examples found by the real bos_choch detector on the fixture candles."""
    entry, glossary, history, _ = sample_inputs()
    examples = lessons.DETECTORS[entry["detector"]].find(history)
    return entry, glossary, lessons.scene_plan(entry, examples), examples


def main() -> int:
    import yaml
    cfg = yaml.safe_load((Path(__file__).resolve().parents[1] / "config.yaml").read_text(encoding="utf-8"))
    entry, glossary, plan, examples = sample_episode()
    print(f"Sample episode: {entry['title']} ({len(examples)} examples: "
          + ", ".join(f"{e['asset']} {e['timeframe']} {e['date']}" for e in examples) + ")")
    try:
        pkg = make_lesson_script(cfg, entry, glossary, plan, examples)
    except RuntimeError as e:
        print(f"FAILED: {e}")
        return 1
    for s in pkg["scenes"]:
        print(f"\n[{s['id']}] {s['text']}")
    problems = check_lesson(pkg, entry, plan, lesson_facts(entry, glossary, examples))
    print(f"\nWords: {_words(pkg)} (target {MIN_WORDS}-{MAX_WORDS})")
    print(f"Fact-check: {pkg['fact_check']['verdict']}"
          + (f" — issues: {pkg['fact_check']['issues']}" if pkg["fact_check"]["issues"] else ""))
    print(f"Problems: {problems or 'none'}")
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
