"""Offline check of graphics + rendering + metadata with sample data (no API keys needed).

    python tests/test_offline.py
"""
import json
import math
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from autopilot import focus, gold, render, script, slides, thumbnail  # noqa: E402
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
    print("OK history")


if __name__ == "__main__":
    main()
