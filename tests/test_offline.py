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

from autopilot import facebook, focus, gold, images, news_post, render, script, slides, thumbnail  # noqa: E402
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
        {"text": "Here is the whole board.", "visual": {"type": "board"}},
        {"text": "Today, US core inflation lands at twelve thirty GMT.", "visual": {"type": "calendar"}},
        {"text": "Not financial advice. See you tomorrow.", "visual": {"type": "outro"}},
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
    cover["hook"] = thumbnail.clean_hook(pkg.get("thumbnail_hook"), cover["default_hook"])
    thumb = thumbnail.render(cover, cfg, data["date_utc"], work / "thumbnail.jpg")
    pics = slides.render_slides(cfg, data, PKG["scenes"], work, cover=thumb)
    assert pics[0]["cover"]

    audio = []
    for i, s in enumerate(PKG["scenes"]):
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

    # contact sheet: one frame from the middle of each scene, plus the chart mid-reveal
    t, stamps = 0.0, []
    for a in audio:
        stamps.append(t + a["duration"] * 0.6)
        t += a["duration"]
    stamps[0] = 0.0  # the very first frame must be the thumbnail design
    stamps.insert(2, audio[0]["duration"] + 0.6)  # chart scene, mid-reveal
    for k, ts in enumerate(stamps):
        run(["ffmpeg", "-y", "-v", "error", "-ss", f"{ts:.2f}", "-i", out, "-frames:v", "1",
             "-vf", "scale=360:640", work / f"frame_{k:02d}.png"])
    run(["ffmpeg", "-y", "-v", "error", "-i", work / "frame_%02d.png", "-vf", "tile=4x2:padding=8",
         "-frames:v", "1", work / "contact.png"])

    meta = build_metadata(PKG, data, cfg, "London Open")
    assert "not financial advice" in meta["description"].lower()
    assert meta["tags"][0] == "bitcoin price today" and len(meta["tags"]) == len({t.lower() for t in meta["tags"]})
    assert "bitcoin" in meta["title"][:45].lower() and "Key numbers:" in meta["description"]
    assert meta["description"].split()[-5:][0] == "#Bitcoin" and meta["description"].endswith("#Shorts")
    assert cover["hook"] == cover["default_hook"]  # "Buy the dip now" is rejected
    print(f"OK: {out} ({got:.1f}s) · thumbnail {cover['template']} '{cover['hook']}' · contact sheet {work / 'contact.png'}")
    print(meta["description"])

    test_gold(cfg, small, gdata)
    test_history()
    test_facebook(cfg, PKG, data, meta, out, work / "thumbnail.jpg")
    test_news_post(cfg)
    test_news_edition(cfg)
    test_video_editions(cfg, out, work / "thumbnail.jpg")


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
    pkg = script.make_gold_script(small, data, [], cover, log=lambda m: None)
    types = [s["visual"]["type"] for s in pkg["scenes"]]
    assert types[0] == "title" and types[-1] == "outro" and {"review", "gold_chart", "bias", "liquidity", "scenarios",
                                                              "drivers", "news"} <= set(types), types
    work = ROOT / "output" / "test_gold"
    work.mkdir(parents=True, exist_ok=True)
    cover["hook"] = thumbnail.clean_hook(pkg["thumbnail_hook"], cover["default_hook"])
    thumb = thumbnail.render(cover, cfg, data["date_utc"], work / "thumbnail.jpg", "Gold")
    pics = slides.render_slides(cfg, data, pkg["scenes"], work, cover=thumb, edition="Gold Outlook",
                                footer=cfg["gold"]["footer"])
    audio = []
    for i, s in enumerate(pkg["scenes"]):
        wav = work / f"voice_{i:02d}.wav"
        run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"sine=frequency={300 + 30 * i}:duration=1.2",
             "-ar", "44100", "-ac", "1", wav])
        audio.append({"audio": wav, "duration": probe_duration(wav), "words": [(0.1, 0.5, s["id"])]})
    out = work / "short.mp4"
    render.build_video(audio, pics, cfg, work, out)
    for k, pic in enumerate(pics):
        run(["ffmpeg", "-y", "-v", "error", "-i", pic["image"], "-vf", "scale=360:640", work / f"frame_{k:02d}.png"])
    run(["ffmpeg", "-y", "-v", "error", "-i", work / "frame_%02d.png", "-vf", "tile=5x2:padding=8",
         "-frames:v", "1", work / "contact.png"])
    meta = build_metadata(pkg, data, cfg, "Gold Outlook")
    assert "rule-based" in meta["description"].lower() and "Key levels:" in meta["description"]
    assert meta["title"].startswith("Gold Price Today")  # the mock's title has no keyword → data-built title
    print(f"OK gold: {out} · card {cover['hero']} {cover['line']} · contact sheet {work / 'contact.png'}")


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

    def __init__(self, finish_fails: bool = False, photo_errors: list | None = None):
        self.calls, self.finish_fails = [], finish_fails
        self.photo_errors = list(photo_errors or [])
        self.status_reads = 0
        self.finished = False

    def request(self, method, url, timeout=None, **kw):
        data = kw.get("data") if isinstance(kw.get("data"), dict) else {}
        self.calls.append((method, url, data.get("upload_phase")))
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
             body="Federal Reserve Chair Jerome Powell said the central bank can be patient before cutting "
                  "interest rates again, citing inflation of 3.4%."),
        item("forex", "CNBC", "Powell signals patience on cuts as inflation stays sticky", 3),
        item("geopolitics", "Bloomberg", "US slaps new tariffs on Chinese chips, markets slide", 5),
        item("crypto", "Cointelegraph", "Bitcoin liquidations top $500M as BTC dips", 20, summary="Ether also fell."),
        item("gold", "Kitco", "Gold holds near two-month low as dollar firms", 30),
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
    s4 = news_post.pick_story(data, titles, [], cfg, now=NOW, log=quiet)
    assert s4["tier"].startswith("best available") and s4["title"] != titles[-1], s4

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
    """Video editions through main(): both platforms → one entry; a later timed run publishes only the
    platform that's missing (with history minus today's slot); --platforms facebook → FB only."""
    import main as app
    from autopilot import youtube

    class FixedNow(datetime):
        @classmethod
        def now(cls, tz=None):
            t = datetime(2026, 10, 8, 5, 45, tzinfo=timezone.utc)  # 5 min after London's start
            return t.astimezone(tz) if tz else t.replace(tzinfo=None)

    tmp = Path(tempfile.mkdtemp())
    shutil.copy(ROOT / "config.yaml", tmp / "config.yaml")
    yt_calls, seen_history = [], []

    def fake_make_brief(cfg_, history, args, session_key):
        seen_history.append(history)
        wd = tmp / "output" / f"run{len(seen_history)}"
        wd.mkdir(parents=True, exist_ok=True)
        entry = {"date": "2026-10-08T05:46:00+00:00", "brief_date": "2026-10-08", "session": session_key,
                 "kind": "market", "title": "t", "video_id": None, "headlines": [f"h{len(seen_history)}"],
                 "workdir": str(wd.relative_to(tmp))}
        return {"entry": entry, "video": video, "thumbnail": cover, "meta": {"title": "t"}, "fb_caption": "c"}

    def fake_upload(*a, **k):
        yt_calls.append(a)
        if fail_yt:
            raise RuntimeError("YouTube upload limit reached for today")
        return f"Y{len(yt_calls)}"

    saved = (app.ROOT, app.datetime, app.make_brief, youtube.upload, youtube.set_thumbnail)
    app.ROOT, app.datetime, app.make_brief = tmp, FixedNow, fake_make_brief
    youtube.upload, youtube.set_thumbnail = fake_upload, (lambda *a, **k: True)
    try:
        # 1) timed London run, both platforms OK → one entry carrying both ids
        fail_yt = False
        fake = FakeGraph()
        _fb_env(fake)
        assert app.main(["--session", "london", "--scheduled"]) == 0
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
        assert app.main(["--session", "london", "--scheduled"]) == 1
        hist = json.loads((tmp / "data" / "history.json").read_text())["videos"]
        assert len(hist) == 1 and hist[0]["video_id"] and not hist[0].get("fb_reel_id"), hist
        assert bad.count("finish") == 1  # the failed Reel was not finished twice

        # 3) the backup timed run: re-makes the edition, Facebook only, history without today's slot
        n_yt = len(yt_calls)
        fake = FakeGraph()
        _fb_env(fake)
        assert app.main(["--session", "london", "--scheduled"]) == 0
        assert len(yt_calls) == n_yt and fake.count("finish") == 1, (yt_calls, fake.calls)
        assert not seen_history[-1].published_on("2026-10-08", "london", "youtube")  # same history as run 1
        hist = json.loads((tmp / "data" / "history.json").read_text())["videos"]
        assert len(hist) == 2 and hist[1]["fb_reel_id"] == "R1" and not hist[1].get("video_id"), hist
        # 4) a third timed run: everything is out → nothing is made
        made = len(seen_history)
        assert app.main(["--session", "london", "--scheduled"]) == 0 and len(seen_history) == made

        # 5) manual run --platforms facebook on a video edition → Facebook only
        fake = FakeGraph()
        _fb_env(fake)
        n_yt = len(yt_calls)
        assert app.main(["--session", "asia", "--platforms", "facebook"]) == 0
        assert len(yt_calls) == n_yt and fake.count("finish") == 1
    finally:
        (app.ROOT, app.datetime, app.make_brief, youtube.upload, youtube.set_thumbnail) = saved
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


if __name__ == "__main__":
    main()
