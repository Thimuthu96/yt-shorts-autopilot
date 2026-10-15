"""Offline check of graphics + rendering + metadata with sample data (no API keys needed).
Facebook (Graph API) and Cloudflare are mocked; nothing is posted anywhere.

    python tests/test_offline.py
"""
import json
import math
import os
import random
import shutil
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
for _k in ("CF_ACCOUNT_ID", "CF_API_TOKEN", "FB_PAGE_ID", "FB_PAGE_TOKEN"):  # never reach real services
    os.environ.pop(_k, None)

from autopilot import facebook, focus, gold, images, news_post, render, rules, script, seo, slides, thumbnail  # noqa: E402
from autopilot.history import History  # noqa: E402
from autopilot.media import probe_duration, run  # noqa: E402
from autopilot.youtube import build_metadata  # noqa: E402


def sample_data() -> dict:
    random.seed(7)
    now = datetime(2026, 10, 7, 5, 40, tzinfo=timezone.utc)

    def walk(start, n, vol):
        v, out = start, []
        for i in range(n):
            v *= 1 + random.gauss(0, vol) + 0.0004 * math.sin(i / 9)
            out.append(v)
        return out

    crypto = {}
    for sym, name, p in (("BTC", "Bitcoin", 62400), ("ETH", "Ethereum", 2450), ("SOL", "Solana", 142), ("XRP", "XRP", 0.53)):
        s = walk(p, 168, 0.004)
        crypto[sym] = {"name": name, "price": s[-1], "change_24h": (s[-1] / s[-25] - 1) * 100,
                       "change_7d": (s[-1] / s[0] - 1) * 100, "high_24h": max(s[-24:]), "low_24h": min(s[-24:]),
                       "series": s, "series_times": [(now - timedelta(hours=167 - i)).isoformat() for i in range(168)]}
    # gold: 30 days of hourly bars ending 06:00 UTC (Asian session done), spot-like prices
    closes = walk(4180, 24 * 30, 0.0022)
    bars, prev = [], closes[0]
    for i, c in enumerate(closes):
        t = now.replace(minute=0) - timedelta(hours=len(closes) - 1 - i)
        bars.append([t.isoformat(), prev, max(prev, c) * 1.0012, min(prev, c) * 0.9988, c])
        prev = c
    gold_d = {"name": "Gold", "symbol": "XAU/USD", "price": closes[-1], "change_24h": (closes[-1] / closes[-25] - 1) * 100,
              "change_7d": (closes[-1] / closes[-168] - 1) * 100, "high_24h": max(b[2] for b in bars[-24:]),
              "low_24h": min(b[3] for b in bars[-24:]), "series_times": [b[0] for b in bars[-168:]],
              "series": closes[-168:], "bars": bars, "source": "sample", "basis": 0}
    fx = {}
    for pair, name, p in (("EURUSD", "EUR/USD", 1.094), ("GBPUSD", "GBP/USD", 1.305), ("USDJPY", "USD/JPY", 148.2)):
        s = walk(p, 30, 0.003)
        fx[pair] = {"name": name, "price": s[-1], "as_of": "2026-10-06", "change_1d": (s[-1] / s[-2] - 1) * 100,
                    "change_30d": (s[-1] / s[0] - 1) * 100, "series": s,
                    "series_times": [(now - timedelta(days=30 - i)).date().isoformat() for i in range(30)]}
    return {
        "kind": "market", "gold": gold_d,
        "macro": {"us10y": {"yield_pct": 5.28, "change_bp": 1, "date": "2026-10-06"},
                  "us10y_real": {"yield_pct": 2.92, "change_bp": 6, "date": "2026-10-06"},
                  "us_cpi": {"headline_yoy": 3.4, "core_yoy": 2.4, "month": "August 2026"}},
        "rate_expectations": [{"source": "Reuters", "title": "Fed hike odds drop to 18% per CME FedWatch",
                               "published": now.isoformat()}],
        "date_utc": "2026-10-07", "weekday": "Wednesday", "weekend": False, "crypto": crypto, "fx": fx,
        "calendar": [
            {"time_utc": "12:30", "currency": "USD", "event": "Core CPI m/m", "forecast": "0.3%", "previous": "0.2%",
             "impact": "High", "datetime": "2026-10-07T12:30:00+00:00"},
            {"time_utc": "14:00", "currency": "CAD", "event": "BOC Rate Statement and Monetary Policy Report",
             "forecast": "", "previous": "", "impact": "High", "datetime": "2026-10-07T14:00:00+00:00"},
            {"time_utc": "18:00", "currency": "USD", "event": "FOMC Meeting Minutes", "forecast": "", "previous": "",
             "impact": "High", "datetime": "2026-10-07T18:00:00+00:00"},
        ],
        "news": [{"category": "crypto", "source": "CoinDesk", "title": "Bitcoin ETFs see third day of outflows",
                  "summary": "", "body": "Spot bitcoin ETFs recorded outflows for a third day as BTC slipped.",
                  "published": now.isoformat(), "link": "https://www.coindesk.com/x"},
                 {"category": "crypto", "source": "Cointelegraph", "title": "Bitcoin liquidations top $500M as BTC dips",
                  "summary": "Ether also fell.", "body": "", "published": now.isoformat(), "link": ""},
                 {"category": "gold", "source": "Kitco", "title": "Gold holds near two-month low as dollar firms",
                  "summary": "", "body": "", "published": now.isoformat(), "link": ""}],
    }


NOTE = {"what_happened": "Spot bitcoin ETFs saw a third day of outflows (CoinDesk).", "why": [],
        "impact": [{"asset": "ETH", "observed": "down", "link": "Ether usually follows Bitcoin", "basis": "typical"}],
        "context": [], "watch": ["USD Core CPI 12:30 GMT"], "angle": "Why is Bitcoin slipping?"}


def gold_pkg(plan):
    words = "gold holds its range as yields stay firm"
    return {"title": "Gold Outlook Oct 7: Range Day | XAU/USD Levels",
            "scenes": [{"id": p["id"], "text": f"{p['id']} {words}."} for p in plan],
            "description": "Gold outlook.", "tags": ["gold price today", "xauusd analysis"],
            "hashtags": ["#Gold"], "headlines_used": [], "thumbnail_hook": "KEY LEVELS TODAY"}


PKG = {
    "title": "Bitcoin Slips Ahead of US Inflation Data | Oct 7",
    "scenes": [
        {"text": "Bitcoin slipped overnight as traders wait for US inflation.", "visual": {"type": "title", "kicker": "Crypto & FX", "headline": "Bitcoin slips before US inflation data"}},
        {"text": "Bitcoin is near sixty-two thousand dollars, down on the day.", "visual": {"type": "price", "asset": "BTC"}},
        {"text": "Spot bitcoin funds saw a third day of outflows.", "visual": {"type": "news", "source": "CoinDesk", "headline": "Bitcoin ETFs log a third straight day of outflows"}},
        {"text": "The euro held near one point oh nine at yesterday's fix.", "visual": {"type": "fx", "asset": "EURUSD"}},
        {"text": "Today, US core inflation lands.", "visual": {"type": "calendar"}},
        {"text": "So that Bitcoin slip comes with a third day of fund outflows.", "visual": {"type": "board"}},
    ],
    "description": "Bitcoin dips ahead of CPI; euro steady.",
    "tags": ["bitcoin price today", "forex news today", "bitcoin price today"],
    "hashtags": ["#Bitcoin", "#Forex"],
    "headlines_used": ["Bitcoin ETFs see third day of outflows"],
    "thumbnail_hook": "Buy the dip now",
}


def main():
    cfg = yaml.safe_load((ROOT / "config.yaml").read_text())
    data = sample_data()
    assert not script.validate(cfg | {"llm": cfg["llm"] | {"min_words": 40, "max_words": 90}}, data, PKG), \
        script.validate(cfg | {"llm": cfg["llm"] | {"min_words": 40, "max_words": 90}}, data, PKG)

    work = ROOT / "output" / "test"
    work.mkdir(parents=True, exist_ok=True)
    # script writer gets the cover facts (LLM mocked) and the prompt must format cleanly
    cover = thumbnail.choose(data)
    prompts = []

    def fake_llm(prompt, models, temperature=0.9):
        prompts.append(prompt)
        if prompt.startswith("RESEARCH TASK"):
            return dict(NOTE)
        if "strict financial news editor" in prompt:
            return {"verdict": "ok", "package": json.loads(prompt.split("SCRIPT:\n", 1)[1].rsplit("\n\n1. Every", 1)[0])}
        if "DAILY GOLD OUTLOOK" in prompt:
            return gold_pkg(script.gold_plan(gdata, []))
        return json.loads(json.dumps(PKG))
    script.generate_json = fake_llm
    small = cfg | {"llm": cfg["llm"] | {"min_words": 40, "max_words": 90}}
    # without a lead story: the old all-markets behaviour still works
    pkg = script.make_script(small, data, [], cover, log=lambda m: None)
    assert cover["facts"] in prompts[0] and pkg["scenes"][0]["visual"]["type"] == "title"

    # focused brief: Bitcoin story → charts stay on BTC + related coins; the EUR/USD chart is swapped
    gdata = json.loads(json.dumps(data))
    f = focus.pick(data, None, [])
    assert f["lead"] == "BTC" and f["assets"][0] == "BTC" and "EURUSD" not in f["assets"], f
    assert f["story"]["source"] == "CoinDesk", f["story"]
    fcover = thumbnail.choose(data)
    assert fcover.get("label", "").upper() in ("BITCOIN", "ETHEREUM", "SOLANA", "XRP") or fcover["template"] != "move"
    prompts.clear()
    fpkg = script.make_script(small, data, [], fcover, log=lambda m: None)
    assert prompts[0].startswith("RESEARCH TASK") and "ONE STORY" in prompts[1] and fpkg["research"] == NOTE
    charted = [s["visual"].get("asset") for s in fpkg["scenes"] if s["visual"]["type"] in ("price", "fx")]
    assert "EURUSD" not in charted and set(charted) <= set(f["assets"]), charted
    assert '"EURUSD"' not in prompts[1].split("TODAY'S DATA")[1].split("Headlines already")[0]
    # opening: the cover hands over to the chart of the cover's asset (else the lead's), which later
    # scenes don't repeat; no outro, no spoken disclaimer asked for
    follow = fpkg["scenes"][0]["visual"]["follow"]
    opened = follow.get("asset") or ("XAU" if follow["type"] == "gold" else None)
    assert follow == script.opening_chart(data, fcover) and opened == (fcover.get("asset") or "BTC"), (follow, fcover)
    assert opened not in charted, charted
    assert all(s["visual"]["type"] != "outro" for p_ in (pkg, fpkg) for s in p_["scenes"])
    assert "5-6 scenes" in prompts[1] and '"outro"' not in prompts[1] and " chart drawing in" in prompts[1]
    assert "~35-second" in prompts[0] and "End with a short spoken note" not in prompts[1]
    # a cover about a non-lead asset (ETH move card): scene 1 follows with ETH, later ETH charts are swapped
    eth = json.loads(json.dumps(PKG))
    eth["scenes"][1]["visual"] = {"type": "price", "asset": "ETH"}
    script.fix_visuals(data, eth, {"template": "move", "asset": "ETH"}, log=lambda m: None)
    assert eth["scenes"][0]["visual"]["follow"] == {"type": "price", "asset": "ETH"}, eth["scenes"][0]
    assert all(s["visual"].get("asset") != "ETH" for s in eth["scenes"][1:]), eth["scenes"]
    assert script.opening_chart(data, {"template": "level", "asset": "SOL"}) == {"type": "price", "asset": "SOL"}
    assert script.opening_chart(data, {"template": "event"}) == {"type": "price", "asset": "BTC"}  # → the lead
    # sign-offs: phrases are cut, the content of the sentence stays; "subscribers" is not a sign-off
    assert script.strip_sign_off("So that 5.7% drop came with ETF outflows — not financial advice.") == \
        "So that 5.7% drop came with ETF outflows."
    assert script.strip_sign_off("Fund subscribers rose 5%. That's your London brief.") == "Fund subscribers rose 5%."
    assert script.strip_sign_off("Not financial advice. See you tomorrow.") == ""
    logs = []
    only = json.loads(json.dumps(PKG))
    only["scenes"].append({"text": "Not financial advice. See you tomorrow.", "visual": {"type": "board"}})
    script.fix_visuals(data, only, log=logs.append)  # a sign-off-only last scene (not typed outro) goes
    assert len(only["scenes"]) == len(PKG["scenes"]) and any("sign-off" in m for m in logs), logs
    short = {"title": "t", "scenes": json.loads(json.dumps(PKG["scenes"][:3])) +
             [{"text": "Not financial advice. See you tomorrow.", "visual": {"type": "board"}}]}
    script.fix_visuals(data, short, log=lambda m: None)  # dropping would leave < 4 scenes: validate rejects
    assert len(short["scenes"]) == 4 and "last scene is only a sign-off" in script.validate(small, data, short)
    # a stray outro from the LLM: a pure sign-off is dropped, one with content becomes the board
    stray = json.loads(json.dumps(PKG))
    stray["scenes"].append({"text": "That's your London brief. Not financial advice.", "visual": {"type": "outro"}})
    script.fix_visuals(data, stray, log=lambda m: None)
    assert len(stray["scenes"]) == len(PKG["scenes"]) and all(s["visual"]["type"] != "outro" for s in stray["scenes"])
    stray = json.loads(json.dumps(PKG))
    stray["scenes"][-1] = {"text": "Bitcoin funds saw a third day of outflows. Not financial advice.",
                           "visual": {"type": "outro"}}
    script.fix_visuals(data, stray, log=lambda m: None)
    assert stray["scenes"][-1] == {"text": "Bitcoin funds saw a third day of outflows.", "visual": {"type": "board"}}, \
        stray["scenes"][-1]
    assert not script.validate(small, data, stray), script.validate(small, data, stray)
    cover["hook"] = thumbnail.clean_hook(pkg.get("thumbnail_hook"), cover["default_hook"])
    fcover["hook"] = thumbnail.clean_hook(fpkg.get("thumbnail_hook"), fcover["default_hook"])
    thumb = thumbnail.render(fcover, cfg, data["date_utc"], work / "thumbnail.jpg")  # the focused brief's card
    scenes = fpkg["scenes"]  # after fix_visuals: the opening card hands over to its asset's chart
    pics = slides.render_slides(cfg, data, scenes, work, cover=thumb)
    assert pics[0]["cover"] and pics[0]["follow"]["reveal"], pics[0]  # the lead chart draws in after the card

    audio = []
    for i, s in enumerate(scenes):
        words = s["text"].split()
        dur = 0.32 * len(words) + 0.4
        wav = work / f"voice_{i:02d}.wav"
        run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"sine=frequency={300 + 40 * i}:duration={dur}",
             "-ar", "44100", "-ac", "1", wav])
        step = (dur - 0.4) / len(words)
        audio.append({"audio": wav, "duration": probe_duration(wav),
                      "words": [(j * step, (j + 0.9) * step, w) for j, w in enumerate(words)]})

    out = work / "short.mp4"
    total = render.build_video(audio, pics, cfg, work, out)
    got = probe_duration(out)
    assert abs(got - total) < 0.25, (got, total)
    assert got <= cfg["video"]["max_seconds"], got
    check_opening(out, work)

    # contact sheet: the first frame (the exact cover design), the follow chart mid-reveal, then the
    # middle of every later scene
    t, stamps = 0.0, [0.0, render.COVER_HOLD + 0.6]
    for a in audio:
        stamps.append(t + a["duration"] * 0.6)
        t += a["duration"]
    del stamps[2]  # scene 1's middle is already the chart mid-reveal
    for old in work.glob("frame_*.png"):  # no stale frames from an earlier, longer run
        old.unlink()
    for k, ts in enumerate(stamps):
        run(["ffmpeg", "-y", "-v", "error", "-ss", f"{ts:.2f}", "-i", out, "-frames:v", "1",
             "-vf", "scale=360:640", work / f"frame_{k:02d}.png"])
    run(["ffmpeg", "-y", "-v", "error", "-i", work / "frame_%02d.png", "-vf", "tile=4x2:padding=8",
         "-frames:v", "1", work / "contact.png"])

    meta = build_metadata(PKG, data, cfg, "London Open")
    assert "not financial advice" in meta["description"].lower()
    assert "not financial advice" in cfg["video"]["footer"].lower() and "not financial advice" in cfg["gold"]["footer"].lower()
    assert "not financial advice" in facebook.reel_caption(meta, PKG, data, cfg).lower()
    assert meta["tags"][0] == "bitcoin price today" and len(meta["tags"]) == len({t.lower() for t in meta["tags"]})
    assert "bitcoin" in meta["title"][:45].lower() and "Key numbers:" in meta["description"]
    assert meta["description"].split()[-5:][0] == "#Bitcoin" and meta["description"].endswith("#Shorts")
    assert cover["hook"] == cover["default_hook"]  # "Buy the dip now" is rejected
    print(f"OK: {out} ({got:.1f}s) · thumbnail {fcover['template']} '{fcover['hook']}' · contact sheet {work / 'contact.png'}")
    print(meta["description"])

    test_gold(cfg, small, gdata)
    test_narration_rules(small)
    test_title_rules(cfg, data)
    test_disclosure(cfg, data, gdata)
    test_focus_crypto_first()
    test_voice_fallback()
    test_voice_pacing(cfg)
    test_voice_ab(cfg, data)
    test_market_overview()
    test_history()
    test_facebook(cfg, PKG, data, meta, out, work / "thumbnail.jpg")
    test_facebook_video(cfg)
    test_news_post(cfg)
    test_news_post_rules(cfg)
    test_news_edition(cfg)
    test_news_post_stops(cfg)
    test_news_post_crypto_only(cfg)
    test_video_editions(cfg, out, work / "thumbnail.jpg")
    test_lesson_slides(cfg)
    test_step_reveal(cfg)
    test_lesson_render(cfg)
    test_youtube_lesson(cfg)
    test_lesson_edition(cfg)
    test_diagrams(cfg)
    test_basics_topics(cfg)
    test_basics_script(cfg)
    test_basics_packaging(cfg)
    test_material(cfg)
    test_basics(cfg)
    test_basics_ready(cfg)
    test_evergreen(cfg)
    test_triggered(cfg)
    test_trigger_rules(cfg)
    test_trigger_limits(cfg)
    test_trigger_poll(cfg)
    test_triggered_packaging(cfg)
    test_recap(cfg)
    test_short_concept(cfg)
    test_short_packaging(cfg)
    test_short_related(cfg)
    test_short_market(cfg)
    test_short_originality(cfg)
    test_short_lesson(cfg)
    test_short_mix(cfg)
    test_slate_timetable(cfg)
    test_slate_budget(cfg)
    test_slate_floor(cfg)


def check_opening(video: Path, work: Path, hold: float = render.COVER_HOLD) -> None:
    """Frame 0 is the cover design, it moves by 0.3 s (push-in) and captions start when it hands over (≤ 1.2 s)."""
    from PIL import Image, ImageChops
    shots = []
    for k, ts in enumerate((0.0, 0.3)):
        png = work / f"opening_{k}.png"
        run(["ffmpeg", "-y", "-v", "error", "-ss", f"{ts:.2f}", "-i", video, "-frames:v", "1", png])
        shots.append(Image.open(png).convert("L"))
    def mean_diff(a, b):
        d = ImageChops.difference(a, b)
        return sum(d.getdata()) / (d.width * d.height)
    design = Image.open(work / "thumbnail.jpg").convert("L").resize(shots[0].size)
    motion, exact = mean_diff(*shots), mean_diff(shots[0], design)
    assert motion > 2, f"no motion in the opening card's first 0.3 s ({motion:.2f})"
    assert exact < 2 and exact < motion / 2, f"frame 0 isn't the exact cover design ({exact:.2f} vs {motion:.2f})"
    first = next(ln for ln in (work / "captions.ass").read_text().splitlines() if ln.startswith("Dialogue:"))
    h_, m_, s_ = first.split(",")[1].split(":")
    start = int(h_) * 3600 + int(m_) * 60 + float(s_)
    assert hold - 0.05 <= start <= 1.2, (start, hold)


def test_title_rules(cfg, data):
    """Packaging title and thumbnail-text checks (rules.py, CAP-8): each banned pattern is flagged with
    its reason, the format patterns pass, and today's brief title is logged but still published."""
    t = rules.title_problems
    for title, want in (("Bitcoin Slips Ahead of US Inflation Data | Oct 7", 'date: "Oct 7"'),
                        ("Crypto Wrap for Monday", 'date: "Monday"'), ("CPI Lands at 8:30", 'date: "8:30"'),
                        ("Bitcoin Price Today | London Open", 'session stamp: "London Open"'),
                        ("Evening News: Ether Slides", 'session stamp: "Evening News"'),
                        ("Why Bitcoin Fell #Bitcoin", 'hashtag: "#Bitcoin"'),
                        ("Bitcoin To $150K?", 'price target: "Bitcoin To $150K"'),
                        ("Will Bitcoin Hit $100K?", 'price target: "Will Bitcoin Hit $100K"'),
                        ("Analysts Raise Their Price Target", 'price target: "Price Target"'),
                        ("Will Bitcoin Drop to $80K?", 'price target: "Will Bitcoin Drop to $80K"'),
                        ("Analysis: BTC to $150K", 'price target: "BTC to $150K"'),
                        ("CPI Day at 8:30 GMT", 'date: "GMT"'), ("Bitcoin on 10/7", 'date: "10/7"'),
                        ("Crypto in May 2026", 'date: "May 2026"'), ("Crypto Wrap for October", 'date: "October"'),
                        ("This Coin Could 10x", '10x: "10x"'), ("Bitcoin Is About To EXPLODE", 'EXPLODE: "EXPLODE"')):
        assert want in t(title), (title, t(title))
    for title in ("What Is a Bitcoin ETF? (Explained Simply)", "Why Bitcoin Just Dropped 7% (What Actually Happened)",
                  "This Week in Crypto: What Moved and Why", "What Is a Break of Structure? (Crypto Chart Example)",
                  "Why Did Bitcoin Fall to $84,000?", "Biggest Bitcoin Drop Since 2022", "Up To $500M Liquidated",
                  "Fed May Cut Rates: What It Means for Crypto", "#1 Reason Ether Lagged", "Crypto Trades 24/7",
                  "Road to 2030: Bitcoin Halving", "Plunges to $80K: Why Bitcoin Fell"):
        assert t(title) == [], (title, t(title))
    assert t("Bitcoin to $150K by Christmas?") == ['price target: "Bitcoin to $150K"']  # one overlapping match
    th = rules.thumbnail_text_problems
    assert th("BITCOIN ETF?") == [] and th("WHY −7%?") == [] and th("BOS vs CHoCH") == []
    assert th("") and th("WHY BITCOIN FELL SO HARD")[0].startswith("thumbnail words:")
    assert th("10x SOON") == ['10x: "10x"']
    assert th("MARCH CPI") == ['date: "MARCH"']  # thumbnail text is all-caps
    # today's brief: the writer's dated title is logged, then published unchanged
    logged = []
    meta = build_metadata(PKG, data, cfg, "London Open", log=logged.append)
    assert meta["title"] == PKG["title"] and len(logged) == 1 and 'date: "Oct 7"' in logged[0], (meta["title"], logged)
    logged.clear()
    build_metadata(dict(PKG, title="Bitcoin Slips Ahead of US Inflation Data"), data, cfg, "London Open",
                   log=logged.append)
    assert logged == [], logged
    # the data-built fallback title carries the edition and date: logged, published as built
    meta = build_metadata(dict(PKG, title="Crypto slips"), data, cfg, "London Open", log=logged.append)
    assert meta["title"] == seo.fallback_title(data, "London Open") and len(logged) == 1, (meta["title"], logged)
    assert 'session stamp: "London Open"' in logged[0] and 'date: "Oct 7"' in logged[0], logged
    print("OK title rules")



OLD_DISCLAIMERS = ("information and education only", "news for information only", "high risk of loss",
                   "do your own research")


def test_disclosure(cfg, data, gdata):
    """narration-rules.md disclosure (CAP-7): a brief, a gold outlook, a Reel caption and a news post
    each carry the line exactly once and none of the old disclaimer text, even when the writer copied it."""
    line = rules.DISCLOSURE
    assert line == "Narrated with a synthetic voice. Researched from public market data. Not financial advice."
    assert cfg["upload"]["disclaimer"] == line and cfg["news_posts"]["disclaimer"] == line
    quiet = lambda m: None  # noqa: E731

    def once(text, what):  # counted in any case or spacing, so a writer echo that survived is caught
        n = " ".join(text.split()).lower().count(line.lower())
        assert n == 1 and text.count(line) == 1, (what, n, text)
        assert not any(old in text.lower() for old in OLD_DISCLAIMERS), (what, text)

    brief = build_metadata(PKG, data, cfg, "London Open", log=quiet)
    once(brief["description"], "brief")
    once(facebook.reel_caption(brief, PKG, data, cfg), "reel caption")
    once(build_metadata(PKG, gdata, cfg, "Gold Outlook", log=quiet)["description"], "gold")
    ndata = news_data()
    story = news_post.pick_story(ndata, [], [], cfg, now=NOW, log=quiet)
    once(news_post.caption(dict(GOOD_POST), story, ndata, cfg), "news post")

    # the writer echoed the line (other case / spacing): still exactly once, the writer's text kept
    echo = dict(PKG, description=PKG["description"] + "  narrated with a synthetic voice.\nResearched from "
                                                     "public market data.  NOT financial advice.")
    meta = build_metadata(echo, data, cfg, "London Open", log=quiet)
    once(meta["description"], "brief echo")
    assert meta["description"].startswith(PKG["description"].strip()[:40]), meta["description"]
    once(facebook.reel_caption(meta, echo, data, cfg), "reel echo")
    cap = news_post.caption(dict(GOOD_POST, caption=GOOD_POST["caption"] + "\n\n" + line), story, ndata, cfg)
    once(cap, "news echo")
    assert cap.startswith("Fed Chair Jerome Powell"), cap

    # no configured value: the builders still carry the built-in line
    bare = cfg | {"upload": {k: v for k, v in cfg["upload"].items() if k != "disclaimer"},
                  "news_posts": {k: v for k, v in cfg["news_posts"].items() if k != "disclaimer"}}
    once(build_metadata(PKG, data, bare, "London Open", log=quiet)["description"], "bare brief")
    once(news_post.caption(dict(GOOD_POST), story, ndata, bare), "bare news post")
    assert rules.disclosure({"news_posts": {"disclaimer": " A  b. "}}, "news_posts") == "A b."
    assert rules.disclosure({"news_posts": {"disclaimer": "  "}, "upload": {"disclaimer": "U."}}, "news_posts") == "U."
    assert rules.disclosure({}) == line  # nothing configured → the built-in line
    assert rules.disclosure({"news_posts": {"disclaimer": " "}, "upload": {"disclaimer": ""}}, "news_posts") == line
    assert rules.without_disclosure("", line) == "" and rules.without_disclosure("Text.", "") == "Text."
    assert rules.without_disclosure("No copy here.", line) == "No copy here."
    assert rules.without_disclosure("Summary. \u26a0\ufe0f " + line, line) == "Summary."  # no stray warning sign
    assert rules.without_disclosure(f"One.\n\n{line}\n\nTwo.", line) == "One.\n\nTwo."
    # a long writer text is cut, never the line or the hashtags
    long = dict(PKG, description="Bitcoin fell. " * 400)
    meta = build_metadata(long, data, cfg, "London Open", log=quiet)
    once(meta["description"], "long brief")
    assert len(meta["description"]) <= 4900 and meta["description"].endswith("#Shorts"), len(meta["description"])
    rc = facebook.reel_caption(meta, long, data, cfg)
    once(rc, "long reel")
    assert len(rc) < 2200 and rc.split()[-1].startswith("#"), rc[-200:]
    print("OK disclosure")


def test_focus_crypto_first():
    """CAP-9: only coins lead. EUR/USD +0.9% with an ECB event and gold/dollar headlines vs BTC −0.5%
    with no headline → the lead is still a coin and no FX / USD / XAU key is scored."""
    now = datetime.now(timezone.utc).isoformat()
    soon = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
    flat = {"change_24h": 0.2, "price": 1.0}

    def news(src, title):
        return {"category": "fx", "source": src, "title": title, "summary": "", "body": "", "published": now}
    data = {"weekend": False, "gold": {"change_24h": 2.5, "price": 4300.0},
            "calendar": [{"currency": "EUR", "datetime": soon, "event": "ECB Rate Decision"}],
            "crypto": {"BTC": {"name": "Bitcoin", "change_24h": -0.5, "price": 60000.0},
                       "ETH": dict(flat, name="Ethereum"), "SOL": dict(flat, name="Solana")},
            "fx": {"EURUSD": {"name": "EUR/USD", "change_1d": 0.9, "price": 1.1},
                   "GBPUSD": {"name": "GBP/USD", "change_1d": 0.6, "price": 1.3}},
            "news": [news("Reuters", "Euro jumps as ECB's Lagarde signals hike"),
                     news("CNBC", "Dollar slides after Fed's Powell speech"),
                     news("Kitco", "Gold surges to record as dollar weakens")]}
    f = focus.pick(data, None, [])
    assert f["lead"] in ("BTC", "ETH", "SOL", "XRP") and f["lead"] == "BTC", f
    assert set(f["scores"]) <= {"BTC", "ETH", "SOL", "XRP"}, f["scores"]
    assert set(f["assets"]) <= {"BTC", "ETH", "SOL", "XRP"} and f["assets"][0] == f["lead"], f["assets"]
    assert not any("fx" in w or "event" in w for w in f["why"]), f["why"]
    # a coin's headline makes it the lead; a repeat lead takes the −0.3 penalty
    data["news"].append(dict(news("CoinDesk", "Ether slides as ETF outflows grow"), category="crypto"))
    assert focus.pick(data, None, [])["lead"] == "ETH"
    data["news"].pop()
    assert focus.pick(data, "BTC", [])["lead"] != "BTC"
    # weekend: FX and gold have no prices, the crypto lead stays
    data["weekend"] = True
    assert focus.pick(data, None, [])["lead"] in ("BTC", "ETH", "SOL")
    # no crypto price data → no focus, never an FX / gold / USD lead
    data.update(weekend=False, crypto={})
    assert focus.pick(data, None, []) == {} and data["focus"] == {}
    print("OK focus: crypto-only lead (FX / gold / USD never lead)")


def test_narration_rules(small):
    """Shared narration rules (rules.py): every I/O row, the year decision, and the stop path: drafts
    that always break a rule are retried 3 times, then make_script raises naming the rule."""
    n = rules.narration_problems
    assert n("Bitcoin fell 4% to $84,000 as liquidations hit $500M.") == []
    assert n("a sell-off hit miners; buy-side liquidity rests above the high") == []  # past facts / liquidity
    got = n("I'm buying ETH here.")
    assert any(p.startswith("first person:") for p in got) and any(p.startswith("buy/sell call:") for p in got), got
    assert n('"I think Bitcoin goes higher," said BlackRock\'s CEO.') == []  # attributed quote
    assert n('"I think Bitcoin goes higher."') == ['first person: "I"']  # quote with no source named
    assert n('"Bitcoin to $200,000," said an analyst.') == ['price target: "Bitcoin to $200,000"']
    assert n("BTC to $150,000?") == ['price target: "BTC to $150,000"']
    for t in ("Ethereum could hit $16,000", "Analysts raised their price target."):
        assert any(p.startswith("price target:") for p in n(t)), (t, n(t))
    for t in ("This coin could 10x", "A 100x gem."):
        assert any(p.startswith("10x:") for p in n(t)), (t, n(t))
    assert n("Rates were set on October 12.") == ['date/time: "October 12"']
    assert n("CPI lands at 14:30 UTC.") == ['date/time: "14:30"', 'date/time: "UTC"']
    assert n("Bitcoin hit the highest since 2021.") == []  # owner 2026-10-13: a bare year is fine in briefs
    assert n("Up to $500M in longs were liquidated.") == []  # "Up to $N" is not a headline target
    # a quote that ends its own sentence, or sits on another line (scene), can't borrow a later "said"
    assert n('"I think Bitcoin goes higher." Analysts said prices fell.') == ['first person: "I"']
    assert n('"I think Bitcoin goes higher,"\nCoinDesk reported outflows, according to Farside.') == ['first person: "I"']
    # "mine" the noun and small multipliers are facts
    assert n("Riot shut a Texas Bitcoin mine.") == [] and n("Gold mine output fell 3%.") == []
    assert n("It launched a 2x leveraged ETF.") == [] and n("Volume hit 3x its average.") == []
    # targets in words and forward forms; past moves in words stay legal
    for t in ("Bitcoin to one hundred fifty thousand dollars?", "Bitcoin is heading to a hundred thousand dollars.",
              "Targeting one hundred thousand dollars.", "Bitcoin is going to $200,000.",
              "Analysts expect Bitcoin to rally to $100,000.", "Gold heads toward $4,400."):
        assert any(p_.startswith("price target:") for p_ in n(t)), (t, n(t))
    assert n("Bitcoin fell to $84,000. Ether rose 3% to $2,505.") == []
    assert n("Bitcoin fell to eighty-four thousand dollars.") == []
    # clock times in words (briefs + gold); amounts in words are not times
    for t in ("CPI lands at eight thirty a.m. Eastern.", "The data is out at half past eight.", "Powell speaks at two p.m."):
        assert any(p_.startswith("date/time:") for p_ in n(t)), (t, n(t))
    assert n("Bitcoin is down two percent, near twelve thousand dollars above the low.") == []
    # lessons keep their own (year-banning) patterns, now imported from rules.py
    from autopilot import lesson_script
    assert lesson_script.SPOKEN_TIME is rules.SPOKEN_TIME and lesson_script.SPOKEN_DATE_WORDS is rules.SPOKEN_DATE_WORDS
    assert lesson_script.DASHES is rules.DASHES  # one Unicode-dash pattern, normalised before matching
    # the headline form is its own pattern (narration only); titles use every PRICE_TARGET pattern
    assert rules.HEADLINE_TARGET.search("BTC to $150,000") and \
        not any(rx.search("BTC to $150,000") for rx in rules.PRICE_TARGET)
    assert n("Bitcoin is heading to eighty\u2011four thousand dollars.") == \
        ['price target: "heading to eighty-four thousand dollars"']
    # validate names the rule; the 3-attempt loop stops the edition with it
    data, prompts = sample_data(), []
    bad = json.loads(json.dumps(PKG))
    bad["scenes"][1]["text"] = "I'm buying ETH here, near sixty-two thousand dollars."
    assert 'first person: "I\'m"' in script.validate(small, data, bad), script.validate(small, data, bad)

    def buying(prompt, models, temperature=0.9):
        prompts.append(prompt)
        if prompt.startswith("RESEARCH TASK"):
            return dict(NOTE)
        if "strict financial news editor" in prompt:
            return {"verdict": "ok", "package": json.loads(prompt.split("SCRIPT:\n", 1)[1].rsplit("\n\n1. Every", 1)[0])}
        return json.loads(json.dumps(bad))
    saved, script.generate_json = script.generate_json, buying
    try:
        script.make_script(small, data, [], thumbnail.choose(data), log=lambda m: None)
        raise AssertionError("a draft that breaks a narration rule was accepted")
    except RuntimeError as e:
        assert "first person" in str(e) and "buy/sell call" in str(e), e
    finally:
        script.generate_json = saved
    writes = [p for p in prompts if p.startswith("You write a YouTube Short")]
    checks = [p for p in prompts if "strict financial news editor" in p]
    assert len(writes) == 3 and len(checks) == 3, (len(writes), len(checks))
    assert all(rules.NARRATION_RULES in p for p in writes + checks)
    print("OK narration rules (first person / quotes, price targets, 10x, buy/sell calls, dates; 3 failing drafts stop)")


def test_gold(cfg, small, data):
    """Daily gold outlook: analysis → card → plan + script (LLM mocked) → every gold slide → video."""
    now = datetime(2026, 10, 7, 6, 15, tzinfo=timezone.utc)
    data["kind"] = "gold"
    prev = {"price": data["gold"]["price"] * 0.99, "daily_bias": "bullish", "time": "2026-10-06T06:20:00+00:00"}
    a = gold.analyze(data, prev, now=now)
    data["gold_analysis"] = a
    assert a["asian_session"] and a["previous_day"]["date"] == "2026-10-06", a["previous_day"]
    assert all(z["price"] > a["price"] for z in a["liquidity_above"]) and all(z["price"] < a["price"] for z in a["liquidity_below"])
    assert {a["bias"][k]["bias"] for k in ("1H", "4H", "Daily")} <= {"bullish", "bearish", "neutral"}
    assert a["review"] and a["review"]["bias"] == "bullish"
    for side in ("bull", "bear"):
        sc = a["scenarios"][side]
        if sc and sc.get("objective"):
            assert abs(sc["objective"]["price"] - sc["trigger"]["price"]) >= 0.6 * a["typical_move"]["next_4h"] - 0.2
    cover = thumbnail.choose_gold(data)
    llm, seen = script.generate_json, []

    def signing_off(prompt, models, temperature=0.9):  # the writer adds a spoken disclaimer to the last scene
        seen.append(prompt)
        res = llm(prompt, models, temperature)
        if "DAILY GOLD OUTLOOK" in prompt:
            res["scenes"][-1]["text"] += " This is not financial advice."
        return res
    script.generate_json, logs = signing_off, []
    try:
        pkg = script.make_gold_script(small, data, [], cover, log=logs.append)
    finally:
        script.generate_json = llm
    assert "financial advice" not in pkg["scenes"][-1]["text"].lower() and pkg["scenes"][-1]["text"], pkg["scenes"][-1]
    assert any("sign-off" in m for m in logs), logs
    assert not any(rules.narration_problems(s["text"]) for s in pkg["scenes"]), pkg["scenes"]
    assert len(seen) == 2 and all(rules.NARRATION_RULES in p_ for p_ in seen) and "GMT time" not in seen[0]
    types = [s["visual"]["type"] for s in pkg["scenes"]]
    assert types == ["title", "review", "bias", "scenarios", "drivers"], types  # no gold_chart repeat, no outro
    assert pkg["scenes"][0]["visual"]["follow"] == {"type": "gold_chart"}
    # thin day (no review, no macro / USD events / gold news): still ≥ 4 scenes, ends on the levels
    thin = dict(data, macro={}, rate_expectations=[], news=[],
                gold_analysis=dict(a, review=None, events_usd=[]))
    plan = script.gold_plan(thin, [])
    assert [p["id"] for p in plan] == ["open", "bias", "liquidity", "levels"], plan
    nogold = dict(data, macro={}, rate_expectations=[], gold_analysis=dict(a, events_usd=[]))
    assert [p["id"] for p in script.gold_plan(nogold, [])] == ["open", "review", "bias", "levels", "news"]
    work = ROOT / "output" / "test_gold"
    work.mkdir(parents=True, exist_ok=True)
    cover["hook"] = thumbnail.clean_hook(pkg["thumbnail_hook"], cover["default_hook"])
    thumb = thumbnail.render(cover, cfg, data["date_utc"], work / "thumbnail.jpg", "Gold")
    pics = slides.render_slides(cfg, data, pkg["scenes"], work, cover=thumb, edition="Gold Outlook",
                                footer=cfg["gold"]["footer"])
    audio = []
    for i, s in enumerate(pkg["scenes"]):
        wav = work / f"voice_{i:02d}.wav"
        run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"sine=frequency={300 + 30 * i}:duration=2.0",
             "-ar", "44100", "-ac", "1", wav])
        audio.append({"audio": wav, "duration": probe_duration(wav),
                      "words": [(0.1, 0.6, s["id"]), (0.7, 1.4, "gold")]})
    out = work / "short.mp4"
    total = render.build_video(audio, pics, cfg, work, out)
    assert total <= cfg["video"]["max_seconds"] and pics[0]["follow"]["reveal"], pics[0]
    check_opening(out, work, hold=min(render.COVER_HOLD, audio[0]["duration"] / 2))
    # contact sheet from the video: frame 0 (the cover), the gold chart mid-reveal, then each later scene
    stamps, t = [0.0, min(render.COVER_HOLD, audio[0]["duration"] / 2) + 0.4], audio[0]["duration"]
    for a in audio[1:]:
        stamps.append(t + a["duration"] * 0.6)
        t += a["duration"]
    for old in work.glob("frame_*.png"):
        old.unlink()
    for k, ts in enumerate(stamps):
        run(["ffmpeg", "-y", "-v", "error", "-ss", f"{ts:.2f}", "-i", out, "-frames:v", "1",
             "-vf", "scale=360:640", work / f"frame_{k:02d}.png"])
    run(["ffmpeg", "-y", "-v", "error", "-i", work / "frame_%02d.png", "-vf", "tile=5x2:padding=8",
         "-frames:v", "1", work / "contact.png"])
    meta = build_metadata(pkg, data, cfg, "Gold Outlook")
    assert "rule-based" in meta["description"].lower() and "Key levels:" in meta["description"]
    assert meta["title"].startswith("Gold Price Today")  # the mock's title has no keyword → data-built title
    print(f"OK gold: {out} · card {cover['hero']} {cover['line']} · contact sheet {work / 'contact.png'}")


def test_voice_fallback():
    """edge-tts refused (403) for every attempt → the whole video is voiced by the Piper fallback
    (faked here: no download), with estimated word timings; later calls skip edge-tts."""
    import wave
    from autopilot import voice
    work = Path(tempfile.mkdtemp())
    tries, logs = [], []

    async def refused(text, v, rate, mp3):
        tries.append(text)
        raise RuntimeError("403, message='Invalid response status'")

    class FakePiper:
        def synthesize_wav(self, text, w, syn_config=None):
            w.setnchannels(1), w.setsampwidth(2), w.setframerate(22050)
            w.writeframes(b"\x00\x01" * int(22050 * 0.25 * len(text.split()) * syn_config.length_scale))

    saved = voice._speak, voice._piper_voice, voice.time.sleep, voice._edge_down
    voice._speak, voice._piper_voice, voice.time.sleep = refused, lambda m: FakePiper(), lambda s: None
    try:
        scenes = [{"text": "Ethereum just rose two percent."}, {"text": "Solana followed, up four percent."}]
        out = voice.synthesize(scenes, "en-US-AndrewMultilingualNeural", "+10%", work, log=logs.append,
                               fallback="en_US-ryan-high")
        assert len(tries) == len(voice.EDGE_WAITS) and len(out) == 2, (tries, out)  # gave up after scene 1's retries
        for s, a in zip(scenes, out):
            assert [w[2] for w in a["words"]] == s["text"].split() and a["words"][-1][1] < a["duration"], a
            with wave.open(str(a["audio"])) as w:
                assert w.getframerate() == 44100
        assert any("fallback Piper voice en_US-ryan-high" in m for m in logs), logs
        tries.clear()
        voice.synthesize(scenes[:1], "x", "+25%", work, log=logs.append, fallback="en_US-ryan-high")
        assert not tries  # the rest of the run goes straight to Piper
        assert voice.length_scale("+10%") == round(1 / 1.1, 3) and voice.length_scale("-20%") == 1.25
        voice._edge_down = False
        try:
            voice.synthesize(scenes[:1], "x", "+10%", work, log=logs.append, fallback=None)
            raise AssertionError("no fallback should fail")
        except RuntimeError as e:
            assert "no fallback voice" in str(e)
    finally:
        voice._speak, voice._piper_voice, voice.time.sleep, voice._edge_down = saved
        shutil.rmtree(work, ignore_errors=True)
    print("OK voice fallback (edge-tts 403 → Piper, estimated timings, rest of run on Piper, no fallback → fail)")


def test_voice_pacing(cfg):
    """Entry 6 (CAP-7): +0% rate, a comma pause after key numbers and before the concept term (edge-tts
    escapes SSML), captions keep the script's words on edge-tts and Piper, over-limit still re-records faster."""
    import inspect
    import re
    import wave
    from unittest import mock
    import main as app
    from autopilot import voice
    assert cfg["voice"]["rate"] == "+0%", cfg["voice"]
    # pauses: only commas are added, only where a pause is natural, and never twice
    cases = {
        "Bitcoin fell two point one percent to about sixty-two thousand dollars after the ETF outflows.":
            "Bitcoin fell two point one percent, to about sixty-two thousand dollars, after the ETF outflows.",
        "Gold is at $4,142 today, up 0.8% since Monday.": "Gold is at $4,142, today, up 0.8%, since Monday.",
        "Yields rose ten basis points on the day.": "Yields rose ten basis points, on the day.",
        "A five percent drop in Ether.": "A five percent drop in Ether.",  # adjective use: no pause
        "Ether is up three percent.": "Ether is up three percent.",  # sentence end already pauses
        "The key points to watch.": "The key points to watch.",  # no number before "points"
        # the gold edition's trader-style levels (script.py: "forty-one forty-three" for $4,143)
        "Gold is holding below forty-one forty-three as the dollar firms.":
            "Gold is holding below forty-one forty-three, as the dollar firms.",
        "Bitcoin hit sixty-two thousand to open the week.": "Bitcoin hit sixty-two thousand, to open the week.",
        "Solana is at one hundred and forty dollars today.": "Solana is at one hundred and forty dollars, today.",
        # ranges and amounts bound to a noun stay together; a move then a level still pauses
        "It gained 2% to 3% over the week.": "It gained 2% to 3%, over the week.",
        "It gained two to three percent over the week.": "It gained two to three percent, over the week.",
        "Bitcoin rose $1,200 to $63,000 on the day.": "Bitcoin rose $1,200 to $63,000, on the day.",
        "Bitcoin ETFs saw $500 million in outflows.": "Bitcoin ETFs saw $500 million in outflows.",
        "It fell 3% to $61,400 after the news.": "It fell 3%, to $61,400, after the news.",
        "One of the biggest moves.": "One of the biggest moves.",
        "The twenty-day average is flat.": "The twenty-day average is flat.",
    }
    for src, want in cases.items():
        got = voice.paced(src)
        assert got == want, (src, got)
        assert got.replace(",", "") == src.replace(",", "") and voice.paced(got) == got, got
    term = "liquidity sweep"
    assert voice.paced("This is called a liquidity sweep.", term) == "This is called, a liquidity sweep."
    assert voice.paced("That move is called liquidity sweep here.", term) == "That move is called, liquidity sweep here."
    assert voice.paced("These are liquidity sweeps.", term) == "These are, liquidity sweeps."
    for same in ("This is the classic liquidity sweep.", "Liquidity sweep first.", "Here: a liquidity sweep.",
                 "Price ran back to the liquidity sweep.", "Meet the liquidity sweep."):
        assert voice.paced(same, term) == same, same
    # edge-tts: the paced text is spoken; WordBoundary words (no punctuation) are the script's words, in order
    work = Path(tempfile.mkdtemp())
    spoken = []

    async def fake_speak(text, v, rate, mp3):
        spoken.append((text, rate))
        words = re.sub(r"[,.]", "", text).split()
        run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "sine=frequency=220:sample_rate=24000",
             "-t", f"{0.3 * len(words) + 0.5:.2f}", "-b:a", "48k", str(mp3)])
        return [(0.1 + 0.3 * i, 0.35 + 0.3 * i, w) for i, w in enumerate(words)]

    scenes = [{"text": "Bitcoin fell two point one percent to about sixty-two thousand dollars after the outflows."},
              {"text": "This is called a liquidity sweep.", "term": term}]
    saved = voice._speak, voice._edge_down
    voice._speak, voice._edge_down = fake_speak, False
    try:
        out = voice.synthesize(scenes, "x", cfg["voice"]["rate"], work, log=lambda m: None, pauses=True)
        assert [t for t, _ in spoken] == [voice.paced(s["text"], s.get("term")) for s in scenes] and \
            {r for _, r in spoken} == {"+0%"}, spoken
        for s, a in zip(scenes, out):
            assert [w[2] for w in a["words"]] == re.sub(r"[,.]", "", s["text"]).split(), a["words"]
            assert all(x[0] < x[1] <= y[0] for x, y in zip(a["words"], a["words"][1:])) and a["words"][-1][1] < a["duration"]
        words, off = [], 0.0
        for a in out:
            words += [(s + off, e + off, t) for s, e, t in a["words"]]
            off += a["duration"]
        render.build_captions(words, cfg["video"]["captions"], 1080, 1920, work / "captions.ass")
        hi = render._ass_color(cfg["video"]["captions"]["highlight"])
        lit = re.findall(r"\{\\c" + re.escape(hi) + r"&\}(.*?)\{", (work / "captions.ass").read_text())
        assert lit == [w[2].upper() for w in words], lit  # each word lit in order, at its own timing
        spoken.clear()
        voice.synthesize(scenes[:1], "x", "+0%", work, log=lambda m: None)
        assert spoken[0][0] == scenes[0]["text"]  # without pauses (lessons) the text is spoken as written
    finally:
        voice._speak, voice._edge_down = saved

    # Piper fallback: timings estimated over the paced text, so the comma's pause sits after the number
    class FakePiper:
        def synthesize_wav(self, text, w, syn_config=None):
            w.setnchannels(1), w.setsampwidth(2), w.setframerate(22050)
            w.writeframes(b"\x00\x01" * int(22050 * 0.25 * len(text.split()) * syn_config.length_scale))

    saved = voice._piper_voice, voice._edge_down
    voice._piper_voice, voice._edge_down = (lambda m: FakePiper()), True
    try:
        a = voice.synthesize(scenes[:1], "x", "+0%", work, log=lambda m: None, fallback="en_US-ryan-high", pauses=True)[0]
        ws = a["words"]
        assert [w[2] for w in ws] == scenes[0]["text"].split() and ws[-1][1] < a["duration"], ws  # script's words
        i = [w[2] for w in ws].index("percent")
        gap = lambda k: ws[k + 1][0] - ws[k][1]  # noqa: E731
        assert gap(i) > gap(i - 1) and voice.length_scale("+0%") == 1.0, ws
    finally:
        voice._piper_voice, voice._edge_down = saved
        shutil.rmtree(work, ignore_errors=True)
    # over the limit at the configured +0%: re-recorded once, faster, with the same pauses
    calls, logs = [], []

    def fake_synth(scenes_, name, rate, workdir, log=print, fallback=None, pauses=False):
        calls.append((rate, pauses))
        return [{"audio": None, "duration": 25.0 if len(calls) == 1 else 20.0, "words": []} for _ in scenes_]
    with mock.patch.object(voice, "synthesize", fake_synth):
        audio, total = app.narrate(cfg["voice"], scenes, cfg["video"]["max_seconds"], Path("."), pauses=True,
                                   log=logs.append)
    assert calls == [("+0%", True), ("+21%", True)] and total == 40.0 and any("re-recording at +21%" in m for m in logs), calls
    calls.clear()
    with mock.patch.object(voice, "synthesize", fake_synth):
        app.narrate(cfg["voice"], scenes[:1], cfg["video"]["max_seconds"], Path("."), pauses=True, log=logs.append)
    assert calls == [("+0%", True)], calls  # within the limit: one recording
    assert "pauses=True" in inspect.getsource(app.make_brief) and "pauses" not in inspect.getsource(app.make_lesson)
    print("OK voice pacing (+0%, pauses after key numbers + before the term, captions aligned, re-record faster)")


def test_voice_ab(cfg, data):
    """Entry 7 (CAP-7): two edge-tts voices alternate per edition (history decides, Piper entries skipped),
    the voice that spoke (edge or Piper) is logged as "voice" in the brief's entry; lessons keep one voice."""
    import inspect
    from unittest import mock

    import main as app
    from autopilot import voice, youtube
    a, b = cfg["voice"]["name"], cfg["voice"]["alternate"]
    assert a != b and a.endswith("Neural") and b.endswith("Neural"), (a, b)
    tmp = Path(tempfile.mkdtemp())
    h = History(tmp / "history.json")

    def published(session, who, vid):
        h.add({"brief_date": "2026-10-07", "session": session, "kind": "market", "video_id": vid, "voice": who})

    pick = lambda s="london": app.ab_voice(cfg["voice"], h, s)["name"]  # noqa: E731
    assert pick() == a  # no history yet → voice.name
    published("london", a, "V1")
    assert pick() == b and pick("newyork") == a  # other editions keep their own turn
    published("london", b, "V2")
    assert pick() == a
    published("london", "en_US-ryan-high", "V3")  # Piper fallback: logged, but takes no turn
    assert pick() == a
    h.data["videos"].append({"session": "london", "kind": "market", "video_id": None, "voice": a})  # never published
    assert pick() == a
    published("newyork", a, "V4")
    assert pick() == a and pick("newyork") == b
    solo = {k: v for k, v in cfg["voice"].items() if k != "alternate"}
    assert app.ab_voice(solo, h, "london") == solo  # without alternate: one voice

    # synthesize tags the voice that actually spoke: the edge voice, or the Piper model on fallback
    async def fine(text, v, rate, mp3):
        mp3.write_bytes(b"\0" * 2000)
        return [(0.0, 0.3, w) for w in text.split()]

    class FakePiper:
        def synthesize_wav(self, text, w, syn_config=None):
            w.setnchannels(1), w.setsampwidth(2), w.setframerate(22050)
            w.writeframes(b"\x00\x01" * 22050)

    scenes = [{"text": "Bitcoin rose two percent."}]
    saved = voice._speak, voice._piper_voice, voice.run, voice.probe_duration, voice._edge_down
    voice._speak, voice.probe_duration, voice._edge_down = fine, (lambda p: 1.0), False
    voice.run = lambda cmd: Path(cmd[-1]).write_bytes(b"x")
    try:
        assert voice.synthesize(scenes, b, "+0%", tmp, log=lambda m: None)[0]["voice"] == b
        voice.run, voice._piper_voice, voice._edge_down = saved[2], (lambda m: FakePiper()), True
        assert voice.synthesize(scenes, b, "+0%", tmp, log=lambda m: None, fallback="en_US-ryan-high")[0]["voice"] \
            == "en_US-ryan-high"
    finally:
        voice._speak, voice._piper_voice, voice.run, voice.probe_duration, voice._edge_down = saved

    # make_brief (heavy steps faked) narrates with the rotated voice and logs the one that spoke
    spoke = []

    def fake_synth(scenes_, name, rate, workdir, log=print, fallback=None, pauses=False):
        spoke.append(name)
        who = fallback if fake_synth.piper else name
        return [{"audio": None, "duration": 5.0, "words": [], "voice": who} for _ in scenes_]

    def brief(history):
        with mock.patch.object(app, "ROOT", tmp), \
                mock.patch.object(app.sources, "gather", lambda *a_, **k: json.loads(json.dumps(data))), \
                mock.patch.object(app.script, "make_script", lambda *a_, **k: json.loads(json.dumps(PKG))), \
                mock.patch.object(app.thumbnail, "render", lambda *a_, **k: tmp / "thumb.jpg"), \
                mock.patch.object(voice, "synthesize", fake_synth), \
                mock.patch.object(app.slides, "render_slides", lambda *a_, **k: []), \
                mock.patch.object(app.render, "build_video", lambda *a_, **k: None), \
                mock.patch.object(youtube, "build_metadata", lambda *a_, **k: {"title": "t"}), \
                mock.patch.object(app.facebook, "reel_caption", lambda *a_, **k: "c"):
            return app.make_brief(cfg, history, None, "london")["entry"]

    fake_synth.piper = False
    h2 = History(tmp / "h2.json")
    e1 = brief(h2)
    assert e1["voice"] == a and spoke == [a], (e1, spoke)
    h2.add({**e1, "video_id": "Y1"})
    e2 = brief(h2)
    assert e2["voice"] == b and spoke[-1] == b, (e2, spoke)  # the next run of the edition: the other voice
    h2.add({**e2, "video_id": "Y2"})
    fake_synth.piper = True
    e3 = brief(h2)
    assert spoke[-1] == a and e3["voice"] == cfg["voice"]["fallback"], e3  # Piper fallback recorded as Piper
    h2.add({**e3, "video_id": "Y3"})
    fake_synth.piper = False
    assert brief(h2)["voice"] == a  # Piper took no turn: voice a gets its run back
    assert "ab_voice" not in inspect.getsource(app.make_lesson)  # lessons: one voice, entries unchanged
    shutil.rmtree(tmp, ignore_errors=True)
    print("OK voice A/B (alternates per edition, Piper logged and skipped, voice in the entry, lessons one voice)")


def test_market_overview():
    """CoinGecko Demo overview (E3-1): parsed from recorded-shape JSON; a missing key, 429, bad key,
    timeout or bad body returns None with a log line. requests.get is mocked — no network."""
    import contextlib
    import io
    from unittest import mock

    import requests
    from autopilot import sources

    fx = ROOT / "tests" / "fixtures"
    glob = json.loads((fx / "coingecko_global.json").read_text())
    rows = json.loads((fx / "coingecko_markets.json").read_text())

    ov = sources.parse_overview(glob, rows)
    assert ov["total_cap_change_24h"] == -4.3172 and ov["total_cap_usd"] == 2412345678901.23, ov
    assert ov["credit"] == sources.CG_CREDIT == "Data provided by CoinGecko"
    assert ov["as_of_utc"].startswith("2026-10-14"), ov["as_of_utc"]
    assert len(ov["coins"]) == 50 and [c["rank"] for c in ov["coins"]] == list(range(1, 51))
    btc, eth = ov["coins"][0], ov["coins"][1]
    assert (btc["symbol"], btc["name"], btc["price"], btc["change_24h"], btc["change_7d"]) == \
        ("BTC", "Bitcoin", 62400, -5.2134, -3.8761), btc
    assert len(btc["sparkline"]) == 168 and btc["sparkline"][-1] == 62400 and eth["change_24h"] == -6.0412
    mover = next(c for c in ov["coins"] if c["symbol"] == "C23")
    assert mover["change_24h"] == 17.881 and mover["change_7d"] == 25.4421, mover
    # null quirks: 24h falls back to price_change_percentage_24h, null 7d stays None, null points dropped
    assert ov["coins"][30]["change_24h"] == rows[30]["price_change_percentage_24h"] == -2.3453
    assert ov["coins"][31]["change_7d"] is None and len(ov["coins"][32]["sparkline"]) == 23
    # a coin with no 24h change at all, or no price, is dropped; extra rows past 50 are ignored
    bad = json.loads(json.dumps(rows))
    bad[3]["price_change_percentage_24h_in_currency"] = bad[3]["price_change_percentage_24h"] = None
    bad[4]["current_price"] = None
    bad[5]["sparkline_in_7d"] = [1, 2]  # malformed sparkline: the coin stays, with no series
    more = bad + [dict(bad[0], id="extra", symbol="xtra", market_cap_rank=51)]
    got = sources.parse_overview(glob, more)
    assert len(got["coins"]) == 48 and {"BNB", "SOL", "XTRA"}.isdisjoint(c["symbol"] for c in got["coins"])
    assert got["coins"][3]["symbol"] == "USDC" and got["coins"][3]["sparkline"] == []
    for ts in (1e20, None, "x"):  # an out-of-range / missing update time leaves as_of blank
        g2 = json.loads(json.dumps(glob))
        g2["data"]["updated_at"] = ts
        assert sources.parse_overview(g2, rows)["as_of_utc"] == ""
    for g_, r_ in (({}, rows), ({"data": {"total_market_cap": {}}}, rows), (glob, {"error": "x"}), (glob, []),
                   ({"data": {"total_market_cap": {"usd": 1e12}, "market_cap_change_percentage_24h_usd": "nan"}}, rows)):
        try:
            sources.parse_overview(g_, r_)
            raise AssertionError(f"parse_overview accepted {g_!r:.60}")
        except ValueError:
            pass

    class Resp:
        def __init__(self, status, body=None, headers=None):
            self.status_code, self.body, self.headers = status, body, headers or {}

        def json(self):
            if isinstance(self.body, Exception):
                raise self.body
            return self.body

    def run_fetch(answers, key="demo-key-123"):
        calls, logs, sleeps = [], [], []
        queue = list(answers)

        def fake_get(url, params=None, headers=None, timeout=None):
            calls.append((url, params, headers, timeout))
            a = queue.pop(0)
            if isinstance(a, Exception):
                raise a
            return a
        with mock.patch.object(sources.requests, "get", fake_get), \
                mock.patch.object(sources.time, "sleep", lambda s: sleeps.append(s)):
            out = sources.fetch_market_overview(log=logs.append, key=key)
        assert all("demo-key-123" not in m for m in logs), logs
        return out, calls, logs, sleeps

    ok = [Resp(200, glob), Resp(200, rows)]
    out, calls, logs, sleeps = run_fetch(ok)
    assert out and out["total_cap_change_24h"] == -4.3172 and len(out["coins"]) == 50 and not sleeps, logs
    (u1, p1, h1, t1), (u2, p2, h2, t2) = calls
    assert u1.endswith("/api/v3/global") and u2.endswith("/api/v3/coins/markets"), calls
    assert h1["x-cg-demo-api-key"] == h2["x-cg-demo-api-key"] == "demo-key-123" and t1 and t2
    assert p2 == {"vs_currency": "usd", "order": "market_cap_desc", "per_page": 50, "page": 1,
                  "sparkline": "true", "price_change_percentage": "24h,7d"}, p2
    assert "demo-key-123" not in u1 + u2 and not any("demo" in str(v) for v in (p2 or {}).values())

    # missing key (env unset or blank): skipped with a log line, no HTTP call
    saved = os.environ.pop("COINGECKO_API_KEY", None)
    try:
        for k in (None, "  "):
            if k is not None:
                os.environ["COINGECKO_API_KEY"] = k
            out, calls, logs, _ = run_fetch([], key=None)
            assert out is None and not calls and logs == ["CoinGecko overview skipped: COINGECKO_API_KEY is not set"], logs
        os.environ["COINGECKO_API_KEY"] = "demo-key-123"  # the env var is read when no key is passed
        out, calls, logs, _ = run_fetch(ok, key=None)
        assert out and calls[0][2]["x-cg-demo-api-key"] == "demo-key-123"
    finally:
        os.environ.pop("COINGECKO_API_KEY", None)
        if saved is not None:
            os.environ["COINGECKO_API_KEY"] = saved

    # 429 twice: one retry (Retry-After capped at 10 s), then None with a log line
    out, calls, logs, sleeps = run_fetch([Resp(429, headers={"Retry-After": "60"}), Resp(429)])
    assert out is None and len(calls) == 2 and sleeps == [10.0], (calls, sleeps)
    assert logs == ["CoinGecko overview skipped: CoinGecko /global: HTTP 429"], logs
    # 429 then 200: the retry wins
    out, calls, logs, sleeps = run_fetch([Resp(429, headers={"Retry-After": "3"}), Resp(200, glob), Resp(200, rows)])
    assert out and len(calls) == 3 and sleeps == [3.0], logs
    # 429 on the markets call (global ok) twice, a non-numeric Retry-After → the 2 s wait
    out, calls, logs, sleeps = run_fetch([Resp(200, glob), Resp(429, headers={"Retry-After": "Wed, 14 Oct 2026"}),
                                          Resp(429)])
    assert out is None and len(calls) == 3 and sleeps == [2.0], (calls, sleeps)
    assert logs == ["CoinGecko overview skipped: CoinGecko /coins/markets: HTTP 429"], logs
    # 5xx on the markets call, then ok
    out, calls, _, sleeps = run_fetch([Resp(200, glob), Resp(503), Resp(200, rows)])
    assert out and len(calls) == 3 and sleeps == [2.0]
    # bad key: 401 is not retried
    out, calls, logs, sleeps = run_fetch([Resp(401, {"status": {"error_code": 10002}})])
    assert out is None and len(calls) == 1 and not sleeps and "HTTP 401" in logs[0], logs
    # timeout twice
    out, calls, logs, _ = run_fetch([requests.Timeout("read timed out"), requests.ConnectionError("down")])
    assert out is None and len(calls) == 2 and logs[0].endswith("ConnectionError"), logs
    # not JSON / unusable body
    out, _, logs, _ = run_fetch([Resp(200, ValueError("Expecting value"))])
    assert out is None and "not JSON" in logs[0], logs
    out, _, logs, _ = run_fetch([Resp(200, {"status": "x"}), Resp(200, rows)])
    assert out is None and logs == ["CoinGecko overview skipped: /global has no data"], logs

    # CLI: `python -m autopilot.sources overview` prints the overview and the credit; exit 1 without one
    buf = io.StringIO()
    with mock.patch.object(sources, "fetch_market_overview", lambda: json.loads(json.dumps(ov))), \
            contextlib.redirect_stdout(buf):
        assert sources._main(["overview"]) == 0
    text = buf.getvalue()
    assert text.startswith("Total crypto market cap $2.41T, 24h -4.32%") and "C23" in text, text[:300]
    assert text.index("C23") < text.index("ETH") < text.index("BTC") and text.rstrip().endswith(sources.CG_CREDIT)
    with mock.patch.object(sources, "fetch_market_overview", lambda: None):
        assert sources._main(["overview"]) == 1
    print("OK market overview: CoinGecko fixtures → total cap -4.32% + 50 coin moves (24h, 7d, sparkline), "
          "null quirks, missing key / 429 / 401 / timeout / bad body → None with a log line, one retry, CLI")


def test_history():
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        h = History(Path(tmp) / "history.json")
        h.add({"brief_date": "2026-10-07", "session": "asia", "video_id": "m1", "trigger": "manual", "counts": False,
               "date": "2026-10-07T03:00:00+00:00"})
        assert not h.uploaded_on("2026-10-07", "asia")  # a manual run doesn't stop the timed run
        h.add({"brief_date": "2026-10-07", "session": "asia", "video_id": "m2", "trigger": "manual", "counts": True,
               "date": "2026-10-07T03:10:00+00:00"})
        assert h.uploaded_on("2026-10-07", "asia")  # ...unless it was started "as the edition"
        assert not h.add({"video_id": "m2"})  # merging the same entry twice is harmless
        h.add({"brief_date": "2026-10-07", "session": "gold", "kind": "gold", "video_id": "g1",
               "date": "2026-10-07T06:20:00+00:00", "outlook": {"price": 1}})
        assert h.last("gold")["video_id"] == "g1" and h.last("market")["video_id"] == "m2"
        assert h.last_upload_time("market").hour == 3
        # per platform: YouTube got the London edition, Facebook (Reel) didn't yet
        h.add({"brief_date": "2026-10-07", "session": "london", "video_id": "y1", "headlines": ["Story L"],
               "date": "2026-10-07T05:45:00+00:00"})
        assert h.published_on("2026-10-07", "london", "youtube") and h.uploaded_on("2026-10-07", "london")
        assert not h.published_on("2026-10-07", "london", "facebook")
        h.add({"brief_date": "2026-10-07", "session": "london", "video_id": None, "fb_reel_id": "r1",
               "headlines": ["Story L"], "date": "2026-10-07T06:05:00+00:00"})
        assert h.published_on("2026-10-07", "london", "facebook")
        assert not h.add({"fb_reel_id": "r1"})  # merging the same Reel entry twice is harmless
        assert h.excluding_slot("2026-10-07", "london").last("market")["video_id"] == "m2"
        # news image posts: Facebook only, tracked apart from the videos' "don't repeat" headlines
        h.add({"brief_date": "2026-10-07", "session": "news_morning", "kind": "post", "fb_post_id": "p1",
               "headlines": ["Fed holds rates"], "topic": "rates", "date": datetime.now(timezone.utc).isoformat()})
        assert h.published_on("2026-10-07", "news_morning", "facebook")
        assert not h.published_on("2026-10-07", "news_morning", "youtube")
        assert h.fb_post_headlines() == ["Fed holds rates"] and h.fb_post_headlines(hours=48) == ["Fed holds rates"]
        assert "Fed holds rates" not in h.used_headlines() and "Story L" in h.used_headlines()
        assert h.last("post")["topic"] == "rates" and h.last("market")["fb_reel_id"] == "r1"
        assert not h.add({"fb_post_id": "p1"})
        # lessons have no headlines and don't take places in the videos' last-15 "don't repeat" window
        for i in range(16):
            h.add({"brief_date": "2026-10-07", "session": "lesson", "kind": "lesson", "episode": f"e{i}",
                   "video_id": f"l{i}", "date": "2026-10-07T14:35:00+00:00"})
        assert "Story L" in h.used_headlines(), h.used_headlines()
    print("OK history")


# ─── Facebook (mocked Graph API) ───────────────────────────────────────────

class FakeResp:
    def __init__(self, status: int, body):
        self.status_code, self._body = status, body
        self.text = json.dumps(body)

    def json(self):
        return self._body


class FakeGraph:
    """Answers like graph.facebook.com / rupload.facebook.com and records every call."""

    def __init__(self, finish_fails: bool = False, photo_errors: list | None = None,
                 video_errors: dict | None = None, video_took: bool = True, video_status_fails: bool = False,
                 video_slow_start: bool = False, chunk: int = 1000):
        self.calls, self.finish_fails = [], finish_fails
        self.photo_errors = list(photo_errors or [])
        self.status_reads = 0
        self.finished = False
        # /{page}/videos (long lesson videos): errors queued per upload phase; video_took = an errored
        # finish went through anyway; video_status_fails = GET /V1 always errors; video_slow_start = the
        # first status read after a finish that took still shows processing not_started
        self.video_errors = {k: list(v) for k, v in (video_errors or {}).items()}
        self.video_took, self.video_status_fails, self.chunk = video_took, video_status_fails, chunk
        self.video_slow_start = video_slow_start
        self.video_size, self.video_finishes, self.video_reads, self.video_published = 0, [], 0, None
        self.chunks = []

    def _video(self, method, url, data, kw):
        phase = data.get("upload_phase")
        if url.endswith("/videos") and self.video_errors.get(phase):
            if phase == "finish":
                self.video_finishes.append(dict(data))
                if self.video_took:
                    self.video_published = data["published"] == "true"
            return self.video_errors[phase].pop(0)
        if url.endswith("/videos") and phase == "start":
            self.video_size = int(data["file_size"])
            return FakeResp(200, {"upload_session_id": "S1", "video_id": "V1", "start_offset": "0",
                                  "end_offset": str(min(self.chunk, self.video_size))})
        if url.endswith("/videos") and phase == "transfer":
            assert data["upload_session_id"] == "S1"
            name, blob, _ = kw["files"]["video_file_chunk"]
            assert isinstance(blob, bytes) and len(blob) > 0
            start = int(data["start_offset"])
            self.chunks.append((start, blob))
            nxt = start + len(blob)
            return FakeResp(200, {"start_offset": str(nxt), "end_offset": str(min(nxt + self.chunk, self.video_size))})
        if url.endswith("/videos") and phase == "finish":
            assert data["upload_session_id"] == "S1" and sum(len(b) for _, b in self.chunks) >= self.video_size
            self.video_finishes.append(dict(data))
            self.video_published = data["published"] == "true"
            return FakeResp(200, {"success": True})
        if method == "GET" and url.endswith("/V1"):
            assert kw["headers"]["Authorization"] == "OAuth TOKEN"
            if self.video_status_fails:
                return FakeResp(500, {"error": {"code": 1, "message": "unknown error"}})
            if self.video_published is None:  # finish hasn't taken: the upload isn't complete
                return FakeResp(200, {"status": {"video_status": "processing",
                                                 "uploading_phase": {"status": "in_progress"},
                                                 "processing_phase": {"status": "not_started"},
                                                 "publishing_phase": {"status": "not_started"}}})
            self.video_reads += 1
            if self.video_slow_start and self.video_reads == 1:  # took, but nothing moving yet
                return FakeResp(200, {"status": {"video_status": "processing",
                                                 "uploading_phase": {"status": "complete"},
                                                 "processing_phase": {"status": "not_started"},
                                                 "publishing_phase": {"status": "not_started"}}})
            done = self.video_reads >= 3
            pub = ("complete" if done else "in_progress") if self.video_published else "not_started"
            return FakeResp(200, {"status": {"video_status": "ready" if done else "processing",
                                             "uploading_phase": {"status": "complete"},
                                             "processing_phase": {"status": "complete" if done else "in_progress"},
                                             "publishing_phase": {"status": pub}}})
        if method == "DELETE" and url.endswith("/V1"):
            assert kw["headers"]["Authorization"] == "OAuth TOKEN"
            return FakeResp(200, {"success": True})
        return None

    def request(self, method, url, timeout=None, **kw):
        data = kw.get("data") if isinstance(kw.get("data"), dict) else {}
        self.calls.append((method, url, data.get("upload_phase")))
        if url.endswith("/videos") or url.endswith("/V1"):
            res = self._video(method, url, data, kw)
            if res is not None:
                return res
        if url.endswith("/video_reels") and data.get("upload_phase") == "start":
            return FakeResp(200, {"video_id": "R1", "upload_url": "https://rupload.facebook.com/video-upload/v26.0/R1"})
        if "rupload.facebook.com" in url:
            assert kw["headers"]["Authorization"].startswith("OAuth ") and int(kw["headers"]["file_size"]) > 0
            return FakeResp(200, {"success": True})
        if url.endswith("/video_reels") and data.get("upload_phase") == "finish":
            self.finished = True
            if self.finish_fails:  # the request went through, but the answer was a 503
                return FakeResp(503, {"error": {"code": 2, "message": "Service temporarily unavailable",
                                                "is_transient": True}})
            return FakeResp(200, {"success": True})
        if method == "GET" and url.endswith("/R1"):
            self.status_reads += 1
            done = self.status_reads >= 2
            return FakeResp(200, {"status": {
                "video_status": "ready" if done else "processing",
                "uploading_phase": {"status": "complete"},
                "processing_phase": {"status": "complete" if done else "in_progress"},
                "publishing_phase": {"status": ("complete" if done else "in_progress") if self.finished
                                     else "not_started", "publish_status": "published" if done else "not_published"}}})
        if url.endswith("/R1/thumbnails"):
            return FakeResp(400, {"error": {"code": 100, "message": "Custom thumbnails not supported"}})
        if url.endswith("/photos"):
            assert "source" in kw.get("files", {}) and data.get("caption")
            if self.photo_errors:
                return self.photo_errors.pop(0)
            return FakeResp(200, {"id": "P1", "post_id": "PAGE_P1"})
        return FakeResp(404, {"error": {"code": 803, "message": f"unknown {method} {url}"}})

    def count(self, phase=None, contains=None):
        return sum(1 for m, u, ph in self.calls if (phase is None or ph == phase) and (contains is None or contains in u))


def _fb_env(fake: FakeGraph):
    os.environ["FB_PAGE_ID"], os.environ["FB_PAGE_TOKEN"] = "PAGE", "TOKEN"
    facebook._http, facebook._sleep = fake, (lambda s: None)


def test_facebook(cfg, pkg, data, meta, video, cover):
    import main as app
    from autopilot import youtube
    assert not facebook.enabled(cfg) and "FB_PAGE_ID" in facebook.disabled_reason(cfg)  # no secrets → skipped
    fcfg = cfg | {"facebook": cfg["facebook"] | {"poll_every_seconds": 1}}

    # Reel: one render published to both; YouTube's quota is gone → the Reel still goes out
    fake = FakeGraph()
    _fb_env(fake)
    yt_calls = []
    saved = youtube.upload, youtube.set_thumbnail

    def quota(*a, **k):
        yt_calls.append(a)
        raise RuntimeError("YouTube upload limit reached for today")
    youtube.upload = quota
    try:
        cap = facebook.reel_caption(meta, pkg, data, cfg)
        made = {"entry": {"brief_date": "2026-10-07", "session": "london", "video_id": None},
                "video": video, "thumbnail": cover, "meta": meta, "fb_caption": cap}
        entry, failed = app.publish(made, ["youtube", "facebook"], fcfg)
    finally:
        youtube.upload, youtube.set_thumbnail = saved
    assert len(yt_calls) == 1 and failed == ["youtube"], failed
    assert entry["fb_reel_id"] == "R1" and entry["video_id"] is None, entry
    assert fake.count("finish") == 1 and fake.count("start") == 1 and fake.count(contains="rupload") == 1
    h = History(Path(tempfile.mkdtemp()) / "h.json")
    assert h.add(entry) and h.published_on("2026-10-07", "london", "facebook")
    assert not h.published_on("2026-10-07", "london", "youtube")

    # Reel caption: hook first, no links, ≤5 hashtags, no #Shorts, disclaimer, < 2,200 chars
    assert cap.startswith(meta["title"]) and "http" not in cap and "#Shorts" not in cap and len(cap) < 2200
    tags = [w for w in cap.split() if w.startswith("#")]
    assert 1 <= len(tags) <= 5 and "not financial advice" in cap.lower(), cap

    # finish answered 503 but went through: the status is checked and finish is NOT sent again
    fake = FakeGraph(finish_fails=True)
    _fb_env(fake)
    assert facebook.publish_reel(video, "x", fcfg) == "R1" and fake.count("finish") == 1, fake.calls

    # expired token (190): fails at once with the fix, no retry
    fake = FakeGraph(photo_errors=[FakeResp(400, {"error": {"code": 190, "error_subcode": 463,
                                                            "message": "Session has expired"}})])
    _fb_env(fake)
    try:
        facebook.publish_photo(cover, "caption", cfg)
        raise AssertionError("190 should fail")
    except facebook.GraphError as e:
        assert e.code == 190 and "FB_PAGE_TOKEN" in str(e) and not e.transient
    assert fake.count(contains="/photos") == 1

    # transient 500 → retried, then posted
    fake = FakeGraph(photo_errors=[FakeResp(500, {"error": {"code": 1, "message": "unknown error"}})])
    _fb_env(fake)
    assert facebook.publish_photo(cover, "caption", cfg) == "PAGE_P1" and fake.count(contains="/photos") == 2
    # permission (200) and throttling (4) fail without retry
    for code in (200, 4):
        fake = FakeGraph(photo_errors=[FakeResp(400, {"error": {"code": code, "message": "nope"}})])
        _fb_env(fake)
        try:
            facebook.publish_photo(cover, "caption", cfg)
            raise AssertionError(f"{code} should fail")
        except facebook.GraphError:
            assert fake.count(contains="/photos") == 1
    for k in ("FB_PAGE_ID", "FB_PAGE_TOKEN"):
        os.environ.pop(k, None)
    print("OK facebook")


def test_facebook_video(cfg):
    """Long vertical lesson → chunked /{page}/videos upload, finish once, status before any re-send."""
    fcfg = cfg | {"facebook": cfg["facebook"] | {"poll_every_seconds": 1}}
    blob = bytes(range(256)) * 11 + b"tail"  # 2,820 bytes → 3 chunks of ≤ 1,000
    video = Path(tempfile.mkdtemp()) / "lesson_9x16.mp4"
    video.write_bytes(blob)
    logs = []
    quiet = logs.append
    unclear = lambda: FakeResp(503, {"error": {"code": 2, "message": "Service temporarily unavailable",  # noqa: E731
                                               "is_transient": True}})

    def no_token_in_urls(fake):
        assert all("TOKEN" not in u for _, u, _ in fake.calls), fake.calls

    def chunks_ok(fake):  # each chunk = exactly the file's bytes for the range Facebook asked for
        assert [(st, len(b)) for st, b in fake.chunks] == [(0, 1000), (1000, 1000), (2000, 820)], fake.chunks
        assert all(b == blob[st:st + len(b)] for st, b in fake.chunks)

    # happy path: start, 3 transfers (the byte ranges asked for), one finish with title/description, poll
    fake = FakeGraph()
    _fb_env(fake)
    desc = "Lesson description " * 400  # > 5,000 chars → cut
    assert facebook.publish_video(video, "T" * 300, desc, fcfg, log=quiet) == "V1"
    assert fake.count("start", "/videos") == 1 and fake.count("transfer") == 3 and fake.count("finish") == 1
    chunks_ok(fake)
    f = fake.video_finishes[0]
    assert f["published"] == "true" and len(f["title"]) == 255 and len(f["description"]) == 5000, f
    assert fake.video_reads == 3 and not any("still processing" in m for m in logs), logs
    no_token_in_urls(fake)

    # token error at start: fails at once with the fix, exactly one request
    fake = FakeGraph(video_errors={"start": [FakeResp(400, {"error": {"code": 190, "message": "Session has expired"}})]})
    _fb_env(fake)
    try:
        facebook.publish_video(video, "t", "d", fcfg, log=quiet)
        raise AssertionError("190 should fail")
    except facebook.GraphError as e:
        assert e.code == 190 and "FB_PAGE_TOKEN" in str(e) and not e.transient
    assert len(fake.calls) == 1, fake.calls

    # finish answered 503 but took (status shows processing/publishing) → not sent again
    fake = FakeGraph(video_errors={"finish": [unclear()]}, video_took=True)
    _fb_env(fake)
    assert facebook.publish_video(video, "t", "d", fcfg, log=quiet) == "V1" and fake.count("finish") == 1
    # ... and took, but processing hasn't begun on the first read (upload complete) → still not re-sent
    for pub in (True, False):
        fake = FakeGraph(video_errors={"finish": [unclear()]}, video_took=True, video_slow_start=True)
        _fb_env(fake)
        assert facebook.publish_video(video, "t", "d", fcfg, published=pub, log=quiet) == "V1"
        assert fake.count("finish") == 1, fake.calls
    # finish answered 503 and didn't take (status: not started) → sent once more
    fake = FakeGraph(video_errors={"finish": [unclear()]}, video_took=False)
    _fb_env(fake)
    logs.clear()
    assert facebook.publish_video(video, "t", "d", fcfg, log=quiet) == "V1" and fake.count("finish") == 2
    assert any("sending finish again" in m for m in logs), logs
    # finish answered 503 and the status can't be read → no re-send, id still returned
    fake = FakeGraph(video_errors={"finish": [unclear()]}, video_status_fails=True)
    _fb_env(fake)
    logs.clear()
    assert facebook.publish_video(video, "t", "d", fcfg, log=quiet) == "V1" and fake.count("finish") == 1
    assert any("not sending finish again" in m for m in logs) and any("status unknown" in m for m in logs), logs

    # unpublished test upload: finish sends published=false, done once ready
    fake = FakeGraph()
    _fb_env(fake)
    assert facebook.publish_video(video, "t", "d", fcfg, published=False, log=quiet) == "V1"
    assert fake.video_finishes[0]["published"] == "false" and fake.count("finish") == 1
    facebook.delete_video("V1", fcfg, log=quiet)
    assert fake.count(contains="/V1") == fake.video_reads + 1 and fake.calls[-1][0] == "DELETE"
    no_token_in_urls(fake)

    # one chunk answers 5xx → that chunk is retried by _call, the upload isn't restarted
    fake = FakeGraph(video_errors={"transfer": [FakeResp(500, {"error": {"code": 1, "message": "unknown error"}})]})
    _fb_env(fake)
    assert facebook.publish_video(video, "t", "d", fcfg, log=quiet) == "V1"
    assert fake.count("start", "/videos") == 1 and fake.count("transfer") == 4 and fake.count("finish") == 1
    chunks_ok(fake)
    for k in ("FB_PAGE_ID", "FB_PAGE_TOKEN"):
        os.environ.pop(k, None)
    print("OK facebook lesson video (chunked /videos, one publish, 190 not retried, status before re-send)")


# ─── news image posts ──────────────────────────────────────────────────────

NOW = datetime(2026, 10, 8, 3, 5, tzinfo=timezone.utc)


def news_data() -> dict:
    data = sample_data()

    def item(cat, src, title, hours, summary="", body=""):
        return {"category": cat, "source": src, "title": title, "summary": summary, "body": body,
                "published": (NOW - timedelta(hours=hours)).isoformat(), "link": "https://example.com/a"}
    data.update(kind="post", date_utc="2026-10-08", weekday="Thursday")
    data["news"] = [
        item("forex", "Reuters", "Fed's Powell signals patience on rate cuts in policy speech", 2,
             summary="Bitcoin and Ether slipped as traders weighed a slower path for US rate cuts.",
             body="Federal Reserve Chair Jerome Powell said the central bank can be patient before cutting "
                  "interest rates again, citing inflation of 3.4%."),
        item("forex", "CNBC", "Powell signals patience on cuts as inflation stays sticky", 3,
             summary="Crypto markets dipped as traders priced fewer cuts."),
        item("geopolitics", "Bloomberg", "US slaps new tariffs on Chinese chips, markets slide", 5,
             summary="Bitcoin fell with stocks as the chip tariffs hit risk appetite."),
        item("crypto", "Cointelegraph", "Bitcoin liquidations top $500M as BTC dips", 20, summary="Ether also fell."),
        item("gold", "Kitco", "Gold holds near two-month low as dollar firms", 30),  # not crypto (CAP-9)
    ]
    return data


GOOD_POST = {"kicker": "FED SPEECH", "headline": ["POWELL SIGNALS", "PATIENCE ON CUTS"], "accent_line": 1,
             "subline": "Fed chair cites inflation of 3.4% in policy speech",
             "caption": "Fed Chair Jerome Powell signalled patience on interest rate cuts in a policy speech.\n\n"
                        "According to Reuters, Powell said the Fed can wait before cutting again, citing inflation "
                        "of 3.4%. A patient Fed usually supports the US dollar and tends to weigh on gold and "
                        "Bitcoin. Traders watch the next US inflation data for the Fed rate decision outlook.",
             "hashtags": ["#Fed", "#Powell", "#InterestRates"],
             "image_prompt": "a grand stone central bank building at dusk, golden light, storm clouds"}


def _news_llm(answer):
    def fake(prompt, models, temperature=0.9):
        if "strict financial news editor" in prompt:
            return {"verdict": "ok", "issues": [],
                    "package": json.loads(prompt.split("SCRIPT:\n", 1)[1].rsplit("\n\n1. Every", 1)[0])}
        if isinstance(answer, Exception):
            raise answer
        return json.loads(json.dumps(answer))
    return fake


def test_news_post(cfg):
    data = news_data()
    quiet = lambda m: None  # noqa: E731
    # picker: rate story first; then never one an earlier post used; never empty
    s1 = news_post.pick_story(data, [], [], cfg, now=NOW, log=quiet)
    assert s1["source"] == "Reuters" and s1["topic"] in ("rates", "central_bank") and s1["tier"] == "fresh", s1
    assert any(c["source"] == "CNBC" for c in s1["coverage"])
    s2 = news_post.pick_story(data, [s1["title"]], [], cfg, now=NOW, log=quiet)
    assert s2["source"] == "Bloomberg" and s2["topic"] == "tariffs", s2  # CNBC's version counts as used too
    titles = [n["title"] for n in data["news"]]
    s3 = news_post.pick_story(data, titles[:3], [], cfg, now=NOW, log=quiet)
    assert s3["tier"] == "not used yet" and s3["title"] in titles[3:], s3
    s4 = news_post.pick_story(data, titles[:4], [], cfg, now=NOW, log=quiet)  # every crypto story used
    assert s4["tier"].startswith("best available") and s4["title"] != titles[3], s4  # not the last used

    # writer: Gemini output used when it checks out; bad numbers / failures → the story's own text
    news_post.generate_json = _news_llm(GOOD_POST)
    script.generate_json = _news_llm(GOOD_POST)
    post = news_post.write_post(cfg, data, s1, log=quiet)
    assert post["writer"] == "gemini" and post["headline"] == GOOD_POST["headline"] and post["accent_line"] == 1
    assert post["caption"].startswith("Fed Chair Jerome Powell")
    news_post.generate_json = _news_llm(dict(GOOD_POST, headline=["BTC TO 1M", "SOON"],
                                             caption=GOOD_POST["caption"] + " Bitcoin could reach $999 billion."))
    risky = news_post.write_post(cfg, data, s1, log=quiet)
    assert risky["headline"] != ["BTC TO 1M", "SOON"] and "$999" not in risky["caption"], risky
    news_post.generate_json = _news_llm(RuntimeError("All Gemini models failed"))
    fb = news_post.write_post(cfg, data, s2, log=quiet)
    assert fb["writer"] == "fallback" and 1 <= len(fb["headline"]) <= 4 and fb["headline"][0].startswith("US SLAPS")

    # caption: hook first, source named, numbers from the data, disclaimer, ≤5 hashtags, no links
    cap = news_post.caption(post, s1, data, cfg, ai_image=False)
    assert cap.startswith("Fed Chair Jerome Powell") and "Reuters" in cap and "http" not in cap
    assert "Market check:" in cap and "not financial advice" in cap.lower()
    tags = [w for w in cap.split() if w.startswith("#")]
    assert 1 <= len(tags) <= 5 and "#Shorts" not in tags, tags
    assert not news_post._BANNED_RX.search(cap.split("Market check:")[0])
    fcap = news_post.caption(fb, s2, data, cfg, ai_image=True)
    assert "Bloomberg" in fcap and "AI illustration" in fcap

    # card: no CF secrets → drawn background; 1080x1350 JPEG for the acceptance check
    work = ROOT / "output" / "test_news"
    work.mkdir(parents=True, exist_ok=True)
    bg, src = images.background(post["image_prompt"], s1["topic"], cfg, log=quiet)
    assert src in ("drawn", "library") and bg.size == (1080, 1350)
    card = images.render_card(post, bg, cfg, data["date_utc"], work / "post.jpg", ai=False, source=s1["source"])
    (work / "caption_fb.txt").write_text(cap, encoding="utf-8")
    from PIL import Image
    with Image.open(card) as im:
        assert im.size == (1080, 1350) and im.format == "JPEG"
    assert card.stat().st_size < 10 * 1024 * 1024
    images.render_card(fb, images.drawn(s2["topic"]), cfg, data["date_utc"], work / "post_fallback.jpg", ai=True,
                       source=s2["source"])

    # Cloudflare (mocked): base64 JPEG → AI background, cover-cropped
    import base64
    import io

    class FakeCF:
        def post(self, url, headers=None, json=None, timeout=None):
            assert "flux-1-schnell" in url and headers["Authorization"] == "Bearer T" and "No text" in json["prompt"]
            buf = io.BytesIO()
            Image.new("RGB", (1024, 1024), (30, 60, 90)).save(buf, "JPEG")
            return FakeResp(200, {"success": True, "result": {"image": base64.b64encode(buf.getvalue()).decode()}})
    os.environ["CF_ACCOUNT_ID"], os.environ["CF_API_TOKEN"] = "A", "T"
    images._http = FakeCF()
    try:
        bg, src = images.background("a vault", "gold", cfg, log=quiet)
        assert src == "ai" and bg.size == (1080, 1350)
    finally:
        images._http = __import__("requests")
        os.environ.pop("CF_ACCOUNT_ID")
        os.environ.pop("CF_API_TOKEN")
    print(f"OK news post: {card} · caption {work / 'caption_fb.txt'} · story {s1['source']}: {s1['title']}")


TARGET_TITLE = "Bitcoin to $150,000? Analysts weigh ETF inflows"


def test_news_post_rules(cfg):
    """CAP-7 on news posts: a rule-breaking Gemini post → the whole fallback post; a rule-breaking
    fallback stops the post (RuntimeError naming the rule); a clean post is untouched."""
    data = news_data()
    quiet = lambda m: None  # noqa: E731
    s1 = news_post.pick_story(data, [], [], cfg, now=NOW, log=quiet)
    saved = news_post.generate_json, script.generate_json
    try:
        script.generate_json = _news_llm(GOOD_POST)
        # clean Gemini post: published as before
        news_post.generate_json = _news_llm(GOOD_POST)
        post = news_post.write_post(cfg, data, s1, log=quiet)
        assert post["writer"] == "gemini" and not news_post.post_problems(post), post
        # Gemini caption with a price target → the deterministic post, rule logged
        logs = []
        news_post.generate_json = _news_llm(dict(GOOD_POST, caption=GOOD_POST["caption"]
                                                 + " Bitcoin could hit a record next."))
        fb = news_post.write_post(cfg, data, s1, log=logs.append)
        assert fb["writer"] == "fallback" and "could hit" not in fb["caption"], fb
        assert fb["headline"] == news_post.fallback_post(s1, data)["headline"] and not news_post.post_problems(fb)
        assert any("narration rules" in m and "price target" in m for m in logs), logs
        assert any("price target" in p for p in fb["fact_check"]["narration"]), fb["fact_check"]
        # first person / buy call in the Gemini card → fallback too
        news_post.generate_json = _news_llm(dict(GOOD_POST, subline="I'm buying the dip on this one"))
        assert news_post.write_post(cfg, data, s1, log=quiet)["writer"] == "fallback"
        # card lines are capitals: the headline is also checked sentence-cased
        assert any("price target" in p for p in news_post.post_problems({"headline": ["BTC TO $150K", "SOON"]}))
        assert any("10x" in p for p in news_post.post_problems({"headline": ["THIS COIN", "COULD 10X"]}))
        for card in ({"headline": ["FED HOLDS", "BTC TO $150K"]}, {"headline": ["ETF INFLOWS:", "BTC TO $150K"]}):
            assert any("price target" in p for p in news_post.post_problems(card)), card  # any line
        for card in ({"headline": ["FED CUT", "IN MARCH"]}, {"headline": ["RATE CUT", "IN MAY"]},
                     {"kicker": "MY PICK", "headline": ["FED", "HOLDS"]}):
            assert news_post.post_problems(card), card
        assert not news_post.post_problems({"kicker": "FED", "headline": ["FED MAY CUT", "RATES AGAIN"]})
        dup = news_post.post_problems(news_post.fallback_post(dict(s1, title="Ether ETFs See Inflows Ahead of "
                                                                   "December Fed Meeting"), data))
        assert len(dup) == 1 and "december" in dup[0].lower(), dup  # one match reported once
        assert not news_post.post_problems({"kicker": "FED SPEECH", "headline": ["POWELL SIGNALS", "PATIENCE"]})
        # the fallback itself carries a price target → the post stops, rule named (both paths)
        bad = dict(s1, title=TARGET_TITLE, body="", summary="")
        for answer in (RuntimeError("All Gemini models failed"),
                       dict(GOOD_POST, caption=GOOD_POST["caption"] + " Ether could reach a record.")):
            news_post.generate_json = _news_llm(answer)
            try:
                news_post.write_post(cfg, data, bad, log=quiet)
                raise AssertionError("a rule-breaking fallback post must stop")
            except RuntimeError as e:
                assert "narration rules" in str(e) and "price target" in str(e), e
        # rule-breaking summary sentences are dropped from the fallback (the post still goes out)
        news_post.generate_json = _news_llm(RuntimeError("All Gemini models failed"))
        story = dict(s1, title="Bitcoin ETFs log record weekly inflows", summary="",
                     body="Analysts expect Bitcoin to rally to $200,000 by year end. Spot ETFs took in $2B "
                          "over the week, led by BlackRock.")
        ok = news_post.write_post(cfg, data, story, log=quiet)
        assert ok["writer"] == "fallback" and "200,000" not in ok["caption"] and "BlackRock" in ok["caption"], ok
        assert not news_post.post_problems(ok)
    finally:
        news_post.generate_json, script.generate_json = saved
    # picker: a rule-breaking title only as a last resort (never skip a post)
    pdata = news_data()
    pdata["news"] = [dict(pdata["news"][3], title=TARGET_TITLE, published=NOW.isoformat()), pdata["news"][3]]
    assert news_post.pick_story(pdata, [], [], cfg, now=NOW, log=quiet)["title"] == pdata["news"][1]["title"]
    pdata["news"] = pdata["news"][:1]
    assert news_post.pick_story(pdata, [], [], cfg, now=NOW, log=quiet)["title"] == TARGET_TITLE
    print("OK news post narration rules (fallback, stop, sanitized fallback, picker)")


def test_news_post_stops(cfg):
    """A news run whose only story breaks the narration rules even as the fallback post: exit 1,
    nothing posted, nothing in history."""
    import main as app
    from autopilot import sources

    class FixedNow(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW.astimezone(tz) if tz else NOW.replace(tzinfo=None)

    tmp = Path(tempfile.mkdtemp())
    shutil.copy(ROOT / "config.yaml", tmp / "config.yaml")
    fake = FakeGraph()
    _fb_env(fake)
    data = news_data()
    data["news"] = [dict(data["news"][0], title=TARGET_TITLE, body="")]
    saved = (app.ROOT, app.datetime, sources.gather, news_post.generate_json, script.generate_json)
    app.ROOT, app.datetime = tmp, FixedNow
    sources.gather = lambda cfg, kind="market", log=print: data
    news_post.generate_json = script.generate_json = _news_llm(RuntimeError("All Gemini models failed"))
    try:
        assert app.main(["--session", "news_morning", "--scheduled"]) == 1
    finally:
        (app.ROOT, app.datetime, sources.gather, news_post.generate_json, script.generate_json) = saved
        for k in ("FB_PAGE_ID", "FB_PAGE_TOKEN"):
            os.environ.pop(k, None)
    assert fake.count(contains="/photos") == 0, fake.calls
    hist = tmp / "data" / "history.json"
    assert not hist.exists() or not json.loads(hist.read_text()).get("videos"), hist.read_text()
    shutil.rmtree(tmp, ignore_errors=True)
    print("OK news post stops when the fallback breaks the narration rules")


def test_news_post_crypto_only(cfg):
    """CAP-9: a news post is a crypto or crypto-regulation story, named in the headline or its lead
    (the body never counts); a set with no crypto story posts nothing (exit 1)."""
    import main as app
    from autopilot import sources
    quiet = lambda m: None  # noqa: E731

    def item(src, title, hours=2, summary="", body=""):
        return {"category": "news", "source": src, "title": title, "summary": summary, "body": body,
                "published": (NOW - timedelta(hours=hours)).isoformat(), "link": "https://example.com/c"}
    war = item("Reuters", "Missile strikes escalate Middle East conflict, oil jumps", 1,
               summary="Traders fled to safety as the conflict widened.")
    tariffs = item("Bloomberg", "US slaps new tariffs on Chinese chips, markets slide", 1)
    rates = item("CNBC", "Fed holds interest rates steady, Powell signals patience", 1)
    mention = item("AP", "Sanctions widen on Russian oil exports", 1,
                   body="Analysts said bitcoin could see flows as sanctioned buyers look for workarounds.")
    bare = item("FT", "ETF inflows hit record as exchange volumes rise", 1,
                summary="Equity funds took in money; the coin toss on rates continues.")
    headline = item("Cointelegraph", "Bitcoin liquidations top $500M", 4)
    lead = item("Reuters", "SEC sues exchange operator over unregistered offers", 3,
                summary="The regulator says Binance's US arm listed securities without registering.")
    other = item("CoinDesk", "Stablecoin supply climbs as traders park cash", 5)

    # the predicate: headline or lead names crypto; body-only, bare ETF / exchange / coin don't count
    assert news_post.is_crypto(headline) and news_post.is_crypto(lead) and news_post.is_crypto(other)
    for n in (war, tariffs, rates, mention, bare):
        assert not news_post.is_crypto(n), n["title"]
    for t in ("Spot bitcoin ETF sees outflows", "Dogecoin jumps", "Tether mints USDT", "Ether ETFs approved",
              "Digital assets bill passes Senate", "Coinbase wins appeal", "XRP rallies"):
        assert news_post.is_crypto({"title": t}), t
    for t in ("Meme coin mania returns", "Stable-coin bill advances"):
        assert news_post.is_crypto({"title": t}), t
    for t in ("Exchange rates steady", "Coin collectors gather", "The ripple effects of tariffs",
              "Tariff shock sends a ripple through Asian markets", "A ripple-effect on bonds"):
        assert not news_post.is_crypto({"title": t}), t
    # Google News: the summary is the title + publisher; a crypto publisher's name doesn't count
    gn = item("Cryptopolitan", "Oil jumps as Iran strikes widen conflict", 1,
              summary="Oil jumps as Iran strikes widen conflict Cryptopolitan")
    assert not news_post.is_crypto(gn) and news_post.is_crypto(dict(gn, title="Bitcoin dips as oil jumps"))

    # a crypto headline among bigger-weighted rates / war / tariff stories is the one picked
    data = news_data()
    data["news"] = [war, tariffs, rates, mention, bare, headline]
    logs = []
    s = news_post.pick_story(data, [], [], cfg, now=NOW, log=logs.append)
    assert s["title"] == headline["title"] and news_post.is_crypto(s), s
    assert any("5 non-crypto skipped" in m for m in logs), logs
    # regulation named only in the lead (summary) can be picked
    data["news"] = [war, rates, lead]
    s = news_post.pick_story(data, [], [], cfg, now=NOW, log=quiet)
    assert s["title"] == lead["title"], s
    # every crypto story already used → "best available", still crypto
    data["news"] = [war, tariffs, headline, other]
    s = news_post.pick_story(data, [headline["title"], other["title"]], [], cfg, now=NOW, log=quiet)
    assert s["tier"].startswith("best available") and news_post.is_crypto(s), s
    # any news set: a returned story is always crypto
    for mix in ([war, mention, other], [bare, lead, tariffs], [rates, headline]):
        data["news"] = mix
        assert news_post.is_crypto(news_post.pick_story(data, [], [], cfg, now=NOW, log=quiet))
    # geopolitics / rates only → no story (RuntimeError naming the skipped count)
    data["news"] = [war, tariffs, rates, mention, bare]
    try:
        news_post.pick_story(data, [], [], cfg, now=NOW, log=quiet)
        raise AssertionError("a news set with no crypto story must not pick one")
    except RuntimeError as e:
        assert "No crypto story" in str(e) and "5 non-crypto" in str(e), e

    # the edition: "Post failed", exit 1, nothing posted, nothing in history
    class FixedNow(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW.astimezone(tz) if tz else NOW.replace(tzinfo=None)

    tmp = Path(tempfile.mkdtemp())
    shutil.copy(ROOT / "config.yaml", tmp / "config.yaml")
    fake = FakeGraph()
    _fb_env(fake)
    logged = []
    saved = (app.ROOT, app.datetime, app.log, sources.gather)
    app.ROOT, app.datetime, app.log = tmp, FixedNow, logged.append
    sources.gather = lambda cfg, kind="market", log=print: data
    try:
        assert app.main(["--session", "news_morning", "--scheduled"]) == 1
    finally:
        (app.ROOT, app.datetime, app.log, sources.gather) = saved
        for k in ("FB_PAGE_ID", "FB_PAGE_TOKEN"):
            os.environ.pop(k, None)
    assert any(m.startswith("Post failed") and "No crypto story" in m for m in logged), logged
    assert fake.count(contains="/photos") == 0, fake.calls
    hist = tmp / "data" / "history.json"
    assert not hist.exists() or not json.loads(hist.read_text()).get("videos"), hist.read_text()
    shutil.rmtree(tmp, ignore_errors=True)
    print("OK news post crypto-only (headline/lead rule, filtered picker, no-crypto set → no post)")


def test_news_edition(cfg):
    """A timed news_* run: YouTube is never called, exactly one photo is posted, the guard stops a repeat."""
    import main as app
    from autopilot import sources, youtube

    class FixedNow(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW.astimezone(tz) if tz else NOW.replace(tzinfo=None)

    tmp = Path(tempfile.mkdtemp())
    shutil.copy(ROOT / "config.yaml", tmp / "config.yaml")
    fake = FakeGraph()
    _fb_env(fake)
    yt_calls = []
    saved = (app.ROOT, app.datetime, sources.gather, youtube.upload, youtube.set_thumbnail,
             news_post.generate_json, script.generate_json)
    app.ROOT, app.datetime = tmp, FixedNow
    sources.gather = lambda cfg, kind="market", log=print: news_data()
    youtube.upload = youtube.set_thumbnail = lambda *a, **k: yt_calls.append(a)
    news_post.generate_json = script.generate_json = _news_llm(GOOD_POST)
    try:
        assert app.main(["--session", "news_morning", "--scheduled"]) == 0
        assert app.main(["--session", "news_morning", "--scheduled"]) == 0  # already posted today → skip
        assert app.main(["--session", "news_morning", "--platforms", "youtube"]) == 0  # not a YouTube edition
    finally:
        (app.ROOT, app.datetime, sources.gather, youtube.upload, youtube.set_thumbnail,
         news_post.generate_json, script.generate_json) = saved
        for k in ("FB_PAGE_ID", "FB_PAGE_TOKEN"):
            os.environ.pop(k, None)
    assert not yt_calls and fake.count(contains="/photos") == 1, (yt_calls, fake.calls)
    hist = json.loads((tmp / "data" / "history.json").read_text())["videos"]
    assert len(hist) == 1 and hist[0]["fb_post_id"] == "PAGE_P1" and hist[0]["kind"] == "post", hist
    assert hist[0]["headlines"] == [news_data()["news"][0]["title"]] and hist[0]["platforms"] == ["facebook"]
    entry = list((tmp / "output").glob("*/history_entry.json"))
    assert len(entry) == 1 and list((tmp / "output").glob("*/post.jpg")) and list((tmp / "output").glob("*/caption_fb.txt"))
    shutil.rmtree(tmp, ignore_errors=True)
    print("OK news edition (Facebook only, one photo, guard)")


def test_video_editions(cfg, video, cover):
    """Video editions (a standalone Short) through main(): both platforms → one entry; a later timed run publishes
    only the platform that's missing (with history minus today's slot); --platforms facebook → FB only."""
    import main as app
    from autopilot import youtube

    class FixedNow(datetime):
        @classmethod
        def now(cls, tz=None):
            t = datetime(2026, 10, 8, 13, 5, tzinfo=timezone.utc)  # 5 min after Short A's start
            return t.astimezone(tz) if tz else t.replace(tzinfo=None)

    tmp = Path(tempfile.mkdtemp())
    c = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    c["shorts"]["enabled"] = True
    (tmp / "config.yaml").write_text(yaml.safe_dump(c, sort_keys=False), encoding="utf-8")
    yt_calls, seen_history = [], []

    def fake_make_short(cfg_, history, session_key, date):
        seen_history.append(history)
        wd = tmp / "output" / f"run{len(seen_history)}"
        wd.mkdir(parents=True, exist_ok=True)
        entry = {"date": "2026-10-08T13:06:00+00:00", "brief_date": "2026-10-08", "session": session_key,
                 "kind": "short", "title": "t", "video_id": None, "workdir": str(wd.relative_to(tmp))}
        return {"entry": entry, "video": video, "thumbnail": cover, "meta": {"title": "t"}, "fb_caption": "c",
                "material": {}}

    def fake_upload(*a, **k):
        yt_calls.append(a)
        if fail_yt:
            raise RuntimeError("YouTube upload limit reached for today")
        return f"Y{len(yt_calls)}"

    saved = (app.ROOT, app.datetime, app.make_short, youtube.upload, youtube.set_thumbnail)
    app.ROOT, app.datetime, app.make_short = tmp, FixedNow, fake_make_short
    youtube.upload, youtube.set_thumbnail = fake_upload, (lambda *a, **k: True)
    try:
        # 1) timed Short A run, both platforms OK → one entry carrying both ids
        fail_yt = False
        fake = FakeGraph()
        _fb_env(fake)
        assert app.main(["--session", "short_a", "--scheduled"]) == 0
        hist = json.loads((tmp / "data" / "history.json").read_text())["videos"]
        assert len(hist) == 1 and hist[0]["video_id"] == "Y1" and hist[0]["fb_reel_id"] == "R1", hist
        assert hist[0]["platforms"] == ["youtube", "facebook"] and fake.count("finish") == 1

        # 2) a new day: YouTube published, Facebook failed (Reel processing error) → exit 1, YT logged
        (tmp / "data" / "history.json").write_text(json.dumps({"videos": []}))
        bad = FakeGraph()
        bad_status = bad.request

        def failing(method, url, timeout=None, **kw):
            if method == "GET" and url.endswith("/R1"):
                bad.calls.append((method, url, None))
                return FakeResp(200, {"status": {"video_status": "error",
                                                 "processing_phase": {"status": "error",
                                                                      "errors": [{"message": "bad codec"}]}}})
            return bad_status(method, url, timeout=timeout, **kw)
        bad.request = failing
        _fb_env(bad)
        assert app.main(["--session", "short_a", "--scheduled"]) == 1
        hist = json.loads((tmp / "data" / "history.json").read_text())["videos"]
        assert len(hist) == 1 and hist[0]["video_id"] and not hist[0].get("fb_reel_id"), hist
        assert bad.count("finish") == 1  # the failed Reel was not finished twice

        # 3) the backup timed run: re-makes the edition, Facebook only, history without today's slot
        n_yt = len(yt_calls)
        fake = FakeGraph()
        _fb_env(fake)
        assert app.main(["--session", "short_a", "--scheduled"]) == 0
        assert len(yt_calls) == n_yt and fake.count("finish") == 1, (yt_calls, fake.calls)
        assert not seen_history[-1].published_on("2026-10-08", "short_a", "youtube")  # same history as run 1
        hist = json.loads((tmp / "data" / "history.json").read_text())["videos"]
        assert len(hist) == 2 and hist[1]["fb_reel_id"] == "R1" and not hist[1].get("video_id"), hist
        # 4) a third timed run: everything is out → nothing is made
        made = len(seen_history)
        assert app.main(["--session", "short_a", "--scheduled"]) == 0 and len(seen_history) == made

        # 5) manual run --platforms facebook on a video edition → Facebook only
        fake = FakeGraph()
        _fb_env(fake)
        n_yt = len(yt_calls)
        assert app.main(["--session", "short_b", "--platforms", "facebook"]) == 0
        assert len(yt_calls) == n_yt and fake.count("finish") == 1
    finally:
        (app.ROOT, app.datetime, app.make_short, youtube.upload, youtube.set_thumbnail) = saved
        for k in ("FB_PAGE_ID", "FB_PAGE_TOKEN"):
            os.environ.pop(k, None)

    # Cloudflare error → no AI image; falls back to the drawn background (no library in this repo)
    class BrokenCF:
        def post(self, url, headers=None, json=None, timeout=None):
            return FakeResp(500, {"success": False, "errors": [{"message": "capacity"}]})
    os.environ["CF_ACCOUNT_ID"], os.environ["CF_API_TOKEN"] = "A", "T"
    images._http = BrokenCF()
    try:
        bg, src = images.background("a vault", "gold", cfg, log=lambda m: None)
        assert src in ("drawn", "library") and bg.size == (1080, 1350), src
    finally:
        images._http = __import__("requests")
        os.environ.pop("CF_ACCOUNT_ID")
        os.environ.pop("CF_API_TOKEN")
    shutil.rmtree(tmp, ignore_errors=True)
    print("OK video editions (both platforms, FB-only re-make, --platforms, Reel error, CF fallback)")


def _contact(paths: list[Path], cell: tuple[int, int], cols: int, out: Path) -> Path:
    from PIL import Image
    rows = -(-len(paths) // cols)
    w, h, pad = cell[0], cell[1], 8
    sheet = Image.new("RGB", (cols * w + (cols + 1) * pad, rows * h + (rows + 1) * pad), (40, 40, 40))
    for k, p in enumerate(paths):
        with Image.open(p) as im:
            sheet.paste(im.convert("RGB").resize((w, h), Image.LANCZOS),
                        (pad + (k % cols) * (w + pad), pad + (k // cols) * (h + pad)))
    sheet.save(out)
    return out


def test_lesson_slides(cfg):
    """Lesson graphics (entries 3 + 4): every scene type in 16:9 and 9:16 from the fixture detectors' real
    examples, every primitive, portrait zoom, flat-series line, schematic label, the mtf (top-down) panels,
    unknown type, thumbnail; writes contact sheets (chart and mtf scenes) for the owner to approve the look."""
    from types import SimpleNamespace
    from PIL import Image, ImageDraw
    from autopilot import detectors, lesson_data, lesson_slides as ls, lessons  # noqa: F401  (detectors registers)
    sample = ROOT / "tests" / "lessons"
    cur, glo = lessons.load_curriculum(sample / "curriculum.yaml"), lessons.load_glossary(sample / "glossary.yaml")
    load = lambda n: json.loads((sample / "candles" / f"{n}.json").read_text(encoding="utf-8"))  # noqa: E731
    down, up = load("downtrend_bos_choch"), load("uptrend")
    flat = [dict(c, o=c["c"], h=c["c"], l=c["c"]) for c in down]  # no bodies or wicks: o=h=l=c, drawn as a line
    examples = lessons.DETECTORS["bos_choch"].find({"BTC/USD": {"1H": down}, "ETH/USD": {"1D": flat}})
    assert [e["asset"] for e in examples] == ["BTC/USD", "ETH/USD"], [e["asset"] for e in examples]
    ex1, ex2 = examples
    # every primitive: add a trendline through the first two LH swings and a zone between the BOS and
    # CHoCH levels, all values taken from the example itself
    f = ex1["facts"]
    lh = [s for s in f["swings"] if s["kind"] == "LH"]
    ex1["primitives"] += [
        {"type": "trendline", "t1": lh[0]["t"], "p1": lh[0]["price"], "t2": lh[1]["t"], "p2": lh[1]["price"]},
        {"type": "zone", "t1": f["bos"]["swing_t"], "t2": f["choch"]["t"], "low": min(f["bos"]["level"], f["choch"]["level"]),
         "high": max(f["bos"]["level"], f["choch"]["level"]), "label": "BOS → CHoCH"}]
    assert lessons.validate_example(ex1) == [], lessons.validate_example(ex1)
    assert {p["type"] for p in ex1["primitives"]} == set(lessons.PRIMITIVES)
    schematic = lessons.DETECTORS["swings"].find({"BTC/USD": {"1H": up}})[0]  # example-shaped dict
    # top-down (mtf): the 1H fixture with nested structure and its 4H aggregation
    h1 = load("top_down_1h")
    rows = {int(datetime.fromisoformat(c["t"]).timestamp()): (c["o"], c["h"], c["l"], c["c"]) for c in h1}
    h4 = lesson_data._candles(lesson_data._aggregate(rows, 4 * 3600))
    mtf = lessons.DETECTORS["top_down"].find({"BTC/USD": {"4H": h4, "1H": h1}})
    assert len(mtf) == 1 and lessons.validate_example(mtf[0]) == [], mtf
    mtf_ex = mtf[0]
    mtf_scene = lessons.scene_plan(cur[2], [mtf_ex])[2]
    assert mtf_scene["id"] == "example_1" and mtf_scene["visual"]["type"] == "mtf"
    plan = lessons.scene_plan(cur[1], examples)
    plan.insert(2, {"id": "schematic", "visual": {"type": "schematic", "example": schematic}})
    plan.insert(5, dict(mtf_scene, id="mtf"))
    types = [s["visual"]["type"] for s in plan]
    assert types == ["chart", "concept", "schematic", "chart", "chart", "mtf", "misreads", "outro"], types
    assert plan[0]["visual"]["still"] and plan[0]["visual"]["heading"] == cur[1]["title"]  # hook: marked example 1

    work = ROOT / "output" / "test_lessons"
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    bg = (14, 15, 18)
    sheets = {}
    for layout, cell, cols in ((ls.LANDSCAPE, (640, 360), 3), (ls.PORTRAIT, (360, 640), 4)):
        pics = ls.render_lesson_slides(cfg, cur[1], plan, glo, layout, work / layout.name)
        assert [p["id"] for p in pics] == [s["id"] for s in plan]
        for s, p in zip(plan, pics):  # example scenes add the step reveal's base + layers; the hook never does
            stepped = s["visual"]["type"] in ("chart", "mtf") and s["visual"].get("steps") and not s["visual"].get("still")
            assert set(p) == {"image", "reveal", "id"} | ({"base", "steps"} if stepped else set()), (s["id"], set(p))
        assert [p["id"] for p in pics if "steps" in p] == ["example_1", "example_2", "mtf"], [p["id"] for p in pics]
        for s, p in zip(plan, pics):
            with Image.open(p["image"]) as im:
                assert im.size == (layout.w, layout.h), (layout.name, s["id"], im.size)
                band = im.convert("RGB").crop((0, layout.caption_band[0], layout.w, layout.caption_band[1]))
                assert band.getextrema() == tuple((c, c) for c in bg), (layout.name, s["id"], "drew into captions")
            if s["visual"].get("still"):
                assert p["reveal"] is None, (layout.name, s["id"])  # the hook is fully drawn from frame 0
            elif s["visual"]["type"] in ("chart", "schematic", "mtf"):
                x, y, w, h = p["reveal"]
                assert w >= 0.85 * layout.w and x >= 0 and x + w <= layout.w, (layout.name, p["reveal"])
                assert y >= layout.rule_y and y + h <= layout.caption_band[0], (layout.name, p["reveal"])
            else:
                assert p["reveal"] is None
        # deterministic: the same inputs give the same bytes
        again = ls.render_lesson_slides(cfg, cur[1], plan, glo, layout, work / f"{layout.name}_again")
        assert all(Path(a["image"]).read_bytes() == Path(b["image"]).read_bytes() for a, b in zip(pics, again))
        shutil.rmtree(work / f"{layout.name}_again")
        sheets[layout.name] = _contact([p["image"] for p in pics], cell, cols, work / f"contact_{layout.name}.png")

        # every primitive drawn, in both shapes (portrait zoomed as on the slides)
        zoom = layout is ls.PORTRAIT
        canvas = Image.new("RGB", (layout.w, layout.h), bg)
        info = ls.draw_chart(canvas, layout.content_box, ex1, layout, zoom=zoom)
        assert set(info["drawn"]) == set(lessons.PRIMITIVES), (layout.name, info["drawn"])
        assert info["label"].startswith(lessons.example_label(ex1)) and "Coinbase" in info["label"]
        assert not info["line"]
        # primitives= limits what is drawn (step reveal)
        info = ls.draw_chart(Image.new("RGB", (layout.w, layout.h), bg), layout.content_box, ex1, layout, zoom=zoom,
                             primitives=[p for p in ex1["primitives"] if p["type"] == "swing"])
        assert set(info["drawn"]) == {"swing"}, info["drawn"]
        # all-flat series (o = h = l = c): a line, not candles
        info = ls.draw_chart(Image.new("RGB", (layout.w, layout.h), bg), layout.content_box, ex2, layout, zoom=zoom)
        assert info["line"] and "ETH/USD" in info["label"] and "Coinbase" in info["label"], info["label"]
        # schematic: labelled "Schematic", never "Historical example"
        info = ls.draw_chart(Image.new("RGB", (layout.w, layout.h), bg), layout.content_box, schematic, layout,
                             zoom=zoom, label=ls.SCHEMATIC)
        assert info["label"].startswith("Schematic") and "Historical example" not in info["label"], info["label"]

        # mtf: two panels, side by side in 16:9 (higher left) / stacked in 9:16 (higher on top), each with
        # its timeframe title and strip, together filling the content width (no crop, no letterbox)
        x0, y0, x1, y1 = layout.content_box
        hi, lo = ls.draw_mtf(Image.new("RGB", (layout.w, layout.h), bg), layout.content_box, mtf_ex, layout)
        (ax, ay, aw, ah), (bx, by, bw, bh) = hi["panel"], lo["panel"]
        if layout is ls.LANDSCAPE:
            assert ay == by and ah == bh and ax == x0 and bx + bw == x1 and bx - (ax + aw) == ls.MTF_GUTTER, (hi, lo)
            assert aw == bw and aw >= 0.45 * (x1 - x0)
        else:
            assert ax == bx == x0 and aw == bw == x1 - x0 and ay == y0 and by + bh == y1, (hi, lo)
            assert by - (ay + ah) == ls.MTF_GUTTER and ah == bh
        assert y1 <= layout.caption_band[0]
        for info, tf, role in ((hi, "4H", "Higher timeframe"), (lo, "1H", "Lower timeframe")):
            assert info["timeframe"] == tf and info["title"] == f"{tf} · {role}", info
            assert info["label"].startswith("Historical example · BTC/USD · ") and f"· {tf}" in info["label"]
            assert "Coinbase" in info["label"] and not info["line"]
            px, py, pw, ph = info["panel"]
            cx, cy, cw, chh = info["box"]
            assert px <= cx and cx + cw <= px + pw and py < cy and cy + chh <= py + ph, info
            assert info["x_range"][1] - info["x_range"][0] >= 10  # readable: a real stretch of candles
        assert "zone" in hi["drawn"] and "swing" in hi["drawn"] and set(lo["drawn"]) == {"swing"}, (hi, lo)
        # headroom: every swing's marker + kind text fits inside its plot (above a high, below a low)
        fs = layout.min_text
        room = ls.SWING_ROOM + max(10, round(fs * 0.42)) + round(fs * 1.2)
        for info, prims in ((hi, mtf_ex["primitives"]), (lo, mtf_ex["lower"]["primitives"])):
            ylo, yhi = info["y_range"]
            plot_h = info["box"][3] - round(fs * 1.3)  # chart box minus the time row
            for sw in prims:
                gap = (yhi - sw["price"] if sw["kind"] in ls.SWING_HIGH else sw["price"] - ylo) / (yhi - ylo) * plot_h
                assert gap >= room - 1, (layout.name, info["timeframe"], sw, gap, room)
        # draw-in box: the slide's reveal never covers a panel title or label strip
        heading = ls._heading(SimpleNamespace(accent=(255, 212, 0)), glo["top_down_analysis"]["term"])
        canvas = Image.new("RGB", (layout.w, layout.h), bg)
        hy = ls._flow(ImageDraw.Draw(canvas), [heading], layout.content_box, layout)
        infos = ls.draw_mtf(canvas, (x0, hy, x1, y1), mtf_ex, layout, label=mtf_scene["visual"]["label"])
        rev = next(p["reveal"] for p in pics if p["id"] == "mtf")
        assert rev == ls.mtf_reveal(infos, layout), (rev, ls.mtf_reveal(infos, layout))

        def overlaps(a, b):
            return a[0] < b[0] + b[2] and b[0] < a[0] + a[2] and a[1] < b[1] + b[3] and b[1] < a[1] + a[3]
        for info in infos:
            for lab in (info["title_box"], info["strip_box"]):
                assert lab[3] > 0 and not overlaps(rev, lab), (layout.name, rev, lab)
        if layout is ls.PORTRAIT:
            assert rev == infos[1]["box"]  # only the lower chart draws in; the higher one shows at once
        if layout is ls.PORTRAIT:  # zoomed to each panel's region, as chart scenes are
            assert hi["x_range"] != (0, len(mtf_ex["candles"]) - 1) or lo["x_range"] != (0, len(mtf_ex["lower"]["candles"]) - 1)
        # the higher panel's zone is the lower window, labelled with the lower timeframe
        higher, lower = ls.mtf_panels(mtf_ex)
        r = mtf_ex["lower"]["region"]
        # the zone ends with the 4H candle holding the window's last 1H candle (not inside the next one)
        t2 = max(c["t"] for c in mtf_ex["candles"] if c["t"] <= r["end"])
        assert t2 < r["end"] < (datetime.fromisoformat(t2) + timedelta(hours=4)).isoformat()
        assert higher["primitives"][-1] == {"type": "zone", "t1": r["start"], "t2": t2, "low": r["low"],
                                            "high": r["high"], "label": "1H"}
        assert "lower" not in higher and higher["primitives"][:-1] == mtf_ex["primitives"]
        assert lower["date"] == r["end"][:10] and lower["candles"] == mtf_ex["lower"]["candles"]

    # 9:16 zoom: x/y limits from the region (± 3 candles, ± 8% of its range); 16:9 shows every candle
    zx = json.loads(json.dumps(ex1))
    c = zx["candles"]
    part = c[30:51]
    zx["region"] = {"start": part[0]["t"], "end": part[-1]["t"], "low": min(b["l"] for b in part),
                    "high": max(b["h"] for b in part)}
    info = ls.draw_chart(Image.new("RGB", (1080, 1920), bg), ls.PORTRAIT.content_box, zx, ls.PORTRAIT, zoom=True)
    span = zx["region"]["high"] - zx["region"]["low"]
    assert info["x_range"] == (27, 53), info["x_range"]
    assert all(abs(a - b) < 1e-9 for a, b in zip(info["y_range"], (zx["region"]["low"] - 0.08 * span,
                                                                  zx["region"]["high"] + 0.08 * span))), info["y_range"]
    info = ls.draw_chart(Image.new("RGB", (1920, 1080), bg), ls.LANDSCAPE.content_box, zx, ls.LANDSCAPE)
    assert info["x_range"] == (0, len(c) - 1), info["x_range"]
    assert info["y_range"][0] <= min(b["l"] for b in c) and info["y_range"][1] >= max(b["h"] for b in c)

    # unknown visual type → ValueError naming it (sessions / pair / walkthrough are not built)
    for t in ("sessions", "pair", "walkthrough"):
        try:
            ls.render_lesson_slides(cfg, cur[1], [{"id": "x", "visual": {"type": t}}], glo, ls.LANDSCAPE, work / "bad")
            raise AssertionError("an unknown visual type must fail")
        except ValueError as e:
            assert t in str(e), e
    # an mtf scene needs an example with its lower panel
    no_lower = {k: v for k, v in mtf_ex.items() if k != "lower"}
    for vis in ({"type": "mtf"}, {"type": "mtf", "example": no_lower}):
        try:
            ls.render_lesson_slides(cfg, cur[2], [{"id": "x", "visual": vis}], glo, ls.LANDSCAPE, work / "bad")
            raise AssertionError("an mtf scene without its panels must fail")
        except ValueError as e:
            assert "mtf" in str(e), e
    # a malformed `lower` panel: ValueError naming the missing field (never a KeyError)
    for field in ("region", "candles", "timeframe"):
        broken = dict(mtf_ex, lower={k: v for k, v in mtf_ex["lower"].items() if k != field})
        try:
            ls.mtf_panels(broken)
            raise AssertionError(f"an mtf lower panel without {field} must fail")
        except ValueError as e:
            assert field in str(e), e
    try:
        ls.mtf_panels(dict(mtf_ex, lower=dict(mtf_ex["lower"], region={"start": mtf_ex["lower"]["region"]["start"]})))
        raise AssertionError("an mtf lower region without its end must fail")
    except ValueError as e:
        assert "region" in str(e), e
    shutil.rmtree(work / "bad", ignore_errors=True)
    # recap: the "Next:" title and the ICT non-affiliation line are drawn when set (each changes the slide;
    # _flow never drops or cuts them, it raises instead), and the captions stay clear
    recap = {"type": "outro", "next": cur[0]["title"], "disclaimer": True, "non_affiliation": True}
    variants = {"full": recap, "no_next": dict(recap, next=None), "no_ict": dict(recap, non_affiliation=False)}
    for layout in (ls.LANDSCAPE, ls.PORTRAIT):
        got = {}
        for name, v in variants.items():
            p = ls.render_lesson_slides(cfg, dict(cur[1], track=4), [{"id": "recap", "visual": v}], glo, layout,
                                        work / "recap" / name)[0]
            with Image.open(p["image"]) as im:
                band = im.convert("RGB").crop((0, layout.caption_band[0], layout.w, layout.caption_band[1]))
                assert band.getextrema() == tuple((x, x) for x in bg), (layout.name, name)
                got[name] = im.convert("RGB").tobytes()
        assert got["full"] != got["no_next"], (layout.name, "Next: line not drawn")
        assert got["full"] != got["no_ict"], (layout.name, "non-affiliation line not drawn")
    shutil.rmtree(work / "recap")
    # approved key points are never cut: too many to fit at the minimum size → ValueError naming the entry
    long = dict(cur[1], key_points=[cur[1]["key_points"][0] + " " + cur[1]["key_points"][1]] * 14)
    for vis in ({"type": "misreads"}, recap):
        try:
            ls.render_lesson_slides(cfg, long, [{"id": "x", "visual": vis}], glo, ls.LANDSCAPE, work / "long")
            raise AssertionError("key points that don't fit must fail")
        except ValueError as e:
            assert cur[1]["id"] in str(e), e
    shutil.rmtree(work / "long", ignore_errors=True)
    # price axis: 2.5-steps add a decimal only below 10 (no "60,250.0")
    vals, dec = ls._ticks(60000, 61000)
    assert [ls._fmt_tick(v, dec) for v in vals][:2] == ["60,000", "60,250"], (vals, dec)
    vals, dec = ls._ticks(4100, 4200)
    assert [ls._fmt_tick(v, dec) for v in vals][:2] == ["4,100", "4,125"], (vals, dec)
    vals, dec = ls._ticks(1.0, 2.0)
    assert ls._fmt_tick(vals[1], dec) == "1.25", (vals, dec)

    thumb = ls.render_lesson_thumbnail(cfg, cur[1], ex1, work / "thumbnail.jpg")
    with Image.open(thumb) as im:
        assert im.size == (1280, 720) and im.format == "JPEG", (im.size, im.format)
    print(f"OK lesson slides: {sheets['16x9']} · {sheets['9x16']} · {thumb}")

def test_step_reveal(cfg):
    """Step-by-step annotation reveal: the plan's steps cover every primitive once, in order (chart and mtf);
    sentence starts (exact and mismatched word lists); step sentences and layer timings for the I/O matrix
    (named, unnamed, one sentence, off-screen, hook / non-chart); base + every layer == the full slide in
    both shapes, and the layers come in the plan's step order."""
    import numpy as np  # noqa: F401
    from PIL import Image
    from autopilot import detectors, lesson_data, lesson_script, lesson_slides as ls, lessons, reveal  # noqa: F401
    entry, glossary, plan, examples = lesson_script.sample_episode()
    sample = ROOT / "tests" / "lessons"
    cur = lessons.load_curriculum(sample / "curriculum.yaml")
    h1 = json.loads((sample / "candles" / "top_down_1h.json").read_text(encoding="utf-8"))
    rows = {int(datetime.fromisoformat(c["t"]).timestamp()): (c["o"], c["h"], c["l"], c["c"]) for c in h1}
    h4 = lesson_data._candles(lesson_data._aggregate(rows, 4 * 3600))
    mtf_ex = lessons.DETECTORS["top_down"].find({"BTC/USD": {"4H": h4, "1H": h1}})[0]

    # steps: every primitive exactly once, groups in first-appearance order, list order inside a group
    for ex in examples:
        steps = lessons.reveal_steps(ex, "chart")
        items = [tuple(i) for s in steps for i in s["items"]]
        assert sorted(items) == [(0, i) for i in range(len(ex["primitives"]))] and len(set(items)) == len(items)
        firsts = [s["items"][0][1] for s in steps]
        assert firsts == sorted(firsts) and all(s["items"] == sorted(s["items"]) for s in steps), steps
        assert [s["key"] for s in steps] == ["swings", "BOS", "CHoCH"], [s["key"] for s in steps]
        bos = next(s for s in steps if s["key"] == "BOS")  # BOS level + BOS label: one step
        assert {ex["primitives"][i]["type"] for _, i in bos["items"]} == {"level", "label"}
        assert "break of structure" in bos["names"] and bos["name"] == "BOS"
    steps = lessons.reveal_steps(mtf_ex, "mtf")
    n0, n1 = len(mtf_ex["primitives"]), len(mtf_ex["lower"]["primitives"])
    assert [s["key"] for s in steps] == ["higher swings", "window", "lower swings"], [s["key"] for s in steps]
    assert [tuple(i) for s in steps for i in s["items"]] == \
        [(0, i) for i in range(n0)] + [(0, n0)] + [(1, i) for i in range(n1)]
    assert ls.mtf_panels(mtf_ex)[0]["primitives"][n0]["type"] == "zone"  # index len(prims) = the window zone
    assert "lower timeframe" in steps[1]["names"] and "hourly" in steps[1]["names"], steps[1]
    odd = dict(examples[0], primitives=[{"type": "label", "t": examples[0]["candles"][3]["t"], "price": 1.0,
                                         "text": "3 touches"}, {"type": "trendline", "t1": "a", "p1": 1, "t2": "b", "p2": 2}])
    steps = lessons.reveal_steps(odd, "chart")
    assert [(s["key"], s["name"], s["names"]) for s in steps] == [("touches", "touches", ["touches"]),
                                                                  ("trendline", "the trendline", ["trendline", "trend line"])]
    for s in lessons.SPOKEN_STEPS.values():
        assert not any(ch.isdigit() for ch in s[0] + "".join(s[1])), s

    # aliases: case-insensitive, plural, hyphen / space, whole words only
    swings = lessons.reveal_steps(examples[0], "chart")[0]["names"]
    assert reveal.names_in("Two Higher Highs formed.", swings) and reveal.names_in("Mark the lower lows.", swings)
    eqh = lessons.SPOKEN_STEPS["eqh"][1]  # singular and plural both name the step
    assert reveal.names_in("An equal high sits here.", eqh) and reveal.names_in("Two equal highs.", eqh)
    assert not reveal.names_in("We'll wait for it.", swings) and not reveal.names_in("A shallow dip.", swings)
    assert reveal.names_in("Two breaks of structure.", ["break of structure"])
    assert reveal.names_in("Buy side liquidity rests above.", ["buy-side liquidity"])
    assert reveal.split_sentences('One. "Two!" Three? Four') == ["One.", '"Two!"', "Three?", "Four"]

    # sentence starts: by index when the word list matches the script's tokens
    text = "Here is the chart. See the higher highs here. Then a break of structure. Then a change of character."
    toks = text.split()
    exact = [(0.1 + 0.3 * j, 0.35 + 0.3 * j, w.strip(".")) for j, w in enumerate(toks)]
    assert reveal.sentence_starts(text, exact, 6.0) == [exact[0][0], exact[4][0], exact[9][0], exact[14][0]]
    # mismatched (edge-tts split "higher" into two words): nearest matching word, else proportional time
    split = exact[:6] + [(1.85, 1.9, "high"), (1.9, 2.0, "er")] + exact[7:]
    got = reveal.sentence_starts(text, split, 6.0)
    assert got[:2] == [exact[0][0], exact[4][0]] and got[2] == exact[9][0] and got[3] == exact[14][0], got
    junk = [(0.2 + 0.3 * j, 0.4 + 0.3 * j, "zz") for j in range(len(toks) + 2)]
    got = reveal.sentence_starts(text, junk, 6.0)  # the first sentence starts with the first spoken word
    assert got == [0.2, 6.0 * 4 / len(toks), 6.0 * 9 / len(toks), 6.0 * 14 / len(toks)], got
    assert reveal.sentence_starts("", [], 3.0) == []

    names = [s["names"] for s in lessons.reveal_steps(examples[0], "chart")]
    sents = reveal.split_sentences(text)
    # named steps: swings at sentence 1, BOS at 2, CHoCH at 3
    assert reveal.step_sentences(names, sents) == [1, 2, 3]
    # unnamed step: BOS never named → the sentence after the swings' sentence
    no_bos = ["Here is the chart.", "See the higher highs here.", "Then price closed lower.", "Later it rose.",
              "Then a change of character."]
    assert reveal.step_sentences(names, no_bos) == [1, 2, 4]
    # unnamed at the end: clamped to the last sentence; the first step unnamed → the first sentence
    assert reveal.step_sentences(names, ["Just one sentence here."]) == [0, 0, 0]
    assert reveal.step_sentences([["nothing"], ["nothing"]], ["A.", "B."]) == [0, 1]
    # steps named in one sentence share its start (searched from the previous step's sentence, inclusive)
    assert reveal.step_sentences(names, ["Intro.", "Higher highs, then a break of structure and a change of character."]) == [1, 1, 1]

    # timings: STAGGER apart, squeezed (≥ MIN_GAP) by a sooner next step, never backwards, all in before the end
    t = reveal.layer_times([1.0, 5.0], [3, 2], 10.0)
    assert t == [[1.0, 1.35, 1.7], [5.0, 5.35]], t
    t = reveal.layer_times([1.0, 2.0], [4, 1], 10.0)
    assert t == [[1.0, 1.25, 1.5, 1.75], [2.0]], t
    t = reveal.layer_times([1.0, 1.5], [4, 1], 10.0)  # can't fit before the next step: it moves later
    assert t == [[1.0, 1.25, 1.5, 1.75], [2.0]], t
    one = reveal.layer_times([0.2, 0.2, 0.2], [10, 2, 2], 6.0)  # one sentence: all from its start
    flat = [x for s in one for x in s]
    assert flat[0] == 0.2 and all(b - a >= reveal.MIN_GAP - 1e-9 for a, b in zip(flat, flat[1:])), flat
    assert flat[-1] + reveal.FADE < 6.0, flat
    late = [x for s in reveal.layer_times([5.0, 5.5], [6, 2], 6.0) for x in s]  # pulled in before the end
    assert late == sorted(late) and late[-1] + reveal.FADE < 6.0 and len(late) == 8, late
    tight = [x for s in reveal.layer_times([0.0], [20], 3.0) for x in s]  # too many: spread evenly
    assert len(tight) == 20 and tight == sorted(tight) and tight[0] >= 0 and tight[-1] + reveal.FADE < 3.0, tight
    # time_steps: one-sentence filler scene (like LESSON_FILLER) on a stepped slide; unstepped slides untouched
    slides = [{"image": "x", "id": "hook"},
              {"image": "y", "id": "example_1", "steps": [{"names": n, "layers": [{} for _ in range(c)]}
                                                          for n, c in zip(names, (10, 2, 2))]}]
    filler = " ".join(["word"] * 60)
    audio = [{"duration": 3.0, "words": []}, {"duration": 7.0, "words": [(0.4 + 0.1 * j, 0.5 + 0.1 * j, "word")
                                                                          for j in range(60)]}]
    logs = []
    reveal.time_steps(slides, [{"text": "Hook."}, {"text": filler}], audio, log=logs.append)
    ats = [ly["at"] for s in slides[1]["steps"] for ly in s["layers"]]
    assert len(logs) == 1 and logs[0].startswith("Step reveal example_1:") and "(fallback)" in logs[0], logs
    assert "steps" not in slides[0] and ats[0] == 0.4 and ats[-1] + reveal.FADE < 7.0, ats
    assert all(b - a >= reveal.MIN_GAP - 1e-9 for a, b in zip(ats, ats[1:])), ats
    # render: the layered path only when every layer is timed; a partly timed slide falls back to the full image
    from unittest import mock
    cmds = []
    with mock.patch.object(render, "run", lambda cmd, **k: cmds.append([str(c) for c in cmd])):
        for layers in ([{"image": "l1.png", "xy": (0, 0), "at": 0.5}, {"image": "l2.png", "xy": (2, 2)}],
                       [{"image": "l1.png", "xy": (0, 0), "at": 0.5}, {"image": "l2.png", "xy": (2, 2), "at": 1.0}]):
            render._segment({"image": "full.png", "base": "base.png", "reveal": (0, 0, 10, 10),
                             "steps": [{"names": [], "layers": layers}]}, 3.0, Path("seg.mp4"), 20, 20, 30)
    assert not any(c.endswith("base.png") for c in cmds[0]) and any(c.endswith("full.png") for c in cmds[0]), cmds[0]
    assert any(c.endswith("base.png") for c in cmds[1]) and sum(c.endswith((".png")) for c in cmds[1]) == 3, cmds[1]

    # rendered layers: base + every layer == the full slide (16:9 and 9:16, chart and mtf); layer k holds
    # step order's k-th mark (each step's composite == the slide drawn with the marks so far); hook unchanged
    mtf_plan = lessons.scene_plan(cur[2], [mtf_ex])
    work = ROOT / "output" / "test_step_reveal"
    shutil.rmtree(work, ignore_errors=True)

    def composite(p, upto=None):
        img = Image.open(p["base"]).convert("RGB")
        layers = [ly for s in p["steps"] for ly in s["layers"]]
        for ly in layers[:upto]:
            with Image.open(ly["image"]) as im:
                img.paste(im.convert("RGB"), tuple(ly["xy"]))
        return img

    for layout in (ls.LANDSCAPE, ls.PORTRAIT):
        for name, e, pl in (("chart", entry, plan), ("mtf", cur[2], mtf_plan)):
            pics = ls.render_lesson_slides(cfg, e, pl, glossary, layout, work / f"{name}_{layout.name}")
            assert "steps" not in pics[0] and "steps" not in pics[1]  # hook (still) and concept
            ctx = ls._Ctx(cfg, e, glossary, layout, ls._hex(cfg["video"].get("accent", "FFD400")),
                          cfg["channel"].get("display_name", "CryptoFX Daily").upper(), ls.footer_text(pl))
            for s, p in zip(pl, pics):
                if "steps" not in p:
                    continue
                with Image.open(p["image"]) as full:
                    assert composite(p).tobytes() == full.convert("RGB").tobytes(), (layout.name, name, s["id"])
                    assert Image.open(p["base"]).convert("RGB").tobytes() != full.convert("RGB").tobytes()
                assert [st["key"] for st in p["steps"]] == [st["key"] for st in s["visual"]["steps"]]
                for ly in (ly for st in p["steps"] for ly in st["layers"]):
                    assert ly["xy"][0] % 2 == 0 and ly["xy"][1] % 2 == 0, ly
                if layout is ls.LANDSCAPE:  # every mark on screen: one layer per primitive
                    assert [len(st["layers"]) for st in p["steps"]] == [len(st["items"]) for st in s["visual"]["steps"]]
                shown, n = [set(), set()], 0
                for st_plan, st in zip(s["visual"]["steps"], p["steps"]):
                    for panel, i in st_plan["items"]:
                        shown[panel].add(i)
                    n += len(st["layers"])
                    img, _ = ls.RENDERERS[s["visual"]["type"]](ctx, s["visual"], show=tuple(shown))
                    assert composite(p, n).tobytes() == img.convert("RGB").tobytes(), (layout.name, name, st["key"])
            # a still visual with steps (the hook) never gets layers
            hook = dict(pl[2], visual=dict(pl[2]["visual"], still=True))
            assert "steps" not in ls.render_lesson_slides(cfg, e, [hook], glossary, layout, work / "still")[0]

    # off-screen: the 9:16 zoom hides marks outside the region → no layer for them, the rest unaffected
    zx = json.loads(json.dumps(examples[0]))
    part = zx["candles"][30:51]
    zx["region"] = {"start": part[0]["t"], "end": part[-1]["t"], "low": min(b["l"] for b in part),
                    "high": max(b["h"] for b in part)}
    zplan = lessons.scene_plan(entry, [zx])
    pics = ls.render_lesson_slides(cfg, entry, zplan, glossary, ls.PORTRAIT, work / "zoom")
    p = pics[2]
    info = ls.draw_chart(Image.new("RGB", (1080, 1920)), ls.PORTRAIT.content_box, zx, ls.PORTRAIT, zoom=True)
    got = sum(len(st["layers"]) for st in p["steps"])
    assert got == len(info["drawn"]) < len(zx["primitives"]), (got, info["drawn"], len(zx["primitives"]))
    with Image.open(p["image"]) as full:
        assert composite(p).tobytes() == full.convert("RGB").tobytes()
    shutil.rmtree(work, ignore_errors=True)
    print("OK step reveal: steps cover every primitive (chart, mtf), aliases, sentence starts, matrix timings, "
          "base + layers == slide in both shapes, off-screen marks, hook unchanged")


LESSON_FILLER = ("A swing point marks where price turned and the next close tells us whether "
                 "the structure held or changed character").split()
LESSON_WORDS = {"hook": 110, "concept": 120, "example_1": 120, "example_2": 120, "misreads": 40, "recap": 110}
# example scenes: four sentences, the 2nd-4th naming the sample's reveal steps (swings, BOS, CHoCH) in order
EXAMPLE_FILLER = "price moved across the chart and each candle shows how the market traded there".split()
EXAMPLE_SENTENCES = (("", 40), ("The swing points mark each turn", 30), ("This close is a break of structure", 25),
                     ("Then the change of character shows", 0))


def _filler(words: list[str], n: int) -> str:
    return " ".join(words[k % len(words)] for k in range(n))


def _lesson_draft(plan: list[dict], tail: str) -> dict:
    """A mocked lesson writer reply: LESSON_WORDS words per scene (the misreads scene is short), no
    numbers, the recap ending with `tail`; example scenes name their marks in EXAMPLE_SENTENCES (the other
    scenes are one sentence)."""
    scenes = []
    for p in plan:
        n = LESSON_WORDS[p["id"]] - (len(tail.split()) if p["id"] == "recap" else 0)
        if p["id"].startswith("example_"):
            parts, left = [], n
            for k, (lead, size) in enumerate(EXAMPLE_SENTENCES):
                size = size or left
                lead = lead.split()
                parts.append(" ".join(lead + _filler(EXAMPLE_FILLER, size - len(lead)).split()) + ".")
                left -= size
            body = " ".join(parts)
        else:
            body = _filler(LESSON_FILLER, n)
        assert len(body.split()) == n, (p["id"], len(body.split()), n)
        scenes.append({"id": p["id"], "text": body + (" " + tail if p["id"] == "recap" else "")})
    return {"scenes": scenes}


def _ink_rows(path: Path, bg=(14, 15, 18), tol: int = 24) -> list[int]:
    """Rows of an image that differ from the channel ground by more than `tol` (a low tol also counts
    caption outline and shadow; the default ignores video-compression noise)."""
    import numpy as np
    from PIL import Image
    with Image.open(path) as im:
        a = np.asarray(im.convert("RGB"), dtype=int)
    return [int(y) for y in np.where((np.abs(a - np.array(bg)).max(axis=2) > tol).any(axis=1))[0]]


def _probe_size(path: Path) -> tuple[int, int]:
    import subprocess
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                        "-of", "csv=p=0", str(path)], capture_output=True, text=True, check=True)
    w, h = r.stdout.strip().split(",")[:2]
    return int(w), int(h)


def _frame(video: Path, t: float, out: Path):
    """One decoded frame of `video` at `t` seconds as an RGB array (also saved to `out`)."""
    import numpy as np
    from PIL import Image
    run(["ffmpeg", "-y", "-v", "error", "-ss", f"{max(t, 0):.3f}", "-i", video, "-frames:v", "1", out])
    with Image.open(out) as im:
        return np.asarray(im.convert("RGB"), dtype=int)


def check_step_render(work: Path, plan: list[dict], timed: list[list[dict]], audio: list[dict], draft: dict) -> None:
    """The rendered step reveal (both shapes): example scenes fade their marks in at the sentences naming them
    (swings → BOS → CHoCH), a frame before the first layer lacks it, the scene's last frame is the full slide,
    the hook opens fully drawn; contact frames at each step's time → output/reveal-sample/ for the owner."""
    import numpy as np
    from PIL import Image
    from autopilot import reveal
    sample = ROOT / "output" / "reveal-sample"
    shutil.rmtree(sample, ignore_errors=True)
    sample.mkdir(parents=True)
    starts = [sum(a["duration"] for a in audio[:i]) for i in range(len(audio))]
    texts = {sc["id"]: sc["text"] for sc in draft["scenes"]}
    for pics in timed:
        shape = Path(pics[0]["image"]).parent.name
        assert "steps" not in pics[0] and pics[0]["id"] == "hook"  # the hook stays fully drawn
        contact = []
        hook = _frame(work / f"lesson_{shape}.mp4", 0.0, sample / f"{shape}_hook.png")
        with Image.open(pics[0]["image"]) as im:
            full = np.asarray(im.convert("RGB"), dtype=int)
        assert np.abs(hook - full)[: full.shape[0] // 2].mean() < 3, (shape, "hook not fully drawn at 0 s")
        contact.append(sample / f"{shape}_hook.png")
        for i, p in enumerate(pics):
            if "steps" not in p:
                continue
            assert [s["key"] for s in p["steps"]] == [s["key"] for s in plan[i]["visual"]["steps"]]
            assert [s["key"] for s in p["steps"]] == ["swings", "BOS", "CHoCH"], [s["key"] for s in p["steps"]]
            sents = reveal.split_sentences(texts[p["id"]])
            sstarts = reveal.sentence_starts(texts[p["id"]], audio[i]["words"], audio[i]["duration"])
            ats = [ly["at"] for s in p["steps"] for ly in s["layers"]]
            assert ats == sorted(ats) and all(b - a >= reveal.MIN_GAP - 1e-6 for a, b in zip(ats, ats[1:])), ats
            assert ats[-1] + reveal.FADE < audio[i]["duration"], (ats[-1], audio[i]["duration"])
            for k, s in enumerate(p["steps"], 1):  # sentence k names step k
                assert abs(s["layers"][0]["at"] - sstarts[k]) < 0.15, (shape, p["id"], s["key"], s["layers"][0]["at"], sstarts[k])
                assert reveal.names_in(sents[k], s["names"]), (sents[k], s["names"])
            seg = work / shape / f"seg_{i:02d}.mp4"
            first = p["steps"][0]["layers"][0]
            with Image.open(first["image"]) as im:
                layer = np.asarray(im.convert("RGB"), dtype=int)
            with Image.open(p["base"]) as im:
                base = np.asarray(im.convert("RGB"), dtype=int)
            x, y = first["xy"]
            h, w = layer.shape[:2]
            under = base[y:y + h, x:x + w]
            assert np.abs(layer - under).mean() > 4, "the first layer adds nothing"
            before = _frame(seg, first["at"] - 0.3, work / "before.png")[y:y + h, x:x + w]
            after = _frame(seg, first["at"] + reveal.FADE + 0.1, work / "after.png")[y:y + h, x:x + w]
            assert np.abs(before - under).mean() < np.abs(before - layer).mean(), (shape, p["id"], "mark shown early")
            assert np.abs(after - layer).mean() < np.abs(after - under).mean(), (shape, p["id"], "mark not shown")
            run(["ffmpeg", "-y", "-v", "error", "-sseof", "-0.1", "-i", seg, "-update", "1", work / "end.png"])
            with Image.open(work / "end.png") as a, Image.open(p["image"]) as b:
                diff = np.abs(np.asarray(a.convert("RGB"), dtype=int) - np.asarray(b.convert("RGB"), dtype=int))
            assert diff.mean() < 2.5 and np.percentile(diff.max(axis=2), 99.5) < 60, (shape, p["id"], diff.mean())
            for s in p["steps"]:  # contact frames: each step's first and last mark in, in the final video
                for ly in (s["layers"][0], s["layers"][-1]):
                    name = f"{shape}_{p['id']}_{s['key']}_{ly['at']:.2f}.png"
                    _frame(work / f"lesson_{shape}.mp4", starts[i] + ly["at"] + reveal.FADE + 0.05, sample / name)
                    contact.append(sample / name)
        for f in ("before.png", "after.png", "end.png"):
            (work / f).unlink(missing_ok=True)
        cell = (480, 270) if shape == "16x9" else (270, 480)
        _contact(contact, cell, 4, sample / f"contact_{shape}.png")


def test_lesson_render(cfg):
    """make_lesson (entry 6): sample entry on fixture candles, mocked narration + sine voice → a 16:9 and a
    9:16 mp4 from the same audio, captions in each layout's band, chapters from the scene timings (a short
    scene merges), lesson metadata; plus the hold, over-limit re-record, ICT and Shorts-caption cases."""
    from unittest import mock
    import main as app
    from autopilot import lesson_meta, lesson_script, lesson_slides as ls, lessons, reveal, voice
    from PIL import Image

    entry, glossary, history, nxt = lesson_script.sample_inputs()
    per_word = 0.1  # seconds per mocked spoken word: keeps the renders short
    prompts, voice_calls, last_audio = [], [], []
    draft = {}

    def fake_llm(prompt, models, temperature=0.9):
        prompts.append(prompt)
        if "strict financial news editor" in prompt:
            pkg = json.loads(prompt.split("SCRIPT:\n", 1)[1].rsplit("\n\n1. Every", 1)[0])
            return {"verdict": "ok", "issues": [], "package": pkg}
        return json.loads(json.dumps(draft))

    def fake_voice(scenes, name, rate, workdir, log=print, fallback=None, pauses=False):
        assert not pauses  # lessons speak their text as written
        voice_calls.append(rate)
        step = per_word * 1.1 / (1 + int(rate.strip("%")) / 100)  # a faster rate → shorter words
        out = []
        for i, sc in enumerate(scenes):
            words = sc["text"].split()
            wav = Path(workdir) / f"voice_{i:02d}.wav"
            run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
                 f"sine=frequency={320 + 30 * i}:duration={step * len(words) + 0.3:.3f}", "-ar", "44100", "-ac", "1",
                 wav])
            out.append({"audio": wav, "duration": probe_duration(wav),
                        "words": [(j * step, (j + 0.9) * step, w) for j, w in enumerate(words)]})
        last_audio[:] = out
        return out

    def make(e, c, workdir, hist=history, logs=None):
        prompts.clear()
        voice_calls.clear()
        with mock.patch.object(lesson_script, "generate_json", fake_llm), \
                mock.patch.object(script, "generate_json", fake_llm), mock.patch.object(voice, "synthesize", fake_voice):
            return app.make_lesson(c, e, glossary, hist, workdir=workdir, next_entry=nxt,
                                   log=(logs.append if logs is not None else (lambda m: None)))

    # Shorts regression: without margin_v the caption line keeps 30% of the height
    tmp = Path(tempfile.mkdtemp())
    render.build_captions([(0.0, 0.4, "hi")], cfg["video"]["captions"], 1080, 1920, tmp / "c.ass")
    style = next(ln for ln in (tmp / "c.ass").read_text().splitlines() if ln.startswith("Style: Cap,"))
    assert style.split(",")[-2] == "576" and style.split(",")[2] == str(cfg["video"]["captions"]["size"]), style
    shutil.rmtree(tmp, ignore_errors=True)

    # no clean example → held, named, nothing made (no narration call, no workdir)
    hold_dir = ROOT / "output" / "test_lesson_hold"
    shutil.rmtree(hold_dir, ignore_errors=True)
    choppy = json.loads((ROOT / "tests" / "lessons" / "candles" / "choppy.json").read_text(encoding="utf-8"))
    logs = []
    held = make(entry, cfg, hold_dir, hist={"BTC/USD": {"1H": choppy}}, logs=logs)
    assert set(held) == {"held"} and entry["id"] in held["held"] and "example" in held["held"], held
    assert not prompts and not voice_calls and not hold_dir.exists() and any("held" in m for m in logs), logs

    # 1) the sample lesson: both shapes rendered from one narration
    work = ROOT / "output" / "test_lesson"
    shutil.rmtree(work, ignore_errors=True)
    plan = lessons.scene_plan(entry, lessons.DETECTORS[entry["detector"]].find(history), nxt)
    draft.update(_lesson_draft(plan, f"{lesson_script.DISCLAIMER} Next, {nxt['title']}." if nxt
                               else lesson_script.DISCLAIMER))  # the recap ends on the next episode
    timed, time_steps = [], reveal.time_steps

    def spy(pics, scenes, audio, log=lambda m: None):  # keeps each shape's slides once their layers are timed
        timed.append(time_steps(pics, scenes, audio, log=log))
        return timed[-1]
    with mock.patch.object(reveal, "time_steps", spy):
        made = make(entry, cfg, work)
    assert len(timed) == 2
    assert set(made) == {"videos", "thumbnail", "meta", "chapters", "seconds", "examples", "workdir"}, set(made)
    assert voice_calls == [cfg["voice"]["rate"]]  # under 300 s: recorded once
    total = sum(a["duration"] for a in last_audio)
    assert set(made["videos"]) == {"16x9", "9x16"} and abs(made["seconds"] - total) < 0.1
    durs = {}
    for name, size in (("16x9", (1920, 1080)), ("9x16", (1080, 1920))):
        path = made["videos"][name]
        assert path == work / f"lesson_{name}.mp4" and path.exists()
        assert _probe_size(path) == size, (name, _probe_size(path))
        durs[name] = probe_duration(path)
        assert abs(durs[name] - total) < 0.25 and durs[name] < 300, (name, durs[name], total)
    assert abs(durs["16x9"] - durs["9x16"]) < 0.1, durs
    # captions: 56 px in 16:9, the Shorts' 84 px in 9:16 (2 words a line), every scene captioned
    for layout, size in ((ls.LANDSCAPE, 56), (ls.PORTRAIT, cfg["video"]["captions"]["size"])):
        ass = (work / layout.name / "captions.ass").read_text()
        assert f"PlayResX: {layout.w}" in ass and f"PlayResY: {layout.h}" in ass
        f = next(ln for ln in ass.splitlines() if ln.startswith("Style: Cap,")).split(",")
        assert int(f[2]) == size, (layout.name, f)
        assert ass.count("Dialogue:") == sum(len(sc["text"].split()) for sc in draft["scenes"])
        # a caption that wraps to two lines (the longest a line of words_per_line words can wrap to) stays
        # inside the caption band, also while its first word pops in at 108%
        cap = app.lesson_video_cfg(cfg, layout)["video"]["captions"]
        words = ["INTERCONTINENTALISATIONSQ", "MISUNDERSTANDINGSHOWNTOGQ", "ACCOMPLISHMENTSXXJQWERTYQ"]
        cdir = work / f"capcheck_{layout.name}"
        cdir.mkdir()
        render.build_captions([(k * 0.1, k * 0.1 + 0.09, w) for k, w in enumerate(words[:cap["words_per_line"]])],
                              cap, layout.w, layout.h, cdir / "c.ass")
        for ts in ("0.0", "0.25"):
            run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"color=c=0x0E0F12:s={layout.w}x{layout.h}:d=1",
                 "-vf", "ass=c.ass", "-ss", ts, "-frames:v", "1", "f.png"], cwd=cdir)
            rows = _ink_rows(cdir / "f.png", tol=4)
            assert rows and layout.caption_band[0] <= rows[0] and rows[-1] <= layout.caption_band[1], \
                (layout.name, ts, rows[0], rows[-1], layout.caption_band)
            assert rows[-1] - rows[0] > 1.5 * cap["size"], (layout.name, "expected two lines", rows[0], rows[-1])
        shutil.rmtree(cdir)
        # push-in: the last frame of a non-chart scene (concept) still shows the whole footer
        seg = work / layout.name / "seg_01.mp4"
        assert next(s for s in plan if s["id"] == "concept")["visual"]["type"] == "concept"
        run(["ffmpeg", "-y", "-v", "error", "-sseof", "-0.3", "-i", seg, "-update", "1", work / "last.png"])
        slide_rows = [r for r in _ink_rows(work / layout.name / f"lesson_{layout.name}_01.png")
                      if r > layout.caption_band[1]]
        frame_rows = [r for r in _ink_rows(work / "last.png") if r > layout.caption_band[1]]
        assert slide_rows and frame_rows and frame_rows[-1] < layout.h - 3, (layout.name, "footer cropped", frame_rows[-1:])
        assert frame_rows[-1] - frame_rows[0] >= slide_rows[-1] - slide_rows[0], (layout.name, frame_rows, slide_rows)
        (work / "last.png").unlink()
    with Image.open(made["thumbnail"]) as im:
        assert im.size == (1280, 720)
    check_step_render(work, plan, timed, last_audio, draft)

    # chapters: start at 0:00, follow the scene starts, ≥ 10 s each; the short misreads scene merges
    starts, t = {}, 0.0
    for p, a in zip(plan, last_audio):
        starts[p["id"]] = t
        t += a["duration"]
    ch = made["chapters"]
    assert [c["title"] for c in ch] == ["Intro", glossary["break_of_structure"]["term"], "Example 1: ETH/USD 1H",
                                        "Example 2: BTC/USD 1H", "Recap"], [c["title"] for c in ch]
    assert [sid for c in ch for sid in c["scenes"]] == [p["id"] for p in plan]
    assert ch[3]["scenes"] == ["example_2", "misreads"] and last_audio[4]["duration"] < 10
    assert ch[0]["start"] == 0 and ch[0]["time"] == "0:00"
    ends = [c["start"] for c in ch[1:]] + [total]
    for c, end in zip(ch, ends):
        assert abs(c["start"] - starts[c["scenes"][0]]) < 0.01 and end - c["start"] >= 10, (c, end)
        assert c["time"] == lesson_meta.timestamp(c["start"])

    # metadata: written, the entry's search title, track label, chapters / examples / credits / disclosure once,
    # no ICT line
    meta = made["meta"]
    saved = json.loads((work / "metadata.json").read_text())
    assert {k: saved[k] for k in meta} == meta and saved["chapters"] == ch
    assert set(meta) == {"title", "description", "tags", "category_id", "fb_title", "fb_description"}
    assert meta["title"] == entry["search_title"] == "What Is a Break of Structure? (Crypto Chart Example)"
    assert meta["category_id"] == "27" and meta["fb_title"] == meta["title"]
    d = meta["description"]
    assert d.startswith(" ".join(entry["key_points"]) + f"\n\nTrack 0 · {entry['title']}\n\nChapters:\n"), d
    assert d.count(rules.DISCLOSURE) == 1 and "education, not financial advice" not in d.lower(), d
    assert "Chapters:\n" + "\n".join(f"{c['time']} {c['title']}" for c in ch) in d, d
    assert "Historical examples:\n" in d and all(lessons.example_label(e) in d for e in made["examples"])
    assert "Coinbase" in d and "not financial advice" in d.lower() and ls.NON_AFFILIATION not in d
    tags = d.rsplit("\n\n", 1)[1].split()
    assert 3 <= len(tags) <= 5 and all(h.startswith("#") for h in tags) and "#Shorts" not in tags, tags
    assert meta["tags"] and len(meta["tags"]) == len({x.lower() for x in meta["tags"]})
    fb = meta["fb_description"]
    assert "http" not in d and "http" not in fb and "www." not in fb and "not financial advice" in fb.lower()
    assert fb.startswith(" ".join(entry["key_points"]) + f"\n\nTrack 0 · {entry['title']}")
    assert 1 <= len(rules.HASHTAG.findall(fb)) <= 5 and fb.count(rules.DISCLOSURE) == 1, fb  # "#2:" is no hashtag

    # 2) ICT entry (track 4) over the limit: re-recorded faster once; the non-affiliation line in both texts.
    # Rendering is stubbed here (the sample above rendered for real); it records each shape's cfg.
    shapes = []

    def fake_build(audio, pics, vcfg, workdir, out, music=None):
        shapes.append(vcfg["video"])
        return sum(a["duration"] for a in audio)
    ict = dict(entry, track=4)
    plan = lessons.scene_plan(ict, made["examples"], nxt)
    draft.clear()
    draft.update(_lesson_draft(plan, f"{lesson_script.DISCLAIMER} {lesson_script.NON_AFFILIATION}"))
    logs = []
    with mock.patch.object(render, "build_video", fake_build):
        made = make(ict, {**cfg, "lessons": {"max_seconds": 40}}, ROOT / "output" / "test_lesson_ict", logs=logs)
    assert len(voice_calls) == 2 and int(voice_calls[1].strip("%")) > int(voice_calls[0].strip("%")), voice_calls
    assert any("re-recording" in m for m in logs), logs
    assert [(s["width"], s["height"], s["captions"]["size"]) for s in shapes] == \
        [(1920, 1080, 56), (1080, 1920, cfg["video"]["captions"]["size"])], shapes
    assert cfg["video"]["max_seconds"] == 42 and "margin_v" not in cfg["video"]["captions"]  # Shorts cfg untouched
    assert ls.NON_AFFILIATION in made["meta"]["description"] and ls.NON_AFFILIATION in made["meta"]["fb_description"]
    assert made["meta"]["title"] == ict["search_title"] and made["meta"]["fb_title"] == ict["search_title"]
    assert all(f"Track 4 · {ict['title']}" in made["meta"][k] for k in ("description", "fb_description"))
    shutil.rmtree(ROOT / "output" / "test_lesson_ict", ignore_errors=True)

    # chapter rules on their own: a short opening absorbs the next scene; a short last scene merges back
    p3 = [{"id": "hook"}, {"id": "concept", "visual": {"concepts": ["swing_point"]}}, {"id": "example_1"},
          {"id": "recap"}]
    ex = [{"asset": "BTC/USD", "timeframe": "4H"}]
    got = lesson_meta.chapters(p3, [{"duration": d} for d in (4.0, 12.0, 15.0, 6.0)], ex, glossary)
    assert [(c["time"], c["title"], c["scenes"]) for c in got] == [
        ("0:00", "Intro", ["hook", "concept"]), ("0:16", "Example 1: BTC/USD 4H", ["example_1", "recap"])], got
    # fewer than 3 chapters: YouTube ignores them, so the description has no "Chapters:" block (logged)
    logs = []
    two = lesson_meta.build_lesson_metadata(entry, made["examples"], got, cfg, log=logs.append)
    assert "Chapters:" not in two["description"] and "0:16" not in two["description"], two["description"]
    assert any("No chapters" in m and "2" in m for m in logs), logs
    assert lesson_meta.timestamp(75.9) == "1:15" and lesson_meta.timestamp(3725) == "1:02:05"
    print(f"OK lesson render: {work / 'lesson_16x9.mp4'} + lesson_9x16.mp4 ({durs['16x9']:.1f}s) · "
          f"{len(ch)} chapters · hold, re-record, ICT, Shorts captions")


# ─── YouTube lesson publishing (fake googleapiclient service) ──────────────

class _Req:
    def __init__(self, fn):
        self.fn = fn

    def execute(self):
        return self.fn()


class FakeYouTube:
    """videos / thumbnails / playlists / playlistItems with .execute() and a resumable next_chunk()."""

    def __init__(self, playlists=(), fail=None, page=2):
        self.playlists_ = [{"id": f"PL{i}", "snippet": {"title": t}} for i, t in enumerate(playlists)]
        self.fail = dict(fail or {})  # op → exception raised once
        self.page = page
        self.calls = []  # (op, kwargs)

    def _maybe_fail(self, op):
        if op in self.fail:
            raise self.fail.pop(op)

    def count(self, op):
        return sum(1 for o, _ in self.calls if o == op)

    def videos(self):
        fake = self

        class V:
            def insert(self, **kw):
                fake.calls.append(("videos.insert", kw))
                chunks = iter([(type("S", (), {"progress": lambda s: 0.5})(), None), (None, {"id": "VID1"})])

                class R:
                    def next_chunk(self):
                        fake._maybe_fail("videos.insert")
                        return next(chunks)
                return R()

            def delete(self, **kw):
                fake.calls.append(("videos.delete", kw))
                return _Req(lambda: fake._maybe_fail("videos.delete") or "")
        return V()

    def thumbnails(self):
        fake = self

        class T:
            def set(self, **kw):
                fake.calls.append(("thumbnails.set", kw))
                return _Req(lambda: fake._maybe_fail("thumbnails.set") or {"items": [{}]})
        return T()

    def playlists(self):
        fake = self

        class P:
            def list(self, **kw):
                fake.calls.append(("playlists.list", kw))
                assert kw.get("mine") is True and kw.get("part") == "snippet", kw
                start = int(kw.get("pageToken") or 0)
                items = fake.playlists_[start:start + fake.page]
                more = start + fake.page < len(fake.playlists_)
                return _Req(lambda: {"items": items} | ({"nextPageToken": str(start + fake.page)} if more else {}))

            def insert(self, **kw):
                fake.calls.append(("playlists.insert", kw))
                pid = f"PL{len(fake.playlists_)}"
                fake.playlists_.append({"id": pid, "snippet": dict(kw["body"]["snippet"])})
                return _Req(lambda: {"id": pid})

            def delete(self, **kw):
                fake.calls.append(("playlists.delete", kw))
                return _Req(lambda: "")
        return P()

    def playlistItems(self):  # noqa: N802 (googleapiclient name)
        fake = self

        class I:  # noqa: E742
            def insert(self, **kw):
                fake.calls.append(("playlistItems.insert", kw))
                return _Req(lambda: fake._maybe_fail("playlistItems.insert") or {"id": "PLI"})
        return I()


def _http_error(status: int, reason: str):
    import httplib2
    from googleapiclient.errors import HttpError
    body = {"error": {"code": status, "message": reason, "errors": [{"reason": reason, "message": reason}]}}
    return HttpError(httplib2.Response({"status": status}), json.dumps(body).encode())


def test_youtube_lesson(cfg):
    """upload_lesson: Education, private + publishAt, thumbnail, track + Path playlists; daily scopes unchanged."""
    from autopilot import youtube
    tmp = Path(tempfile.mkdtemp())
    video, thumb = tmp / "lesson_16x9.mp4", tmp / "thumbnail.jpg"
    video.write_bytes(b"\0" * 1024)
    thumb.write_bytes(b"\xff\xd8\xff\xd9")
    meta = {"title": "What Is a Break of Structure? (Crypto Chart Example)",
            "description": "Summary\n\nChapters:\n0:00 Intro\n0:12 Break of structure\n0:40 Recap",
            "tags": ["market structure"], "category_id": "27"}
    track, path = "Track 0 · Structure", "The Path"
    scopes_seen = []

    class FakeCreds:
        def __init__(self, token, **kw):
            scopes_seen.append(kw["scopes"])

        def refresh(self, request):
            pass

    saved = (youtube.build, youtube.Credentials, youtube.time.sleep,
             {k: os.environ.get(k) for k in ("YT_CLIENT_ID", "YT_CLIENT_SECRET", "YT_REFRESH_TOKEN")})
    os.environ.update(YT_CLIENT_ID="id", YT_CLIENT_SECRET="secret", YT_REFRESH_TOKEN="refresh")
    youtube.Credentials, youtube.time.sleep = FakeCreds, (lambda s: None)
    logs = []

    def use(fake):
        youtube.build = lambda *a, **k: fake
        scopes_seen.clear()
        logs.clear()
        return fake

    try:
        # daily path: _client() default and upload()/set_thumbnail() ask for youtube.upload only
        use(FakeYouTube())
        youtube._client()
        assert scopes_seen == [["https://www.googleapis.com/auth/youtube.upload"]], scopes_seen
        fake = use(FakeYouTube())
        ucfg = cfg | {"upload": cfg["upload"] | {"privacy_status": "public", "review_window_hours": 0}}
        assert youtube.upload(video, {"title": "t", "description": "d", "tags": []}, ucfg, log=logs.append) == "VID1"
        assert youtube.set_thumbnail("VID1", thumb, log=logs.append)
        assert scopes_seen == [youtube.SCOPES] * 2 and youtube.SCOPES == scopes_seen[0], scopes_seen
        b = fake.calls[0][1]["body"]
        assert b["snippet"]["categoryId"] == str(cfg["upload"]["category_id"]) and b["status"]["privacyStatus"] == "public"
        assert "publishAt" not in b["status"] and any("youtube.com/shorts/VID1" in m for m in logs), logs

        # happy path: both playlists exist (Path on the 2nd page) → no create, 2 playlistItems inserts
        fake = use(FakeYouTube(playlists=["Other", track, "Old", path]))
        before = datetime.now(timezone.utc)
        res = youtube.upload_lesson(video, meta, thumb, track, path, log=logs.append)
        assert scopes_seen == [youtube.LESSON_SCOPES] and len(youtube.LESSON_SCOPES) == 3, scopes_seen
        assert set(youtube.LESSON_SCOPES) == {"https://www.googleapis.com/auth/youtube.upload",
                                              "https://www.googleapis.com/auth/youtube",
                                              "https://www.googleapis.com/auth/yt-analytics.readonly"}
        ins = fake.calls[0][1]
        assert fake.calls[0][0] == "videos.insert" and ins["notifySubscribers"] is True
        sn, st = ins["body"]["snippet"], ins["body"]["status"]
        assert sn["categoryId"] == "27" and sn["description"] == meta["description"] and sn["title"] == meta["title"]
        assert st["privacyStatus"] == "private" and st["selfDeclaredMadeForKids"] is False
        pub = datetime.strptime(st["publishAt"], "%Y-%m-%dT%H:%M:%S.000Z").replace(tzinfo=timezone.utc)
        assert abs((pub - before).total_seconds() - 24 * 3600) < 120, st["publishAt"]
        assert res == {"video_id": "VID1", "publish_at": st["publishAt"], "thumbnail_set": True,
                       "playlists": {track: "PL1", path: "PL3"}, "errors": []}, res
        assert fake.count("thumbnails.set") == 1 and fake.count("playlists.insert") == 0
        assert fake.count("playlistItems.insert") == 2 and fake.count("playlists.list") >= 3  # paged
        items = [kw["body"]["snippet"] for o, kw in fake.calls if o == "playlistItems.insert"]
        assert items == [{"playlistId": "PL1", "resourceId": {"kind": "youtube#video", "videoId": "VID1"}},
                         {"playlistId": "PL3", "resourceId": {"kind": "youtube#video", "videoId": "VID1"}}], items

        # playlists missing → each created once (public, described), then the video is added
        fake = use(FakeYouTube(playlists=["Other"]))
        res = youtube.upload_lesson(video, meta, thumb, track, path, review_hours=48, notify=False, log=logs.append)
        made = [kw["body"] for o, kw in fake.calls if o == "playlists.insert"]
        assert [m["snippet"]["title"] for m in made] == [track, path] and all(
            m["status"]["privacyStatus"] == "public" for m in made), made
        assert made[0]["snippet"]["description"] == "CryptoFX Daily trading lessons · Track 0 · Structure"
        assert made[1]["snippet"]["description"] == "CryptoFX Daily trading lessons in curriculum order"
        assert res["playlists"] == {track: "PL1", path: "PL2"} and fake.count("playlistItems.insert") == 2
        assert fake.calls[0][1]["notifySubscribers"] is False and not res["errors"]
        # a second lesson finds the playlists it created (exact title) instead of creating them again
        res2 = youtube.upload_lesson(video, meta, thumb, track, path, log=logs.append)
        assert fake.count("playlists.insert") == 2 and res2["playlists"] == res["playlists"]

        # thumbnail refused (403) → logged, thumbnail_set False, upload + playlists still done
        fake = use(FakeYouTube(playlists=[track, path], fail={"thumbnails.set": _http_error(403, "forbidden")}))
        res = youtube.upload_lesson(video, meta, thumb, track, path, log=logs.append)
        assert res["video_id"] == "VID1" and res["thumbnail_set"] is False and not res["errors"], res
        assert any("Custom thumbnail not accepted (403" in m for m in logs), logs
        assert fake.count("playlistItems.insert") == 2

        # playlist add fails → logged, listed in errors, video id returned, the other playlist still added
        fake = use(FakeYouTube(playlists=[track, path],
                               fail={"playlistItems.insert": _http_error(403, "playlistItemsNotAccessible")}))
        res = youtube.upload_lesson(video, meta, thumb, track, path, log=logs.append)
        assert res["video_id"] == "VID1" and res["playlists"] == {track: None, path: "PL1"}, res
        assert len(res["errors"]) == 1 and track in res["errors"][0], res["errors"]
        assert any("Could not add the lesson to playlist 'Track 0" in m for m in logs), logs

        # quota exceeded → the same clear RuntimeError as upload(), nothing else called
        quota = None
        for fn in (lambda: youtube.upload(video, {"title": "t", "description": "d", "tags": []}, ucfg, log=logs.append),
                   lambda: youtube.upload_lesson(video, meta, thumb, track, path, log=logs.append)):
            fake = use(FakeYouTube(playlists=[track, path], fail={"videos.insert": _http_error(403, "quotaExceeded")}))
            try:
                fn()
                raise AssertionError("quota should raise")
            except RuntimeError as e:
                assert str(e) == youtube.QUOTA_MESSAGE and "upload limit" in str(e)
                quota = quota or str(e)
                assert str(e) == quota
            assert fake.count("thumbnails.set") == 0 and fake.count("playlistItems.insert") == 0

        # 5xx during the upload is retried, not raised
        fake = use(FakeYouTube(playlists=[track, path], fail={"videos.insert": _http_error(503, "backendError")}))
        assert youtube.upload_lesson(video, meta, thumb, track, path, log=logs.append)["video_id"] == "VID1"

        # playlists off (owner manages them by hand): only the upload scope, no playlist calls
        fake = use(FakeYouTube())
        scopes_seen.clear()
        res = youtube.upload_lesson(video, meta, thumb, None, None, log=logs.append, playlists=False)
        assert res["video_id"] == "VID1" and res["thumbnail_set"] and res["playlists"] == {}, res
        assert scopes_seen == [youtube.SCOPES], scopes_seen
        assert not [o for o, _ in fake.calls if o.startswith("playlist")], fake.calls
        scopes_seen.clear()

        # review_hours 0 (config default): public straight away, no publishAt
        fake = use(FakeYouTube())
        res = youtube.upload_lesson(video, meta, thumb, None, None, review_hours=0, log=logs.append, playlists=False)
        st0 = next(kw["body"]["status"] for o, kw in fake.calls if o == "videos.insert")
        assert st0["privacyStatus"] == "public" and "publishAt" not in st0 and res["publish_at"] is None, st0
        scopes_seen.clear()

        # delete (owner's test cleanup) uses the lesson scopes
        fake = use(FakeYouTube())
        youtube.delete_video("VID1", log=logs.append)
        assert fake.calls == [("videos.delete", {"id": "VID1"})] and scopes_seen == [youtube.LESSON_SCOPES]
        assert "Chapters:" in youtube._test_meta(95)["description"] and "0:31 Middle" in youtube._test_meta(95)["description"]
        assert "Chapters:" not in youtube._test_meta(20)["description"]

        # owner's test CLI (stdin not a terminal → no pause); the fake mp4 has no duration
        import contextlib
        import io

        def cli(fake, creds=FakeCreds, extra=("--playlists",)):
            use(fake)
            youtube.Credentials, out, stdin = creds, io.StringIO(), sys.stdin
            sys.stdin = io.StringIO()
            try:
                with contextlib.redirect_stdout(out):
                    rc = youtube._main(["test-lesson", str(video), str(thumb), "--days", "30", *extra])
            finally:
                youtube.Credentials, sys.stdin = FakeCreds, stdin
            return rc, out.getvalue()

        fake = FakeYouTube()
        rc, out = cli(fake)
        made = [kw["body"]["status"]["privacyStatus"] for o, kw in fake.calls if o == "playlists.insert"]
        assert rc == 0 and made == ["private", "private"], (rc, made, out)
        assert "no chapters" in out and fake.count("videos.delete") == 1 and fake.count("playlists.delete") == 2, out
        # refused thumbnail → exit 1 (the live check needs it), still cleaned up
        fake = FakeYouTube(fail={"thumbnails.set": _http_error(403, "forbidden")})
        rc, out = cli(fake)
        assert rc == 1 and fake.count("videos.delete") == 1 and fake.count("playlists.delete") == 2, out
        # video delete fails → reported, the TEST playlists are still deleted
        fake = FakeYouTube(fail={"videos.delete": _http_error(500, "backendError")})
        rc, out = cli(fake)
        assert rc == 1 and "could not delete test video VID1" in out and fake.count("playlists.delete") == 2, out

        # default test (no --playlists): works with the upload-only token, nothing deleted via the API
        fake = FakeYouTube()
        scopes_seen.clear()
        rc, out = cli(fake, extra=())
        assert rc == 0 and "delete the test video in YouTube Studio" in out, out
        assert scopes_seen == [youtube.SCOPES] and fake.count("videos.delete") == 0, (scopes_seen, out)
        assert not [o for o, _ in fake.calls if o.startswith("playlist")], fake.calls

        # old token without the lesson scopes → upload fails, nothing to clean, no false "delete in Studio"
        class OldToken(FakeCreds):
            def refresh(self, request):
                raise RuntimeError("invalid_scope")
        fake = FakeYouTube()
        rc, out = cli(fake, OldToken)
        assert rc == 1 and "test upload failed" in out and "nothing to clean up" in out, out
        assert "Studio" not in out and not fake.calls, out
    finally:
        youtube.build, youtube.Credentials, youtube.time.sleep, env = saved
        for k, v in env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    print("OK YouTube lesson publishing (Education, private + publishAt 24 h, thumbnail, track + Path playlists, "
          "daily scopes unchanged)")


def test_lesson_edition(cfg):
    """The lesson edition through main() (entry 12): days rule, lessons.enabled, next episode on both
    platforms, the guard, a held episode, one platform failing + the re-run of the slot's recorded
    episode, empty slots, curriculum problems, a manual run on another day, history merge by
    fb_video_id and the cron-job.org days. Weekly Thursday 15:00 slot + `--slot` top-ups (crypto-lessons
    entry 4). Price history, make_lesson and both publishers are faked."""
    import main as app
    import setup_cronjobs
    from autopilot import lesson_data, lessons, youtube

    clock = [datetime(2026, 10, 15, 15, 5, tzinfo=timezone.utc)]  # a Thursday, 5 min after 15:00

    class FixedNow(datetime):
        @classmethod
        def now(cls, tz=None):
            return clock[0].astimezone(tz) if tz else clock[0].replace(tzinfo=None)

    tmp = Path(tempfile.mkdtemp())
    (tmp / "lessons").mkdir()
    shutil.copy(ROOT / "tests" / "lessons" / "glossary.yaml", tmp / "lessons" / "glossary.yaml")
    sample = (ROOT / "tests" / "lessons" / "curriculum.yaml").read_text(encoding="utf-8")
    (tmp / "lessons" / "curriculum.yaml").write_text(sample, encoding="utf-8")
    ids = [e["id"] for e in lessons.load_curriculum(tmp / "lessons" / "curriculum.yaml")]
    assert ids == ["swing-structure", "bos-vs-choch", "top-down-reading"], ids

    def write_cfg(enabled: bool):
        c = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
        c["lessons"]["enabled"] = enabled
        # a recap slot for the top-up runs (crypto-pivot epic 5 adds the real one: Sat 15:00)
        c["sessions"]["recap"] = {"label": "Weekly Recap", "short": "Recap", "start_utc": "15:00", "days": ["sat"],
                                  "platforms": ["youtube"]}
        (tmp / "config.yaml").write_text(yaml.safe_dump(c, allow_unicode=True), encoding="utf-8")

    def history() -> list[dict]:
        f = tmp / "data" / "history.json"
        return json.loads(f.read_text())["videos"] if f.exists() else []

    available = {"swings", "bos_choch", "top_down"}  # detectors that find a clean example
    fetched, made, yt, fb, logs = [], [], [], [], []
    fail_fb, other_first = [False], [False]
    region = {"start": "2026-09-01T00:00:00+00:00", "end": "2026-09-02T00:00:00+00:00", "low": 1, "high": 2}

    def fake_detector(name):
        real = lessons.DETECTORS[name]

        def find(hist):
            assert hist == {"BTC/USD": {"1H": [{"t": "x"}]}}, hist
            if name not in available:
                return []
            ex = {"asset": "BTC/USD", "timeframe": "1H", "date": "2026-09-01", "detector": name, "region": region}
            other = {**ex, "asset": "ETH/USD", "region": {**region, "start": "2026-09-05T00:00:00+00:00"}}
            return [other, ex] if other_first[0] else [ex]  # other_first: a new example now ranks first
        return lessons.Detector(name, real.glossary, find)

    def fake_fetch(log=print, now=None):
        fetched.append(1)
        return {"BTC/USD": {"1H": [{"t": "x"}]}}

    def fake_make_lesson(cfg_, entry, glossary, hist, workdir=None, next_entry=None, log=print, examples=None):
        if examples is None:  # as the real one: run the detector itself
            examples = lessons.DETECTORS[entry["detector"]].find(hist)
            if not examples:
                return {"held": f"{entry['id']}: no clean example"}
        made.append({"id": entry["id"], "examples": examples, "next": (next_entry or {}).get("id"),
                     "glossary": sorted(glossary)})
        wd = Path(workdir)
        wd.mkdir(parents=True, exist_ok=True)
        return {"videos": {"16x9": wd / "lesson_16x9.mp4", "9x16": wd / "lesson_9x16.mp4"},
                "thumbnail": wd / "thumbnail.jpg", "seconds": 120.0, "chapters": [], "workdir": wd,
                "examples": examples,
                "meta": {"title": f"Lesson {entry['id']}", "description": "d", "tags": [], "category_id": "27",
                         "fb_title": f"FB {entry['id']}", "fb_description": "fd"}}

    def fake_upload_lesson(video, meta, thumbnail, track_playlist, path_playlist, review_hours=24, notify=True,
                           log=print, playlist_privacy="public", playlists=True):
        yt.append({"video": Path(video).name, "title": meta["title"], "track": track_playlist,
                   "path": path_playlist, "review": review_hours, "playlists": playlists})
        return {"video_id": f"Y{len(yt)}", "publish_at": "2026-10-14T14:40:00.000Z", "thumbnail_set": True,
                "playlists": {}, "errors": []}

    def fake_publish_video(video, title, description, cfg_, published=True, poll_minutes=None, log=print):
        fb.append({"video": Path(video).name, "title": title, "published": published})
        if fail_fb[0]:
            e = RuntimeError("Facebook video V9 failed: bad codec")
            e.video_id = "V9"
            raise e
        return f"F{len(fb)}"

    def run(*argv) -> int:
        logs.clear()
        return app.main(list(argv))

    def said(text: str) -> bool:
        return any(text in m for m in logs)

    saved_det = dict(lessons.DETECTORS)
    saved = (app.ROOT, app.datetime, app.make_lesson, app.log, lesson_data.fetch_history, youtube.upload_lesson,
             facebook.publish_video, youtube.upload, youtube.set_thumbnail)
    env = {k: os.environ.get(k) for k in ("FB_PAGE_ID", "FB_PAGE_TOKEN")}
    for name in available:
        lessons.DETECTORS[name] = fake_detector(name)
    app.ROOT, app.datetime, app.make_lesson, app.log = tmp, FixedNow, fake_make_lesson, logs.append
    lesson_data.fetch_history, youtube.upload_lesson, facebook.publish_video = (fake_fetch, fake_upload_lesson,
                                                                                fake_publish_video)
    youtube.upload = youtube.set_thumbnail = lambda *a, **k: (_ for _ in ()).throw(AssertionError("daily upload"))
    os.environ["FB_PAGE_ID"], os.environ["FB_PAGE_TOKEN"] = "PAGE", "TOKEN"
    try:
        # disabled: timed and manual runs log why and stop before fetching; manual --no-upload still makes
        write_cfg(False)
        assert run("--session", "lesson", "--scheduled") == 0 and said("lessons.enabled is false"), logs
        assert run("--session", "lesson") == 0 and said("lessons.enabled is false"), logs
        assert not fetched and not made and not yt and not fb
        assert run("--session", "lesson", "--no-upload") == 0 and made[-1]["id"] == "swing-structure", logs
        assert not yt and not fb and not history()
        made.clear()
        fetched.clear()

        write_cfg(True)
        # wrong day: timed runs on Tuesday, Saturday and Sunday (the old lesson days) are skipped before
        # anything is fetched
        for day in (13, 17, 18):
            clock[0] = datetime(2026, 10, day, 15, 5, tzinfo=timezone.utc)
            assert run("--session", "lesson", "--scheduled") == 0 and said("runs only on thu;"), logs
        assert not fetched and not made

        # Thursday: episode 1 made once (examples from the hold check passed through), both platforms
        clock[0] = datetime(2026, 10, 15, 15, 5, tzinfo=timezone.utc)
        assert run("--session", "lesson", "--scheduled") == 0, logs
        assert [m["id"] for m in made] == ["swing-structure"] and made[0]["examples"], made
        assert made[0]["next"] == "bos-vs-choch" and len(fetched) == 1
        assert yt == [{"video": "lesson_16x9.mp4", "title": "Lesson swing-structure", "track": "Track 0 · Structure",
                       "path": "Trading Lessons · The Path", "review": 0, "playlists": False}], yt  # config default: public on upload
        assert fb == [{"video": "lesson_9x16.mp4", "title": "FB swing-structure", "published": True}], fb
        h = history()
        assert len(h) == 1 and h[0]["kind"] == "lesson" and h[0]["episode"] == "swing-structure", h
        assert h[0]["video_id"] == "Y1" and h[0]["fb_video_id"] == "F1" and h[0]["platforms"] == ["youtube", "facebook"]
        assert h[0]["session"] == "lesson" and h[0]["brief_date"] == "2026-10-15" and h[0]["counts"] is True
        assert h[0]["trigger"] == "timed", h[0]
        assert h[0]["examples"] == [{"asset": "BTC/USD", "timeframe": "1H", "start": region["start"],
                                     "end": region["end"]}], h[0]["examples"]  # identity only, no candles
        assert list((tmp / "output").glob("*/history_entry.json"))
        # the backup run of the same slot: everything is out → nothing fetched or made
        assert run("--session", "lesson", "--scheduled") == 0 and said("already published"), logs
        assert len(made) == 1 and len(fetched) == 1 and len(history()) == 1

        # next Thursday: episode 2's detector finds nothing → held (logged with its reason, not stored), episode 3 made
        clock[0] = datetime(2026, 10, 22, 15, 5, tzinfo=timezone.utc)
        available.discard("bos_choch")
        assert run("--session", "lesson", "--scheduled") == 0, logs
        assert said("Lesson bos-vs-choch held: no clean bos_choch example"), logs
        assert made[-1]["id"] == "top-down-reading" and made[-1]["next"] is None, made
        h = history()
        assert len(h) == 2 and h[1]["episode"] == "top-down-reading" and "held" not in json.dumps(h), h
        available.add("bos_choch")

        # the Thursday after: episode 2 is clean again; Facebook fails → YouTube id still logged, exit 1
        clock[0] = datetime(2026, 10, 29, 15, 5, tzinfo=timezone.utc)
        fail_fb[0] = True
        n_yt = len(yt)
        assert run("--session", "lesson", "--scheduled") == 1, logs
        assert said("Facebook lesson video failed") and said("V9") and said("Not published on: facebook"), logs
        h = history()
        assert len(h) == 3 and h[2]["episode"] == "bos-vs-choch" and h[2]["video_id"] == f"Y{n_yt + 1}", h
        assert not h[2].get("fb_video_id") and h[2]["platforms"] == ["youtube"]
        fail_fb[0] = False
        # a re-run while the recorded episode has no clean example now: can't be re-made → exit 1, said so
        available.discard("bos_choch")
        n_yt, n_fb, n_made = len(yt), len(fb), len(made)
        assert run("--session", "lesson", "--scheduled") == 1, logs
        assert said("recorded episode bos-vs-choch can't be re-made"), logs
        assert len(made) == n_made and len(fb) == n_fb and len(history()) == 3
        available.add("bos_choch")
        # the re-run of that slot: the recorded episode with its recorded example (a new one now ranks
        # first), Facebook only, a second entry
        other_first[0] = True
        assert run("--session", "lesson", "--scheduled") == 0, logs
        assert made[-1]["id"] == "bos-vs-choch" and [e["asset"] for e in made[-1]["examples"]] == ["BTC/USD"], made
        assert len(yt) == n_yt and len(fb) == n_fb + 1 and fb[-1]["title"] == "FB bos-vs-choch", (yt, fb)
        h = history()
        assert len(h) == 4 and h[3]["episode"] == "bos-vs-choch" and h[3]["fb_video_id"] and not h[3].get("video_id"), h
        assert h[3]["platforms"] == ["facebook"]
        other_first[0] = False
        # a third run: both platforms out → nothing made
        n_made = len(made)
        assert run("--session", "lesson", "--scheduled") == 0 and len(made) == n_made, logs

        # a later Thursday: every episode is published → "nothing to publish in this slot", exit 0, no entry
        clock[0] = datetime(2026, 11, 5, 15, 5, tzinfo=timezone.utc)
        n_fetch = len(fetched)
        assert run("--session", "lesson", "--scheduled") == 0 and said("nothing to publish in this slot"), logs
        assert len(made) == n_made and len(history()) == 4 and len(fetched) == n_fetch

        # all held (fresh history, no detector finds anything) → empty slot
        (tmp / "data" / "history.json").write_text(json.dumps({"videos": []}))
        available.clear()
        assert run("--session", "lesson", "--scheduled") == 0 and said("nothing to publish in this slot"), logs
        assert said("Lesson top-down-reading held") and len(made) == n_made and not history()
        available.update({"swings", "bos_choch", "top_down"})

        # empty curriculum → empty slot, nothing fetched
        (tmp / "lessons" / "curriculum.yaml").write_text("episodes: []\n", encoding="utf-8")
        n_fetch = len(fetched)
        assert run("--session", "lesson", "--scheduled") == 0 and said("the curriculum is empty"), logs
        assert len(fetched) == n_fetch and len(made) == n_made and not history()

        # curriculum problems → each logged, exit 1, nothing fetched or made
        (tmp / "lessons" / "curriculum.yaml").write_text(
            sample.replace("detector: swings", "detector: no_such_detector"), encoding="utf-8")
        assert run("--session", "lesson", "--scheduled") == 1, logs
        assert said("Curriculum problem: swing-structure: detector 'no_such_detector' is not registered"), logs
        assert len(fetched) == n_fetch and len(made) == n_made
        (tmp / "lessons" / "curriculum.yaml").write_text(sample, encoding="utf-8")

        # a manual run works on any day (Monday) and doesn't fill the slot
        clock[0] = datetime(2026, 11, 9, 9, 0, tzinfo=timezone.utc)
        assert run("--session", "lesson") == 0, logs
        h = history()
        assert len(h) == 1 and h[0]["episode"] == "swing-structure" and h[0]["trigger"] == "manual", h
        assert h[0]["counts"] is False and h[0]["video_id"] and h[0]["fb_video_id"]

        # Thursday, fresh history: the timed run gets YouTube up but Facebook fails
        clock[0] = datetime(2026, 11, 12, 15, 5, tzinfo=timezone.utc)
        (tmp / "data" / "history.json").write_text(json.dumps({"videos": []}))
        fail_fb[0] = True
        assert run("--session", "lesson", "--scheduled") == 1 and made[-1]["id"] == "swing-structure", logs
        fail_fb[0] = False
        # a manual run meanwhile takes the next unpublished episode (not the slot's), counts: false
        assert run("--session", "lesson") == 0 and made[-1]["id"] == "bos-vs-choch", logs
        # the backup timed run then publishes the slot's episode on Facebook once
        assert run("--session", "lesson", "--scheduled") == 0 and made[-1]["id"] == "swing-structure", logs
        h = history()
        assert [(v["episode"], v["platforms"], v["counts"]) for v in h] == [
            ("swing-structure", ["youtube"], True), ("bos-vs-choch", ["youtube", "facebook"], False),
            ("swing-structure", ["facebook"], True)], h
        assert len([v for v in h if v["episode"] == "swing-structure" and v.get("fb_video_id")]) == 1
        # a manual run after the slot is full still publishes (the next unpublished episode)
        n_yt, n_fb = len(yt), len(fb)
        assert run("--session", "lesson") == 0 and made[-1]["id"] == "top-down-reading", logs
        assert len(yt) == n_yt + 1 and len(fb) == n_fb + 1 and history()[-1]["counts"] is False
        # --force on the full slot: the recorded episode again on both platforms
        assert run("--session", "lesson", "--scheduled", "--force") == 0, logs
        assert made[-1]["id"] == "swing-structure" and len(yt) == n_yt + 2 and len(fb) == n_fb + 2, (yt, fb)

        # ── top-ups (crypto-pivot weekly floor): --slot <session> fills another edition's slot ──
        (tmp / "data" / "history.json").write_text(json.dumps({"videos": []}))
        clock[0] = datetime(2026, 11, 19, 15, 5, tzinfo=timezone.utc)  # Thursday: episode 1 in the lesson slot
        assert run("--session", "lesson", "--scheduled") == 0 and made[-1]["id"] == "swing-structure", logs
        clock[0] = datetime(2026, 11, 21, 15, 5, tzinfo=timezone.utc)  # Saturday
        # lessons off: a top-up is gated like any lesson run
        write_cfg(False)
        n_made, n_fetch = len(made), len(fetched)
        assert run("--session", "lesson", "--slot", "recap") == 0 and said("lessons.enabled is false"), logs
        write_cfg(True)
        # the timed lesson run is skipped on Saturday; the top-up into the recap slot makes the next episode
        assert run("--session", "lesson", "--scheduled") == 0 and said("runs only on thu;"), logs
        assert len(made) == n_made and len(fetched) == n_fetch
        n_yt, n_fb = len(yt), len(fb)
        assert run("--session", "lesson", "--scheduled", "--slot", "recap") == 0, logs
        assert said("Top-up") and made[-1]["id"] == "bos-vs-choch", (logs, made)
        assert len(yt) == n_yt + 1 and len(fb) == n_fb + 1, (yt, fb)  # the lesson's platforms, not the slot's
        h = history()
        assert [(v["episode"], v["session"], v["brief_date"], v["trigger"], v["counts"]) for v in h] == [
            ("swing-structure", "lesson", "2026-11-19", "timed", True),
            ("bos-vs-choch", "recap", "2026-11-21", "topup", True)], h
        # the same slot again (timer + backup, or a second call): nothing fetched or made
        n_made, n_fetch = len(made), len(fetched)
        assert run("--session", "lesson", "--slot", "recap") == 0 and said("already published"), logs
        assert len(made) == n_made and len(fetched) == n_fetch and len(history()) == 2
        # Sunday's slot: the next unpublished episode, never one already out
        clock[0] = datetime(2026, 11, 22, 15, 5, tzinfo=timezone.utc)
        assert run("--session", "lesson", "--slot", "recap") == 0 and made[-1]["id"] == "top-down-reading", logs
        assert [v["episode"] for v in history()] == ["swing-structure", "bos-vs-choch", "top-down-reading"]
        # every episode out: another slot's top-up publishes nothing (no repeat)
        n_made = len(made)
        assert run("--session", "lesson", "--slot", "basics") == 0 and said("nothing to publish in this slot"), logs
        assert len(made) == n_made and len(history()) == 3
        # a slot that already holds another edition's upload is left alone (nothing fetched)
        clock[0] = datetime(2026, 11, 28, 15, 5, tzinfo=timezone.utc)
        (tmp / "data" / "history.json").write_text(json.dumps({"videos": [
            {"brief_date": "2026-11-28", "session": "recap", "kind": "recap", "video_id": "R1", "counts": True}]}))
        n_fetch = len(fetched)
        assert run("--session", "lesson", "--slot", "recap") == 0 and said("already published a recap upload"), logs
        assert len(made) == n_made and len(fetched) == n_fetch and len(history()) == 1
        # a top-up whose Facebook upload fails: the same slot's re-run re-makes its episode, Facebook only
        fail_fb[0] = True
        assert run("--session", "lesson", "--slot", "basics") == 1 and made[-1]["id"] == "swing-structure", logs
        fail_fb[0] = False
        n_yt, n_fb = len(yt), len(fb)
        assert run("--session", "lesson", "--slot", "basics") == 0 and made[-1]["id"] == "swing-structure", logs
        assert len(yt) == n_yt and len(fb) == n_fb + 1, (yt, fb)
        assert [(v["episode"], v["session"], v["platforms"]) for v in history()[1:]] == [
            ("swing-structure", "basics", ["youtube"]), ("swing-structure", "basics", ["facebook"])], history()
        # the next Thursday's timed run takes the episode after it (the top-up's episode isn't repeated)
        clock[0] = datetime(2026, 12, 3, 15, 5, tzinfo=timezone.utc)
        assert run("--session", "lesson", "--scheduled") == 0 and made[-1]["id"] == "bos-vs-choch", logs
        # bad top-ups: unknown slot, or an edition other than the lesson → exit 1, nothing made
        n_made = len(made)
        assert run("--session", "lesson", "--slot", "nope") == 1 and said("Unknown slot 'nope'"), logs
        assert run("--session", "news_morning", "--slot", "recap") == 1 and said("--slot works only with"), logs
        assert run("--session", "lesson", "--slot", "news_evening") == 1 and said("a Facebook news post"), logs
        assert len(made) == n_made
    finally:
        lessons.DETECTORS.clear()
        lessons.DETECTORS.update(saved_det)
        (app.ROOT, app.datetime, app.make_lesson, app.log, lesson_data.fetch_history, youtube.upload_lesson,
         facebook.publish_video, youtube.upload, youtube.set_thumbnail) = saved
        for k, v in env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    # history merge: an entry with only fb_video_id is idempotent by it and counts as Facebook
    hist = History(tmp / "merge.json")
    e = {"brief_date": "2026-10-13", "session": "lesson", "kind": "lesson", "episode": "x", "fb_video_id": "F9"}
    assert hist.add(dict(e)) and not hist.add(dict(e)) and len(hist.data["videos"]) == 1
    assert hist.published_on("2026-10-13", "lesson", "facebook") and not hist.published_on("2026-10-13", "lesson", "youtube")
    assert len(hist.uploaded()) == 1

    # cron-job.org: lesson (Thursday 15:00 UTC), basics and recap on their days, the rest every day
    sessions = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))["sessions"]
    # as setup_cronjobs.main: only editions with a start_utc get a job (evergreen has none: epic 5 calls it)
    wd = {k: setup_cronjobs.job_for(k, s, "T", True)["schedule"]["wdays"] for k, s in sessions.items()
          if s.get("start_utc")}
    assert "evergreen" in sessions and "evergreen" not in wd, wd
    assert wd["lesson"] == [4] and "gold" not in wd and "asia" not in wd and wd["short_a"] == [-1], wd
    job = setup_cronjobs.job_for("lesson", sessions["lesson"], "T", True)["schedule"]
    assert (job["hours"], job["minutes"]) == ([15], [0]) and sessions["lesson"]["start_utc"] == "15:00", job
    assert wd["basics"] == [3], wd
    assert wd["recap"] == [6], wd  # the Saturday recap (dark until recap.enabled; epic 5 wires the timer)
    assert all(v == [-1] for k, v in wd.items() if k not in ("lesson", "basics", "recap", "topup_sun")), wd
    # workflow: the lesson's backup cron (17 min after 15:00, Thursday) maps to `lesson` in EDITION and
    # concurrency.group; the old Tue/Thu/Sat/Sun line is gone; the `slot` input reaches --slot
    text = (ROOT / ".github" / "workflows" / "autopilot.yml").read_text(encoding="utf-8")
    wf = yaml.safe_load(text)
    on = wf.get("on", wf.get(True))
    assert {"cron": "17 15 * * 4"} in on["schedule"] and "0,2,4,6" not in text and "47 14" not in text, on
    job = wf["jobs"]["make-and-upload"]
    assert "'17 15 * * 4' && 'lesson'" in job["concurrency"]["group"]
    assert job["concurrency"]["group"].startswith("${{ inputs.slot && format('topup-{0}', inputs.slot) || ")
    assert "Manual" in wf["run-name"] and "slot {0}" in wf["run-name"]
    step = next(x for x in job["steps"] if x.get("name") == "Make and publish")
    assert "'17 15 * * 4' && 'lesson'" in step["env"]["EDITION"]
    assert "--slot=" in step["env"]["SLOT"] and '${SLOT:+"$SLOT"}' in step["run"], step
    assert on["workflow_dispatch"]["inputs"]["slot"]["type"] == "string"
    shutil.rmtree(tmp, ignore_errors=True)
    print("OK lesson edition (Thursday days, disabled, both platforms, guard, held, FB failure + recorded-episode "
          "re-run, empty slot, curriculum problems, manual any day, --slot top-ups, fb_video_id merge, cron days, "
          "workflow)")


DIAGRAM_SAMPLE = ROOT / "output" / "basics-diagram-sample"  # the owner's look check (hitl): contact sheets


def _sample_narration() -> dict:
    """tests/basics/sample_narration.yaml: scene id → text naming every diagram part in reveal order."""
    raw = yaml.safe_load((ROOT / "tests" / "basics" / "sample_narration.yaml").read_text(encoding="utf-8"))
    return {k: " ".join(str(v).split()) for k, v in raw.items()}


def _topic_narration(topic: dict) -> dict:
    """A mocked narration of any Basics topic: scene id → text (each point's approved text, then every diagram
    part named in reveal order; the recap carries the disclaimer). Passes rules.narration_problems."""
    from autopilot import diagrams
    out = {"hook": f"{topic['question'].split(' (')[0]} Here is the simple version, one idea at a time."}
    for n, p in enumerate(topic["points"], 1):
        names = [st["name"] for st in diagrams.steps(p["diagram"])] if p.get("diagram") else []
        out[f"point_{n}"] = " ".join(p["text"].split()) + (
            " The picture names each part: " + ", then ".join(names) + "." if names else "")
    out["recap"] = "That is the whole idea, step by step. This is education, not financial advice."
    return out


def _extra_diagrams() -> list[dict]:
    """Points beyond the sample (test only): a timeline with two notes, a five-node flow with BTC / ETH / other-coin
    badges and a note, a four-row compare with a coin on each side, and a point without a diagram."""
    return [
        {"term": "Timeline", "text": "How a fund comes to trade, in order.",
         "diagram": {"type": "timeline", "events": [
             {"label": "Fund launches", "say": ["launches"]},
             {"label": "Fund buys bitcoin", "note": "held by a custodian", "say": ["buys"]},
             {"label": "Shares list on the exchange", "say": ["list"]},
             {"label": "Investors trade shares", "say": ["investors"]},
             {"label": "Fees come out yearly", "say": ["fees"]}],
             "notes": [{"text": "A drawing of the order, not dates", "say": ["order"]},
                       {"text": "Each step follows the last", "say": ["each step"]}]}},
        {"term": "Many coins", "text": "A flow with several coins.",
         "diagram": {"type": "flow", "nodes": [
             {"label": "Bitcoin", "coin": "BTC", "say": ["bitcoin"]},
             {"label": "Ether", "coin": "ETH", "arrow": "and", "say": ["ether"]},
             {"label": "Another token", "coin": "ABCDE", "say": ["token"]},
             {"label": "An exchange", "note": "where coins trade", "say": ["exchange"]},
             {"label": "Wallet", "arrow": "into", "say": ["wallet"]}],
             "notes": [{"text": "Badges are drawn, never images", "say": ["badges"]}]}},
        {"term": "Two coins", "text": "Bitcoin against ether.",
         "diagram": {"type": "compare", "left": {"label": "Bitcoin", "coin": "BTC", "say": ["bitcoin"]},
                     "right": {"label": "Ether", "coin": "ETH", "say": ["ether"]},
                     "rows": [{"left": "First coin", "right": "Second network", "say": ["first"]},
                              {"left": "Fixed supply rules", "right": "Smart contracts", "say": ["contracts"]},
                              {"left": "Blocks", "right": "Blocks", "say": ["blocks"]},
                              {"left": "Wallet", "right": "Wallet", "say": ["wallet"]}]}},
        {"term": "No diagram", "text": "A point without a diagram keeps the text concept slide."},
    ]


def test_diagrams(cfg):
    """Drawn concept diagrams (crypto-basics entry 2): the sample topic's diagrams validate; each malformed
    spec gets its one reason (draw and scene_plan raise); reveal order; every type (flow, compare, timeline,
    coin badges, notes) in both shapes: slide size, caption band untouched, nothing outside the content box,
    text ≥ min_text, deterministic, base + layers == the full slide; text that can't fit → ValueError naming
    the diagram; a point without a diagram keeps the text slide; the sample narration reveals every part on
    the sentence naming it (no fallback, times increasing) in both shapes; per-step contact sheets →
    output/test_diagrams/ (copied to output/basics-diagram-sample/ for the owner)."""
    from unittest import mock
    from PIL import Image, ImageChops
    from autopilot import basics, diagrams, lesson_slides as ls, reveal

    accent = (255, 212, 0)
    bg = (14, 15, 18)
    topic = basics.sample_topic()
    narration = _sample_narration()
    for p in topic["points"]:
        assert p.get("diagram") and diagrams.validate(p["diagram"]) == [], (p["term"], diagrams.validate(p.get("diagram")))
    assert [p["diagram"]["type"] for p in topic["points"]] == ["flow", "flow", "flow", "compare"]
    assert [n["label"] for n in topic["points"][0]["diagram"]["nodes"]] == ["Fund", "Shares", "Stock exchange"]
    assert [n.get("coin") for n in topic["points"][1]["diagram"]["nodes"]] == [None, "BTC", None]
    assert "fees" in topic["points"][1]["diagram"]["notes"][0]["say"]
    assert "shareholders" in topic["points"][2]["diagram"]["notes"][0]["say"]

    # malformed specs: one reason each; draw raises ValueError with it
    node = {"label": "Fund", "say": ["fund"]}
    flow = {"type": "flow", "nodes": [node, {"label": "Shares", "say": ["shares"], "arrow": "split"}]}
    cmp_ = {"type": "compare", "left": {"label": "A", "say": ["a"]}, "right": {"label": "B", "say": ["b"]},
            "rows": [{"left": "x", "right": "y", "say": ["x"]}]}
    bad = {
        "unknown type": ({"type": "pie", "nodes": flow["nodes"]}, "type 'pie'"),
        "empty say": (dict(flow, nodes=[node, dict(flow["nodes"][1], say=[])]), "nodes[1]: say must be a non-empty"),
        "empty alias": (dict(flow, nodes=[node, dict(flow["nodes"][1], say=[" "])]), "empty alias"),
        "digit in say": (dict(flow, nodes=[dict(node, say=["top 10 fund"]), flow["nodes"][1]]), "has a digit"),
        "six nodes": (dict(flow, nodes=[dict(node, label=f"Part {c}") for c in "ABCDEF"]), "2-5 nodes (got 6)"),
        "bad coin": (dict(flow, nodes=[dict(node, coin="btc"), flow["nodes"][1]]), "coin 'btc'"),
        "coin with a newline": (dict(flow, nodes=[dict(node, coin="BTC\n"), flow["nodes"][1]]), "2-5 uppercase"),
        "long coin": (dict(flow, nodes=[dict(node, coin="BITCOIN"), flow["nodes"][1]]), "2-5 uppercase"),
        "arrow into the first node": (dict(flow, nodes=[dict(node, arrow="from"), flow["nodes"][1]]), "incoming arrow"),
        "empty label": (dict(flow, nodes=[dict(node, label=""), flow["nodes"][1]]), "nodes[0]: empty label"),
        "unknown key": (dict(flow, nodes=[dict(node, colour="red"), flow["nodes"][1]]), "unknown key(s) colour"),
        "three notes": (dict(flow, notes=[{"text": "A", "say": ["a"]}] * 3), "at most 2"),
        "five rows": (dict(cmp_, rows=cmp_["rows"] * 5), "1-4 rows (got 5)"),
        "empty cell": (dict(cmp_, rows=[dict(cmp_["rows"][0], right="")]), "rows[0]: empty right"),
        "one event": ({"type": "timeline", "events": [{"label": "A", "say": ["a"]}]}, "2-5 events (got 1)"),
        "coin on an event": ({"type": "timeline", "events": [{"label": "A", "say": ["a"], "coin": "BTC"},
                                                             {"label": "B", "say": ["b"]}]}, "unknown key(s) coin"),
    }
    for name, (spec, reason) in bad.items():
        got = diagrams.validate(spec)
        assert len(got) == 1 and reason in got[0], (name, got)
        try:
            diagrams.draw(Image.new("RGB", (1920, 1080)), ls.LANDSCAPE.content_box, spec, ls.LANDSCAPE, accent, who="bad one")
            raise AssertionError(f"{name}: a malformed diagram must not draw")
        except ValueError as e:
            assert "bad one" in str(e) and reason in str(e), (name, e)
    broken = json.loads(json.dumps(topic))
    broken["points"][2]["diagram"]["nodes"][0]["say"] = ["one 2 three"]
    try:
        basics.scene_plan(broken)
        raise AssertionError("an invalid point diagram must stop the plan")
    except ValueError as e:
        assert f"{topic['id']} point 3 diagram" in str(e) and "digit" in str(e), e

    # reveal order = spec order; names = the say aliases (first = name); the plan asks for that naming order
    s = diagrams.steps(topic["points"][1]["diagram"])
    assert [x["key"] for x in s] == ["node_1", "node_2", "node_3", "note_1"], s
    assert [x["items"] for x in s] == [["node:0"], ["arrow:1", "node:1"], ["arrow:2", "node:2"], ["note:0"]], s
    assert s[1]["name"] == "actual bitcoin" and s[1]["names"] == ["actual bitcoin", "real bitcoin"], s
    s = diagrams.steps(topic["points"][3]["diagram"])
    assert [x["key"] for x in s] == ["left", "right", "row_1", "row_2", "row_3"], s
    assert s[2]["items"] == ["row:0:left", "row:0:right"] and s[0]["items"] == ["left"], s
    s = diagrams.steps(_extra_diagrams()[0]["diagram"])
    assert [x["items"] for x in s][:3] == [["event:0"], ["segment:1", "event:1"], ["segment:2", "event:2"]], s
    assert [x["key"] for x in s][-2:] == ["note_1", "note_2"], s
    assert diagrams.naming_order(topic["points"][0]["diagram"]) == '"fund", "shares", "stock exchange"'
    plan = basics.scene_plan(topic)
    assert '"fund", "shares", "stock exchange"' in plan[1]["covers"] and ".." not in plan[1]["covers"], plan[1]["covers"]
    assert plan[1]["visual"]["diagram"] == topic["points"][0]["diagram"]
    assert "diagram parts" in basics._prompt(cfg, topic, plan)

    # every type in both shapes
    work = ROOT / "output" / "test_diagrams"
    shutil.rmtree(work, ignore_errors=True)
    shutil.rmtree(DIAGRAM_SAMPLE, ignore_errors=True)
    DIAGRAM_SAMPLE.mkdir(parents=True)
    extra = dict(topic, points=topic["points"] + _extra_diagrams())
    xplan = basics.scene_plan(extra)
    assert "diagram" not in xplan[-2]["visual"] and xplan[-2]["visual"]["text"]
    sizes = []
    real_font = diagrams._font

    def font(size, bold=False):
        sizes.append(size)
        return real_font(size, bold)
    sheets = []
    for L in (ls.LANDSCAPE, ls.PORTRAIT):
        sizes.clear()
        with mock.patch.object(diagrams, "_font", font):
            pics = basics.render_slides(cfg, extra, xplan, L, work / L.name)
        assert sizes and min(sizes) >= L.min_text, (L.name, min(sizes))
        again = basics.render_slides(cfg, extra, xplan, L, work / f"{L.name}_again")
        chrome = basics._base(basics._ctx(cfg, extra, L))[0]  # brand, chip, rule, footer: no content
        x0, y0, x1, y1 = L.content_box
        for p, q, sc in zip(pics, again, xplan):
            v = sc["visual"]
            with Image.open(p["image"]) as im:
                full = im.convert("RGB")
            assert full.size == (L.w, L.h), (L.name, full.size)
            band = full.crop((0, L.caption_band[0], L.w, L.caption_band[1]))
            assert band.getextrema() == tuple((c, c) for c in bg), (L.name, sc["id"], "caption band drawn into")
            assert Path(p["image"]).read_bytes() == Path(q["image"]).read_bytes(), (L.name, sc["id"])
            if v["type"] != "concept":
                continue
            if not v.get("diagram"):  # the text concept slide, no steps
                assert "steps" not in p and "base" not in p, p
                continue
            ink = ImageChops.difference(full, chrome).getbbox()
            assert ink and x0 <= ink[0] and y0 <= ink[1] and ink[2] <= x1 and ink[3] <= y1, (L.name, sc["id"], ink)
            boxes = diagrams.draw(Image.new("RGB", (L.w, L.h), bg), L.content_box, v["diagram"], L, accent)
            assert all(x0 <= b[0] and y0 <= b[1] and b[2] <= x1 and b[3] <= y1 for b in boxes.values()), boxes
            want = diagrams.steps(v["diagram"])
            assert [st["key"] for st in p["steps"]] == [st["key"] for st in want], (L.name, sc["id"])
            assert [len(st["layers"]) for st in p["steps"]] == [len(st["items"]) for st in want], (L.name, sc["id"])
            assert Path(p["base"]).read_bytes() == Path(q["base"]).read_bytes()
            for a, b in zip(p["steps"], q["steps"]):
                for la, lb in zip(a["layers"], b["layers"]):
                    assert la["xy"] == lb["xy"] and Path(la["image"]).read_bytes() == Path(lb["image"]).read_bytes()
            with Image.open(p["base"]) as im:
                comp = im.convert("RGB")
            assert comp.crop((x0, y0, x1, y1)).tobytes() != full.crop((x0, y0, x1, y1)).tobytes()
            frames = [work / f"{L.name}_{sc['id']}_0.png"]
            comp.save(frames[0])
            for k, st in enumerate(p["steps"], 1):  # base + each step's layers, pasted in order
                for ly in st["layers"]:
                    with Image.open(ly["image"]) as im:
                        comp.paste(im.convert("RGB"), tuple(ly["xy"]))
                frames.append(work / f"{L.name}_{sc['id']}_{k}.png")
                comp.save(frames[-1])
            assert comp.tobytes() == full.tobytes(), (L.name, sc["id"], "base + layers != full slide")
            cell = (480, 270) if L.name == "16x9" else (270, 480)
            sheet = _contact(frames, cell, min(len(frames), 4 if L.name == "16x9" else 6),
                             work / f"contact_{L.name}_{sc['id']}.png")
            shutil.copy(sheet, DIAGRAM_SAMPLE / sheet.name)
            sheets.append(sheet)
            for f in frames:
                f.unlink()
        shutil.rmtree(work / f"{L.name}_again")

    # text that can't fit at the minimum size → ValueError naming the diagram (never cut or shrunk below min)
    for label in ("Supercalifragilisticexpialidociouslyunbreakableword" * 2, "a fairly long label " * 80):
        long = dict(topic, points=[dict(topic["points"][0], diagram={"type": "flow", "nodes": [
            node, {"label": label, "say": ["shares"]}]})])
        for L in (ls.LANDSCAPE, ls.PORTRAIT):
            try:
                basics.render_slides(cfg, long, basics.scene_plan(long), L, work / "long")
                raise AssertionError("a diagram that can't fit must fail")
            except ValueError as e:
                assert f"{topic['id']} point 1 diagram" in str(e) and "doesn't fit" in str(e), e
    shutil.rmtree(work / "long", ignore_errors=True)

    # the sample narration reveals every part on the sentence naming it, in order, in both shapes
    assert not rules.narration_problems("\n".join(narration.values())), rules.narration_problems("\n".join(narration.values()))
    assert set(narration) == {p["id"] for p in plan}, narration.keys()
    scenes = [{"id": p["id"], "text": narration[p["id"]]} for p in plan]
    audio = []
    for sc in scenes:
        words = sc["text"].split()
        audio.append({"duration": 0.3 * len(words) + 0.5, "words": [(j * 0.3, j * 0.3 + 0.27, w) for j, w in enumerate(words)]})
    for L in (ls.LANDSCAPE, ls.PORTRAIT):
        pics = basics.render_slides(cfg, topic, plan, L, work / f"narr_{L.name}")
        logs = []
        reveal.time_steps(pics, scenes, audio, log=logs.append)
        assert [m.split(":")[0] for m in logs] == [f"Step reveal point_{n}" for n in range(1, 5)], logs
        assert not any("(fallback)" in m for m in logs), logs
        for p, sc, a in zip(pics, scenes, audio):
            if not p.get("steps"):
                continue
            sents = reveal.split_sentences(sc["text"])
            starts = reveal.sentence_starts(sc["text"], a["words"], a["duration"])
            at = reveal.step_sentences([st["names"] for st in p["steps"]], sents)
            assert at == sorted(at), (sc["id"], at)
            for st, k in zip(p["steps"], at):
                assert reveal.names_in(sents[k], st["names"]), (sc["id"], st["key"], sents[k])
                assert abs(st["layers"][0]["at"] - starts[k]) < 0.05, (sc["id"], st["key"], st["layers"][0]["at"], starts[k])
            ats = [ly["at"] for st in p["steps"] for ly in st["layers"]]
            assert all(b - a_ >= reveal.MIN_GAP - 1e-6 for a_, b in zip(ats, ats[1:])), (sc["id"], ats)
            assert ats[-1] + reveal.FADE < a["duration"], (sc["id"], ats)
        shutil.rmtree(work / f"narr_{L.name}")

    # a part the narration never names: not a script problem (the edition continues); it reveals on the
    # sentence after its predecessor's and the step reveal logs "(fallback)"
    skip = dict(narration, point_1="An exchange-traded fund, or ETF, is a fund. It is split into equal parts, "
                                   "just like a company. Those parts trade on a regular stock exchange.")
    sk_scenes = [{"id": p["id"], "text": skip[p["id"]]} for p in plan]
    assert not rules.narration_problems(skip["point_1"])
    wide = dict(cfg, basics={"min_words": 1, "max_words": 10 ** 4})
    assert basics.check_script(wide, plan, basics._with_ask(wide, plan, sk_scenes)) == []
    sk_audio = [{"duration": 0.3 * len(s["text"].split()) + 0.5,
                 "words": [(j * 0.3, j * 0.3 + 0.27, w) for j, w in enumerate(s["text"].split())]} for s in sk_scenes]
    pics = basics.render_slides(cfg, topic, plan, ls.LANDSCAPE, work / "skip")
    logs = []
    reveal.time_steps(pics, sk_scenes, sk_audio, log=logs.append)
    p1 = next(m for m in logs if m.startswith("Step reveal point_1"))
    assert "node_2 → sentence 2 (fallback)" in p1 and "node_3 → sentence 3" in p1, p1
    assert "node_1 → sentence 1" in p1 and p1.count("(fallback)") == 1, p1
    ats = [ly["at"] for st in pics[1]["steps"] for ly in st["layers"]]
    assert ats == sorted(ats) and all("at" in ly for st in pics[1]["steps"] for ly in st["layers"]), ats
    shutil.rmtree(work / "skip")
    shutil.rmtree(work / "16x9", ignore_errors=True)
    shutil.rmtree(work / "9x16", ignore_errors=True)
    print(f"OK diagrams: validate (one reason each), steps order, flow/compare/timeline + coin badges + notes in "
          f"16x9 and 9x16 (caption band clear, inside the content box, deterministic, base + layers == full), "
          f"too long → ValueError, sample narration reveals in order with no fallback · {len(sheets)} contact "
          f"sheets in {work.relative_to(ROOT)} and {DIAGRAM_SAMPLE.relative_to(ROOT)}")


def test_basics_topics(cfg):
    """The Basics topic list (crypto-basics entry 3): basics/topics.yaml ships four builder drafts that validate
    and are all `approved: false`; each I/O-matrix problem gets its reason (dated question, long thumbnail,
    price target in a point, malformed diagram, missing field / bad types, duplicate id / question); the
    picker takes the first approved topic no uploaded basics entry has published (drafts, published, manual
    non-counting publishes skipped; an entry without a platform id isn't a publish) and returns None while
    nothing is approved; every draft's point scenes render in 16:9 and 9:16 (diagrams fit)."""
    import copy
    from PIL import Image
    from autopilot import basics, diagrams, lesson_slides as ls

    topics = basics.load_topics()
    assert basics.validate_topics(topics) == [], basics.validate_topics(topics)
    assert [t["id"] for t in topics] == ["what-is-bitcoin-and-how-does-it-work", "ethereum-vs-bitcoin",
                                         "what-is-the-lightning-network", "bitcoin-mining-explained"]
    assert all(t["approved"] is False for t in topics), [t["approved"] for t in topics]
    assert "DRAFT" in basics.TOPICS.read_text(encoding="utf-8")
    for t in topics:  # drafts: no digits anywhere in the content, 3-5 points, a diagram on every point
        assert not any(ch.isdigit() for ch in json.dumps(t)), t["id"]
        assert 3 <= len(t["points"]) <= 5 and all(p.get("diagram") for p in t["points"]), t["id"]
        assert set(t) == set(basics.TOPIC_FIELDS), t["id"]

    # each matrix row: its reason
    base = topics[0]

    def problems(edit) -> list[str]:
        t = copy.deepcopy(base)
        edit(t)
        return basics.validate_topic(t)

    def one(edit, *words) -> str:
        got = problems(edit)
        assert len(got) == 1 and all(w in got[0] for w in words), (words, got)
        return got[0]

    got = problems(lambda t: t.update(question="Bitcoin ETF Explained (October 2026)?"))
    assert got and all(r.startswith("question date:") for r in got), got
    one(lambda t: t.update(thumbnail="WHAT IS A BITCOIN ETF"), "thumbnail words", "(5, allowed 1-3)")
    one(lambda t: t["points"][0].update(text="Bitcoin to $150,000 soon."), "point 1 text", "price target")
    one(lambda t: t["points"][1].update(diagram={"type": "pie", "nodes": []}), "point 2 diagram", "type 'pie'")
    one(lambda t: t.pop("thumbnail"), "missing field 'thumbnail'")
    one(lambda t: t.update(approved="yes"), "approved must be true or false")
    one(lambda t: t["points"][2].pop("diagram"), "point 3: missing field 'diagram'")
    one(lambda t: t.pop("summary"), "missing field 'summary'")
    one(lambda t: t.update(colour="red"), "unknown key(s) colour")
    one(lambda t: t["points"][0].update(digram={}), "point 1: unknown key(s) digram")
    one(lambda t: t.update(id="What_Is_Bitcoin"), "not a kebab-case slug")
    one(lambda t: t.update(question="What is bitcoin"), 'no "?"')
    one(lambda t: t.update(question="What Is Bitcoin? " + "Really " * 15), "characters (at most 100)")
    one(lambda t: t.update(points=[]), "points must be a non-empty list")
    one(lambda t: t.update(points=t["points"][:3]), "3 points (at least 4")  # Shorts material: 5 segments
    one(lambda t: t.update(summary="Analysts could hit $100k soon."), "summary", "price target")
    one(lambda t: t["points"][0].update(term="My favourite coin"), "point 1 term", "first person")
    one(lambda t: t.update(thumbnail="BITCOIN #BTC"), "thumbnail hashtag")
    one(lambda t: t.update(thumbnail=True), "thumbnail must be non-empty text (got True)")  # YAML `yes`
    one(lambda t: t["points"][0].update(term=2024), "point 1: term must be non-empty text (got 2024)")
    assert basics.validate_topic("not a topic") == ["topic must be a mapping"]
    same_id = dict(copy.deepcopy(topics[1]), id=base["id"])
    got = basics.validate_topics([base, same_id])
    assert got == [f"{base['id']}: duplicate id"], got
    same_q = dict(copy.deepcopy(topics[1]), question="  what is BITCOIN and how   does it WORK? (explained simply) ")
    got = basics.validate_topics([base, same_q])
    assert got == [f"ethereum-vs-bitcoin: duplicate question (same as {base['id']})"], got
    got = basics.validate_topics([base, copy.deepcopy(base)])  # same id and question: the earlier one by position
    assert got == [f"{base['id']}: duplicate id", f"{base['id']}: duplicate question (same as #1)"], got
    assert basics.validate_topics({"topics": []}) == ["topics must be a list"]
    bad_file = Path(tempfile.mkdtemp()) / "topics.yaml"
    bad_file.write_text("- id: x\n", encoding="utf-8")
    try:
        basics.load_topics(bad_file)
        raise AssertionError("a file without a `topics:` list must not load")
    except ValueError as e:
        assert "topics" in str(e), e

    # picker: list order = queue; only approved: true; a published topic is never repeated
    tmp = Path(tempfile.mkdtemp())

    def hist(*entries) -> History:
        h = History(tmp / "history.json")
        h.data = {"videos": [dict(e) for e in entries]}
        return h

    assert basics.pick(topics, hist()) is None  # all drafts
    a, b, c, d, e = (dict(copy.deepcopy(base), id=f"topic-{k}", approved=True) for k in "abcde")
    queue = [dict(topics[0]), a, b, c, d, e]
    assert basics.pick(queue, hist())["id"] == "topic-a"
    h = hist({"kind": "basics", "topic": "topic-a", "video_id": "Y1"},  # published (counting)
             {"kind": "basics", "topic": "topic-b", "fb_video_id": "F1", "counts": False},  # manual publish
             {"kind": "basics", "topic": "topic-c"},  # made but never reached a platform
             {"kind": "lesson", "episode": "topic-c", "topic": "topic-c", "video_id": "Y2"})  # not a basics entry
    assert basics.pick(queue, h)["id"] == "topic-c"
    h.data["videos"].append({"kind": "basics", "topic": "topic-c", "video_id": "Y3"})
    assert basics.pick(queue, h)["id"] == "topic-d"
    assert basics.pick([dict(d, approved="yes"), e], h)["id"] == "topic-e"  # only `approved is True`
    assert basics.pick([a, b], h) is None
    assert basics.pick([dict(a, id=None)], hist({"kind": "basics", "video_id": "Y9"}))["id"] is None  # no `topic`

    # every draft's point scenes render in both shapes; each diagram fits (no ValueError) with its steps
    work = ROOT / "output" / "test_basics_topics"
    shutil.rmtree(work, ignore_errors=True)
    bg = (14, 15, 18)
    scenes = 0
    for t in topics:
        plan = basics.scene_plan(t)
        for L in (ls.LANDSCAPE, ls.PORTRAIT):
            pics = basics.render_slides(cfg, t, plan, L, work / t["id"] / L.name)
            for p, sc in zip(pics, plan):
                with Image.open(p["image"]) as im:
                    full = im.convert("RGB")
                assert full.size == (L.w, L.h), (t["id"], L.name, sc["id"])
                band = full.crop((0, L.caption_band[0], L.w, L.caption_band[1]))
                assert band.getextrema() == tuple((c_, c_) for c_ in bg), (t["id"], L.name, sc["id"])
                if sc["visual"]["type"] == "concept":
                    want = diagrams.steps(sc["visual"]["diagram"])
                    assert [st["key"] for st in p["steps"]] == [st["key"] for st in want], (t["id"], L.name, sc["id"])
                    scenes += 1
    shutil.rmtree(work, ignore_errors=True)
    print(f"OK basics topics: basics/topics.yaml validates ({len(topics)} drafts, none approved), each matrix "
          f"problem gets its reason, picker (drafts / published / manual / no platform id / kind) and "
          f"{scenes} point scenes rendered in 16x9 + 9x16")


def test_basics_script(cfg):
    """Basics narration (crypto-basics entry 5) with the real 600-900 word budget (4-6 minutes): the subscribe
    ask closes the first payoff scene exactly once; a draft that puts a subscribe ask elsewhere or says "I'm
    buying" is discarded 3 times and the narration fails; the passing draft is fact-checked against the topic's
    approved points only (the ask not sent): a reject or a spoken number the points don't hold stops it at
    once (no retry); a revised draft is used, with the ask added back."""
    from autopilot import basics

    topic = basics.sample_topic()
    plan = basics.scene_plan(topic)
    live = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    bc = live["basics"]
    assert (bc["min_words"], bc["max_words"]) == (600, 900) and bc["max_seconds"] <= 390, bc
    ask = basics.subscribe_ask(live)
    assert ask == bc["subscribe_ask"] and "subscribe" in ask.lower() and not rules.narration_problems(ask)
    long = _sample_narration()  # padded to the real budget with the points' own approved text
    n = 1
    while sum(len(v.split()) for v in long.values()) < 640:
        long[f"point_{n}"] += " " + " ".join(topic["points"][n - 1]["text"].split())
        n = n % len(topic["points"]) + 1
    answers, calls, checks = [], [], []
    verdict = ["ok", None]

    def fake_llm(prompt, models, temperature=0.9):
        calls.append(prompt)
        return {"scenes": [{"id": k, "text": v} for k, v in answers[min(len(calls), len(answers)) - 1].items()]}

    def fake_fact_check(cfg_, facts, pkg, extra_rules=""):
        checks.append((cfg_, facts, json.loads(json.dumps(pkg)), extra_rules))
        return verdict[0], (verdict[1] or pkg), (["fixed"] if verdict[0] != "ok" else [])

    saved = (basics.generate_json, basics.fact_check)
    basics.generate_json, basics.fact_check = fake_llm, fake_fact_check
    quiet = lambda m: None
    try:
        answers[:] = [long]
        got = basics.write_script(live, topic, plan, log=quiet)
        words = sum(len(s["text"].split()) for s in got["scenes"])
        assert 600 <= words <= 900, words
        texts = {s["id"]: s["text"] for s in got["scenes"]}
        assert texts["point_1"].endswith(ask) and sum(t.lower().count("subscribe") for t in texts.values()) == 1
        assert ask not in texts["hook"] and got["fact_check"] == {"verdict": "ok", "issues": []}
        assert len(calls) == 1 and "never ask viewers to subscribe" in calls[0]
        fcfg, facts, sent, extra = checks[0]
        assert facts == basics.facts(topic) and set(facts) == {"question", "summary", "points"}, facts
        assert [p["text"] for p in facts["points"]] == [" ".join(p["text"].split()) for p in topic["points"]]
        assert all(ask not in s["text"] for s in sent["scenes"]) and sent["title"] == topic["question"]
        assert (fcfg["llm"]["min_words"], fcfg["llm"]["max_words"]) == (600, 900) and "approved" in extra

        # the ask misplaced (in the opening) or a second ask: discarded, 3 times → fails
        calls.clear(); checks.clear()
        answers[:] = [dict(long, hook=long["hook"] + " Subscribe now."), dict(long, recap=long["recap"] + " Please subscribe."),
                      dict(long, hook="Subscribe first. " + long["hook"])]
        try:
            basics.write_script(live, topic, plan, log=quiet)
            raise AssertionError("a misplaced subscribe ask must fail")
        except RuntimeError as e:
            assert "subscribe ask" in str(e) and "(also in hook)" in str(e) and len(calls) == 3 and not checks, e

        # "I'm buying" three times: the narration fails, nothing is fact-checked
        calls.clear()
        answers[:] = [dict(long, point_2="I'm buying more bitcoin through the fund. " + long["point_2"])]
        try:
            basics.write_script(live, topic, plan, log=quiet)
            raise AssertionError("first person must fail")
        except RuntimeError as e:
            assert "3 attempts" in str(e) and "first person" in str(e) and len(calls) == 3 and not checks, e

        # a number the approved points don't hold: the fact-check stage stops it at once (no retry)
        calls.clear()
        answers[:] = [dict(long, point_3=long["point_3"] + " The first funds came from 11 different issuers.")]
        try:
            basics.write_script(live, topic, plan, log=quiet)
            raise AssertionError("an unknown number must stop the narration")
        except RuntimeError as e:
            assert str(e).startswith("Basics fact-check failed") and "11" in str(e) and len(calls) == 1, e
        # a small number too (the shared news check skips bare numbers up to ten)
        calls.clear()
        answers[:] = [dict(long, point_3=long["point_3"] + " The first funds came from 5 different issuers.")]
        try:
            basics.write_script(live, topic, plan, log=quiet)
            raise AssertionError("an unknown small number must stop the narration")
        except RuntimeError as e:
            assert "numbers not in the approved points: 5" in str(e) and len(calls) == 1, e
        assert basics.unknown_numbers("Funds from 5 issuers, 1,200 coins.", {"x": "1,200 coins"}) == ["5"]
        # "subscribers" counts as a subscribe mention (only the ask may have one)
        calls.clear()
        answers[:] = [dict(long, hook="Millions of subscribers ask this. " + long["hook"])]
        try:
            basics.write_script(live, topic, plan, log=quiet)
            raise AssertionError("a second subscribe mention must fail")
        except RuntimeError as e:
            assert "(also in hook)" in str(e) and len(calls) == 3, e
        # a reject verdict stops it too
        calls.clear(); checks.clear()
        answers[:] = [long]
        verdict[0] = "reject"
        try:
            basics.write_script(live, topic, plan, log=quiet)
            raise AssertionError("a reject must stop the narration")
        except RuntimeError as e:
            assert "verdict reject" in str(e) and len(calls) == 1 and len(checks) == 1, e
        # revised: the checker's text is used and the ask added back (once)
        fixed = {"scenes": [{"id": k, "text": v.replace("regular stock exchange", "stock exchange")}
                            for k, v in long.items()]}
        verdict[:] = ["revised", fixed]
        got = basics.write_script(live, topic, plan, log=quiet)
        texts = {s["id"]: s["text"] for s in got["scenes"]}
        assert "regular stock exchange" not in texts["point_1"] and texts["point_1"].endswith(ask), texts["point_1"]
        assert texts["point_1"].count(ask) == 1 and got["fact_check"]["verdict"] == "revised"
        assert [s.get("term") for s in got["scenes"]][1:5] == [p["term"] for p in topic["points"]]
        # a revised draft that breaks a rule stops it
        verdict[:] = ["revised", {"scenes": [dict(s, text=s["text"] + (" I think it could 10x." if s["id"] == "recap"
                                                                       else "")) for s in fixed["scenes"]]}]
        try:
            basics.write_script(live, topic, plan, log=quiet)
            raise AssertionError("a rule-breaking revision must stop the narration")
        except RuntimeError as e:
            assert str(e).startswith("Basics fact-check failed") and "first person" in str(e), e
    finally:
        basics.generate_json, basics.fact_check = saved
    print(f"OK basics script: {words} words with the real 600-900 budget, subscribe ask once after the first "
          "payoff, misplaced ask / \"I'm buying\" discarded 3x, fact-check (approved points only): unknown "
          "number / reject / rule-breaking revision stop at once, revision used")


def test_basics_packaging(cfg):
    """Basics packaging (crypto-basics entry 6, packaging.md Basics row): the sample topic's YouTube title is the
    search question verbatim, its description has the key ideas, chapters (Intro / terms / Recap, ≥ 3) and the
    disclosure line exactly once before the hashtags (also when the summary echoes it), the Facebook 9:16
    description carries it exactly once and no chapters; a dated title, a 5-word thumbnail text, a missing
    thumbnail or a hashtag stops it; fewer than 3 chapters → no Chapters block; the thumbnail is 1280x720
    with the 1-3 words, a diagram when it fits, else a coin icon; a dated title stops the edition (exit 1)."""
    import copy
    from PIL import Image
    from autopilot import basics

    topic = dict(basics.sample_topic(), thumbnail="BITCOIN ETF?", approved=True)
    plan = basics.scene_plan(topic)
    line = rules.disclosure(cfg, "basics")
    audio = [{"duration": d} for d in (12.0, 50.0, 55.0, 4.0, 60.0, 20.0)]
    ch = basics.chapters(plan, audio)
    assert ch[0]["time"] == "0:00" and ch[0]["title"] == "Intro" and ch[-1]["title"] == "Recap", ch
    assert ch[1]["title"] == topic["points"][0]["term"] and ch[2]["scenes"] == ["point_2", "point_3"], ch
    meta = basics.metadata(cfg, topic, ch, log=lambda m: None)
    assert meta["title"] == "What Is a Bitcoin ETF? (Explained Simply)" == meta["fb_title"], meta["title"]
    assert meta["category_id"] == "27" and meta["tags"][0] == "what is a bitcoin etf", meta["tags"]
    assert sum(len(t) + 1 for t in meta["tags"]) <= 480
    d = meta["description"]
    assert d.count(line) == 1 and d.index("Chapters:\n0:00 Intro") < d.index(line) < d.index("#CryptoBasics"), d
    assert "• Exchange-traded fund" in d and "#Bitcoin" in d and d.count("#") <= 5, d
    fbd = meta["fb_description"]
    assert fbd.count(line) == 1 and "Chapters" not in fbd and "http" not in fbd and fbd.count("#") <= 5, fbd
    echoed = dict(topic, summary=topic["summary"] + " " + line)
    m2 = basics.metadata(cfg, echoed, ch, log=lambda m: None)
    assert m2["description"].count(line) == 1 and m2["fb_description"].count(line) == 1
    logs = []
    m3 = basics.metadata(cfg, topic, ch[:2], log=logs.append)
    assert "Chapters" not in m3["description"] and logs and "only 2" in logs[0], logs
    long = dict(topic, summary="Plain words here. " * 600)
    assert len(basics.metadata(cfg, long, ch, log=lambda m: None)["description"]) <= 4900
    assert basics.metadata(cfg, long, ch, log=lambda m: None)["description"].endswith(" ".join(basics.hashtags(topic)))

    # packaging rules stop it
    assert basics.packaging_problems(topic) == []
    for edit, word in ((dict(question="Bitcoin ETF Explained (October 2026)?"), "title date"),
                       (dict(thumbnail="WHAT IS A BITCOIN ETF"), "thumbnail words"),
                       (dict(thumbnail=""), "missing thumbnail"),
                       (dict(thumbnail="ETF #BTC"), "thumbnail hashtag"),
                       (dict(question="Will Bitcoin 10x? (Explained Simply)"), "10x")):
        bad = dict(topic, **edit)
        got = basics.packaging_problems(bad)
        assert got and any(word in r for r in got), (edit, got)
        for fn in (lambda: basics.metadata(cfg, bad), lambda: basics.render_thumbnail(cfg, bad, Path(tempfile.mkdtemp()) / "t.jpg")):
            try:
                fn()
                raise AssertionError(f"packaging must stop {edit}")
            except ValueError as e:
                assert "Basics packaging" in str(e), e

    # the thumbnail: 1280x720, words left, a diagram when it fits, else a coin icon
    out = ROOT / "output" / "test_basics_packaging"
    shutil.rmtree(out, ignore_errors=True)
    logs = []
    path = basics.render_thumbnail(cfg, topic, out / "thumbnail.jpg", log=logs.append)
    with Image.open(path) as im:
        assert im.size == (1280, 720) and im.format == "JPEG"
    assert not logs, logs  # the first point's flow fits the column
    assert 1 <= len(topic["thumbnail"].split()) <= 3
    huge = copy.deepcopy(topic)
    huge["points"][0]["diagram"] = {"type": "flow", "nodes": [
        {"label": "A very long label that keeps going and going " * 3, "say": [w], "coin": "SOL"}
        for w in ("alpha", "beta", "gamma", "delta", "omega")]}
    logs = []
    basics.render_thumbnail(cfg, huge, out / "icon.jpg", log=logs.append)
    assert logs and "coin icon" in logs[0] and basics._thumb_icon(huge) == "SOL", logs
    with Image.open(out / "icon.jpg") as im:
        assert im.size == (1280, 720)
        assert im.convert("RGB").getpixel((956, 390)) != (14, 15, 18)  # the badge is drawn in the column
    try:
        basics.render_thumbnail(cfg, dict(topic, thumbnail="DECENTRALIZATIONMAXIMALISM"), out / "wide.jpg")
        raise AssertionError("a word too wide for the thumbnail must stop it")
    except ValueError as e:
        assert "too wide" in str(e), e
    cut = basics.metadata(cfg, dict(topic, summary="Plain words here. " * 256), ch, log=lambda m: None)["description"]
    body = cut.split("\n\n⚠️")[0]
    assert len(cut) <= 4900 and "Chapters:" in body and not body.endswith("Recap"), (len(cut), body[-120:])
    for ln in body.splitlines():  # no chapter line is cut in half
        if ln[:1].isdigit():
            assert any(ln.endswith(c["title"]) for c in ch), ln
    print("OK basics packaging: title = search question verbatim, key ideas + chapters + disclosure once (YT) / "
          "disclosure once (FB 9:16), dated title / 5-word or missing / hashtag thumbnail text stop, <3 chapters "
          "→ no block, 1280x720 thumbnail with diagram or coin icon")


def test_material(cfg):
    """Shorts material (crypto-basics entry 7): a Basics episode's material (overview + one concept segment per
    point: narration without the subscribe ask, diagram, approved fact, hooks ≤ 60 chars) validates, saves to
    data/material/basics-<id>.json and round-trips with its video id; a later run's Facebook id merges into the
    same file (twice = no change); each malformed case gets its reason (4 segments, empty narration, a rule-
    breaking narration, bad diagram, long or dated hook, no platform id, duplicate id); `add` skips an invalid
    copy; the workflow's history-save step merges and commits data/material/."""
    import copy
    from autopilot import basics, material

    topic = dict(basics.sample_topic(), thumbnail="BITCOIN ETF?", approved=True)
    ask = basics.subscribe_ask(cfg)
    narr = _sample_narration()
    scenes = [{"id": k, "text": v + (" " + ask if k == "point_1" else "")} for k, v in narr.items()]
    entry = {"video_id": "Y1", "fb_video_id": None, "date": "2026-10-14T15:05:00+00:00",
             "publish_at": "2026-10-15T15:05:00.000Z"}
    m = material.build_basics(topic, scenes, entry, cfg)
    assert material.validate(m) == [], material.validate(m)
    assert [s_["id"] for s_ in m["segments"]] == ["overview", "point_1", "point_2", "point_3", "point_4"]
    assert m["source"] == {"kind": "basics", "id": topic["id"], "title": topic["question"]}
    assert m["youtube_id"] == "Y1" and m["facebook_id"] is None and m["published_at"] == entry["publish_at"]
    seg = m["segments"][1]
    assert seg["kind"] == "concept" and seg["term"] == topic["points"][0]["term"] and ask not in seg["narration"]
    assert seg["diagram"] == topic["points"][0]["diagram"] and seg["facts"] == [" ".join(topic["points"][0]["text"].split())]
    assert seg["hooks"] == ["What is exchange-traded fund?", "What Is a Bitcoin ETF?"], seg["hooks"]
    assert m["segments"][0]["hooks"] == ["What Is a Bitcoin ETF?"] and m["segments"][0]["diagram"] is None
    assert all(len(h) <= 60 for s_ in m["segments"] for h in s_["hooks"])
    q = "Ethereum vs Bitcoin: What's the Difference? (Explained Simply)"
    assert material.hooks_for("Bitcoin mining") == ["What is Bitcoin mining?"]
    assert material.hooks_for("The block reward", q)[0] == "What is the block reward?"
    assert material.hooks_for("Wallets and private keys")[0] == "What are wallets and private keys?"
    assert material.hooks_for("Payment channels") == ["What are payment channels?"]
    assert material.hooks_for("What each one is for", q) == ["Ethereum vs Bitcoin: What's the Difference?"]
    for t_ in basics.load_topics():  # every shipped draft gives every segment a hook
        assert all(material.hooks_for(p_["term"], t_["question"]) for p_ in t_["points"]), t_["id"]

    tmp = Path(tempfile.mkdtemp())
    try:
        path = material.write(m, tmp)
        assert path == tmp / "data" / "material" / f"basics-{topic['id']}.json"
        back = material.load(path)
        assert back == m and back["youtube_id"] == "Y1" and material.validate(back) == []
        later = material.build_basics(topic, scenes, dict(entry, video_id=None, fb_video_id="F1"), cfg)
        material.write(later, tmp)
        both = material.load(path)
        assert both["youtube_id"] == "Y1" and both["facebook_id"] == "F1" and both["segments"] == m["segments"]
        material.write(later, tmp)
        assert material.load(path) == both
        # the workflow's merge: valid copies merged, an invalid one skipped
        copy_ok = material.save(dict(m, source=dict(m["source"], id="other-topic")), tmp / "out1" / "material.json")
        bad = dict(m, segments=m["segments"][:4])
        copy_bad = material.save(bad, tmp / "out2" / "material.json")
        done = material.add([copy_ok, copy_bad], tmp)
        assert done == [tmp / "data" / "material" / "basics-other-topic.json"], done
        # an unreadable copy or existing file never stops the merge (the workflow then commits history)
        (tmp / "out3").mkdir()
        (tmp / "out3" / "material.json").write_text("{not json", encoding="utf-8")
        path.write_text("[1, 2]", encoding="utf-8")  # a broken file on main is replaced
        done = material.add([tmp / "out3" / "material.json", copy_ok, tmp / "out1" / "material.json"], tmp)
        assert len(done) == 2 and material.write(m, tmp) == path and material.load(path) == m
        try:
            material.write(bad, tmp)
            raise AssertionError("an invalid material must not be written")
        except ValueError as e:
            assert "4 segments" in str(e), e
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    def reasons(edit) -> list[str]:
        x = copy.deepcopy(m)
        edit(x)
        return material.validate(x)

    def one(edit, *words):
        got = reasons(edit)
        assert len(got) == 1 and all(w in got[0] for w in words), (words, got)

    one(lambda x: x.update(segments=x["segments"][:4]), "4 segments (at least 5)")
    one(lambda x: x["segments"][2].update(narration=""), "segment point_2: empty narration")
    one(lambda x: x["segments"][2].update(narration="I think it works well."), "point_2 narration", "first person")
    one(lambda x: x["segments"][3].update(diagram={"type": "pie"}), "point_3 diagram")
    one(lambda x: x["segments"][1].update(hooks=["What does this very long concept name mean for every beginner out there?"]),
        "over 60")
    one(lambda x: x["segments"][1].update(hooks=["Bitcoin ETF in October 2026?"]), "title rule")
    one(lambda x: x["segments"][1].update(hooks=[]), "at least one hook")
    one(lambda x: x.update(youtube_id=None), "no platform id")
    one(lambda x: x["segments"][4].update(id="point_1"), "duplicate id")
    one(lambda x: x["segments"][1].update(kind="clip"), "kind must be")
    one(lambda x: x["segments"][1].update(facts=[]), "facts")
    one(lambda x: x.update(version=2), "version")
    assert material.validate([]) == ["material must be a mapping"]

    wf = (ROOT / ".github" / "workflows" / "autopilot.yml").read_text(encoding="utf-8")
    save_step = wf.split("- name: Save history", 1)[1].split("- name:", 1)[0]
    assert "data/material/" in save_step and "python -m autopilot.material add" in save_step, save_step
    assert "output/*/material.json" in wf
    print("OK material: Basics material (overview + concept segments, no subscribe ask, hooks ≤ 60) validates, "
          "saves to data/material/ and round-trips, later FB id merges (idempotent), add skips invalid copies, "
          "each malformed case has its reason, workflow merges + commits data/material/")


def test_basics(cfg):
    """The Crypto Basics edition (crypto-basics entries 1-2, 5) through main(): the sample topic narrated (mocked
    Gemini answering with tests/basics/sample_narration.yaml, small word bounds), picked as the first approved
    topic of a tmp basics/topics.yaml (sample + two approved drafts + one draft) → a 16:9 and a 9:16 render of
    one narration, every point's diagram revealed part by part on the sentences naming it (no fallback) with
    contact frames grabbed from both mp4s → output/test_basics/, YouTube gets 16:9 and Facebook 9:16, the
    history entry (kind basics + voice); a rule-breaking writer stops it (exit 1, nothing published); a
    Facebook failure keeps the YouTube id (exit 1); a narration with a number not in the approved points stops
    it at the fact-check (exit 1, nothing published); each later run picks the next approved topic; with only
    a draft left: nothing to publish (exit 0); an invalid topic list stops it (exit 1); timed runs: wrong
    weekday → days skip, dark Wednesday → skip log, no LLM call; the workflow's session options."""
    from unittest import mock
    import numpy as np
    import main as app
    from autopilot import basics, reveal, voice, youtube

    topic = basics.sample_topic()
    assert topic["id"] == "what-is-a-bitcoin-etf" and topic["question"] == "What Is a Bitcoin ETF? (Explained Simply)"
    assert len(topic["points"]) == 4 and topic["summary"].strip()
    for p in topic["points"]:  # the approved points pass the data-desk rules and carry no number
        assert p["term"].strip() and not rules.narration_problems(p["text"]), p
        assert not any(ch.isdigit() for ch in p["text"]), p
    plan = basics.scene_plan(topic)
    assert [p["id"] for p in plan] == ["hook", "point_1", "point_2", "point_3", "point_4", "recap"], plan
    assert [p["visual"]["type"] for p in plan] == ["title"] + ["concept"] * 4 + ["recap"]
    assert all(p["visual"].get("diagram") for p in plan[1:5])
    assert plan[1]["term"] == "Exchange-traded fund" and topic["points"][0]["text"].split()[0] in plan[1]["covers"]

    clock = [datetime(2026, 10, 14, 15, 5, tzinfo=timezone.utc)]  # a Wednesday, 5 min after 15:00

    class FixedNow(datetime):
        @classmethod
        def now(cls, tz=None):
            return clock[0].astimezone(tz) if tz else clock[0].replace(tzinfo=None)

    tmp = Path(tempfile.mkdtemp())
    drafts = basics.load_topics()
    queue = ([dict(topic, thumbnail="BITCOIN ETF?", approved=True)] + [dict(t, approved=True) for t in drafts[:2]]
             + [drafts[2]])  # the last one stays a draft

    def write_topics(topics):
        (tmp / "basics").mkdir(parents=True, exist_ok=True)
        (tmp / "basics" / "topics.yaml").write_text(yaml.safe_dump({"topics": topics}, allow_unicode=True,
                                                                   sort_keys=False), encoding="utf-8")
    write_topics(queue)
    live = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    assert live["basics"]["enabled"] is False and live["basics"]["review_window_hours"] == 24
    assert live["basics"]["fb_published"] is False and str(live["basics"]["category_id"]) == "27"
    assert live["sessions"]["basics"] == {"label": "Crypto Basics", "short": "Basics", "start_utc": "15:00",
                                          "kind": "basics", "days": ["wed"], "platforms": ["youtube", "facebook"]}

    def write_cfg(enabled: bool):
        c = json.loads(json.dumps(live))
        c["basics"].update(enabled=enabled, min_words=30, max_words=400)
        (tmp / "config.yaml").write_text(yaml.safe_dump(c, allow_unicode=True), encoding="utf-8")

    def history() -> list[dict]:
        f = tmp / "data" / "history.json"
        return json.loads(f.read_text())["videos"] if f.exists() else []

    good = _sample_narration()  # names every diagram part in reveal order
    answer, prompts, voices, yt, fb, logs, checks = [None], [], [], [], [], [], []
    last_audio, timed, current = [], [], [topic]
    fail_fb = [False]

    def fake_llm(prompt, models, temperature=0.9):
        prompts.append(prompt)
        current[0] = next(t for t in queue if f'"{t["question"]}"' in prompt)
        text = good if current[0]["id"] == topic["id"] else _topic_narration(current[0])
        if answer[0] == "bad":
            text = dict(text, point_2="I'm buying more bitcoin through the fund.")
        elif answer[0] == "number":
            text = dict(text, point_3=text["point_3"] + " The first funds came from 11 different issuers.")
        return {"scenes": [{"id": k, "text": v} for k, v in text.items()]}

    def fake_fact_check(cfg_, facts, pkg, extra_rules=""):
        checks.append(facts)
        return "ok", pkg, []

    def fake_voice(scenes, name, rate, workdir, log=print, fallback=None, pauses=False):
        assert pauses  # Basics speak with the key-number / concept-term pauses
        voices.append(name)
        assert [s.get("term") for s in scenes][1:-1] == [p["term"] for p in current[0]["points"]], scenes
        out = []
        for i, sc in enumerate(scenes):
            words = sc["text"].split()
            wav = Path(workdir) / f"voice_{i:02d}.wav"
            run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
                 f"sine=frequency={300 + 25 * i}:duration={0.08 * len(words) + 0.3:.3f}", "-ar", "44100", "-ac", "1",
                 wav])
            out.append({"audio": wav, "duration": probe_duration(wav), "voice": name,
                        "words": [(j * 0.08, (j + 0.9) * 0.08, w) for j, w in enumerate(words)]})
        last_audio[:] = out
        return out

    time_steps = reveal.time_steps

    def spy(pics, scenes, audio, log=lambda m: None):  # keeps each shape's slides once their layers are timed
        timed.append(time_steps(pics, scenes, audio, log=log))
        return timed[-1]

    def fake_upload_lesson(video, meta, thumbnail, track_playlist, path_playlist, review_hours=24, notify=True,
                           log=print, playlist_privacy="public", playlists=True):
        yt.append({"video": Path(video), "meta": dict(meta), "thumbnail": Path(thumbnail), "track": track_playlist,
                   "path": path_playlist, "review": review_hours, "playlists": playlists})
        return {"video_id": f"Y{len(yt)}", "publish_at": "2026-10-15T15:05:00.000Z", "thumbnail_set": True,
                "playlists": {}, "errors": []}

    def fake_publish_video(video, title, description, cfg_, published=True, poll_minutes=None, log=print):
        fb.append({"video": Path(video), "title": title, "description": description, "published": published})
        if fail_fb[0]:
            e = RuntimeError("Facebook video V7 failed: bad codec")
            e.video_id = "V7"
            raise e
        return f"F{len(fb)}"

    def go(*argv) -> int:
        logs.clear()
        return app.main(list(argv))

    def said(text: str) -> bool:
        return any(text in m for m in logs)

    saved = (app.ROOT, app.datetime, app.log, basics.generate_json, voice.synthesize, youtube.upload_lesson,
             facebook.publish_video, youtube.upload, youtube.set_thumbnail, basics.fact_check)
    env = {k: os.environ.get(k) for k in ("FB_PAGE_ID", "FB_PAGE_TOKEN")}
    app.ROOT, app.datetime, app.log = tmp, FixedNow, logs.append
    basics.generate_json, voice.synthesize, basics.fact_check = fake_llm, fake_voice, fake_fact_check
    youtube.upload_lesson, facebook.publish_video = fake_upload_lesson, fake_publish_video
    youtube.upload = youtube.set_thumbnail = lambda *a, **k: (_ for _ in ()).throw(AssertionError("daily upload"))
    os.environ["FB_PAGE_ID"], os.environ["FB_PAGE_TOKEN"] = "PAGE", "TOKEN"
    try:
        write_cfg(False)
        # dark: the timed Wednesday run logs why and stops before anything is made
        assert go("--session", "basics", "--scheduled") == 0 and said("basics.enabled is false"), logs
        assert not prompts and not voices and not yt and not fb and not history()
        # a timed run on another weekday is skipped by the days rule (even when enabled)
        write_cfg(True)
        clock[0] = datetime(2026, 10, 13, 15, 5, tzinfo=timezone.utc)  # Tuesday
        assert go("--session", "basics", "--scheduled") == 0 and said("runs only on wed"), logs
        assert not prompts and not voices and not history()
        write_cfg(False)

        # manual run while dark (any day): made in both shapes from one narration and published
        with mock.patch.object(reveal, "time_steps", spy):
            assert go("--session", "basics") == 0, logs
        assert len(prompts) == 1 and "Exchange-traded fund" in prompts[0] and "Narration rules" in prompts[0], prompts
        assert '"fund", "shares", "stock exchange"' in prompts[0] and '"ETF", "holding bitcoin directly"' in prompts[0]
        steps_said = [m for m in logs if m.startswith("Step reveal")]
        assert [m.split(":")[0] for m in steps_said] == [f"Step reveal point_{n}" for n in (1, 2, 3, 4)] * 2, logs
        assert not any("(fallback)" in m for m in steps_said), steps_said
        assert "30-400 word CRYPTO BASICS" in prompts[0] and all(p["text"].split()[0] in prompts[0] for p in topic["points"])
        h = history()
        assert len(h) == 1, h
        e = h[0]
        assert e["kind"] == "basics" and e["session"] == "basics" and e["topic"] == topic["id"], e
        assert e["title"] == topic["question"] and e["video_id"] == "Y1" and e["fb_video_id"] == "F1", e
        assert e["voice"] == voices[0] == cfg["voice"]["name"] and e["brief_date"] == "2026-10-13", e
        assert e["platforms"] == ["youtube", "facebook"] and e["counts"] is False and e["trigger"] == "manual", e
        assert e["seconds"] > 0 and "workdir" not in e and e["publish_at"], e
        work = next((tmp / "output").glob("*/history_entry.json")).parent
        mat = json.loads((tmp / "data" / "material" / f"basics-{topic['id']}.json").read_text())
        from autopilot import material
        assert material.validate(mat) == [] and mat["youtube_id"] == "Y1" and mat["facebook_id"] == "F1", mat
        assert json.loads((work / "material.json").read_text()) == mat and said("Shorts material: data/material/")
        package = json.loads((work / "package.json").read_text())
        spoken = {s_["id"]: s_["text"] for s_ in package["scenes"]}
        ask = basics.subscribe_ask(live)
        assert spoken["point_1"].endswith(ask) and sum(t.count(ask) for t in spoken.values()) == 1, spoken
        assert package["fact_check"]["verdict"] == "ok" and checks == [basics.facts(topic)], checks
        assert said(f"Basics topic: {topic['id']}"), logs
        for name, size in (("16x9", (1920, 1080)), ("9x16", (1080, 1920))):
            path = work / f"basics_{name}.mp4"
            assert path.exists() and _probe_size(path) == size, (name, path)
            assert abs(probe_duration(path) - e["seconds"]) < 0.3, (name, probe_duration(path), e["seconds"])
        from PIL import Image
        with Image.open(work / "thumbnail.jpg") as im:
            assert im.size == (1280, 720)
        # contact frames from both mp4s: each diagram scene's start, then after each layer's fade-in
        frames_dir = ROOT / "output" / "test_basics"
        shutil.rmtree(frames_dir, ignore_errors=True)
        frames_dir.mkdir(parents=True)
        starts = [sum(a["duration"] for a in last_audio[:i]) for i in range(len(last_audio))]
        assert len(timed) == 2 and len(last_audio) == len(plan)
        for pics in timed:
            shape = Path(pics[0]["image"]).parent.name
            video, contact = work / f"basics_{shape}.mp4", []
            for i, p in enumerate(pics):
                if not p.get("steps"):
                    assert p["id"] in ("hook", "recap"), p["id"]
                    continue
                at = [ly["at"] for st in p["steps"] for ly in st["layers"]]
                assert at == sorted(at) and at[-1] + reveal.FADE < last_audio[i]["duration"], (shape, p["id"], at)
                # a part revealed later in the scene (the first one starts fading in at 0 s): absent in the
                # scene-start frame, in after its fade
                probe = next(ly for st in p["steps"] for ly in st["layers"] if ly["at"] >= 0.3)
                x, y = probe["xy"]
                with Image.open(probe["image"]) as im:
                    layer = np.asarray(im.convert("RGB"), dtype=int)
                with Image.open(p["base"]) as im:
                    under = np.asarray(im.convert("RGB"), dtype=int)[y:y + layer.shape[0], x:x + layer.shape[1]]
                shots = [(starts[i] + 0.02, f"{shape}_{p['id']}_0_start.png", None)]
                shots += [(starts[i] + ly["at"] + reveal.FADE + 0.05, f"{shape}_{p['id']}_{k}_{st['key']}_{j}.png", ly)
                          for k, st in enumerate(p["steps"], 1) for j, ly in enumerate(st["layers"])]
                for n, (t, name, ly) in enumerate(shots):
                    frame = _frame(video, t, frames_dir / name)
                    contact.append(frames_dir / name)
                    if n == 0 or ly is probe:
                        part = frame[y:y + layer.shape[0], x:x + layer.shape[1]]
                        near_base = np.abs(part - under).mean() < np.abs(part - layer).mean()
                        assert near_base == (n == 0), (shape, p["id"], name)
            cell = (480, 270) if shape == "16x9" else (270, 480)
            sheet = _contact(contact, cell, 6, frames_dir / f"contact_{shape}.png")
            DIAGRAM_SAMPLE.mkdir(parents=True, exist_ok=True)
            shutil.copy(sheet, DIAGRAM_SAMPLE / f"video_{sheet.name}")
        assert yt[0]["video"] == work / "basics_16x9.mp4" and yt[0]["review"] == 24 and yt[0]["playlists"] is False
        assert yt[0]["track"] is None and yt[0]["path"] is None and yt[0]["thumbnail"] == work / "thumbnail.jpg"
        meta = yt[0]["meta"]
        assert set(meta) == {"title", "description", "tags", "category_id"} and meta["category_id"] == "27", meta
        assert meta["description"].count(rules.disclosure(cfg, "basics")) == 1, meta["description"]
        assert meta["description"].startswith(" ".join(topic["summary"].split())), meta["description"]
        saved_meta = json.loads((work / "metadata.json").read_text())
        assert fb == [{"video": work / "basics_9x16.mp4", "title": topic["question"],
                       "description": saved_meta["fb_description"], "published": False}], fb
        fbd = fb[0]["description"]
        assert fbd.count(rules.disclosure(cfg, "basics")) == 1 and "Key ideas:" in fbd and "Chapters" not in fbd, fbd
        assert fbd.endswith(" ".join(basics.hashtags(topic))), fbd
        assert saved_meta["title"] == topic["question"] and saved_meta["chapters"][0]["title"] == "Intro"
        assert said("Chapters: 0:00 Intro"), logs
        # A/B: the next Basics edition takes the other voice
        assert app.ab_voice(cfg["voice"], History(tmp / "data" / "history.json"), "basics")["name"] == \
            cfg["voice"]["alternate"]

        # the remaining cases stub the renders (both shapes rendered for real above)
        shapes = []

        def fake_build(audio, pics, vcfg, workdir, out, music=None):
            shapes.append((vcfg["video"]["width"], vcfg["video"]["height"], len(pics)))
            Path(out).write_bytes(b"")
            return sum(a["duration"] for a in audio)
        with mock.patch.object(render, "build_video", fake_build):
            # a writer that breaks the narration rules every time ("I'm buying"): 3 attempts, the edition stops
            answer[0] = "bad"
            prompts.clear()
            n_yt, n_fb, n_voice = len(yt), len(fb), len(voices)
            assert go("--session", "basics") == 1, logs
            assert len(prompts) == 3 and said("attempt 3/3") and said("Discarding draft") and said("first person"), logs
            assert said("Basics failed: Could not produce valid Basics narration in 3 attempts"), logs
            assert len(yt) == n_yt and len(fb) == n_fb and len(voices) == n_voice and len(history()) == 1
            # the second run picked the next approved topic (the sample is published)
            assert current[0]["id"] == queue[1]["id"] and said(f"Basics topic: {queue[1]['id']}"), logs
            # a number the approved points don't hold: the fact-check stops it, nothing published, no retry
            answer[0] = "number"
            prompts.clear()
            assert go("--session", "basics") == 1, logs
            assert said("Basics failed: Basics fact-check failed") and said("11") and len(prompts) == 1, logs
            assert len(yt) == n_yt and len(fb) == n_fb and len(voices) == n_voice and len(history()) == 1
            mat_dir = tmp / "data" / "material"
            assert sorted(p_.name for p_ in mat_dir.iterdir()) == [f"basics-{topic['id']}.json"]  # nothing published
            answer[0] = None

            # Facebook fails: the YouTube id is kept, exit 1, said so
            fail_fb[0] = True
            assert go("--session", "basics") == 1, logs
            assert said("Facebook Basics video failed") and said("V7") and said("Not published on: facebook"), logs
            h = history()
            assert len(h) == 2 and h[1]["video_id"] == f"Y{n_yt + 1}" and not h[1].get("fb_video_id"), h
            assert h[1]["topic"] == queue[1]["id"], h[1]
            m1 = json.loads((mat_dir / f"basics-{queue[1]['id']}.json").read_text())
            assert m1["youtube_id"] == h[1]["video_id"] and m1["facebook_id"] is None, m1
            assert h[1]["platforms"] == ["youtube"] and h[1]["voice"] == cfg["voice"]["alternate"], h[1]
            assert shapes == [(1920, 1080, 6), (1080, 1920, 6)], shapes

            # both platforms fail: nothing recorded, no Shorts material, exit 1
            def yt_down(*a, **k):
                raise RuntimeError("quota exceeded")
            with mock.patch.object(youtube, "upload_lesson", yt_down):
                assert go("--session", "basics") == 1 and said("Not published on: youtube, facebook"), logs
            assert len(history()) == 2 and not (mat_dir / f"basics-{queue[2]['id']}.json").exists()
            fail_fb[0] = False

            # enabled, timed on Wednesday: made and published, counts for the slot
            write_cfg(True)
            clock[0] = datetime(2026, 10, 14, 15, 5, tzinfo=timezone.utc)
            assert go("--session", "basics", "--scheduled") == 0, logs
            assert history()[-1]["counts"] is True and history()[-1]["trigger"] == "timed"
            assert history()[-1]["topic"] == queue[2]["id"], history()[-1]  # the FB-failed topic isn't repeated
            assert go("--session", "basics", "--scheduled") == 0 and said("already published"), logs
            # only a draft left: nothing to publish, nothing made
            prompts.clear()
            assert go("--session", "basics") == 0 and said("Basics: nothing to publish"), logs
            assert not prompts and len(history()) == 3
            # a dated title (packaging) stops it before any LLM call, even if the list check is bypassed
            dated = [dict(t, question=t["question"].replace("?", " in October 2026?"), approved=True) for t in queue]
            write_topics(dated)
            with mock.patch.object(basics, "validate_topics", lambda topics: []):
                assert go("--session", "basics") == 1 and said("Basics packaging") and said("date"), logs
            assert not prompts and len(history()) == 3
            # a topic that can't give the Shorts material its 5 segments stops before narration is voiced
            short = [dict(t_, points=t_["points"][:3], approved=True) for t_ in queue]
            write_topics(short)
            with mock.patch.object(basics, "validate_topics", lambda topics: []):
                assert go("--session", "basics") == 1 and said("Basics Shorts material") and said("4 segments"), logs
            assert len(history()) == 3
            prompts.clear()
            write_topics(dated[:1] + queue[1:])
            assert go("--session", "basics") == 1 and said("Basics topic problem"), logs  # the list check too
            # an invalid topic list stops the edition before anything is made
            write_topics(queue + [dict(queue[0], thumbnail="WHAT IS A BITCOIN ETF")])
            assert go("--session", "basics") == 1 and said("Basics topic problem") and said("duplicate id"), logs
            assert not prompts and len(history()) == 3
    finally:
        (app.ROOT, app.datetime, app.log, basics.generate_json, voice.synthesize, youtube.upload_lesson,
         facebook.publish_video, youtube.upload, youtube.set_thumbnail, basics.fact_check) = saved
        for k, v in env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(tmp, ignore_errors=True)

    # the workflow's Run workflow menu offers the edition
    wf = yaml.safe_load((ROOT / ".github" / "workflows" / "autopilot.yml").read_text(encoding="utf-8"))
    on = wf.get("on", wf.get(True))  # PyYAML reads the bare key `on` as True
    assert "basics" in on["workflow_dispatch"]["inputs"]["session"]["options"], on["workflow_dispatch"]
    print("OK basics: first approved topic → 16x9 + 9x16 from one narration, diagrams revealed in narration order (no "
          "fallback, contact frames in output/test_basics), YouTube 16:9 + Facebook 9:16, history kind basics + topic + "
          "voice, subscribe ask after the first payoff, rule-breaking writer stops, unknown number stops at the "
          "fact-check, next run → next topic, FB failure keeps YT, nothing to publish, bad list stops, days skip, "
          "dark timed skip, workflow option")


def test_basics_ready(cfg):
    """Ready-episode packages (crypto-basics entry 8) through main(): `--prepare next` writes the first approved,
    unpublished topic's package to basics/ready/<id>.yaml that validates (no upload, no history); `--prepare
    <id>` with a narration holding a number not in the approved points, or for a draft / unknown / published
    topic, writes nothing and exits 1; the edition with a ready package makes no LLM call and publishes it
    (history topic); a tampered package ("I'm buying") stops it; `--stock` counts ready packages minus
    published topics; --prepare / --stock need --session basics."""
    from unittest import mock
    import main as app
    from autopilot import basics, voice, youtube

    topic = dict(basics.sample_topic(), thumbnail="BITCOIN ETF?", approved=True)
    drafts = basics.load_topics()
    queue = [topic, dict(drafts[0], approved=True), dict(drafts[1], approved=True), drafts[2]]
    tmp = Path(tempfile.mkdtemp())
    (tmp / "basics").mkdir(parents=True)
    (tmp / "basics" / "topics.yaml").write_text(yaml.safe_dump({"topics": queue}, allow_unicode=True, sort_keys=False),
                                                encoding="utf-8")
    c = json.loads(json.dumps(yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))))
    c["basics"].update(min_words=30, max_words=400)
    (tmp / "config.yaml").write_text(yaml.safe_dump(c, allow_unicode=True), encoding="utf-8")
    calls, logs, yt, fb = [], [], [], []
    extra = [""]

    def fake_llm(prompt, models, temperature=0.9):
        calls.append(prompt)
        cur = next(t_ for t_ in queue if f'"{t_["question"]}"' in prompt)
        text = _sample_narration() if cur["id"] == topic["id"] else _topic_narration(cur)
        text = dict(text, point_3=text["point_3"] + extra[0])
        return {"scenes": [{"id": k, "text": v} for k, v in text.items()]}

    def fake_fact_check(cfg_, facts, pkg, extra_rules=""):
        calls.append("fact_check")
        return "ok", pkg, []

    def fake_voice(scenes, name, rate, workdir, log=print, fallback=None, pauses=False):
        return [{"audio": Path(workdir) / f"v{i}.wav", "duration": 0.3 * len(sc["text"].split()) + 0.5, "voice": name,
                 "words": [(j * 0.3, j * 0.3 + 0.27, w) for j, w in enumerate(sc["text"].split())]}
                for i, sc in enumerate(scenes)]

    def fake_build(audio, pics, vcfg, workdir, out, music=None):
        Path(out).write_bytes(b"")

    def fake_upload_lesson(video, meta, thumbnail, track_playlist, path_playlist, review_hours=24, notify=True,
                           log=print, playlist_privacy="public", playlists=True):
        yt.append(meta["title"])
        return {"video_id": f"Y{len(yt)}", "errors": []}

    def fake_publish_video(video, title, description, cfg_, published=True, poll_minutes=None, log=print):
        fb.append(title)
        return f"F{len(fb)}"

    def go(*argv) -> int:
        logs.clear()
        return app.main(list(argv))

    def said(text: str) -> bool:
        return any(text in m for m in logs)

    ready = tmp / "basics" / "ready"
    saved = (app.ROOT, app.log, basics.generate_json, basics.fact_check, voice.synthesize, render.build_video,
             youtube.upload_lesson, facebook.publish_video)
    env = {k: os.environ.get(k) for k in ("FB_PAGE_ID", "FB_PAGE_TOKEN")}
    app.ROOT, app.log = tmp, logs.append
    basics.generate_json, basics.fact_check, voice.synthesize, render.build_video = (fake_llm, fake_fact_check,
                                                                                      fake_voice, fake_build)
    youtube.upload_lesson, facebook.publish_video = fake_upload_lesson, fake_publish_video
    os.environ["FB_PAGE_ID"], os.environ["FB_PAGE_TOKEN"] = "PAGE", "TOKEN"
    try:
        # prepare next: the first approved, unpublished topic → a package that validates; nothing uploaded
        assert go("--session", "basics", "--prepare", "next") == 0, logs
        path = ready / f"{topic['id']}.yaml"
        pkg = basics.load_ready(path)
        assert basics.validate_ready(pkg, topic, c) == [], basics.validate_ready(pkg, topic, c)
        assert pkg["topic"] == topic["id"] and pkg["title"] == topic["question"] and pkg["thumbnail"] == "BITCOIN ETF?"
        assert pkg["fact_check"]["verdict"] == "ok" and "fact_check" in calls and path.read_text().startswith("# Crypto")
        assert [x["id"] for x in pkg["scenes"]] == [p_["id"] for p_ in basics.scene_plan(topic)]
        assert not yt and not fb and not (tmp / "data" / "history.json").exists() and said("merge it by PR")
        # next again: the second topic (the first has a package)
        assert go("--session", "basics", "--prepare", "next") == 0 and (ready / f"{queue[1]['id']}.yaml").exists()
        # a number not in the approved points: nothing written, exit 1
        extra[0] = " The first funds came from 11 different issuers."
        assert go("--session", "basics", "--prepare", queue[2]["id"]) == 1 and said("fact-check failed"), logs
        assert not (ready / f"{queue[2]['id']}.yaml").exists() and said("nothing written")
        extra[0] = ""
        assert go("--session", "basics", "--prepare", drafts[2]["id"]) == 1 and said("is a draft"), logs
        assert go("--session", "basics", "--prepare", "no-such-topic") == 1 and said("is not in basics/topics.yaml")
        assert go("--session", "lesson", "--stock") == 1 and said("only with --session basics"), logs
        # stock: two ready, none published
        assert go("--session", "basics", "--stock") == 0 and said("Ready, unpublished Basics episodes: 2"), logs
        assert said(f"{queue[2]['id']}: no package"), logs

        # the edition with a ready package: no LLM call, published, history topic
        calls.clear()
        assert go("--session", "basics") == 0, logs
        assert not calls and said("using the ready package"), (calls, logs)
        h = json.loads((tmp / "data" / "history.json").read_text())["videos"]
        assert h[-1]["topic"] == topic["id"] and h[-1]["video_id"] == "Y1" and h[-1]["fb_video_id"] == "F1", h
        work = next((tmp / "output").glob("*/history_entry.json")).parent
        spoken = {x["id"]: x["text"] for x in json.loads((work / "package.json").read_text())["scenes"]}
        assert spoken == {x["id"]: " ".join(x["text"].split()) for x in pkg["scenes"]}
        # stock: one ready, unpublished left (the published one no longer counts)
        assert go("--session", "basics", "--stock") == 0 and said("Ready, unpublished Basics episodes: 1"), logs
        assert said(f"{topic['id']}: published"), logs
        assert go("--session", "basics", "--prepare", topic["id"]) == 1 and said("is already published"), logs

        # a tampered package stops the edition: nothing published, no LLM call
        p2 = ready / f"{queue[1]['id']}.yaml"
        bad = basics.load_ready(p2)
        bad["scenes"][2]["text"] = "I'm buying more bitcoin. " + bad["scenes"][2]["text"]
        basics.save_ready(bad, p2)
        calls.clear()
        assert go("--session", "basics") == 1 and said("Basics ready package") and said("first person"), logs
        assert not calls and len(yt) == 1, (calls, yt)
        assert go("--session", "basics", "--stock") == 0 and said("package invalid"), logs
        assert said("Ready, unpublished Basics episodes: 0"), logs
        # a package of another topic's text or with a changed title is refused too
        assert basics.validate_ready(dict(pkg, title="Other"), topic, c) and basics.validate_ready(dict(pkg, topic="x"),
                                                                                                    topic, c)
        assert "scene ids" in " ".join(basics.validate_ready(dict(pkg, scenes=pkg["scenes"][:3]), topic, c))
    finally:
        (app.ROOT, app.log, basics.generate_json, basics.fact_check, voice.synthesize, render.build_video,
         youtube.upload_lesson, facebook.publish_video) = saved
        for k, v in env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(tmp, ignore_errors=True)
    print("OK basics ready: --prepare next/<id> writes a validating package (no upload, no history), unknown "
          "number / draft / unknown / published topic → nothing written, exit 1; edition uses the package with no "
          "LLM call; tampered package stops it; --stock counts ready minus published")


def test_evergreen(cfg):
    """"Publish next evergreen" (crypto-basics entry 9) through main(), on the merged --slot top-up path:
    `--session evergreen --slot recap` publishes the next ready Basics episode into today's recap slot (no LLM
    call; history session recap, trigger topup, counts, evergreen; Shorts material saved); a second run for the
    same slot and day publishes nothing; with an empty stock it takes the lesson path (make_lesson_edition under
    the slot's key) only while lessons are on, else nothing; a slot holding another edition's upload is left
    alone; no --slot / a news-post slot → exit 1; a dark timed run skips; the workflow offers `evergreen` and
    passes the `slot` input to --slot."""
    import main as app
    from autopilot import basics, voice, youtube

    clock = [datetime(2026, 11, 21, 15, 5, tzinfo=timezone.utc)]  # a Saturday

    class FixedNow(datetime):
        @classmethod
        def now(cls, tz=None):
            return clock[0].astimezone(tz) if tz else clock[0].replace(tzinfo=None)

    topic = dict(basics.sample_topic(), thumbnail="BITCOIN ETF?", approved=True)
    queue = [topic, dict(basics.load_topics()[0], approved=True)]
    tmp = Path(tempfile.mkdtemp())
    (tmp / "basics").mkdir(parents=True)
    (tmp / "basics" / "topics.yaml").write_text(yaml.safe_dump({"topics": queue}, allow_unicode=True, sort_keys=False),
                                                encoding="utf-8")
    live = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    assert live["evergreen"]["enabled"] is False and live["sessions"]["evergreen"]["kind"] == "evergreen"
    assert not live["sessions"]["evergreen"].get("start_utc")  # no timer of its own (setup_cronjobs skips it)

    def write_cfg(evergreen: bool, lessons_on: bool):
        c = json.loads(json.dumps(live))
        c["basics"].update(min_words=30, max_words=400)
        c["evergreen"]["enabled"] = evergreen
        c["lessons"]["enabled"] = lessons_on
        c["sessions"]["recap"] = {"label": "Weekly Recap", "short": "Recap", "start_utc": "15:00",
                                  "platforms": ["youtube"]}  # epic 3 adds the real one
        (tmp / "config.yaml").write_text(yaml.safe_dump(c, allow_unicode=True), encoding="utf-8")

    calls, logs, yt, fb, lesson_calls = [], [], [], [], []

    def fake_llm(prompt, models, temperature=0.9):
        calls.append(prompt)
        return {"scenes": [{"id": k, "text": v} for k, v in _sample_narration().items()]}

    def fake_fact_check(cfg_, facts, pkg, extra_rules=""):
        calls.append("fact_check")
        return "ok", pkg, []

    def fake_voice(scenes, name, rate, workdir, log=print, fallback=None, pauses=False):
        return [{"audio": Path(workdir) / f"v{i}.wav", "duration": 0.3 * len(sc["text"].split()) + 0.5, "voice": name,
                 "words": [(j * 0.3, j * 0.3 + 0.27, w) for j, w in enumerate(sc["text"].split())]}
                for i, sc in enumerate(scenes)]

    def fake_build(audio, pics, vcfg, workdir, out, music=None):
        Path(out).write_bytes(b"")

    def fake_upload_lesson(video, meta, thumbnail, track_playlist, path_playlist, review_hours=24, notify=True,
                           log=print, playlist_privacy="public", playlists=True):
        yt.append(meta["title"])
        return {"video_id": f"Y{len(yt)}", "errors": []}

    def fake_publish_video(video, title, description, cfg_, published=True, poll_minutes=None, log=print):
        fb.append(title)
        return f"F{len(fb)}"

    def fake_lesson_edition(cfg_, history, date, session_key, pending, no_upload=False, counts=True, force=False):
        lesson_calls.append((date, session_key, list(pending), counts))
        return None, pending

    def go(*argv) -> int:
        logs.clear()
        return app.main(list(argv))

    def said(text: str) -> bool:
        return any(text in m for m in logs)

    def history() -> list[dict]:
        f = tmp / "data" / "history.json"
        return json.loads(f.read_text())["videos"] if f.exists() else []

    saved = (app.ROOT, app.datetime, app.log, app.make_lesson_edition, basics.generate_json, basics.fact_check,
             voice.synthesize, render.build_video, youtube.upload_lesson, facebook.publish_video)
    env = {k: os.environ.get(k) for k in ("FB_PAGE_ID", "FB_PAGE_TOKEN")}
    app.ROOT, app.datetime, app.log, app.make_lesson_edition = tmp, FixedNow, logs.append, fake_lesson_edition
    basics.generate_json, basics.fact_check, voice.synthesize, render.build_video = (fake_llm, fake_fact_check,
                                                                                      fake_voice, fake_build)
    youtube.upload_lesson, facebook.publish_video = fake_upload_lesson, fake_publish_video
    os.environ["FB_PAGE_ID"], os.environ["FB_PAGE_TOKEN"] = "PAGE", "TOKEN"
    try:
        write_cfg(False, False)
        assert go("--session", "basics", "--prepare", "next") == 0, logs  # the stock: one ready episode
        # dark: a timed evergreen run skips
        calls.clear()
        assert go("--session", "evergreen", "--slot", "recap", "--scheduled") == 0 and said("evergreen.enabled is false")
        assert not history() and not calls
        # bad calls
        assert go("--session", "evergreen") == 1 and said("needs --slot"), logs
        assert go("--session", "evergreen", "--slot", "news_midday") == 1 and said("Facebook news post"), logs
        assert go("--session", "evergreen", "--slot", "nope") == 1 and said("Unknown slot"), logs
        # the ready Basics episode fills today's recap slot: no LLM call, both platforms, recorded under recap
        assert go("--session", "evergreen", "--slot", "recap") == 0, logs
        assert not calls and said("using the ready package") and said("Evergreen: the ready Basics episode"), logs
        e = history()[-1]
        assert (e["kind"], e["topic"], e["session"], e["trigger"], e["counts"], e["evergreen"]) == (
            "basics", topic["id"], "recap", "topup", True, True), e
        assert e["video_id"] == "Y1" and e["fb_video_id"] == "F1" and e["brief_date"] == "2026-11-21", e
        assert (tmp / "data" / "material" / f"basics-{topic['id']}.json").exists() and not lesson_calls
        # the same slot and day again: nothing published
        assert go("--session", "evergreen", "--slot", "recap") == 0 and said("already published"), logs
        assert len(history()) == 1 and len(yt) == 1 and not lesson_calls
        # next day, empty stock: lessons off → nothing; lessons on → the lesson path under the slot's key
        clock[0] = datetime(2026, 11, 22, 15, 5, tzinfo=timezone.utc)
        assert go("--session", "evergreen", "--slot", "recap") == 0 and said("no ready Basics episode"), logs
        assert said("lessons are off") and not lesson_calls and len(history()) == 1
        write_cfg(False, True)
        assert go("--session", "evergreen", "--slot", "recap") == 0, logs
        assert lesson_calls == [("2026-11-22", "recap", ["youtube", "facebook"], True)], lesson_calls
        # a slot that already holds another edition's upload is left alone
        h = json.loads((tmp / "data" / "history.json").read_text())
        h["videos"].append({"brief_date": "2026-11-22", "session": "recap", "kind": "recap", "video_id": "R1",
                            "counts": True})
        (tmp / "data" / "history.json").write_text(json.dumps(h))
        assert go("--session", "evergreen", "--slot", "recap") == 0 and said("no evergreen top-up"), logs
        assert len(lesson_calls) == 1
        # enabled: a timed run tops up too
        write_cfg(True, True)
        clock[0] = datetime(2026, 11, 23, 15, 5, tzinfo=timezone.utc)
        assert go("--session", "evergreen", "--slot", "recap", "--scheduled") == 0 and len(lesson_calls) == 2, logs
    finally:
        (app.ROOT, app.datetime, app.log, app.make_lesson_edition, basics.generate_json, basics.fact_check,
         voice.synthesize, render.build_video, youtube.upload_lesson, facebook.publish_video) = saved
        for k, v in env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(tmp, ignore_errors=True)
    wf = yaml.safe_load((ROOT / ".github" / "workflows" / "autopilot.yml").read_text(encoding="utf-8"))
    on = wf.get("on", wf.get(True))
    assert "evergreen" in on["workflow_dispatch"]["inputs"]["session"]["options"]
    assert "slot" in on["workflow_dispatch"]["inputs"]
    run_step = next(st for st in wf["jobs"]["make-and-upload"]["steps"] if st.get("name") == "Make and publish")
    assert "--slot" in run_step["env"]["SLOT"] and "$SLOT" in run_step["run"], run_step
    print("OK evergreen: --session evergreen --slot recap → ready Basics episode (no LLM, recorded under the slot, "
          "material), once per slot/day, empty stock → lesson path under the slot (lessons on) else nothing, other "
          "edition in the slot → left alone, bad slot / no slot → exit 1, dark timed skip, workflow option + slot")


# ─── triggered videos (epic-volatility-videos) ─────────────────────────────

TRIGGER_NOW = datetime(2026, 10, 15, 9, 30, tzinfo=timezone.utc)


def _coin(name: str, price: float, ch24: float, ch7: float = 0.0, now: datetime = TRIGGER_NOW) -> dict:
    """168 hourly closes ending at `price` with a 24 h change of `ch24` % and a 7 d change of `ch7` %."""
    day_ago, week_ago = price / (1 + ch24 / 100), price / (1 + ch7 / 100) if ch7 else price / (1 + ch24 / 100)
    s = [week_ago + (day_ago - week_ago) * i / 143 for i in range(144)]
    s += [day_ago + (price - day_ago) * i / 24 for i in range(1, 25)]
    s[-25] = day_ago
    return {"name": name, "price": price, "change_24h": ch24, "change_7d": (price / s[0] - 1) * 100,
            "series": s, "series_times": [(now - timedelta(hours=167 - i)).isoformat() for i in range(168)],
            "high_24h": max(s[-24:]), "low_24h": min(s[-24:])}


def trigger_data(btc: float = -7.2, eth: float = -4.5, sol: float = -9.4, xrp: float = -4.0, news=None,
                 now: datetime = TRIGGER_NOW) -> dict:
    """Sources-style market data for the trigger engine: Coinbase coins + crypto headlines."""
    t = (now - timedelta(hours=2)).isoformat()
    if news is None:
        news = [{"category": "crypto", "source": "CoinDesk", "title": "Bitcoin slides as spot ETF outflows hit a record",
                 "summary": "Bitcoin fell as spot bitcoin ETFs saw record outflows.", "published": t},
                {"category": "crypto", "source": "Cointelegraph", "title": "Bitcoin ETF outflows deepen crypto sell-off",
                 "summary": "", "published": t},
                {"category": "crypto", "source": "The Block", "title": "Ether and Solana follow bitcoin lower",
                 "summary": "", "published": t}]
    return {"now": now.isoformat(), "crypto": {"BTC": _coin("Bitcoin", 62400, btc), "ETH": _coin("Ethereum", 2450, eth),
                                               "SOL": _coin("Solana", 142, sol), "XRP": _coin("XRP", 0.53, xrp)},
            "news": news}


def _sine_voice(spoken: list):
    def fake_voice(scenes, name, rate, workdir, log=print, fallback=None, pauses=False):
        spoken.append([dict(s_) for s_ in scenes])
        out = []
        for i, sc in enumerate(scenes):
            words = sc["text"].split()
            wav = Path(workdir) / f"voice_{i:02d}.wav"
            dur = 0.05 * len(words) + 0.3
            run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"sine=frequency={300 + 25 * i}:duration={dur:.3f}",
                 "-ar", "44100", "-ac", "1", wav])
            out.append({"audio": wav, "duration": probe_duration(wav), "voice": name,
                        "words": [(j * 0.05, (j + 0.9) * 0.05, w) for j, w in enumerate(words)]})
        return out
    return fake_voice


TRIGGERED_TEXT = {
    "move": "Bitcoin fell 7.2% in the last 24 hours. Here is what actually happened behind the drop.",
    "cause": "Spot bitcoin ETFs saw record outflows. When those funds sell, the selling reaches the market quickly.",
    "coins": "It started with the headline about fund outflows. Then Bitcoin moved first. Solana fell further, "
             "and Ethereum followed the same way.",
    "context": "Over the past week the move adds to a slide that was already under way across the large coins.",
    "watch": "The next thing to watch is whether the fund outflows continue in the coming sessions.",
    "recap": "Bitcoin dropped on record ETF outflows and the large coins followed. This is market data, not "
             "financial advice."}


def test_triggered(cfg):
    """The triggered video (epic-volatility-videos entries 1 + 6): BTC -7% fires rule 1 with its cause and the coins
    it moved; BTC -3% fires nothing; `--session triggered --trigger <fixture> --no-upload` renders a 16:9 video (mocked
    LLM, fact-check and voice) from the fixed scene plan (move → cause → coins diagram → context → watch → recap) with
    the subscribe ask once after the cause, the coins diagram revealed as named; a writer that states a price target
    three times stops the edition (exit 1); an unknown number stops it at the fact-check; a timed run while
    triggers.enabled is false logs and exits 0 (no LLM call); the move chart draws in both shapes."""
    import main as app
    from autopilot import reveal, triggered, triggers, voice

    fired = triggers.evaluate(trigger_data(btc=-7.0), now=TRIGGER_NOW, log=lambda m: None)
    assert len(fired) == 1 and fired[0]["rule"] == 1 and fired[0]["lead"] == "BTC", [f["lead"] for f in fired]
    t = fired[0]
    assert t["cause"]["title"].startswith("Bitcoin") and t["coins"][0] == "BTC" and 1 <= len(t["coins"]) <= 3, t["coins"]
    assert round(t["moves"]["BTC"]["change_24h"], 1) == -7.0 and t["id"] == "20261015-0930-r1-btc", t["id"]
    assert not triggers.evaluate(trigger_data(btc=-3.0, eth=-2.0), now=TRIGGER_NOW, log=lambda m: None)
    plan = triggered.scene_plan(t)
    assert [p_["id"] for p_ in plan] == ["move", "cause", "coins", "context", "watch", "recap"]
    assert '"headline", "Bitcoin", "Solana", "Ethereum"' in plan[2]["covers"], plan[2]["covers"]
    assert triggered.unknown_numbers("Bitcoin fell 7% to 62,400 over 24 hours", triggered.facts(t)) == []
    assert triggered.unknown_numbers("Bitcoin fell 12% to 58,000", triggered.facts(t)) == ["12", "58,000"]

    live = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    assert live["triggers"]["enabled"] is False and (live["triggers"]["min_words"], live["triggers"]["max_words"]) == (420, 600)
    assert live["sessions"]["triggered"]["kind"] == "triggered" and live["sessions"]["triggered"]["platforms"] == ["youtube"]
    assert not live["sessions"]["triggered"].get("start_utc")
    tmp = Path(tempfile.mkdtemp())
    c = json.loads(json.dumps(live))
    c["triggers"].update(min_words=60, max_words=400)
    (tmp / "config.yaml").write_text(yaml.safe_dump(c, allow_unicode=True), encoding="utf-8")
    fixture = tmp / "btc_drop.json"
    fixture.write_text(json.dumps(trigger_data(btc=-7.2)), encoding="utf-8")

    prompts, spoken, logs, checks, timed = [], [], [], [], []
    text = [dict(TRIGGERED_TEXT)]

    def fake_llm(prompt, models, temperature=0.9):
        prompts.append(prompt)
        return {"scenes": [{"id": k, "text": v} for k, v in text[0].items()]}

    def fake_fact_check(cfg_, facts, pkg, extra_rules=""):
        checks.append(facts)
        return "ok", pkg, []
    time_steps = reveal.time_steps

    def spy(pics, scenes, audio, log=lambda m: None):
        timed.append(time_steps(pics, scenes, audio, log=log))
        return timed[-1]

    saved = (app.ROOT, app.log, triggered.generate_json, triggered.fact_check, voice.synthesize, reveal.time_steps)
    app.ROOT, app.log = tmp, logs.append
    triggered.generate_json, triggered.fact_check, voice.synthesize = fake_llm, fake_fact_check, _sine_voice(spoken)
    reveal.time_steps = spy
    try:
        assert app.main(["--session", "triggered", "--trigger", str(fixture), "--scheduled"]) == 0, logs
        assert any("triggers.enabled is false" in m for m in logs) and not prompts, logs
        assert app.main(["--session", "triggered"]) == 1 and any("needs --trigger" in m for m in logs), logs
        assert app.main(["--session", "triggered", "--trigger", str(fixture), "--no-upload"]) == 0, logs
        assert len(prompts) == 1 and "Bitcoin slides as spot ETF outflows" in prompts[0] and "60-400 word" in prompts[0]
        assert len(checks) == 1 and checks[0]["moves"]["BTC"]["change_24h"] == -7.2, checks
        work = next((tmp / "output").glob("*/triggered_16x9.mp4")).parent
        assert _probe_size(work / "triggered_16x9.mp4") == (1920, 1080)
        said = {s_["id"]: s_["text"] for s_ in json.loads((work / "package.json").read_text())["scenes"]}
        ask = triggered.subscribe_ask(live)
        assert said["cause"].endswith(ask) and sum(v.count("subscribe") for v in said.values()) == 1, said
        assert list(said)[1] == "cause" and spoken[-1][0]["id"] == "move"  # the ask comes after the first payoff
        steps = [m for m in logs if m.startswith("Step reveal")]
        assert steps and steps[0].startswith("Step reveal coins") and not any("(fallback)" in m for m in steps), steps
        assert not (tmp / "data" / "history.json").exists()  # made only
        # a writer stating a price target three times: the edition stops, nothing made
        text[0] = dict(TRIGGERED_TEXT, watch="Bitcoin could reach $70,000 if the selling stops.")
        prompts.clear()
        assert app.main(["--session", "triggered", "--trigger", str(fixture), "--no-upload"]) == 1, logs
        assert len(prompts) == 3 and any("price target" in m for m in logs) and any("Triggered failed" in m for m in logs)
        # an unknown number stops it at the fact-check (no retry)
        text[0] = dict(TRIGGERED_TEXT, context="Over the past week the slide reached 12% across the large coins.")
        prompts.clear()
        assert app.main(["--session", "triggered", "--trigger", str(fixture), "--no-upload"]) == 1, logs
        assert len(prompts) == 1 and any("numbers not in the fetched data: 12" in m for m in logs), logs
    finally:
        app.ROOT, app.log, triggered.generate_json, triggered.fact_check, voice.synthesize, reveal.time_steps = saved
    # the move chart draws in both shapes (epic 4's market Short reuses it)
    from PIL import Image
    from autopilot import lesson_slides
    for layout in (lesson_slides.LANDSCAPE, lesson_slides.PORTRAIT):
        img = Image.new("RGB", (layout.w, layout.h))
        info = triggered.draw_move_chart(img, layout.content_box, t["moves"]["BTC"]["series"][-25:], layout, (255, 212, 0))
        assert layout.content_box[0] <= info["last"][0] <= layout.content_box[2], info
        triggered.render_slides(live, t, plan, layout, tmp / f"shape_{layout.name}")
    shutil.rmtree(tmp, ignore_errors=True)
    print("OK triggered: rule 1 at BTC -7% (cause + coins), nothing at -3%, fixture → 16:9 render (6 scenes, ask "
          "after the cause, coins diagram revealed as named, fact-checked), price target ×3 / unknown number stop, "
          "dark timed run skips, move chart + slides in both shapes")


def trigger_overview(cap: float = 1.0, coins=None) -> dict:
    """A CoinGecko overview (sources.parse_overview's shape): the total cap's 24 h change + top-50 coins."""
    coins = coins if coins is not None else [("BTC", "Bitcoin", 62400, -2.0), ("ETH", "Ethereum", 2450, -1.5),
                                             ("PEPE", "Pepe", 0.00001, 20.0), ("SUI", "Sui", 3.1, 15.0),
                                             ("USDT", "Tether", 1.0, 0.0)]
    return {"source": "CoinGecko", "credit": "Data provided by CoinGecko", "fetched_utc": TRIGGER_NOW.isoformat(),
            "as_of_utc": TRIGGER_NOW.isoformat(), "total_cap_usd": 2.3e12, "total_cap_change_24h": cap,
            "coins": [{"id": n.lower(), "symbol": sym, "name": n, "rank": i + 1, "price": p, "market_cap": 1e9,
                       "change_24h": ch, "change_7d": ch * 1.2, "sparkline": [p / (1 + ch / 100), p], "last_updated": ""}
                      for i, (sym, n, p, ch) in enumerate(coins)]}


def test_trigger_rules(cfg):
    """All four trigger rules and the coin gate (epic-volatility-videos entry 3): each rule fires at its threshold
    and not just below; a +20% coin with no matching story fires nothing; an ETF-approval headline fires rule 4
    with that cause; no trigger leads with a coin that failed the gate; every trigger carries 1-3 coins."""
    from autopilot import focus, triggers
    quiet = lambda m: None  # noqa: E731
    calm = dict(btc=-1.0, eth=-1.0, sol=-1.0, xrp=-1.0)
    t0 = (TRIGGER_NOW - timedelta(hours=1)).isoformat()

    def rules_of(data, ov=None):
        got = triggers.evaluate(data, ov, now=TRIGGER_NOW, log=quiet)
        for t in got:
            assert 1 <= len(t["coins"]) <= 3 and t["coins"][0] == t["lead"] or t["lead"] == "CRYPTO", t
        return got

    # rule 1: ±5.0 fires, 4.9 doesn't (ETH too)
    assert [t["rule"] for t in rules_of(trigger_data(**dict(calm, btc=5.0)))] == [1]
    assert [t["lead"] for t in rules_of(trigger_data(**dict(calm, eth=-5.0)))] == ["ETH"]
    assert not rules_of(trigger_data(**dict(calm, btc=4.9, eth=-4.9)))
    # rule 2: total cap ±4.0 fires, 3.9 doesn't; topic-led (label Crypto, the focus story as cause)
    got = rules_of(trigger_data(**calm), trigger_overview(cap=-4.0, coins=[]))
    assert [t["rule"] for t in got] == [2] and got[0]["label"] == "Crypto" and got[0]["cause"], got
    assert got[0]["market"]["total_cap_change_24h"] == -4.0 and "CoinGecko" in got[0]["data_sources"]
    assert not rules_of(trigger_data(**calm), trigger_overview(cap=3.9, coins=[]))
    # rule 3 + the coin gate: +20% PEPE with no story → nothing (logged); with a story → fires with that cause
    logs = []
    assert not triggers.evaluate(trigger_data(**calm), trigger_overview(coins=[("PEPE", "Pepe", 1e-5, 20.0)]),
                                 now=TRIGGER_NOW, log=logs.append)
    assert any("Coin gate: PEPE" in m for m in logs), logs
    story = {"category": "crypto", "source": "CoinDesk", "title": "Pepe jumps as memecoin traders pile in",
             "summary": "", "published": t0}
    news = trigger_data()["news"][:1] + [story]
    got = rules_of(trigger_data(**calm, news=news), trigger_overview(coins=[("PEPE", "Pepe", 1e-5, 20.0)]))
    assert [t["rule"] for t in got] == [3] and got[0]["lead"] == "PEPE" and got[0]["cause"]["title"] == story["title"]
    assert got[0]["moves"]["PEPE"]["source"] == "CoinGecko" and got[0]["moves"]["PEPE"]["change_24h"] == 20.0
    # threshold: 15.0 fires (a SUI story), 14.9 doesn't
    sui = dict(story, title="Sui rallies after network news")
    assert [t["lead"] for t in rules_of(trigger_data(**calm, news=[sui]),
                                        trigger_overview(coins=[("SUI", "Sui", 3.1, 15.0)]))] == ["SUI"]
    assert not rules_of(trigger_data(**calm, news=[sui]), trigger_overview(coins=[("SUI", "Sui", 3.1, 14.9)]))
    # no trigger leads with a gated-out coin: PEPE +20% without a story, SUI +16% with one → only SUI
    got = rules_of(trigger_data(**calm, news=[sui]),
                   trigger_overview(coins=[("PEPE", "Pepe", 1e-5, 20.0), ("SUI", "Sui", 3.1, 16.0)]))
    assert [t["lead"] for t in got] == ["SUI"] and all("PEPE" not in t["coins"] for t in got), got
    # rule 4: an ETF-approval headline (fresh) fires with that cause; old or not major → nothing
    etf = dict(story, title="SEC approves first spot Solana ETF")
    assert focus.major_story(etf) == "etf"
    assert focus.major_story({"title": "Hackers drain $40 million from crypto exchange"}) == "hack"
    assert focus.major_story({"title": "Ethereum's Fusaka upgrade goes live"}) == "upgrade"
    assert focus.major_story({"title": "Senate passes stablecoin bill"}) == "regulation"
    assert focus.major_story({"title": "Bitcoin slides as spot ETF outflows hit a record"}) is None
    assert focus.major_story({"title": "SEC approves new stock exchange rules"}) is None  # no crypto named
    got = rules_of(trigger_data(**calm, news=[etf]))
    assert [t["rule"] for t in got] == [4] and got[0]["cause"]["title"] == etf["title"], got
    assert got[0]["category"] == "etf" and got[0]["lead"] == "SOL", got
    old = dict(etf, published=(TRIGGER_NOW - timedelta(hours=7)).isoformat())
    assert not rules_of(trigger_data(**calm, news=[old]))
    # several at once: rule order
    got = rules_of(trigger_data(**dict(calm, btc=-6.0), news=[etf]), trigger_overview(cap=-4.5, coins=[]))
    assert [t["rule"] for t in got] == [1, 2, 4], [t["rule"] for t in got]
    print("OK trigger rules: 1-4 at their thresholds (not just below), coin gate (no story → no trigger, logged), "
          "ETF approval → rule 4 with its cause, gated-out coin never leads, rule order")



def test_trigger_limits(cfg):
    """Trigger limits (epic-volatility-videos entry 4) over a simulated week: a third trigger in an ISO week is
    dropped, one 40 hours after the last published one is dropped, a 05:00 trigger is due at 12:00, a stale
    trigger is dropped with a log line, a repeat fire for a pending cause adds nothing; triggers.load by id."""
    from autopilot import triggers
    base = triggers.evaluate(trigger_data(), now=TRIGGER_NOW, log=lambda m: None)[0]

    def fire(at: datetime, cause: str) -> dict:
        return dict(base, id=f"{at:%Y%m%d-%H%M}-r1-btc", key=f"r1:BTC:{cause}", fired_utc=at.isoformat(),
                    due_utc=at.isoformat())

    def at(day: int, hour: int, minute: int = 0) -> datetime:
        return datetime(2026, 10, day, hour, minute, tzinfo=timezone.utc)  # 12 = Monday … 18 = Sunday

    assert triggers.due_time(at(14, 5)) == at(14, 12) and triggers.due_time(at(14, 3)) == at(14, 12)
    assert triggers.due_time(at(14, 11)) == at(14, 11) and triggers.due_time(at(14, 2, 59)) == at(14, 2, 59)
    state, videos, logs = {"version": 1, "triggers": []}, [], []

    def publish(t: dict, when: datetime):
        videos.append({"kind": "triggered", "trigger_id": t["id"], "video_id": f"V{len(videos)}",
                       "date": when.isoformat(), "session": "triggered"})

    def rec(t, now):
        logs.clear()
        return triggers.record(state, [t], videos, now=now, log=logs.append)

    a = rec(fire(at(12, 14), "a"), at(12, 14))
    assert a and a["due_utc"] == at(12, 14).isoformat() and triggers.due_now(state, at(12, 14, 10))["id"] == a["id"]
    assert rec(fire(at(12, 14, 30), "a"), at(12, 14, 30)) is None and any("already pending" in m for m in logs)
    assert len(state["triggers"]) == 1
    publish(a, at(12, 14, 30))
    # 40 h after the published one (Wed 06:30 → held to 12:00, still < 48 h) → dropped
    assert rec(fire(at(14, 6, 30), "b"), at(14, 6, 30)) is None and any("dropped" in m and "48 h" in m for m in logs)
    assert state["triggers"][0]["status"] == "published" and state["triggers"][-1]["status"] == "dropped"
    # a 05:00 trigger (Thu, > 48 h after) is due at 12:00
    c = rec(fire(at(15, 5), "c"), at(15, 5))
    assert c and c["due_utc"] == at(15, 12).isoformat() and triggers.due_now(state, at(15, 11)) is None
    assert triggers.due_now(state, at(15, 12, 5))["id"] == c["id"]
    triggers.mark_dispatched(state, c["id"], at(15, 12, 5))
    publish(c, at(15, 14))
    # a third trigger in the same ISO week (Sat, > 48 h after) → dropped by the cap
    assert rec(fire(at(17, 15), "d"), at(17, 15)) is None and any("this week already has 2" in m for m in logs), logs
    # next week: a new trigger, then stale (not published within 3 h of its due time) → dropped with a log line
    e = rec(fire(at(19, 20), "e"), at(19, 20))
    assert e and triggers.due_now(state, at(19, 23, 30)) is None
    assert rec(fire(at(19, 23, 30), "f"), at(19, 23, 30))  # refresh drops e, so f (a new cause) is pending
    assert any(f"Trigger {e['id']} dropped: not published within 3 h" in m for m in logs), logs
    assert next(x for x in state["triggers"] if x["id"] == e["id"])["status"] == "dropped"
    # simulated history entries never count
    sim = {"kind": "triggered", "trigger_id": "X", "video_id": "S", "date": at(21, 12).isoformat(), "simulated": True}
    assert triggers.published([sim]) == {}
    # state on disk + triggers.load by id
    tmp = Path(tempfile.mkdtemp())
    triggers.save_state(state, tmp / triggers.STATE)
    assert triggers.load(c["id"], tmp)["due_utc"] == c["due_utc"]
    try:
        triggers.load("nope", tmp)
        raise AssertionError("an unknown id must fail")
    except ValueError:
        pass
    shutil.rmtree(tmp, ignore_errors=True)
    print("OK trigger limits: 48 h spacing, 2 per ISO week, 03:00-11:00 → 12:00, stale dropped (logged), "
          "repeat cause adds nothing, simulated never counts, load by id")



def test_trigger_poll(cfg):
    """Trigger polling job (epic-volatility-videos entry 5): `triggers.check` on fetched data (mocked) records a
    trigger and, when it is due, marks it dispatched only with triggers.enabled true (dark: logs only); the two
    workflow files: triggers.yml on a 30-minute cron off :00/:30 with a light install, the COINGECKO_API_KEY secret,
    the state commit with retries and the `triggered` dispatch; autopilot.yml's `triggered` choice, `trigger`
    input → --trigger, its concurrency group and the secret."""
    from autopilot import triggers
    tmp = Path(tempfile.mkdtemp())
    live = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    logs, fetched = [], []

    def fake_fetch(cfg_, log=print):
        fetched.append(1)
        return trigger_data(btc=-7.2), trigger_overview(cap=-2.0)

    # dark: a 14:00 trigger is recorded and due at once, but never dispatched
    now = datetime(2026, 10, 15, 14, 0, tzinfo=timezone.utc)
    res = triggers.check(live, tmp, now=now, log=logs.append, fetch=fake_fetch)
    assert res["recorded"] and res["due"] == "" and any("triggers.enabled is false" in m for m in logs), (res, logs)
    state = triggers.load_state(tmp / triggers.STATE)
    assert [t["status"] for t in state["triggers"]] == ["pending"] and "CoinGecko" in state["triggers"][0]["data_sources"]
    # on: the next poll dispatches it once (marked dispatched), the one after doesn't again
    on = json.loads(json.dumps(live))
    on["triggers"]["enabled"] = True
    res = triggers.check(on, tmp, now=now + timedelta(minutes=30), log=logs.append, fetch=fake_fetch)
    assert res["due"] == state["triggers"][0]["id"] and res["recorded"] == "", res
    assert triggers.load_state(tmp / triggers.STATE)["triggers"][0]["status"] == "dispatched"
    res = triggers.check(on, tmp, now=now + timedelta(minutes=60), log=logs.append, fetch=fake_fetch)
    assert res["due"] == "" and len(fetched) == 3, res
    shutil.rmtree(tmp, ignore_errors=True)

    wf = yaml.safe_load((ROOT / ".github" / "workflows" / "triggers.yml").read_text(encoding="utf-8"))
    on_ = wf.get("on", wf.get(True))
    cron = on_["schedule"][0]["cron"]
    assert cron == "13,43 * * * *" and "workflow_dispatch" in on_, on_
    assert wf["permissions"] == {"contents": "write", "actions": "write"}
    steps = wf["jobs"]["check"]["steps"]
    assert not any("ffmpeg" in str(x) for x in steps)
    chk = next(x for x in steps if x.get("id") == "check")
    assert chk["run"] == "python -m autopilot.triggers check" and "secrets.COINGECKO_API_KEY" in chk["env"]["COINGECKO_API_KEY"]
    assert "data/triggers.json" in next(x for x in steps if x.get("id") == "save")["run"]
    disp = next(x for x in steps if x.get("name") == "Dispatch the triggered edition")
    assert "gh workflow run autopilot.yml" in disp["run"] and "session=triggered" in disp["run"]
    assert 'trigger="$DUE"' in disp["run"] and "scheduled=true" in disp["run"] and "outputs.due" in disp["if"]
    ap = yaml.safe_load((ROOT / ".github" / "workflows" / "autopilot.yml").read_text(encoding="utf-8"))
    inputs = ap.get("on", ap.get(True))["workflow_dispatch"]["inputs"]
    assert "triggered" in inputs["session"]["options"] and inputs["trigger"]["type"] == "string"
    job = ap["jobs"]["make-and-upload"]
    assert "inputs.session == 'triggered' && 'triggered'" in job["concurrency"]["group"]
    step = next(x for x in job["steps"] if x.get("name") == "Make and publish")
    assert "--trigger=" in step["env"]["TRIGGER"] and '${TRIGGER:+"$TRIGGER"}' in step["run"]
    assert "secrets.COINGECKO_API_KEY" in step["env"]["COINGECKO_API_KEY"]
    print("OK trigger poll: check records + dispatches only when enabled (once), triggers.yml 30-min cron + light "
          "install + secret + state commit + dispatch, autopilot.yml triggered choice/group/--trigger")



def test_triggered_packaging(cfg):
    """Triggered packaging (epic-volatility-videos entry 7): a BTC -7.2% trigger → "Why Bitcoin Just Dropped 7% (What
    Actually Happened)" (the % from the data), thumbnail text of 1-3 words on a 1280x720 thumbnail, a description with
    the disclosure and "Data provided by CoinGecko" once each; a title with a date stops the edition before anything
    is made; a manual run publishes to YouTube only (mocked) and records kind: triggered with its trigger_id; a second
    run for the same trigger publishes nothing."""
    import main as app
    from autopilot import reveal, triggered, triggers, voice, youtube
    from autopilot.sources import CG_CREDIT
    t = triggers.evaluate(trigger_data(btc=-7.2), trigger_overview(cap=-3.0), now=TRIGGER_NOW, log=lambda m: None)[0]
    title = triggered.title_for(t)
    assert title == "Why Bitcoin Just Dropped 7% (What Actually Happened)" and not rules.title_problems(title), title
    words = triggered.thumbnail_words(t)
    assert words == "WHY -7%?" and 1 <= len(words.split()) <= 3 and not rules.thumbnail_text_problems(words), words
    up = dict(t, moves={"BTC": dict(t["moves"]["BTC"], change_24h=5.6)})
    assert triggered.title_for(up) == "Why Bitcoin Just Jumped 6% (What Actually Happened)"
    rule4 = dict(t, category="etf", moves={"BTC": dict(t["moves"]["BTC"], change_24h=0.4)})
    assert triggered.title_for(rule4) == "What the ETF Decision Means for Bitcoin (What Actually Happened)"
    assert triggered.packaging_problems("Why Bitcoin Dropped 7% on October 14", words)
    live = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    meta = triggered.metadata(live, t)
    line = rules.disclosure(live, "triggers")
    assert meta["title"] == title and meta["description"].count(line) == 1, meta["description"]
    assert meta["description"].count(CG_CREDIT) == 1 and "Bitcoin slides as spot ETF outflows" in meta["description"]
    assert CG_CREDIT not in triggered.metadata(live, dict(t, data_sources=["Coinbase"]))["description"]
    tmp = Path(tempfile.mkdtemp())
    from PIL import Image
    with Image.open(triggered.render_thumbnail(live, t, tmp / "thumb.jpg")) as im:
        assert im.size == (1280, 720)

    c = json.loads(json.dumps(live))
    c["triggers"].update(min_words=60, max_words=400)
    (tmp / "config.yaml").write_text(yaml.safe_dump(c, allow_unicode=True), encoding="utf-8")
    fixture = tmp / "trigger.json"
    fixture.write_text(json.dumps({"trigger": t}), encoding="utf-8")
    prompts, logs, yt = [], [], []

    def fake_llm(prompt, models, temperature=0.9):
        prompts.append(prompt)
        return {"scenes": [{"id": k, "text": v} for k, v in TRIGGERED_TEXT.items()]}

    def fake_upload_lesson(video, meta_, thumbnail, track_playlist, path_playlist, review_hours=24, notify=True,
                           log=print, playlist_privacy="public", playlists=True):
        yt.append({"video": Path(video), "meta": dict(meta_), "review": review_hours, "playlists": playlists})
        return {"video_id": f"T{len(yt)}", "publish_at": "2026-10-15T12:00:00.000Z", "errors": []}

    def boom(*a, **k):
        raise AssertionError("a triggered video goes to YouTube only, as a 16:9 upload")
    saved = (app.ROOT, app.log, triggered.generate_json, triggered.fact_check, voice.synthesize, youtube.upload_lesson,
             youtube.upload, facebook.publish_video, facebook.publish_reel, triggered.title_for)
    app.ROOT, app.log = tmp, logs.append
    triggered.generate_json, triggered.fact_check = fake_llm, (lambda cfg_, f, pkg, extra_rules="": ("ok", pkg, []))
    voice.synthesize, youtube.upload_lesson = _sine_voice([]), fake_upload_lesson
    youtube.upload = facebook.publish_video = facebook.publish_reel = boom
    try:
        # a dated title stops it before anything is made
        triggered.title_for = lambda trig: "Why Bitcoin Dropped 7% on October 14 (What Actually Happened)"
        assert app.main(["--session", "triggered", "--trigger", str(fixture)]) == 1, logs
        assert not prompts and any("Triggered packaging" in m and "date" in m for m in logs), logs
        triggered.title_for = saved[-1]
        assert app.main(["--session", "triggered", "--trigger", str(fixture)]) == 0, logs
        assert len(yt) == 1 and yt[0]["video"].name == "triggered_16x9.mp4" and yt[0]["playlists"] is False
        assert yt[0]["meta"]["title"] == title and yt[0]["review"] == live["triggers"]["review_window_hours"]
        h = json.loads((tmp / "data" / "history.json").read_text())["videos"]
        assert len(h) == 1 and h[0]["kind"] == "triggered" and h[0]["trigger_id"] == t["id"], h
        assert h[0]["video_id"] == "T1" and h[0]["platforms"] == ["youtube"] and h[0]["title"] == title, h
        assert h[0]["session"] == "triggered" and h[0]["trigger"] == "manual", h
        # Shorts material (entry 9): market section with the fetched numbers, their source and ≥ 2 hooks
        from autopilot import material
        mat = json.loads((tmp / "data" / "material" / f"triggered-{t['id']}.json").read_text())
        assert material.validate(mat) == [] and mat["youtube_id"] == "T1" and mat["segments"] == [], mat["source"]
        mk = mat["market"]
        assert mk["numbers"]["BTC"]["change_24h"] == -7.2 and mk["numbers"]["BTC"]["source"] == "Coinbase", mk["numbers"]
        assert mk["data_source"] == ["CoinGecko", "Coinbase"] and mk["credit"] == CG_CREDIT
        assert len(mk["hooks"]) >= 2 and mk["hooks"][0] == "Why did Bitcoin just drop 7%?", mk["hooks"]
        assert mk["cause_headline"] == t["cause"]["title"] and len(mk["series"]["BTC"]) == 168
        assert material.validate(dict(mat, market=dict(mk, hooks=mk["hooks"][:1]))) == [
            "market: needs at least 2 distinct hook candidates"]
        assert any("market material needs" in r for r in material.validate(dict(mat, market=None)))
        assert app.main(["--session", "triggered", "--trigger", str(fixture)]) == 0 and len(yt) == 1, logs
        assert any("already published" in m for m in logs), logs
    finally:
        (app.ROOT, app.log, triggered.generate_json, triggered.fact_check, voice.synthesize, youtube.upload_lesson,
         youtube.upload, facebook.publish_video, facebook.publish_reel, triggered.title_for) = saved
    shutil.rmtree(tmp, ignore_errors=True)
    print("OK triggered packaging: move + cause title from the data, 1-3 thumbnail words + 1280x720 thumbnail, "
          "disclosure + CoinGecko credit once, dated title stops, YouTube-only publish + kind triggered record, "
          "no second publish")



RECAP_TEXT = {
    "hook": "This week in crypto, three coins moved the most. Here is what moved and why.",
    "move_1": "Sui rose about 18% over seven days after news about its network drew in buyers.",
    "move_2": "Solana fell about 12% over the week as traders pulled back from the large coins.",
    "move_3": "Bitcoin gained about 8% over seven days, helped by steady fund inflows.",
    "market": "Across the wider market, the total crypto market cap moved about 2% in the last day.",
    "watch": "Next week, watch whether the fund flows keep coming and how the network news develops.",
    "recap": "Sui led, Solana lagged and Bitcoin climbed. This is market data, not financial advice."}


def test_recap(cfg):
    """Saturday recap (epic-volatility-videos entry 8): a week whose history holds a triggered video skips the recap
    with a log line (no LLM call); a quiet fixture week renders a recap (mocked LLM, fact-check, voice and upload)
    whose moves match the fixture data (the 3 biggest 7-day moves, Coinbase + CoinGecko) and whose metadata passes
    title_problems, carries the disclosure and the CoinGecko credit once; YouTube only, kind: recap; a timed run while
    recap.enabled is false skips; autopilot.yml offers `recap`."""
    import main as app
    from autopilot import recap, voice, youtube
    from autopilot.sources import CG_CREDIT
    now = datetime(2026, 10, 17, 15, 5, tzinfo=timezone.utc)  # Saturday, ISO week 42
    t0 = (now - timedelta(days=2)).isoformat()
    news = [{"category": "crypto", "source": "CoinDesk", "title": "Sui rallies after network news", "summary": "",
             "published": t0},
            {"category": "crypto", "source": "The Block", "title": "Solana slides as traders pull back", "summary": "",
             "published": t0},
            {"category": "crypto", "source": "Cointelegraph", "title": "Bitcoin climbs on steady ETF inflows",
             "summary": "", "published": t0},
            {"category": "crypto", "source": "Decrypt", "title": "Bitcoin fund flows stay positive", "summary": "",
             "published": t0}]
    data = {"crypto": {"BTC": _coin("Bitcoin", 62400, 1.0, 8.1, now), "ETH": _coin("Ethereum", 2450, 0.5, 3.0, now),
                       "SOL": _coin("Solana", 142, -2.0, -12.0, now), "XRP": _coin("XRP", 0.53, 0.2, 1.0, now)},
            "news": news}
    ov = trigger_overview(cap=2.0, coins=[("BTC", "Bitcoin", 62400, 1.0), ("SUI", "Sui", 3.1, 15.0),
                                          ("USDT", "Tether", 1.0, 30.0)])  # change_7d = 1.2 × change_24h
    week = recap.build(data, ov, now)
    assert week["coins"] == ["SUI", "SOL", "BTC"] and week["week"] == "2026-W42", week["coins"]
    assert week["moves"]["SUI"]["change_7d"] == 18.0 and week["moves"]["SUI"]["source"] == "CoinGecko"
    assert round(week["moves"]["SOL"]["change_7d"], 1) == -12.0 and week["moves"]["BTC"]["source"] == "Coinbase"
    assert week["causes"]["SUI"]["title"] == "Sui rallies after network news"
    assert week["causes"]["BTC"]["title"].startswith("Bitcoin"), week["causes"]
    plan = recap.scene_plan(week)
    assert [p_["id"] for p_ in plan] == list(RECAP_TEXT), [p_["id"] for p_ in plan]

    live = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    assert live["recap"]["enabled"] is False and live["sessions"]["recap"]["kind"] == "recap"
    assert live["sessions"]["recap"]["platforms"] == ["youtube"] and live["sessions"]["recap"]["days"] == ["sat"]
    assert live["sessions"]["recap"]["start_utc"] == "15:00" and "weekend_sessions" not in live
    tmp = Path(tempfile.mkdtemp())
    c = json.loads(json.dumps(live))
    c["recap"].update(min_words=60, max_words=400)
    (tmp / "config.yaml").write_text(yaml.safe_dump(c, allow_unicode=True), encoding="utf-8")

    class FixedNow(datetime):
        @classmethod
        def now(cls, tz=None):
            return now.astimezone(tz) if tz else now.replace(tzinfo=None)

    prompts, logs, yt = [], [], []

    def fake_llm(prompt, models, temperature=0.9):
        prompts.append(prompt)
        return {"scenes": [{"id": k, "text": v} for k, v in RECAP_TEXT.items()]}

    def fake_upload_lesson(video, meta_, thumbnail, track_playlist, path_playlist, review_hours=24, notify=True,
                           log=print, playlist_privacy="public", playlists=True):
        yt.append({"video": Path(video), "meta": dict(meta_), "thumbnail": Path(thumbnail)})
        return {"video_id": f"R{len(yt)}", "publish_at": None, "errors": []}

    def boom(*a, **k):
        raise AssertionError("the recap goes to YouTube only, as a 16:9 upload")
    saved = (app.ROOT, app.log, app.datetime, recap.fetch, recap.generate_json, recap.fact_check, voice.synthesize,
             youtube.upload_lesson, facebook.publish_video, youtube.upload)
    app.ROOT, app.log, app.datetime = tmp, logs.append, FixedNow
    recap.fetch = lambda cfg_, log=print: (data, ov)
    recap.generate_json, recap.fact_check = fake_llm, (lambda cfg_, f, pkg, extra_rules="": ("ok", pkg, []))
    voice.synthesize, youtube.upload_lesson = _sine_voice([]), fake_upload_lesson
    facebook.publish_video = youtube.upload = boom
    hist = tmp / "data" / "history.json"
    try:
        assert app.main(["--session", "recap", "--scheduled"]) == 0 and any("recap.enabled is false" in m for m in logs)
        # a triggered video this ISO week → the recap is skipped (logged), nothing made
        hist.parent.mkdir(parents=True)
        hist.write_text(json.dumps({"videos": [{"kind": "triggered", "trigger_id": "T", "video_id": "V1",
                                                "date": (now - timedelta(days=3)).isoformat()}]}))
        assert app.main(["--session", "recap"]) == 0 and any("Recap skipped" in m for m in logs) and not prompts
        # a triggered video last week (and a simulated one this week) → the recap runs
        hist.write_text(json.dumps({"videos": [
            {"kind": "triggered", "trigger_id": "T", "video_id": "V1", "date": (now - timedelta(days=8)).isoformat()},
            {"kind": "triggered", "trigger_id": "S", "video_id": "V2", "date": now.isoformat(), "simulated": True}]}))
        assert app.main(["--session", "recap"]) == 0, logs
        assert len(prompts) == 1 and "Sui rallies after network news" in prompts[0]
        assert len(yt) == 1 and yt[0]["video"].name == "recap_16x9.mp4" and _probe_size(yt[0]["video"]) == (1920, 1080)
        meta = yt[0]["meta"]
        assert meta["title"] == recap.TITLE and not rules.title_problems(meta["title"])
        assert meta["description"].count(rules.disclosure(live, "recap")) == 1 and meta["description"].count(CG_CREDIT) == 1
        assert "Sui: +18.0% over 7 days" in meta["description"] and "Solana: −12.0%" in meta["description"], meta
        from PIL import Image
        with Image.open(yt[0]["thumbnail"]) as im:
            assert im.size == (1280, 720)
        e = json.loads(hist.read_text())["videos"][-1]
        assert e["kind"] == "recap" and e["video_id"] == "R1" and e["week"] == "2026-W42" and e["platforms"] == ["youtube"]
        assert e["coins"] == ["SUI", "SOL", "BTC"], e
        from autopilot import material
        mat = json.loads((tmp / "data" / "material" / "recap-recap-2026-W42.json").read_text())
        assert material.validate(mat) == [] and mat["youtube_id"] == "R1", material.validate(mat)
        mk = mat["market"]
        assert mk["numbers"]["SUI"]["change_7d"] == 18.0 and mk["numbers"]["SUI"]["source"] == "CoinGecko"
        assert mk["credit"] == CG_CREDIT and len(mk["hooks"]) >= 2 and mk["causes"]["SUI"] == news[0]["title"], mk
    finally:
        (app.ROOT, app.log, app.datetime, recap.fetch, recap.generate_json, recap.fact_check, voice.synthesize,
         youtube.upload_lesson, facebook.publish_video, youtube.upload) = saved
    ap = yaml.safe_load((ROOT / ".github" / "workflows" / "autopilot.yml").read_text(encoding="utf-8"))
    assert "recap" in ap.get("on", ap.get(True))["workflow_dispatch"]["inputs"]["session"]["options"]
    shutil.rmtree(tmp, ignore_errors=True)
    print("OK recap: skipped in a week with a triggered video (logged), quiet week → 16:9 recap of the 3 biggest "
          "7-day moves (fixture numbers, causes), fixed title + disclosure + CoinGecko credit once, mini-board "
          "thumbnail, YouTube only, dark timed skip, workflow option")


# ─── standalone Shorts (epic-standalone-shorts) ─────────────────────────────

SHORT_NOW = datetime(2026, 10, 15, 13, 5, tzinfo=timezone.utc)  # Thursday, Short A's slot
SHORT_VOCAB = ("ledger", "network", "block", "wallet", "node", "miner", "token", "chain", "reward", "supply", "holder",
               "fund", "share", "exchange", "custodian", "record", "fee", "signal", "layer", "bridge", "vault", "key",
               "address", "balance", "transfer", "proof", "stake", "validator", "pool", "order", "trade", "volume",
               "spread", "candle", "trend", "range", "level", "swing", "zone", "pattern", "breakout", "retest",
               "momentum", "session", "liquidity", "flow", "chart", "move", "story", "idea", "rule", "step", "part")


def _short_answer(n: int, prompt: str, first: str | None = None) -> dict:
    """A mocked Short script (30 words a scene, distinct per call n) whose hook names the prompt's term."""
    import re as _re
    rnd = random.Random(n)
    term = (_re.search(r'"term": "([^"]+)"', prompt) or _re.search(r"HOOK: (.+)", prompt))
    term = term.group(1) if term else "this idea"

    def text(k):
        return " ".join(rnd.choice(SHORT_VOCAB) for _ in range(k)).capitalize() + "."
    hook = f"Why does {term.lower()} matter for the {SHORT_VOCAB[n % len(SHORT_VOCAB)]}?"
    if len(hook) > 60:
        hook = f"What does the {SHORT_VOCAB[n % len(SHORT_VOCAB)]} part show?"
    return {"hook": hook, "card": "WHY IT MATTERS?",
            "scenes": [{"id": "hook", "text": first or f"Why does {term.lower()} matter? " + text(22)},
                       {"id": "explain", "text": text(15) + " " + text(15)},
                       {"id": "payoff", "text": text(14) + " " + text(14)}]}


def _basics_material(cfg, vid: str = "Y1", published: str = "2026-10-14T15:05:00+00:00", topic_id: str = "") -> dict:
    from autopilot import basics, material
    topic = dict(basics.sample_topic(), thumbnail="BITCOIN ETF?", approved=True)
    if topic_id:
        topic["id"] = topic_id
    scenes = [{"id": k, "text": v} for k, v in _sample_narration().items()]
    return material.build_basics(topic, scenes, {"video_id": vid, "fb_video_id": None, "date": published}, cfg)


class _ShortRun:
    """A temporary ROOT with the live config (+ `update`) and `materials` in data/material/; Gemini, the voice,
    YouTube and the Facebook Reel mocked. `answer(n, prompt)` gives the n-th LLM answer (default _short_answer)."""

    def __init__(self, materials, answer=None, now=SHORT_NOW, update=None, history=None):
        from autopilot import material
        self.tmp = Path(tempfile.mkdtemp())
        live = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
        self.cfg = json.loads(json.dumps(live))
        for k, v in (update or {}).items():
            self.cfg.setdefault(k, {}).update(v)
        (self.tmp / "config.yaml").write_text(yaml.safe_dump(self.cfg, allow_unicode=True), encoding="utf-8")
        for m in materials:
            material.write(m, self.tmp)
        if history:
            (self.tmp / "data").mkdir(parents=True, exist_ok=True)
            (self.tmp / "data" / "history.json").write_text(json.dumps({"videos": history}))
        self.now, self.answer = now, answer or _short_answer
        self.prompts, self.logs, self.yt, self.fb, self.spoken = [], [], [], [], []

    def __enter__(self):
        import main as app
        from autopilot import shorts, voice, youtube
        self.app = app
        run_ = self

        class FixedNow(datetime):
            @classmethod
            def now(cls, tz=None):
                return run_.now.astimezone(tz) if tz else run_.now.replace(tzinfo=None)

        def fake_llm(prompt, models, temperature=0.9):
            self.prompts.append(prompt)
            return self.answer(len(self.prompts), prompt)

        def fake_upload(video, meta, cfg_, log=print):
            self.yt.append({"video": Path(video), "meta": dict(meta)})
            return f"S{len(self.yt) + len(self.fb) * 0}"

        def fake_reel(video, caption, cfg_, cover=None, log=print):
            self.fb.append({"video": Path(video), "caption": caption, "cover": cover})
            return f"FR{len(self.fb)}"
        self.saved = (app.ROOT, app.log, app.datetime, shorts.generate_json, voice.synthesize, youtube.upload,
                      youtube.set_thumbnail, facebook.publish_reel, facebook.disabled_reason)
        app.ROOT, app.log, app.datetime = self.tmp, self.logs.append, FixedNow
        shorts.generate_json, voice.synthesize = fake_llm, _sine_voice(self.spoken)
        youtube.upload, youtube.set_thumbnail = fake_upload, (lambda *a, **k: True)
        facebook.publish_reel, facebook.disabled_reason = fake_reel, (lambda cfg_: "")
        return self

    def run(self, *argv) -> int:
        return self.app.main(list(argv))

    def history(self) -> list[dict]:
        p = self.tmp / "data" / "history.json"
        return json.loads(p.read_text())["videos"] if p.exists() else []

    def __exit__(self, *exc):
        from autopilot import shorts, voice, youtube
        (self.app.ROOT, self.app.log, self.app.datetime, shorts.generate_json, voice.synthesize, youtube.upload,
         youtube.set_thumbnail, facebook.publish_reel, facebook.disabled_reason) = self.saved
        shutil.rmtree(self.tmp, ignore_errors=True)
        return False


def test_short_concept(cfg):
    """Concept Short (epic-standalone-shorts entry 1): from a fixture Basics material file with a mocked LLM, a
    manual short_a run renders a 9:16 Short (the segment's diagram stepped), publishes it as a YouTube Short + a
    Facebook Reel through main.publish and records kind: short with its material, segment and A/B voice; a draft
    whose first sentence asks viewers to subscribe is discarded; a timed run while shorts.enabled is false logs
    and exits 0; autopilot.yml offers short_a and short_b."""
    from autopilot import shorts
    live = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    assert live["shorts"]["enabled"] is False
    assert live["sessions"]["short_a"]["start_utc"] == "13:00" and live["sessions"]["short_b"]["start_utc"] == "23:00"
    assert all(live["sessions"][k]["kind"] == "short" for k in ("short_a", "short_b"))
    assert shorts.opening_problems("Subscribe for more! Here is what an ETF is.")
    assert shorts.opening_problems("Before we start, hit the bell. A fund holds assets.")
    assert not shorts.opening_problems("What is an ETF? It is a fund. Subscribe later.")
    m = _basics_material(cfg)

    def answer(n, prompt):
        return _short_answer(n, prompt, first="Subscribe for more, but first: what is a fund?" if n == 1 else None)
    with _ShortRun([m], answer=answer) as r:
        assert r.run("--session", "short_a", "--scheduled") == 0
        assert any("shorts.enabled is false" in x for x in r.logs) and not r.prompts
        assert r.run("--session", "short_a") == 0, r.logs[-5:]
        assert any("Discarding Short draft" in x and "subscribe ask in the opening" in x for x in r.logs), r.logs
        assert len(r.prompts) == 2 and "Exchange-traded fund" in r.prompts[0]
        assert len(r.yt) == 1 and len(r.fb) == 1 and _probe_size(r.yt[0]["video"]) == (1080, 1920)
        assert any(x.startswith("Step reveal explain") for x in r.logs), r.logs
        e = r.history()[-1]
        assert e["kind"] == "short" and e["session"] == "short_a" and e["material"] == f"basics-{m['source']['id']}"
        assert e["segment"] == "point_1" and e["source_video"] == "Y1" and e["video_id"] == "S1"
        assert e["fb_reel_id"] == "FR1" and e["voice"] in (live["voice"]["name"], live["voice"]["alternate"]), e
        assert r.spoken and r.spoken[0][0]["id"] == "hook"
    ap = yaml.safe_load((ROOT / ".github" / "workflows" / "autopilot.yml").read_text(encoding="utf-8"))
    opts = ap.get("on", ap.get(True))["workflow_dispatch"]["inputs"]["session"]["options"]
    assert opts[-3:] == ["recap", "short_a", "short_b"], opts
    print("OK short concept: Basics material → own hook + script (subscribe-first draft discarded), 9:16 render with "
          "the stepped diagram, YouTube Short + Reel via main.publish, history kind short + material/segment/voice, "
          "dark timed skip, workflow options")


def test_short_packaging(cfg):
    """Short packaging (entry 2): a 61-character or dated hook title is rewritten once (and the rewrite is used),
    one still breaking a rule stops the Short (exit 1, nothing published); the title carries no hashtag, the
    description carries the hashtags (#Shorts last) and the disclosure line exactly once, the Reel caption the
    same without #Shorts; frame 0 is the hook card (1-4 words)."""
    from autopilot import shorts
    long_hook = "Why does an exchange-traded fund matter to an everyday saver?"
    assert len(long_hook) == 61 and shorts.title_problems(long_hook)
    assert shorts.title_problems("What changed for Bitcoin ETFs on Oct 15, 2026?")
    assert not shorts.title_problems("What is an exchange-traded fund?")
    assert not shorts.card_problems("WHAT IS AN ETF?") and shorts.card_problems("WHAT IS AN ETF REALLY?")
    m = _basics_material(cfg)
    line = rules.disclosure(cfg, "shorts")

    def answer(n, prompt):
        if "Rewrite the title" in prompt:
            return {"hook": "What is an exchange-traded fund?", "card": "WHAT IS AN ETF?"}
        return dict(_short_answer(n, prompt), hook=long_hook, card="")
    with _ShortRun([m], answer=answer) as r:
        assert r.run("--session", "short_a") == 0, r.logs[-5:]
        assert any("Short title rewrite" in x for x in r.logs) and sum("Rewrite the title" in p for p in r.prompts) == 1
        meta = r.yt[0]["meta"]
        assert meta["title"] == "What is an exchange-traded fund?" and "#" not in meta["title"]
        d = meta["description"]
        assert d.count(line) == 1 and d.rstrip().endswith("#Shorts") and "#Crypto" in d, d
        cap = r.fb[0]["caption"]
        assert cap.count(line) == 1 and "#Shorts" not in cap and "#Crypto" in cap, cap
        check_opening(r.yt[0]["video"], r.yt[0]["video"].parent, hold=0.85)  # mocked voice: a short hook scene
        assert r.fb[0]["cover"].name == "thumbnail.jpg"
        assert json.loads((r.yt[0]["video"].parent / "package.json").read_text())["card"] == "WHAT IS AN ETF?"

    def dated(n, prompt):
        if "Rewrite the title" in prompt:
            return {"hook": "What changed for Bitcoin ETFs on Oct 15?", "card": "ETF NEWS"}
        return dict(_short_answer(n, prompt), hook="What changed for Bitcoin ETFs on Oct 15?")
    with _ShortRun([m], answer=dated) as r:
        assert r.run("--session", "short_a") == 1
        assert any("Short packaging" in x for x in r.logs) and not r.yt and not r.fb and not r.history()
    print("OK short packaging: long title rewritten once, dated title stops the Short, hashtags + disclosure once "
          "in the description and Reel caption (no #Shorts there), frame 0 = hook card")


def test_short_related(cfg):
    """Related-video link (entry 3): a Short made from material with video id X has https://youtu.be/X on its
    description's first line and in its Reel caption; after the upload one line logs the owner's Studio task
    (the API has no related-video field); the history entry gains nothing for it."""
    m = _basics_material(cfg, vid="Xvid123")
    with _ShortRun([m]) as r:
        assert r.run("--session", "short_b") == 0, r.logs[-5:]
        d = r.yt[0]["meta"]["description"]
        assert d.splitlines()[0] == "▶ Full video: https://youtu.be/Xvid123", d
        assert "https://youtu.be/Xvid123" in r.fb[0]["caption"].splitlines()[0]
        assert any(x.startswith("Studio task: set the related video of https://youtube.com/shorts/S1 to "
                                "https://youtu.be/Xvid123") for x in r.logs), r.logs[-4:]
        e = r.history()[-1]
        assert e["source_video"] == "Xvid123" and not any("related" in k for k in e), e
    print("OK short related: youtu.be/<source> first line of the description + Reel caption, Studio task logged")


def _market_material(tid: str = "t1", vid: str = "TV1", published: datetime | None = None,
                     sources=("Coinbase", "CoinGecko"), kind: str = "triggered", hooks=None) -> dict:
    """A triggered (or recap) Shorts material in epic 3 entry 9's format: Bitcoin −7.2%, Ethereum −4.5%."""
    from autopilot.sources import CG_CREDIT
    published = published or SHORT_NOW - timedelta(days=1)
    return {"version": 1, "source": {"kind": kind, "id": tid, "title": "Why Bitcoin Just Dropped 7% (What Actually Happened)"},
            "youtube_id": vid, "facebook_id": None, "published_at": published.isoformat(), "segments": [],
            "market": {"numbers": {"BTC": {"name": "Bitcoin", "price": 62400, "change_24h": -7.2, "change_7d": -9.1,
                                           "source": "Coinbase"},
                                   "ETH": {"name": "Ethereum", "price": 2450, "change_24h": -4.5, "change_7d": -6.0,
                                           "source": "Coinbase"}},
                       "total_cap_change_24h": -5.1, "data_source": list(sources),
                       "credit": CG_CREDIT if "CoinGecko" in sources else "",
                       "series": {"BTC": [67200 - 100 * i for i in range(49)], "ETH": [2565 - 2.4 * i for i in range(49)]},
                       "cause_headline": "Bitcoin slides as spot ETF outflows hit a record",
                       "causes": {"BTC": "Bitcoin slides as spot ETF outflows hit a record", "ETH": None},
                       "hooks": list(hooks or ["Why did Bitcoin just drop 7%?", "What really moved Bitcoin?",
                                               "Why is Bitcoin down 7%?"])}}


def _market_answer(n: int, prompt: str, bad: bool = False) -> dict:
    a = _short_answer(n, prompt)
    a["scenes"][0]["text"] = "Bitcoin fell 7.2% in a day. " + a["scenes"][0]["text"]
    a["scenes"][2]["text"] = f"Ethereum lost {'9.9' if bad else '4.5'}% too. " + a["scenes"][2]["text"]
    a["card"] = "WHY -7%?"
    return a


def test_short_market(cfg):
    """Market Short (entry 4): a triggered material under 3 days old renders a market Short (mocked LLM; a draft
    with a number the material lacks is discarded) whose hook is the first candidate and whose spoken numbers
    match the material; a second Short uses the other hook candidate; a third is refused (logged); the CoinGecko
    credit is in the description exactly once for a CoinGecko-sourced material and absent for Coinbase-only; a
    4-day-old source is refused with a log line."""
    from autopilot import material, shorts
    from autopilot.sources import CG_CREDIT
    m = _market_material()
    assert material.validate(m) == [], material.validate(m)
    assert shorts.lead_coin(m) == "BTC" and shorts.market_diagram(m)["nodes"][1]["label"] == "Bitcoin −7.2%"

    def answer(n, prompt):
        return _market_answer(n, prompt, bad=n == 1)
    with _ShortRun([m], answer=answer) as r:
        assert r.run("--session", "short_a") == 0, r.logs[-5:]
        assert any("Discarding Short draft" in x and "9.9" in x for x in r.logs), r.logs
        assert "HOOK: Why did Bitcoin just drop 7%?" in r.prompts[0] and "62400" in r.prompts[0]
        assert _probe_size(r.yt[0]["video"]) == (1080, 1920)
        meta = r.yt[0]["meta"]
        assert meta["title"] == "Why did Bitcoin just drop 7%?" and meta["description"].count(CG_CREDIT) == 1
        assert r.fb[0]["caption"].count(CG_CREDIT) == 1 and "https://youtu.be/TV1" in meta["description"]
        said = " ".join(sc["text"] for sc in r.spoken[-1])
        assert "7.2%" in said and "4.5%" in said and "9.9" not in said
        e = r.history()[-1]
        assert e["short_kind"] == "market" and e["material"] == "triggered-t1" and e["segment"] == "hook_0", e
        assert r.run("--session", "short_b") == 0
        assert r.yt[1]["meta"]["title"] == "What really moved Bitcoin?" and r.history()[-1]["segment"] == "hook_1"
        assert r.run("--session", "short_a") == 0 and len(r.yt) == 2
        assert any("triggered-t1 already has 2 market Shorts; refused" in x for x in r.logs)
        assert any("nothing to publish in this slot" in x for x in r.logs)
    with _ShortRun([_market_material(tid="t2", sources=("Coinbase",))]) as r:
        r.answer = _market_answer
        assert r.run("--session", "short_a") == 0 and CG_CREDIT not in r.yt[0]["meta"]["description"]
        assert "Data: Coinbase" in r.yt[0]["meta"]["description"]
    with _ShortRun([_market_material(tid="t3", published=SHORT_NOW - timedelta(days=4))]) as r:
        assert r.run("--session", "short_a") == 0 and not r.yt and not r.prompts
        assert any("triggered-t3 is 4 days old" in x and "refused" in x for x in r.logs), r.logs
    print("OK short market: own hook per candidate (2 max, third refused), numbers from the material only, move "
          "chart + stepped cause diagram, CoinGecko credit once only when sourced, 4-day-old source refused")


def test_short_originality(cfg):
    """Originality guard (entry 5): every Short records a script fingerprint; a mocked script identical to an
    earlier Short's is rewritten once (and the rewrite used); one that stays identical moves the run to another
    segment; a used segment is skipped; two Shorts from one episode differ in segment, hook and script."""
    from autopilot import shorts
    a = _short_answer(5, '"term": "Exchange-traded fund"')
    fp = shorts.fingerprint(shorts.script_text(a))
    assert shorts.similarity(fp, shorts.fingerprint(shorts.script_text(a))) == 1.0
    b = _short_answer(6, '"term": "Exchange-traded fund"')
    assert shorts.similarity(fp, shorts.fingerprint(shorts.script_text(b))) < shorts.MAX_SIMILARITY
    m = _basics_material(cfg)
    k = f"basics-{m['source']['id']}"
    old = [{"kind": "short", "session": "short_b", "brief_date": "2026-10-14", "material": "basics-older",
            "segment": "point_9", "hook": "What is an old idea?", "fingerprint": fp, "video_id": "OLD"}]

    def copy_once(n, prompt):  # the first draft repeats the earlier Short; the rewrite is new
        return dict(a) if n == 1 else _short_answer(n, prompt)
    with _ShortRun([m], answer=copy_once, history=old) as r:
        assert r.run("--session", "short_a") == 0, r.logs[-5:]
        assert any("too close to an earlier Short" in x and "rewriting once" in x for x in r.logs), r.logs
        assert "100% like an earlier Short" in r.prompts[1]
        e = r.history()[-1]
        assert e["segment"] == "point_1" and e["fingerprint"] != fp and len(e["fingerprint"]) == shorts.FP_SLOTS

    def stuck(n, prompt):  # point_1 always repeats the earlier Short → the guard moves to another segment
        return dict(a) if "Exchange-traded fund" in prompt else _short_answer(n, prompt)
    with _ShortRun([m], answer=stuck, history=old) as r:
        assert r.run("--session", "short_a") == 0, r.logs[-5:]
        assert any(f"Originality guard: {k} · point_1" in x and "moving to another segment" in x for x in r.logs)
        assert r.history()[-1]["segment"] == "point_2", r.history()[-1]

    used = old + [{"kind": "short", "session": "short_a", "brief_date": "2026-10-14", "material": k,
                   "segment": "point_1", "hook": "Why does an ETF matter?", "video_id": "U1"}]
    with _ShortRun([m], history=used) as r:
        assert r.run("--session", "short_a") == 0 and r.run("--session", "short_b") == 0, r.logs[-5:]
        e1, e2 = r.history()[-2:]
        assert (e1["segment"], e2["segment"]) == ("point_2", "point_3"), (e1["segment"], e2["segment"])
        assert e1["hook"] != e2["hook"] and shorts.similarity(e1["fingerprint"], e2["fingerprint"]) < 0.5
        assert not any("Exchange-traded fund" in p_ for p_ in r.prompts)
    print("OK short originality: fingerprint recorded, identical script rewritten once, a stuck segment passed "
          "over, used segments skipped, two Shorts of one episode differ in hook and script")


def test_short_lesson(cfg):
    """Lesson material (entry 6): a fixture lesson history entry with the sample curriculum yields material that
    validates (≥ 5 segments, the recorded BTC example in the facts) and a concept Short renders from it with a
    mocked LLM; a lesson whose recorded example is gold or EUR/USD yields no material."""
    from autopilot import lesson_material, lessons, material
    cur = lessons.load_curriculum(ROOT / "tests" / "lessons" / "curriculum.yaml")
    glo = lessons.load_glossary(ROOT / "tests" / "lessons" / "glossary.yaml")
    ep = next(e for e in cur if e["id"] == "bos-vs-choch")
    entry = {"kind": "lesson", "episode": "bos-vs-choch", "video_id": "L1", "fb_video_id": "LF1", "session": "lesson",
             "brief_date": "2026-10-08", "date": "2026-10-08T15:05:00+00:00",
             "examples": [{"asset": "BTC", "timeframe": "4h", "start": "2026-10-01T00:00:00+00:00",
                           "end": "2026-10-03T00:00:00+00:00"}]}
    m = lesson_material.build_lesson(ep, glo, entry)
    assert material.validate(m) == [] and len(m["segments"]) >= 5, material.validate(m)
    assert m["source"] == {"kind": "lesson", "id": "bos-vs-choch", "title": ep["search_title"]} and m["youtube_id"] == "L1"
    assert any("Bitcoin chart on the 4h timeframe" in f for f in m["segments"][1]["facts"])
    for bad in ("XAU/USD", "EURUSD", "PAXG-USD"):
        assert lesson_material.build_lesson(ep, glo, dict(entry, examples=[dict(entry["examples"][0], asset=bad)])) is None
    assert lesson_material.build_lesson(ep, glo, dict(entry, examples=[])) is None
    gold = dict(entry, episode="swing-structure", video_id="L2", examples=[dict(entry["examples"][0], asset="XAU/USD")])
    with _ShortRun([], history=[entry, gold]) as r:
        (r.tmp / "lessons").mkdir()
        for f in ("curriculum.yaml", "glossary.yaml"):
            shutil.copy(ROOT / "tests" / "lessons" / f, r.tmp / "lessons" / f)
        assert r.run("--session", "short_a") == 0, r.logs[-5:]
        assert any("lesson swing-structure's examples aren't BTC / ETH" in x for x in r.logs), r.logs
        e = r.history()[-1]
        assert e["material"] == "lesson-bos-vs-choch" and e["segment"] == "point_1" and e["source_video"] == "L1", e
        assert _probe_size(r.yt[0]["video"]) == (1080, 1920) and "https://youtu.be/L1" in r.yt[0]["meta"]["description"]
    print("OK short lesson: BTC lesson → validating material (key points + glossary terms + example) → concept "
          "Short; gold / EUR/USD / no-example lessons give none")


def test_short_mix(cfg):
    """Daily Shorts mix (entry 7): a simulated week of timed short_a / short_b runs (14 slots, shorts.enabled on)
    gives 4 market Shorts when 2 market videos are published that week (none from a 5-day-old one) and only
    evergreen Shorts when there are none, with no segment repeated; a slot's second timed run stops under the
    once-per-slot guard; with every segment used a slot logs the skip and the low-stock warning and publishes
    nothing."""
    import main as app
    week0 = SHORT_NOW.replace(hour=10, minute=0)
    basics_m = [_basics_material(cfg, vid=f"B{i}", topic_id=f"topic-{i}",
                                 published=(week0 - timedelta(days=20 - i)).isoformat()) for i in range(3)]
    market = [_market_material(tid="m1", vid="M1", published=week0),
              _market_material(tid="m2", vid="M2", published=week0 + timedelta(days=3),
                               hooks=["Why did crypto slide again?", "What dragged Ethereum lower?"]),
              _market_material(tid="m0", vid="M0", published=week0 - timedelta(days=5))]
    saved = app.render.build_video
    app.render.build_video = lambda audio, pics, cfg_, wd, out, music=None: Path(out).write_bytes(b"mp4") and 0.0

    def week(materials):
        def answer(n, prompt):
            return (_market_answer if "HOOK: " in prompt else _short_answer)(n, prompt)
        with _ShortRun(materials, answer=answer, update={"shorts": {"enabled": True}}) as r:
            for d in range(7):
                for sess, hour in (("short_a", 13), ("short_b", 23)):
                    r.now = (SHORT_NOW + timedelta(days=d)).replace(hour=hour, minute=5)
                    assert r.run("--session", sess, "--scheduled") == 0, r.logs[-6:]
            r.now = (SHORT_NOW + timedelta(days=6)).replace(hour=23, minute=20)
            assert r.run("--session", "short_b", "--scheduled") == 0
            assert any("already published" in x for x in r.logs[-4:]), r.logs[-4:]
            return r.history(), list(r.logs)
    try:
        hist, logs = week(basics_m + market)
        assert len(hist) == 14 and len({(e["session"], e["brief_date"]) for e in hist}) == 14
        kinds = [e["short_kind"] for e in hist]
        assert kinds.count("market") == 4 and kinds.count("concept") == 10, kinds
        assert {e["material"] for e in hist if e["short_kind"] == "market"} == {"triggered-m1", "triggered-m2"}
        assert len({(e["material"], e["segment"]) for e in hist}) == 14
        assert any("triggered-m0 is 5 days old" in x for x in logs)
        assert [e["material"] for e in hist if e["short_kind"] == "concept"][:5] == ["basics-topic-0"] * 5
        hist, _ = week(basics_m)
        assert [e["short_kind"] for e in hist] == ["concept"] * 14 and len({(e["material"], e["segment"]) for e in hist}) == 14
        used = [{"kind": "short", "session": "short_b", "brief_date": "2026-10-14", "material": "basics-topic-0",
                 "segment": s_["id"], "hook": f"Old hook {s_['id']}?", "video_id": f"U{s_['id']}"}
                for s_ in basics_m[0]["segments"]]
        with _ShortRun([basics_m[0]], update={"shorts": {"enabled": True}}, history=used) as r:
            assert r.run("--session", "short_a", "--scheduled") == 0 and not r.yt and not r.prompts
            assert any("the short_a slot is skipped" in x for x in r.logs), r.logs[-4:]
            assert any("low-stock warning: 0 unused" in x for x in r.logs) and len(r.history()) == len(used)
    finally:
        app.render.build_video = saved
    print("OK short mix: simulated week → 4 market + 10 evergreen Shorts with 2 market videos (old one refused), "
          "14 evergreen with none, no segment repeated, once per slot, empty stock → skip + low-stock warning")


def _wf_map(text: str) -> tuple[dict, dict, dict]:
    """autopilot.yml: ({cron: edition} from EDITION, the same from concurrency.group, the `on` section)."""
    import re
    wf = yaml.safe_load(text)
    job = wf["jobs"]["make-and-upload"]
    step = next(x for x in job["steps"] if x.get("name") == "Make and publish")
    pairs = lambda t: dict(re.findall(r"github\.event\.schedule == '([^']+)' && '([a-z_]+)'", t))  # noqa: E731
    return pairs(step["env"]["EDITION"]), pairs(job["concurrency"]["group"]), wf.get("on", wf.get(True))


def _main_logs(app, argv: list[str], now: datetime, root: Path) -> tuple[int, list[str]]:
    """main(argv) at a fixed UTC time under `root`, with its log lines."""
    class FixedNow(datetime):
        @classmethod
        def now(cls, tz=None):
            return now.astimezone(tz) if tz else now.replace(tzinfo=None)
    logs = []
    saved = (app.ROOT, app.datetime, app.log)
    app.ROOT, app.datetime, app.log = root, FixedNow, logs.append
    try:
        return app.main(argv), logs
    finally:
        app.ROOT, app.datetime, app.log = saved


def test_slate_timetable(cfg):
    """Slate 5.1: every timed session has one backup cron (17 min after start_utc, on its days) whose string maps to
    it in EDITION and concurrency.group; retired editions (asia, london, newyork, gold) and `auto` are gone; no
    weekend skip (a Saturday timed short_a run is made); setup_cronjobs.py --dry-run plans only the slate's jobs."""
    import contextlib
    import io
    import main as app
    import setup_cronjobs

    live = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    sessions = live["sessions"]
    retired = ("asia", "london", "newyork", "gold")
    assert not set(retired) & set(sessions) and not set(retired) & set(app.DEFAULT_SESSIONS), sessions.keys()
    assert "weekend_sessions" not in live and not hasattr(app, "auto_session")
    timed = {k: s for k, s in sessions.items() if s.get("start_utc")}
    want = {"news_morning": ("12:00", []), "news_midday": ("16:00", []), "news_evening": ("21:00", []),
            "short_a": ("13:00", []), "short_b": ("23:00", []), "basics": ("15:00", ["wed"]),
            "lesson": ("15:00", ["thu"]), "recap": ("15:00", ["sat"])}
    for k, (t, days) in want.items():
        assert timed[k]["start_utc"] == t and list(timed[k].get("days") or []) == days, (k, timed[k])
    text = (ROOT / ".github" / "workflows" / "autopilot.yml").read_text(encoding="utf-8")
    edition, group, on = _wf_map(text)
    crons = [c["cron"] for c in on["schedule"]]
    assert edition == group and set(edition) == set(crons) and len(crons) == len(set(crons)), (edition, group, crons)
    dow = {"sun": "0", "mon": "1", "tue": "2", "wed": "3", "thu": "4", "fri": "5", "sat": "6"}
    for k, s in timed.items():
        mine = [c for c, e in edition.items() if e == k]
        assert len(mine) == 1, (k, mine)
        h, m = (int(x) for x in s["start_utc"].split(":"))
        t = h * 60 + m + 17
        exp = f"{t % 60} {t // 60 % 24} * * " + (",".join(dow[d] for d in s.get("days") or []) or "*")
        assert mine[0] == exp, (k, mine[0], exp)
    assert set(edition.values()) == set(timed), edition
    choices = on["workflow_dispatch"]["inputs"]["session"]["options"]
    assert not set(retired) & set(choices) and "auto" not in choices and set(choices) <= set(sessions), choices
    assert not any(r in text for r in ("'asia'", "'london'", "'newyork'", "'gold'", "'auto'"))

    tmp = Path(tempfile.mkdtemp())
    c = json.loads(json.dumps(live))
    c["shorts"]["enabled"] = True
    (tmp / "config.yaml").write_text(yaml.safe_dump(c, sort_keys=False), encoding="utf-8")
    sat = datetime(2026, 10, 17, 13, 4, tzinfo=timezone.utc)  # a Saturday, 4 min after Short A's start
    for argv in (["--session", "gold"], ["--session", "london", "--scheduled"], ["--session", "auto"], []):
        rc, logs = _main_logs(app, argv, sat, tmp)
        assert rc == 1 and not any("Edition:" in x for x in logs), (argv, logs)
    assert any("Unknown edition 'gold'" in x for x in _main_logs(app, ["--session", "gold"], sat, tmp)[1])
    made = []
    saved = app.make_short
    app.make_short = lambda *a, **k: made.append(a[2]) or None
    try:
        rc, logs = _main_logs(app, ["--session", "short_a", "--scheduled"], sat, tmp)
    finally:
        app.make_short = saved
    assert rc == 0 and made == ["short_a"] and not any("eekend" in x for x in logs), logs

    out = io.StringIO()
    argv0 = sys.argv
    sys.argv = ["setup_cronjobs.py", "--dry-run"]
    try:
        with contextlib.redirect_stdout(out):
            assert setup_cronjobs.main() == 0
    finally:
        sys.argv = argv0
    planned = [ln.split()[2] for ln in out.getvalue().splitlines() if ln.startswith("  CryptoFX · ")]
    assert sorted(planned) == sorted(timed), out.getvalue()
    assert "Retired" in out.getvalue() and all(f"CryptoFX · {r}" in out.getvalue() for r in retired)
    shutil.rmtree(tmp, ignore_errors=True)
    print("OK slate timetable (one backup cron per timed session in EDITION + concurrency.group, retired editions "
          "and auto gone, no weekend skip, setup_cronjobs --dry-run plans only the slate)")


def _simulate_week(cfg, trigger_times: list[datetime], start: datetime = datetime(2026, 10, 12, tzinfo=timezone.utc)):
    """A slate week through the budget rules (slate.short_skip, triggers.hold): Short A 13:00, the standing long
    video 15:00 (Wed Basics, Thu Lesson, Sat recap unless a triggered video published this week), Short B 23:00,
    and triggered videos at their due times (a held one moves to 00:00 next day). Returns (history, logs)."""
    from autopilot import slate, triggers
    hist, logs = [], []
    state = {"version": 1, "triggers": [{"id": f"t{i}", "status": "pending", "due_utc": t.isoformat()}
                                       for i, t in enumerate(trigger_times)]}

    def up(kind, session, when):
        hist.append({"brief_date": when.strftime("%Y-%m-%d"), "session": session, "kind": kind,
                     "video_id": f"V{len(hist)}", "date": when.isoformat(), "counts": True})
    for d in range(8):  # the week + the Monday after (a held Sunday trigger lands there)
        day = start + timedelta(days=d)
        events = [(day.replace(hour=13), "short_a"), (day.replace(hour=15), "long"), (day.replace(hour=23), "short_b")]
        while True:
            due = [t for t in state["triggers"] if t["status"] == "pending"
                   and datetime.fromisoformat(t["due_utc"]).date() == day.date()]
            evs = sorted(events + [(datetime.fromisoformat(t["due_utc"]), t) for t in due], key=lambda x: x[0])
            if not evs:
                break
            when, what = evs[0]
            if isinstance(what, dict):
                if not triggers.hold(what, hist, when, cfg, logs.append):
                    what["status"] = "published"
                    up("triggered", "triggered", when)
                continue
            events.remove((when, what))
            if what == "long":
                wd = when.weekday()
                if wd in (2, 3):
                    up("basics" if wd == 2 else "lesson", "basics" if wd == 2 else "lesson", when)
                elif wd == 5 and not any(v["kind"] == "triggered" for v in slate.long_videos(hist, when)):
                    up("recap", "recap", when)
                continue
            seen = {"triggers": [t for t in state["triggers"]  # a trigger is known once it has fired (≈ its due time)
                                 if datetime.fromisoformat(t.get("held_from") or t["due_utc"]) <= when]}
            why = slate.short_skip(hist, seen, what, when, cfg)
            if why:
                logs.append(f"{what} {when:%a} yields: {why}")
            else:
                up("short", what, when)
    return hist, logs


def test_slate_budget(cfg):
    """Slate 5.2: at most 3 YouTube uploads a UTC day. A Wednesday with Basics and a due trigger skips the timed
    Short B with a log line (through main); on a Thursday where Short B is already up a due trigger holds to 00:00
    UTC next day (triggers.check moves its due time, then dispatches it); simulated weeks never exceed 3 a day."""
    from collections import Counter
    import main as app
    from autopilot import slate, triggers

    live = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    assert live["slate"] == {"day_cap": 3, "yield_days": ["wed", "thu"], "week_floor": 3, "week_cap": 4}
    tmp = Path(tempfile.mkdtemp())
    c = json.loads(json.dumps(live))
    c["shorts"]["enabled"], c["triggers"]["enabled"] = True, True
    (tmp / "config.yaml").write_text(yaml.safe_dump(c, sort_keys=False), encoding="utf-8")
    (tmp / "data").mkdir()
    wed = datetime(2026, 10, 14, 23, 4, tzinfo=timezone.utc)

    def entry(kind, session, vid, date="2026-10-14"):
        return {"brief_date": date, "session": session, "kind": kind, "video_id": vid, "counts": True,
                "date": f"{date}T15:05:00+00:00"}
    (tmp / "data" / "history.json").write_text(json.dumps({"videos": [entry("short", "short_a", "A1"),
                                                                       entry("basics", "basics", "B1")]}))
    triggers.save_state({"version": 1, "triggers": [{"id": "t-wed", "status": "pending",
                                                     "due_utc": "2026-10-14T19:00:00+00:00"}]}, tmp / triggers.STATE)
    made = []
    saved = app.make_short
    app.make_short = lambda *a, **k: made.append(a[2]) or None
    try:
        rc, logs = _main_logs(app, ["--session", "short_b", "--scheduled"], wed, tmp)
        assert rc == 0 and not made and any("Short B yields its slot today" in x and "Wed" in x for x in logs), logs
        # a Tuesday with a due trigger and no long video: Short B goes ahead
        triggers.save_state({"version": 1, "triggers": [{"id": "t-tue", "status": "pending",
                                                         "due_utc": "2026-10-13T19:00:00+00:00"}]}, tmp / triggers.STATE)
        rc, logs = _main_logs(app, ["--session", "short_b", "--scheduled"], wed - timedelta(days=1), tmp)
        assert rc == 0 and made == ["short_b"], logs
    finally:
        app.make_short = saved

    # Thursday: Short A, Lesson and Short B are up; a trigger due 23:30 holds to Friday 00:00, then dispatches
    thu = "2026-10-15"
    (tmp / "data" / "history.json").write_text(json.dumps({"videos": [
        entry("short", "short_a", "A2", thu), entry("lesson", "lesson", "L2", thu), entry("short", "short_b", "S2", thu)]}))
    triggers.save_state({"version": 1, "triggers": [{"id": "t-thu", "status": "pending", "key": "k",
                                                     "fired_utc": "2026-10-15T23:30:00+00:00",
                                                     "due_utc": "2026-10-15T23:30:00+00:00"}]}, tmp / triggers.STATE)
    quiet = lambda cfg_, log=print: ({"crypto": {}, "news": []}, None)  # noqa: E731  (nothing new fires)
    logs = []
    res = triggers.check(c, tmp, now=datetime(2026, 10, 15, 23, 43, tzinfo=timezone.utc), log=logs.append, fetch=quiet)
    t = triggers.load_state(tmp / triggers.STATE)["triggers"][0]
    assert res["due"] == "" and t["status"] == "pending" and t["due_utc"] == "2026-10-16T00:00:00+00:00", (res, t)
    assert t["held_from"] == "2026-10-15T23:30:00+00:00" and any("held to 2026-10-16T00:00" in m for m in logs), logs
    res = triggers.check(c, tmp, now=datetime(2026, 10, 16, 0, 13, tzinfo=timezone.utc), log=logs.append, fetch=quiet)
    assert res["due"] == "t-thu", (res, logs)
    shutil.rmtree(tmp, ignore_errors=True)

    # simulated weeks (Mon 12 Oct 2026): never more than 3 YouTube uploads on a UTC day
    D = lambda d, h, m=0: datetime(2026, 10, d, h, m, tzinfo=timezone.utc)  # noqa: E731
    for times in ([], [D(14, 12)], [D(14, 23, 30)], [D(15, 18)], [D(17, 20)], [D(17, 23, 40)], [D(18, 23, 30)],
                  [D(12, 12), D(14, 16)], [D(13, 23, 30), D(15, 23, 45)], [D(16, 14), D(18, 18)]):
        hist, logs = _simulate_week(live, times)
        per_day = Counter(v["brief_date"] for v in hist)
        assert max(per_day.values()) <= 3, (times, per_day, logs)
        assert sum(v["kind"] == "triggered" for v in hist) == len(times), (times, hist)  # every trigger published
    hist, logs = _simulate_week(live, [D(14, 23, 30)])  # Wed after Short B: held to Thu 00:00, Thu Short B yields
    trig = next(v for v in hist if v["kind"] == "triggered")
    assert trig["date"] == "2026-10-15T00:00:00+00:00", trig
    assert any(x.startswith("short_b Thu yields") for x in logs), logs
    assert slate.next_day(D(15, 23, 59)) == D(16, 0)
    print("OK slate budget (Wed trigger → Short B yields with a log line, Thu full day → trigger held to 00:00 then "
          "dispatched, simulated weeks ≤ 3 YouTube uploads a day)")


def test_slate_floor(cfg):
    """Slate 5.3: the weekly floor of 3 and cap of 4 long videos (ISO week, UTC). A skipped Saturday recap with the
    week short runs the evergreen top-up into the recap slot; a week whose Saturday already had the recap (or a
    triggered video) tops up Sunday 15:00 (topup_sun); Basics + Lesson + one trigger → no top-up; a long upload in a
    week that already has 4 is refused with a log line. make_evergreen / make_lesson_edition are faked."""
    import main as app

    live = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    assert live["sessions"]["topup_sun"] == {"label": "Sunday top-up", "short": "Top-up", "start_utc": "15:00",
                                             "kind": "floor", "days": ["sun"], "platforms": ["youtube", "facebook"]}
    tmp = Path(tempfile.mkdtemp())
    c = json.loads(json.dumps(live))
    c["recap"]["enabled"] = c["evergreen"]["enabled"] = c["lessons"]["enabled"] = True
    (tmp / "config.yaml").write_text(yaml.safe_dump(c, sort_keys=False), encoding="utf-8")
    (tmp / "data").mkdir()
    sat, sun = datetime(2026, 10, 17, 15, 4, tzinfo=timezone.utc), datetime(2026, 10, 18, 15, 4, tzinfo=timezone.utc)

    def week(*rows):
        (tmp / "data" / "history.json").write_text(json.dumps({"videos": [
            {"brief_date": d, "session": k, "kind": k, "video_id": f"V{i}", "date": f"{d}T15:05:00+00:00",
             "counts": True, **({"trigger_id": f"t{i}"} if k == "triggered" else {})}
            for i, (k, d) in enumerate(rows)]}))
    calls = []
    saved = (app.make_evergreen, app.make_lesson_edition, app.make_recap)
    app.make_evergreen = lambda cfg_, h, date, slot, pending, nu, force: (calls.append(("evergreen", slot)) and None,
                                                                          pending, "basics")
    app.make_lesson_edition = lambda *a, **k: (calls.append(("lesson", a[3])) and None, a[4])
    app.make_recap = lambda *a, **k: calls.append(("recap", a[2])) or (_ for _ in ()).throw(RuntimeError("faked"))
    try:
        # a trigger Monday, Basics Wednesday, the lesson held: the recap skips → Saturday top-up into the recap slot
        week(("triggered", "2026-10-12"), ("basics", "2026-10-14"))
        rc, logs = _main_logs(app, ["--session", "recap", "--scheduled"], sat, tmp)
        assert rc == 0 and calls == [("evergreen", "recap")], (calls, logs)
        assert any("Recap skipped" in x for x in logs) and any("under 3" in x and "recap slot" in x for x in logs), logs
        # no trigger + a held lesson: the recap goes out Saturday, so the top-up is Sunday 15:00 (topup_sun)
        calls.clear()
        week(("basics", "2026-10-14"), ("recap", "2026-10-17"))
        rc, logs = _main_logs(app, ["--session", "topup_sun", "--scheduled"], sun, tmp)
        assert rc == 0 and calls == [("evergreen", "topup_sun")], (calls, logs)
        # a triggered video on Saturday itself: no Saturday top-up (logged), Sunday tops up
        calls.clear()
        week(("basics", "2026-10-14"), ("triggered", "2026-10-17"))
        rc, logs = _main_logs(app, ["--session", "recap", "--scheduled"], sat, tmp)
        assert rc == 0 and calls == [] and any("waits for the next free slot" in x for x in logs), logs
        rc, logs = _main_logs(app, ["--session", "topup_sun", "--scheduled"], sun, tmp)
        assert rc == 0 and calls == [("evergreen", "topup_sun")], (calls, logs)
        # Basics + Lesson + one trigger = 3: no top-up on Saturday or Sunday
        calls.clear()
        week(("triggered", "2026-10-12"), ("basics", "2026-10-14"), ("lesson", "2026-10-15"))
        for argv, when in ((["--session", "recap", "--scheduled"], sat), (["--session", "topup_sun", "--scheduled"], sun)):
            rc, logs = _main_logs(app, argv, when, tmp)
            assert rc == 0 and calls == [] and any("already has 3 long videos" in x for x in logs), (argv, logs)
        # last week's videos don't count for this week; a manual topup_sun run is a manual evergreen top-up
        week(("triggered", "2026-10-05"), ("basics", "2026-10-07"), ("lesson", "2026-10-08"))
        rc, logs = _main_logs(app, ["--session", "topup_sun"], sun, tmp)
        assert rc == 0 and calls == [("evergreen", "topup_sun")], (calls, logs)
        # the cap: a week with 4 long videos refuses a fifth (a counting lesson run; a timed triggered-less recap)
        calls.clear()
        week(("triggered", "2026-10-12"), ("basics", "2026-10-14"), ("lesson", "2026-10-15"), ("lesson", "2026-10-16"))
        rc, logs = _main_logs(app, ["--session", "lesson", "--as-edition"], sun, tmp)
        assert rc == 0 and calls == [] and any("Weekly cap" in x and "at most 4" in x for x in logs), logs
        rc, logs = _main_logs(app, ["--session", "evergreen", "--slot", "topup_sun"], sun, tmp)
        assert rc == 0 and calls == [] and any("Weekly cap" in x for x in logs), logs
        week(("basics", "2026-10-14"), ("lesson", "2026-10-15"), ("lesson", "2026-10-16"), ("basics", "2026-10-16"))
        rc, logs = _main_logs(app, ["--session", "recap", "--scheduled"], sat, tmp)
        assert rc == 0 and calls == [] and any("Weekly cap" in x for x in logs), logs
        # under the cap the recap is made (faked: it raises after being called)
        week(("basics", "2026-10-14"))
        rc, logs = _main_logs(app, ["--session", "recap", "--scheduled"], sat, tmp)
        assert rc == 1 and calls == [("recap", "recap")], (calls, logs)
    finally:
        app.make_evergreen, app.make_lesson_edition, app.make_recap = saved
    shutil.rmtree(tmp, ignore_errors=True)
    print("OK slate floor (skipped recap → Saturday top-up, Saturday used → Sunday topup_sun, 3 long → no top-up, "
          "ISO week only, a fifth long upload refused with a log line)")


if __name__ == "__main__":
    main()
