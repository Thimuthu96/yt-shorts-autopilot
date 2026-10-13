"""Shared narration rules (narration-rules.md): deterministic checks, no LLM.

    narration_problems(text)  every broken rule, named with the matched words, e.g.
                              'price target: "BTC to $150,000"'; [] when the text is clean
    NARRATION_RULES           the same rules as prompt text, for the writer and fact-check prompts
    title_problems(title)     packaging.md title rules (CAP-8): no date, session stamp, hashtag, price
                              target, "10x" or "EXPLODE"; logged only on today's brief and gold titles,
                              enforced by the new formats
    thumbnail_text_problems(text)   1-4 words plus the title rules, for the new formats' thumbnails
    DISCLOSURE / disclosure(cfg)    the disclosure line every description carries exactly once
                              (config `upload.disclaimer`, `news_posts.disclaimer`; DISCLOSURE if unset)
    without_disclosure(text, line)  writer text with any copy of the line removed, before it is appended
    SPOKEN_TIME / SPOKEN_DATE_WORDS / _MONTHS   date and clock-time patterns (lessons import them too)

Rules: a data desk, not a person: no first person (except inside a quote attributed to a source),
no price targets or predictions, no "10x", no buy/sell calls, and no spoken dates, month names,
clock times or UTC/GMT. Past facts stay legal ("Bitcoin fell to $84,000", "a sell-off"). Briefs and
the gold outlook may say a bare year ("the highest since 2021"); lessons ban years too (their own check).
"""
import re

# ─── dates and times (shared with lesson_script) ──────────────────────────
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

# briefs and gold: SPOKEN_DATE_WORDS without the bare year (owner, 2026-10-13: "the highest since 2021" is fine)
MONTH_OR_ZONE = re.compile(r"\b(?:january|february|april|june|july|august|september|october|november|"
                           r"december|sept?|oct|nov|dec)\b|\butc\b|\bgmt\b", re.I)
# "March" / "May" count only capitalised, and "May" not at a sentence start (there it can be the verb)
MARCH_MAY = re.compile(r"\bMarch\b|(?<![.!?]\s)(?<![\"\u201c\n])(?<!^)\bMay\b")
# clock times in words: "eight thirty a.m. Eastern", "at two p.m.", "nine o'clock", "half past eight"
_ONE_NINE = "one|two|three|four|five|six|seven|eight|nine"
_HOUR = rf"(?:{_ONE_NINE}|ten|eleven|twelve|1[0-2]|[1-9])"
_MINUTES = (rf"(?:oh[-\s]+(?:{_ONE_NINE})|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|"
            rf"eighteen|nineteen|(?:twenty|thirty|forty|fifty)(?:[-\s]+(?:{_ONE_NINE}))?)")
SPOKEN_CLOCK = [
    re.compile(rf"\b{_HOUR}(?:[-\s]+{_MINUTES})?\s*(?:[ap]\.\s?m\.?|[ap]m\b|o['\u2019]clock\b)", re.I),
    # a zone word, not "Eastern European exchanges" / "Central Bank"
    re.compile(rf"(?i:\b{_HOUR}(?:[-\s]+{_MINUTES})?)\s+(?:(?:Eastern|Pacific|Central|Mountain)\b"
               r"(?!\s+(?!Time\b)[A-Z]|\s+[Bb]ank)(?:\s+[Tt]ime\b)?|"
               r"(?:Central European|British|London|New York|Tokyo|Sydney)\s+[Tt]ime\b)"),
    re.compile(rf"\b(?:half|quarter)\s+(?:past|to)\s+{_HOUR}\b", re.I),
]

# ─── voice frame: data desk, not a person ─────────────────────────────────
FIRST_PERSON = re.compile(r"\bI(?:['\u2019](?:m|ve|d|ll))?(?![\w'\u2019])|\b[Mm](?:e|y|ine)\b")
# "mine" the noun ("a Texas Bitcoin mine", "gold mine output") is not first person
MINE_BEFORE = {"a", "an", "the", "this", "that", "its", "their", "our", "his", "her", "each", "every", "one",
               "new", "largest", "biggest", "bitcoin", "btc", "crypto", "gold", "coal", "copper", "silver",
               "lithium", "iron", "diamond", "salt", "open-pit", "underground"}
MINE_AFTER = {"output", "operator", "operators", "production", "site", "sites", "owner", "owners", "workers",
              "shaft", "closure", "closures", "expansion", "capacity", "supply", "in", "near", "at", "on"}
QUOTE = re.compile(r"[\"\u201c][^\"\u201c\u201d]*[\"\u201d]")
ATTRIBUTION = re.compile(r"\b(?:said|says|say|told|tells|wrote|writes|according to|added|adds|noted|notes|"
                         r"posted|posts|tweeted|stated|argued|warned|explained|commented)\b", re.I)

# ─── price targets and predictions ────────────────────────────────────────
_ADVERB = r"(?:\w+ly\s+|soon\s+|even\s+|still\s+|now\s+)?"
_NUMBER_WORD = (r"(?:zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|"
                r"fifteen|sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|sixty|seventy|eighty|"
                r"ninety|hundred|thousand|million|billion|point)")
# "a hundred thousand dollars", "one hundred fifty thousand", "eighty-four thousand dollars"
_AMOUNT = (rf"(?:an?\s+|{_NUMBER_WORD}[-\s]+(?:and\s+)?)(?:{_NUMBER_WORD}[-\s]+(?:and\s+)?)*"
           r"(?:thousand|million|billion|dollars)\b(?:\s+dollars\b)?")
_LEVEL = rf"(?:\$?\s?\d(?:[\d,.]*\d)?(?:k\b|m\b|[a-z]*illion\b)?|{_AMOUNT})"  # "$150,000", "150k", "$1.2m"
PRICE_TARGET = [re.compile(p) for p in (
    r"(?i:\bprice[- ]targets?\b)",
    r"(?i:\btarget(?:s|ing)?\s+(?:of\s+|at\s+|near\s+|around\s+)?" + _LEVEL + ")",
    # modal / prediction verb + level: "could hit", "will reach", "set to top", "heading for"
    r"(?i:\b(?:will|could|might|may|set to|poised to|expected to|going to|about to|likely to)\s+" + _ADVERB +
    r"(?:hit|reach|top|go to|climb to|rise to|fall to|drop to|sink to|soar to)\b(?:\s+" + _LEVEL + ")?)",
    r"(?i:\bhead(?:s|ed|ing)?\s+(?:to|for|toward|towards)\s+" + _LEVEL + ")",
    r"(?i:\bgoing\s+to\s+" + _LEVEL + ")",  # "is going to $200,000"
    # "expect Bitcoin to rally to $100,000", "expected to climb toward one hundred thousand"
    r"(?i:\bexpect(?:s|ed|ing)?\s+(?:[\w'\u2019]+\s+){0,4}?to\s+[a-z]+\s+(?:to|toward|towards|past|above|below)\s+"
    + _LEVEL + ")",
    # headline form at the start of a sentence or quote: "BTC to $150,000"
    r"(?:(?m:^)|(?<=[.!?:;])[\"\u201d]?\s+|(?<=[\"\u201c]))(?!(?:Up|Down|Close|Due|Back|Next|Equal)\b)"
    r"[A-Z][\w]{1,12} to " + _LEVEL,
)]
PREDICTION = re.compile(r"\b(?:to the moon|moon(?:ing|shot)?|could explode|will explode|guaranteed?|"
                        r"can'?t lose|easy money|get rich)\b", re.I)
TEN_X = re.compile(r"\b[1-9]\d+(?:\.\d+)?[xX\u00d7](?!\w)|\b(?:ten|twenty|fifty|hundred|thousand)[- ]x\b", re.I)

# ─── buy / sell calls ("buy-side" / "sell-side" liquidity and "a sell-off" are fine) ───
BUY_SELL_CALL = [re.compile(p, re.I) for p in (
    r"\b(?:i['\u2019]m|i am|i['\u2019]ll|we['\u2019]re|we are|we['\u2019]ll)\s+(?:\w+ly\s+)?"
    r"(?:buying|selling|shorting|going long|going short|adding|loading up)\b",
    r"\b(?:time to|now['\u2019]?s the time to|you should|should you|consider|go ahead and|don['\u2019]t miss|"
    r"start|better|you (?:can|could|might) want to|it['\u2019]s time to)\s+(?:buy|sell|short|go long|go short)\b",
    r"\b(?:buy|sell)(?:ing)?\s+(?:\w+\s+)?(?:here|right now|at these levels|the dip|the rip)\b",
    r"\b(?:buy|sell)(?![- ]side)\s+(?:signal|zone|setup|opportunity|now)\b",
    r"\b(?:good|great|best) (?:time|place|price|level) to (?:buy|sell)\b",
    r"\bgo (?:long|short)\b",
    r"\bentry (?:point|zone|level|price)s?\b",
)]


def _attributed(text: str, start: int, end: int) -> bool:
    """A quote counts as attributed when its own sentence names a speaker with an attribution verb
    (`"…," said BlackRock's CEO.` / `Analysts at X said: "…"` / `according to X, "…"`). Never across a
    line (scene) break; a quote that ends its sentence (`."` `?"` `!"`) can't take the next sentence's verb."""
    before = re.split(r"[.!?]\s", text[max(0, start - 120):start].rsplit("\n", 1)[-1])[-1]
    after = "" if re.search(r"[.!?]\W*$", text[start:end]) else \
        re.split(r"(?<=[.!?])\s", text[end:end + 120].split("\n", 1)[0])[0]
    return bool(ATTRIBUTION.search(before) or ATTRIBUTION.search(after))


def _noun_mine(text: str, m: re.Match) -> bool:
    before = re.findall(r"[\w'-]+", text[max(0, m.start() - 30):m.start()])
    after = re.findall(r"[\w'-]+", text[m.end():m.end() + 30])
    return bool((before and before[-1].lower() in MINE_BEFORE) or (after and after[0].lower() in MINE_AFTER))


def _unquoted(text: str) -> str:
    """The text with attributed quotes blanked out (first-person check only)."""
    out, last = [], 0
    for m in QUOTE.finditer(text):
        if _attributed(text, m.start(), m.end()):
            out += [text[last:m.start()], " " * (m.end() - m.start())]
            last = m.end()
    return "".join(out) + text[last:]


def narration_problems(text: str) -> list[str]:
    """Every narration rule `text` breaks, as 'rule: "matched words"' (each match once, in rule order)."""
    text = _dashes(text)
    found: list[str] = []

    def add(rule: str, words: str) -> None:
        _add(found, rule, words)

    unquoted = _unquoted(text)
    for m in FIRST_PERSON.finditer(unquoted):
        if m.group(0).lower() != "mine" or not _noun_mine(unquoted, m):
            add("first person", m.group(0))
    for rx in PRICE_TARGET:
        for m in rx.finditer(text):
            add("price target", m.group(0))
    for m in PREDICTION.finditer(text):
        add("prediction", m.group(0))
    for m in TEN_X.finditer(text):
        add("10x", m.group(0))
    for rx in BUY_SELL_CALL:
        for m in rx.finditer(text):
            add("buy/sell call", m.group(0))
    for m in _dates(text, [MONTH_OR_ZONE, MARCH_MAY, *SPOKEN_CLOCK]):
        add("date/time", m.group(0))
    return found


def _dashes(text: str | None) -> str:
    return re.sub("[\u2010-\u2015\u2212]", "-", text or "")


def _add(found: list[str], rule: str, words: str) -> None:
    p = f'{rule}: "{words.strip()}"'
    if p not in found:
        found.append(p)


def _dates(text: str, extra: list[re.Pattern]) -> list[re.Match]:
    """SPOKEN_TIME matches plus `extra` matches outside them ("October 12" once, not also "October")."""
    dates = [m.span() for m in SPOKEN_TIME.finditer(text)]
    said = [*SPOKEN_TIME.finditer(text), *(m for rx in extra for m in rx.finditer(text))]
    return [m for m in sorted(said, key=lambda m: m.start())
            if m.re is SPOKEN_TIME or not any(a <= m.start() < b for a, b in dates)]


NARRATION_RULES = """
   Narration rules (a data desk, not a person; a script that breaks one is discarded):
   - No first person ("I", "I'm", "I think", "my", "me"); say "here's what moved and why". First person
     is allowed only inside a quote attributed to a named source ("..., said BlackRock's CEO").
   - No price targets or predictions, even inside a quote: no "BTC to $150,000", "price target",
     "could hit", "will reach", "set to top", "heading for". Past moves are fine ("fell to $84,000").
   - No "10x" / "100x", no "moon", no "guaranteed".
   - No buy/sell calls: no "buy the dip", "I'm buying", "time to sell", "go long", "entry point".
     Facts like "a sell-off" or "buy-side liquidity" are fine.
   - Never say a date, a month name, a clock time or a time zone (no "October 12", "14:30", "UTC",
     "GMT"); say "today", "later today" or "this week". A bare year ("the highest since 2021") is fine."""


# ─── titles and thumbnail text (packaging.md, CAP-8) ──────────────────────
# dates beyond the narration ones: "March" (title-case "May" is the verb), a month + year, weekdays,
# "10/7"; a bare
# year stays legal ("Biggest Drop Since 2022"), as in brief narration
TITLE_DATE = [MONTH_OR_ZONE, re.compile(r"\bMarch\b|\bMARCH\b"),  # all-caps too: thumbnail text
              re.compile(rf"\b(?:{_MONTHS})\.? \d{{4}}\b", re.I),  # "Jan 2027", "May 2026"
              re.compile(r"\b(?:mon|tues|wednes|thurs|fri|satur|sun)day\b", re.I),
              re.compile(r"\b(?!24/7\b)\d{1,2}/\d{1,2}(?:/\d{2,4})?\b"), *SPOKEN_CLOCK]
# a market session or edition-time label: "London Open", "NY Close", "Evening News", "Morning Brief"
SESSION_STAMP = re.compile(
    r"\b(?:Asian?|Asia-Pacific|Tokyo|Sydney|London|European?|New York|(?-i:NY|US|U\.S\.)|Wall Street)"
    r"\s+(?:Open|Close|Session)\b"
    r"|\b(?:Morning|Midday|Afternoon|Evening|Overnight)\s+(?:News|Brief|Briefing|Edition|Update|Report)\b", re.I)
HASHTAG = re.compile(r"(?<![\w&])#[A-Za-z]\w*")  # "#1 Reason" is a rank, not a hashtag
EXPLODE = re.compile(r"\bexplod(?:e|es|ed|ing)\b", re.I)
# a price, not a bare year: "$150K", "150k", "$1.2m", "a hundred thousand dollars"
_PRICE = rf"(?:\$\s?\d(?:[\d,.]*\d)?(?:k\b|m\b|[a-z]*illion\b)?|\d(?:[\d,.]*\d)?(?:k|m|[a-z]*illion)\b|{_AMOUNT})"
TITLE_PRICE_TARGET = [re.compile(p) for p in (
    # replaces PRICE_TARGET's headline form in titles, at the start or after ":" / "|": "Bitcoin To $150K?";
    # not "Up To $500M Liquidated", a reported move ("Plunges to $80K") or a year ("Road to 2030")
    r"(?i:(?:^|(?<=[:|?!.])\s+)\W*(?!(?:up|down|close|due|back|next|equal)\b|\w+(?:ed|s)\b)\w{2,13}\s+to\s+"
    + _PRICE + ")",
    # the question form, either way: "Will Bitcoin Hit $100K?", "Could Ether Sink to $1,000?"
    r"(?i:\b(?:will|can|could)\s+(?:[\w'\u2019]+\s+){1,2}(?:hit|reach|top|break|(?:go|climb|rise|fall|drop|"
    r"sink|crash|plunge|soar)\s+(?:to|toward|towards|above|below|past|under|over))\s+" + _PRICE + ")",
)]
THUMBNAIL_MAX_WORDS = 4


def title_problems(title: str) -> list[str]:
    """Every packaging rule `title` breaks, as 'rule: "matched words"' (each match once, in rule order)."""
    text = _dashes(title)
    found: list[str] = []
    for m in _dates(text, TITLE_DATE):
        _add(found, "date", m.group(0))
    for m in SESSION_STAMP.finditer(text):
        _add(found, "session stamp", m.group(0))
    for m in HASHTAG.finditer(text):
        _add(found, "hashtag", m.group(0))
    targets = sorted((m for rx in (*PRICE_TARGET[:-1], *TITLE_PRICE_TARGET) for m in rx.finditer(text)),
                     key=lambda m: (m.start(), -m.end()))
    end = -1
    for m in targets:  # overlapping matches ("Bitcoin to $150" / "Bitcoin to $150K") count once, the longest
        if m.start() >= end:
            _add(found, "price target", m.group(0).lstrip(" \"\u201c\u201d"))
        end = max(end, m.end())
    for m in TEN_X.finditer(text):
        _add(found, "10x", m.group(0))
    for m in EXPLODE.finditer(text):
        _add(found, "EXPLODE", m.group(0))
    return found


def thumbnail_text_problems(text: str, max_words: int = THUMBNAIL_MAX_WORDS) -> list[str]:
    """Thumbnail text carries 1-`max_words` words and breaks no title rule."""
    words = (text or "").split()
    found = [] if 1 <= len(words) <= max_words else \
        [f'thumbnail words: "{" ".join(words)}" ({len(words)}, allowed 1-{max_words})']
    return found + title_problems(text)


# ─── disclosure line (narration-rules.md: every description carries it exactly once) ───
DISCLOSURE = "Narrated with a synthetic voice. Researched from public market data. Not financial advice."


def disclosure(cfg: dict, *sections: str) -> str:
    """The configured disclosure line: the first non-empty `<section>.disclaimer` of `sections`, then
    `upload.disclaimer`, whitespace-collapsed; DISCLOSURE when none is set."""
    for section in (*sections, "upload"):
        text = " ".join(str((cfg.get(section) or {}).get("disclaimer") or "").split())
        if text:
            return text
    return DISCLOSURE


def without_disclosure(text: str, line: str) -> str:
    """`text` with every copy of the disclosure `line` removed (any case or spacing), so a description
    that appends the line carries it exactly once."""
    words = line.split()
    rx = re.compile(r"(?:\u26a0\ufe0f?\s*)?" + r"\s*".join(re.escape(w) for w in words), re.I) if words else None
    if not text or not rx or not rx.search(text):
        return text or ""
    return re.sub(r"\n{3,}", "\n\n", re.sub(r"[ \t]{2,}", " ", rx.sub("", text))).strip()
