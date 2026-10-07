"""Offline check of the render step: synthetic footage + tones, no API keys needed.

    python tests/test_render.py
"""
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from autopilot import render  # noqa: E402
from autopilot.media import probe_duration, run  # noqa: E402
from autopilot.youtube import build_metadata  # noqa: E402


def main():
    cfg = yaml.safe_load((ROOT / "config.yaml").read_text())
    work = ROOT / "output" / "test"
    work.mkdir(parents=True, exist_ok=True)

    lines = [
        "Why does ice feel so slippery?",
        "Most people think pressure melts it.",
        "But the real answer is stranger.",
        "The top layer of ice never fully freezes.",
    ]
    audio, clips = [], []
    for i, text in enumerate(lines):
        dur = 1.6 + 0.4 * i
        wav = work / f"voice_{i:02d}.wav"
        run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
             f"sine=frequency={300 + 80 * i}:duration={dur}", "-ar", "44100", "-ac", "1", wav])
        words = text.split()
        step = dur / len(words)
        audio.append({"audio": wav, "duration": probe_duration(wav),
                      "words": [(j * step, (j + 0.9) * step, w) for j, w in enumerate(words)]})
        # landscape and portrait sources, some shorter than the scene (forces looping)
        size = "1280x720" if i % 2 else "720x1280"
        clip = work / f"clip_{i:02d}.mp4"
        run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
             f"testsrc2=size={size}:rate=25:duration={1.0 if i == 2 else 6}",
             "-pix_fmt", "yuv420p", clip])
        clips.append(clip)

    music = work / "music.mp3"
    run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "anoisesrc=d=3:a=0.3", music])

    out = work / "short.mp4"
    total = render.build_video(audio, clips, cfg, work, out, music=music)
    got = probe_duration(out)
    assert abs(got - total) < 0.25, f"duration {got} vs narration {total}"
    run(["ffmpeg", "-y", "-v", "error", "-ss", "4.2", "-i", out, "-frames:v", "1", work / "frame.png"])

    meta = build_metadata({"title": "Why is ice <so> slippery?", "description": "Ice has a liquid-like skin.",
                           "tags": ["why is ice slippery"] * 60, "hashtags": ["#science", "physics"]},
                          "Pixabay — Jane Doe")
    assert "<" not in meta["title"] and "#Shorts" in meta["description"]
    assert sum(len(t) + 3 for t in meta["tags"]) <= 500
    print(f"OK: {out} ({got:.2f}s), frame at {work / 'frame.png'}")
    print(meta)


if __name__ == "__main__":
    main()
