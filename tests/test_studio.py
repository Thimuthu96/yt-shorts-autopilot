import json
import stat
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from autopilot import studio as S  # noqa: E402


def probe(path, what):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-of", "json", str(path)],
                         capture_output=True, text=True, check=True).stdout
    return [s for s in json.loads(out)["streams"] if s["codec_type"] == what]


def media(tmp_path):
    v = tmp_path / "v.mp4"
    a = tmp_path / "a.wav"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=s=1080x1920:r=30:d=2", "-pix_fmt", "yuv420p", str(v)], check=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "sine=f=300:d=2:sample_rate=48000", "-ac", "1", str(a)], check=True)
    return v, a


def test_render_error(tmp_path):
    fake = tmp_path / "node"
    fake.write_text("#!/bin/sh\necho 'render failed at frame 42: boom' >&2\nexit 1\n")
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
    with pytest.raises(S.RenderError, match="frame 42"):
        S.render({"beats": []}, {"duration": 1, "beats": []}, tmp_path / "w", node=str(fake))
    assert json.loads((tmp_path / "w" / "story.json").read_text()) == {"beats": []}


def test_render_ok_with_fake_node(tmp_path):
    fake = tmp_path / "node"
    fake.write_text("#!/bin/sh\ntouch \"$6/video.mp4\"\n")  # args: render.js story --timeline t --out dir
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
    assert S.render({"beats": []}, {"duration": 1}, tmp_path / "w", node=str(fake)) == tmp_path / "w" / "video.mp4"


def test_mux_and_thumbnail(tmp_path):
    v, a = media(tmp_path)
    out = S.mux(v, a, tmp_path / "o.mp4")
    vs, as_ = probe(out, "video"), probe(out, "audio")
    assert len(vs) == 1 and len(as_) == 1
    assert (vs[0]["width"], vs[0]["height"], vs[0]["avg_frame_rate"]) == (1080, 1920, "30/1")
    assert (as_[0]["codec_name"], as_[0]["channels"], as_[0]["sample_rate"]) == ("aac", 2, "48000")
    th = S.thumbnail(out, tmp_path / "t.jpg")
    s = probe(th, "video")[0]
    assert (s["width"], s["height"]) == (1080, 1920)
