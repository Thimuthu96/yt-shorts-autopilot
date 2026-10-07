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

from autopilot import render, script, slides, thumbnail  # noqa: E402
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
    fx = {}
    for pair, name, p in (("EURUSD", "EUR/USD", 1.094), ("GBPUSD", "GBP/USD", 1.305), ("USDJPY", "USD/JPY", 148.2)):
        s = walk(p, 30, 0.003)
        fx[pair] = {"name": name, "price": s[-1], "as_of": "2026-10-06", "change_1d": (s[-1] / s[-2] - 1) * 100,
                    "change_30d": (s[-1] / s[0] - 1) * 100, "series": s,
                    "series_times": [(now - timedelta(days=30 - i)).date().isoformat() for i in range(30)]}
    return {
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
                  "summary": "", "published": now.isoformat(), "link": "https://www.coindesk.com/x"}],
    }


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
        pkg = json.loads(json.dumps(PKG))
        return {"verdict": "ok", "package": pkg} if "editor" in prompt else pkg
    script.generate_json = fake_llm
    small = cfg | {"llm": cfg["llm"] | {"min_words": 40, "max_words": 90}}
    pkg = script.make_script(small, data, [], cover, log=lambda m: None)
    assert cover["facts"] in prompts[0] and pkg["scenes"][0]["visual"]["type"] == "title"
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

    meta = build_metadata(PKG, data, cfg)
    assert "not financial advice" in meta["description"].lower()
    assert meta["tags"] == ["bitcoin price today", "forex news today"]
    assert cover["hook"] == cover["default_hook"]  # "Buy the dip now" is rejected
    print(f"OK: {out} ({got:.1f}s) · thumbnail {cover['template']} '{cover['hook']}' · contact sheet {work / 'contact.png'}")
    print(meta["description"])


if __name__ == "__main__":
    main()
