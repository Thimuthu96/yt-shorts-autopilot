import json
import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from autopilot import timeline as T  # noqa: E402
from autopilot import voice  # noqa: E402
import subprocess  # noqa: E402
import pytest  # noqa: E402

STORY = {"beats": [{"text": "Every lighthouse blinks here."}, {"text": "Its own secret code"},
                   {"text": "means a ship knows where it is."}]}
V = {"name": "en-US-AndrewMultilingualNeural", "rate": "+8%"}


def tone(path, seconds, lead=0.2, tail=0.2):
    n = int(48000 * seconds)
    a = np.zeros(n, np.float32)
    s, e = int(lead * 48000), n - int(tail * 48000)
    a[s:e] = 0.5 * np.sin(2 * np.pi * 220 * np.arange(e - s) / 48000)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "f32le", "-ar", "48000", "-ac", "1", "-i", "pipe:0", str(path)],
                   input=a.tobytes(), check=True)


def fake(durs, who="en-US-AndrewMultilingualNeural", calls=None, nwords=None):
    def synth(scenes, voice_name, rate, workdir, log=print, fallback=None, pauses=False):
        if calls is not None:
            calls.append(rate)
        out = []
        for i, (sc, d) in enumerate(zip(scenes, durs)):
            p = Path(workdir) / f"voice_{i:02d}.wav"
            tone(p, d)
            ws = sc["text"].split()
            if nwords is not None:
                ws = ws[:nwords]
            span = (d - 0.4) / max(1, len(ws))
            out.append({"audio": p, "duration": d, "voice": who,
                        "words": [(0.2 + k * span, 0.2 + (k + 1) * span, w) for k, w in enumerate(ws)]})
        return out
    return synth


def test_layout_gaps_and_words(tmp_path, monkeypatch):
    monkeypatch.setattr(voice, "synthesize", fake([2.0, 1.5, 2.5]))
    tl = T.build(STORY, V, tmp_path)
    b = tl["beats"]
    assert b[0]["start"] == 0.0
    # trimmed audio is ~1.4 s (tone 1.6 s + 0.02 + 0.06 pads) ; gaps: 0.12 after "." / 0.06 after "blinks"-less text
    d0 = b[0]["end"] - T.LEAD
    assert b[1]["start"] == pytest.approx(T.LEAD + d0 + T.GAP, abs=0.01)
    assert b[2]["start"] == pytest.approx(b[1]["end"] + T.GAP_IN, abs=0.01)
    assert tl["duration"] == pytest.approx(b[2]["end"] + T.GAP + T.TAIL, abs=0.02)
    for beat, sb in zip(b, STORY["beats"]):
        assert [w["w"] for w in beat["words"]] == sb["text"].split()
        assert all(beat["start"] - 0.01 <= w["s"] <= w["e"] <= beat["end"] + 0.01 for w in beat["words"][1:])
    assert (tmp_path / "voice.wav").exists() and (tmp_path / "timeline.json").exists()
    assert json.loads((tmp_path / "timeline.json").read_text())["fps"] == 30
    assert tl["voice"] == "en-US-AndrewMultilingualNeural"


def test_mouth(tmp_path, monkeypatch):
    monkeypatch.setattr(voice, "synthesize", fake([2.0, 1.5, 2.5]))
    tl = T.build(STORY, V, tmp_path)
    assert len(tl["mouth"]) == math.ceil(tl["duration"] * 30)
    assert all(0 <= m <= 1 for m in tl["mouth"]) and max(tl["mouth"]) > 0.5


def test_too_long_rerecords_once(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(voice, "synthesize", fake([25, 25, 25], calls=calls))
    with pytest.raises(T.TooLong) as e:
        T.build(STORY, V, tmp_path, max_seconds=60)
    assert len(calls) == 2 and calls[0] == "+8%" and calls[1] != "+8%"
    assert e.value.seconds > 60


def test_rerecord_fits(tmp_path, monkeypatch):
    calls = []
    def synth(scenes, voice_name, rate, workdir, **kw):
        calls.append(rate)
        return fake([25, 25, 25] if len(calls) == 1 else [18, 18, 18])(scenes, voice_name, rate, workdir)
    monkeypatch.setattr(voice, "synthesize", synth)
    tl = T.build(STORY, V, tmp_path, max_seconds=60)
    assert len(calls) == 2 and tl["duration"] < 60


def test_piper_word_count_differs(tmp_path, monkeypatch):
    monkeypatch.setattr(voice, "synthesize", fake([2.0, 1.5, 2.5], who="en_US-ryan-high", nwords=2))
    tl = T.build(STORY, V, tmp_path)
    assert tl["voice"] == "en_US-ryan-high"
    for beat, sb in zip(tl["beats"], STORY["beats"]):
        assert [w["w"] for w in beat["words"]] == sb["text"].split()


def test_faster_rate():
    assert T.faster_rate("+0%", 1.1) == "+12%"
    assert T.faster_rate("+30%", 2) == "+35%"


def test_gaps_count_towards_the_first_pass_limit(tmp_path, monkeypatch):
    # 3 x 19.7 s + lead 0.15 + tail 0.6 = 59.85 s fits without gaps; with them (0.12 + 0.06 + 0.12) it is 60.15 s
    calls = []
    monkeypatch.setattr(voice, "synthesize", fake([19.7, 19.7, 19.7], calls=calls))
    T.build(STORY, V, tmp_path, max_seconds=60)  # (the fake trims to < 60 s after the re-record)
    assert len(calls) == 2  # the first pass already saw the overrun and re-recorded
