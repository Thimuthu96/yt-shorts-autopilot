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
    test_facebook_video(cfg)
    test_news_post(cfg)
    test_news_edition(cfg)
    test_video_editions(cfg, out, work / "thumbnail.jpg")
    test_lesson_slides(cfg)
    test_lesson_render(cfg)


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
    examples, every primitive, portrait zoom, daily-fix line, schematic label, the mtf (top-down) panels,
    unknown type, thumbnail; writes contact sheets (chart and mtf scenes) for the owner to approve the look."""
    from types import SimpleNamespace
    from PIL import Image, ImageDraw
    from autopilot import detectors, lesson_data, lesson_slides as ls, lessons  # noqa: F401  (detectors registers)
    sample = ROOT / "tests" / "lessons"
    cur, glo = lessons.load_curriculum(sample / "curriculum.yaml"), lessons.load_glossary(sample / "glossary.yaml")
    load = lambda n: json.loads((sample / "candles" / f"{n}.json").read_text(encoding="utf-8"))  # noqa: E731
    down, up = load("downtrend_bos_choch"), load("uptrend")
    fix = [dict(c, o=c["c"], h=c["c"], l=c["c"]) for c in down]  # EUR/USD daily reference fix: o=h=l=c
    examples = lessons.DETECTORS["bos_choch"].find({"BTC/USD": {"1H": down}, "EUR/USD": {"1D": fix}})
    assert [e["asset"] for e in examples] == ["BTC/USD", "EUR/USD"], [e["asset"] for e in examples]
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
    assert types == ["title", "concept", "schematic", "chart", "chart", "mtf", "misreads", "outro"], types

    work = ROOT / "output" / "test_lessons"
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    bg = (14, 15, 18)
    sheets = {}
    for layout, cell, cols in ((ls.LANDSCAPE, (640, 360), 3), (ls.PORTRAIT, (360, 640), 4)):
        pics = ls.render_lesson_slides(cfg, cur[1], plan, glo, layout, work / layout.name)
        assert [p["id"] for p in pics] == [s["id"] for s in plan] and all(set(p) == {"image", "reveal", "id"} for p in pics)
        for s, p in zip(plan, pics):
            with Image.open(p["image"]) as im:
                assert im.size == (layout.w, layout.h), (layout.name, s["id"], im.size)
                band = im.convert("RGB").crop((0, layout.caption_band[0], layout.w, layout.caption_band[1]))
                assert band.getextrema() == tuple((c, c) for c in bg), (layout.name, s["id"], "drew into captions")
            if s["visual"]["type"] in ("chart", "schematic", "mtf"):
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
        # daily reference fix: a line, not candles
        info = ls.draw_chart(Image.new("RGB", (layout.w, layout.h), bg), layout.content_box, ex2, layout, zoom=zoom)
        assert info["line"] and "Frankfurter" in info["label"]
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

LESSON_FILLER = ("A swing point marks where price turned and the next close tells us whether "
                 "the structure held or changed character").split()
LESSON_WORDS = {"hook": 110, "concept": 120, "example_1": 120, "example_2": 120, "misreads": 40, "recap": 110}


def _lesson_draft(plan: list[dict], tail: str) -> dict:
    """A mocked lesson writer reply: LESSON_WORDS words per scene (the misreads scene is short), no
    numbers, the recap ending with `tail`."""
    scenes = []
    for p in plan:
        n = LESSON_WORDS[p["id"]] - (len(tail.split()) if p["id"] == "recap" else 0)
        body = " ".join(LESSON_FILLER[k % len(LESSON_FILLER)] for k in range(n))
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


def test_lesson_render(cfg):
    """make_lesson (entry 6): sample entry on fixture candles, mocked narration + sine voice → a 16:9 and a
    9:16 mp4 from the same audio, captions in each layout's band, chapters from the scene timings (a short
    scene merges), lesson metadata; plus the hold, over-limit re-record, ICT and Shorts-caption cases."""
    from unittest import mock
    import main as app
    from autopilot import lesson_meta, lesson_script, lesson_slides as ls, lessons, voice
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

    def fake_voice(scenes, name, rate, workdir, log=print):
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
    draft.update(_lesson_draft(plan, lesson_script.DISCLAIMER))
    made = make(entry, cfg, work)
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

    # metadata: written, keyword-first title, chapters / examples / credits / disclaimer, no ICT line
    meta = made["meta"]
    saved = json.loads((work / "metadata.json").read_text())
    assert {k: saved[k] for k in meta} == meta and saved["chapters"] == ch
    assert set(meta) == {"title", "description", "tags", "category_id", "fb_title", "fb_description"}
    assert meta["title"] == f"{entry['title']} Explained | Structure Lesson" and len(meta["title"]) <= 100
    assert meta["category_id"] == "27" and meta["fb_title"] == meta["title"]
    d = meta["description"]
    assert d.startswith(" ".join(entry["key_points"]))
    assert "Chapters:\n" + "\n".join(f"{c['time']} {c['title']}" for c in ch) in d, d
    assert "Historical examples:\n" in d and all(lessons.example_label(e) in d for e in made["examples"])
    assert "Coinbase" in d and "not financial advice" in d.lower() and ls.NON_AFFILIATION not in d
    tags = d.rsplit("\n\n", 1)[1].split()
    assert 3 <= len(tags) <= 5 and all(h.startswith("#") for h in tags) and "#Shorts" not in tags, tags
    assert meta["tags"] and len(meta["tags"]) == len({x.lower() for x in meta["tags"]})
    fb = meta["fb_description"]
    assert "http" not in d and "http" not in fb and "www." not in fb and "not financial advice" in fb.lower()
    assert fb.startswith(" ".join(entry["key_points"])) and 1 <= len([w for w in fb.split() if w.startswith("#")]) <= 5

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
    assert cfg["video"]["max_seconds"] == 59 and "margin_v" not in cfg["video"]["captions"]  # Shorts cfg untouched
    assert ls.NON_AFFILIATION in made["meta"]["description"] and ls.NON_AFFILIATION in made["meta"]["fb_description"]
    assert made["meta"]["title"].endswith("| ICT concepts Lesson"), made["meta"]["title"]
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
    two = lesson_meta.build_lesson_metadata(entry, {}, made["examples"], got, cfg, log=logs.append)
    assert "Chapters:" not in two["description"] and "0:16" not in two["description"], two["description"]
    assert any("No chapters" in m and "2" in m for m in logs), logs
    assert lesson_meta.timestamp(75.9) == "1:15" and lesson_meta.timestamp(3725) == "1:02:05"
    print(f"OK lesson render: {work / 'lesson_16x9.mp4'} + lesson_9x16.mp4 ({durs['16x9']:.1f}s) · "
          f"{len(ch)} chapters · hold, re-record, ICT, Shorts captions")


if __name__ == "__main__":
    main()
