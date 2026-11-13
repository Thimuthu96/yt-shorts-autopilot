"""Offline run of the whole Gus Explains edition (no keys, no network; nothing is published).

    python tests/test_offline.py        # also collected by pytest

Mocked: Gemini (research → the sample story's notes; the draft = a cut-down of stories/sample/lighthouse.json: no
sources / hashtags, which the writer fills from the research), source URL checks, edge-tts (tone wavs, ~0.13 s
a word, so the video is ~25 s), YouTube and Facebook uploads. Real: topics, writer checks, validator, timeline,
soundtrack mix, studio render (Node + Chromium at --scale 0.25; a plain test video with a log line when Chromium
is missing), mux, thumbnail, metadata, history entry.
Writes output/test/{short.mp4, short_fb.mp4, thumbnail.jpg, metadata.json, story.json, history_entry.json}.
"""
import copy
import json
import os
import shutil
import subprocess
import sys
import tempfile
import wave
from contextlib import ExitStack
from pathlib import Path
from unittest import mock

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
for _k in ("GEMINI_API_KEY", "FB_PAGE_ID", "FB_PAGE_TOKEN", "YT_REFRESH_TOKEN"):  # never reach real services
    os.environ.pop(_k, None)

import autopilot  # noqa: E402
import main as M  # noqa: E402
from autopilot import llm, studio, topics, voice, writer  # noqa: E402

SAMPLE = json.loads((ROOT / "stories/sample/lighthouse.json").read_text())
OUT = ROOT / "output" / "test"
NOTES = ("VERDICT: TRUE\nFACTS:\n- Each lighthouse has its own light characteristic, e.g. Fl(2) 10s [1]\n"
         "- Fresnel lenses from 1823 [2]\nSOURCES:\n[1] Light characteristic - https://en.wikipedia.org/wiki/Light_characteristic\n"
         "[2] Fresnel lens - https://en.wikipedia.org/wiki/Fresnel_lens\nHASHTAGS: #lighthouse #sailing #engineering")


def log(msg):
    print(f"[offline] {msg}", flush=True)


def cut_down() -> dict:
    s = copy.deepcopy(SAMPLE)
    s.update(slug="why-lighthouses-blink-offline", title="Why Lighthouses Blink in Codes", sources=[], hashtags=[])
    return s


def fake_text(prompt, models, tools=None, temperature=0.7, rounds=2):
    return NOTES, {"groundingChunks": [{"web": {"uri": "https://en.wikipedia.org/wiki/Light_characteristic",
                                                "title": "Light characteristic"}},
                                       {"web": {"uri": "https://en.wikipedia.org/wiki/Fresnel_lens",
                                                "title": "Fresnel lens"}}]}


def fake_json(prompt, models, temperature=0.9):
    task = prompt.split("\n", 1)[0]
    if "draft_story" in task:
        return cut_down()
    if "hook_check" in task:
        return {"score": 9, "problems": []}
    if "fact_check" in task:
        return {"ok": True, "problems": []}
    if "propose_topics" in task:
        words = ("Anchors", "Bells", "Candles", "Doors", "Engines", "Flags", "Gears", "Harbours", "Inkwells", "Jars",
                 "Kettles", "Lanterns", "Mirrors", "Nails", "Ovens")
        return {"topics": [{"title_idea": f"Why {w} Matter", "category": "science", "format": "explainer",
                            "angle": "a test angle"} for w in words]}
    raise AssertionError(f"unexpected prompt: {task}")


def fake_tts(scenes, voice_name, rate, workdir, log=print, fallback=None, pauses=False):
    """A tone per word (silence between), so the timeline, mouth envelope and mix have real audio."""
    sr, out = 24000, []
    for i, sc in enumerate(scenes):
        words = sc["text"].split()
        t, chunks, times = 0.05, [np.zeros(int(0.05 * sr))], []
        for w in words:
            d = 0.1 + 0.01 * min(len(w), 6)
            n = int(d * sr)
            env = np.sin(np.linspace(0, np.pi, n)) ** 0.5
            chunks += [0.5 * env * np.sin(2 * np.pi * (180 + 20 * (i % 5)) * np.arange(n) / sr), np.zeros(int(0.03 * sr))]
            times.append((t, t + d, w))
            t += d + 0.03
        chunks.append(np.zeros(int(0.05 * sr)))
        a = (np.concatenate(chunks) * 32767).astype(np.int16)
        p = Path(workdir) / f"tts_{i:02d}.wav"
        with wave.open(str(p), "wb") as f:
            f.setnchannels(1)
            f.setsampwidth(2)
            f.setframerate(sr)
            f.writeframes(a.tobytes())
        out.append({"audio": p, "duration": len(a) / sr, "words": times, "voice": "fake-tts"})
    return out


def chromium_ok() -> bool:
    if not shutil.which("node"):
        return False
    p = subprocess.run(["node", "-e", "const {chromium}=require('playwright');"
                        "process.stdout.write(require('fs').existsSync(chromium.executablePath())?'1':'0')"],
                       capture_output=True, text=True, cwd=ROOT)
    return p.stdout.strip() == "1"


def plain_render(story, tl, workdir, log=print, node="node", scale=1.0):
    log("studio: Chromium not installed, using a plain test video instead of the engine render")
    out = Path(workdir) / "video.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"color=c=0x4a90d9:s=270x480:r=30:d={tl['duration']}",
                    "-pix_fmt", "yuv420p", str(out)], check=True)
    return out


def probe(path: Path) -> list[dict]:
    p = subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-of", "json", str(path)], capture_output=True,
                       text=True, check=True)
    return json.loads(p.stdout)["streams"]


def run_offline() -> Path:
    tmp = Path(tempfile.mkdtemp(prefix="gus-offline-"))
    cfg = M.load_config()
    cfg["video"] = {**cfg.get("video", {}), "render_scale": 0.25}
    backlog = [{"id": "lighthouse-codes", "title_idea": "Why Lighthouses Blink in Codes", "category": "engineering",
                "format": "explainer", "angle": "a wait-really angle", "status": "queued", "used_on": None,
                "reason": None}]
    topics.save(tmp / "backlog.yaml", backlog)
    uploads = {}

    def yt_upload(video, meta, cfg, log=print):
        uploads["youtube"] = (Path(video), meta)
        return "offline-yt"

    def fb_reel(video, caption, cfg, cover=None, log=print):
        uploads["facebook"] = (Path(video), caption)
        return "offline-fb"

    with ExitStack() as st:
        P = lambda *a, **k: st.enter_context(mock.patch.object(*a, **k))  # noqa: E731
        P(M, "load_config", lambda path=None: cfg)
        P(M, "HISTORY", tmp / "history.json")
        P(M, "BACKLOG", tmp / "backlog.yaml")
        P(M, "OUTPUT", tmp / "output")
        P(M, "PUBLISHED", tmp / "published")
        P(M, "platform_off", lambda plat, cfg: "")
        P(llm, "generate_text", fake_text)
        P(llm, "generate_json", fake_json)
        P(writer, "check_url", lambda url: url)
        P(voice, "synthesize", fake_tts)
        if not chromium_ok():
            P(studio, "render", plain_render)
        st.enter_context(mock.patch.dict(sys.modules, {
            "autopilot.youtube": mock.Mock(upload=yt_upload, set_thumbnail=lambda *a, **k: False),
            "autopilot.facebook": mock.Mock(publish_reel=fb_reel)}))
        P(autopilot, "youtube", sys.modules["autopilot.youtube"], create=True)
        P(autopilot, "facebook", sys.modules["autopilot.facebook"], create=True)
        code = M.main(["--session", "short_a"])
    assert code == 0, f"main returned {code}"
    work = next((tmp / "output").iterdir())
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    for name in ("short.mp4", "short_fb.mp4", "thumbnail.jpg", "metadata.json", "story.json", "timeline.json",
                 "history_entry.json"):
        shutil.copy(work / name, OUT / name)

    streams = probe(OUT / "short.mp4")
    v = [s for s in streams if s["codec_type"] == "video"]
    a = [s for s in streams if s["codec_type"] == "audio"]
    assert v and a and a[0]["codec_name"] == "aac" and a[0]["channels"] == 2 and a[0]["sample_rate"] == "48000"
    assert uploads["youtube"][0].name == "short.mp4" and uploads["facebook"][0].name == "short_fb.mp4"
    entry = json.loads((OUT / "history_entry.json").read_text())
    for k in ("date", "session", "kind", "slug", "title", "category", "format", "topic_id", "voice", "music_yt",
              "music_fb", "video_id", "fb_reel_id", "trigger", "counts", "seconds"):
        assert k in entry, k
    assert entry["topic_id"] == "lighthouse-codes" and entry["video_id"] == "offline-yt"
    assert entry["fb_reel_id"] == "offline-fb" and entry["voice"] == "fake-tts" and entry["kind"] == "short"
    meta = json.loads((OUT / "metadata.json").read_text())
    assert meta["description"].count("Narrated with a synthetic voice.") == 1
    assert meta["description"].split()[-1] == "#Shorts" and "#Shorts" not in meta["fb_caption"]
    assert "https://en.wikipedia.org/wiki/Fresnel_lens" in meta["description"]
    bl = topics.load(tmp / "backlog.yaml")
    assert bl[0]["status"] == "used" and len(bl) > 1  # used, then refilled from the (mocked) proposals
    changes = json.loads((work / "backlog_changes.json").read_text())  # what the workflow re-applies
    assert topics.apply([dict(e) for e in backlog], changes) == bl
    assert (tmp / "published" / f"{entry['slug']}.json").exists()
    log(f"OK: {OUT / 'short.mp4'} ({entry['seconds']} s, {v[0]['width']}x{v[0]['height']}), history entry and "
        "metadata checked")
    shutil.rmtree(tmp, ignore_errors=True)
    return OUT


def test_offline_pipeline():
    run_offline()


if __name__ == "__main__":
    run_offline()
