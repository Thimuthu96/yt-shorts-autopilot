import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from autopilot import soundtrack as S  # noqa: E402

CAT = json.loads((ROOT / "studio/catalog.json").read_text())


def wav(path, seconds, hz=220, amp=0.4):
    t = np.arange(int(48000 * seconds)) / 48000
    a = (amp * np.sin(2 * np.pi * hz * t)).astype(np.float32)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "f32le", "-ar", "48000", "-ac", "1", "-i", "pipe:0", str(path)],
                   input=a.tobytes(), check=True)
    return path


def dur(path):
    return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                                capture_output=True, text=True, check=True).stdout)


def test_sfx_types_match_catalog():
    assert list(S.SFX_TYPES) == CAT["sfx"]
    for n in S.SFX_TYPES:
        x = S.sfx(n)
        assert x.dtype == np.float32 and 0.05 * S.SR < len(x) < 1.5 * S.SR and 0 < np.abs(x).max() <= 1


def test_empty_manifest_no_track(tmp_path):
    assert S.load_tracks(tmp_path) == []
    assert S.load_tracks(ROOT / "music") == []
    assert S.pick_track([], "curious", "youtube", "s") is None
    assert S.pick_track([], "curious", "facebook", "s") is None


def test_platform_and_mood(tmp_path):
    (tmp_path / "a.mp3").write_bytes(b"x")
    (tmp_path / "b.mp3").write_bytes(b"x")
    (tmp_path / "tracks.yaml").write_text(
        "- {file: a.mp3, title: A, artist: X, attribution: null, facebook_ok: false, moods: [curious]}\n"
        "- {file: b.mp3, title: B, artist: Y, attribution: 'CC BY', facebook_ok: true, moods: [tense]}\n"
        "- {file: gone.mp3, title: G, artist: Z, attribution: null, facebook_ok: true, moods: [tense]}\n")
    logs = []
    tr = S.load_tracks(tmp_path, log=logs.append)
    assert [t["file"] for t in tr] == ["a.mp3", "b.mp3"] and any("gone.mp3" in l for l in logs)
    assert S.pick_track(tr, "curious", "youtube", "s")["file"] == "a.mp3"
    assert S.pick_track(tr, "curious", "facebook", "s")["file"] == "b.mp3"  # only facebook_ok
    assert S.pick_track(tr[:1], "curious", "facebook", "s") is None
    assert S.pick_track(tr, "tense", "youtube", "q") == S.pick_track(tr, "tense", "youtube", "q")
    assert S.attribution_line(tr[0]) == "" and "CC BY" in S.attribution_line(tr[1])


def test_mix_without_track(tmp_path):
    v = wav(tmp_path / "v.wav", 3.0)
    tl = {"beats": [{"i": 0, "start": 0.0, "end": 1.0, "words": []}]}
    story = {"beats": [{"sfx": [{"type": "boom", "at": 0.5}]}]}
    out = S.mix(v, tl, story, None, tmp_path / "m.wav")
    assert abs(dur(out) - 3.0) < 0.05
    info = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=channels,sample_rate", "-of", "csv=p=0", str(out)],
                          capture_output=True, text=True).stdout.strip()
    assert info == "48000,2"


def test_mix_with_music_and_unknown_sfx(tmp_path):
    v = wav(tmp_path / "v.wav", 2.0)
    m = wav(tmp_path / "m.wav", 0.7, hz=330)
    tl = {"beats": [{"i": 0, "start": 0.0, "end": 1.0, "words": []}]}
    out = S.mix(v, tl, {"beats": [{}]}, {"path": m}, tmp_path / "o.wav")
    assert abs(dur(out) - 2.0) < 0.05
    with pytest.raises(ValueError):
        S.mix(v, tl, {"beats": [{"sfx": [{"type": "moo", "at": 0}]}]}, None, tmp_path / "x.wav")


def test_sfx_mark_events_land_on_their_words():
    story = {"beats": [{"text": "a b c", "sfx": [{"type": "pop", "at": 0.1}],
                        "events": [{"at_word": 2, "do": "sfx_mark", "sfx": "ding"},
                                   {"at_word": 1, "do": "sfx_mark", "sfx": "boom", "delay": 0.05},
                                   {"at_word": 0, "do": "expr", "who": "x", "expr": "happy"}]}]}
    tl = {"beats": [{"i": 0, "start": 1.0, "end": 2.0, "words": [{"w": "a", "s": 1.0, "e": 1.2},
                                                                   {"w": "b", "s": 1.3, "e": 1.5},
                                                                   {"w": "c", "s": 1.6, "e": 1.9}]}]}
    got = S.sfx_times(story, tl)
    assert [n for _, n in got] == ["pop", "boom", "ding"]
    assert [round(t, 3) for t, _ in got] == [1.1, 1.35, 1.6]
