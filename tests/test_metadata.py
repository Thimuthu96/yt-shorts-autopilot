import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from autopilot import metadata as M  # noqa: E402

STORY = json.loads((ROOT / "stories/sample/lighthouse.json").read_text())
CFG = {"upload": {"disclaimer": "Narrated with a synthetic voice."}}
LINE = "Narrated with a synthetic voice."
TRACK = {"title": "Sea Song", "artist": "Ann", "attribution": "CC BY 4.0 https://example.org/sea", "file": "x.mp3"}


def test_youtube_description():
    m = M.build(STORY, None, CFG)
    d = m["description"]
    assert m["category_id"] == "22" and len(m["title"]) <= 60
    assert d.count(LINE) == 1
    assert d.split()[-1] == "#Shorts"
    assert d.startswith("If your captain mixed up two lighthouses at night, you'd hit the rocks before morning.")
    for s in STORY["sources"]:
        assert s["url"] in d
    assert "Music:" not in d
    assert m["tags"] and sum(len(t) + 1 for t in m["tags"]) <= 480


def test_attribution_only_with_track():
    d = M.build(STORY, TRACK, CFG)["description"]
    assert "Music: Sea Song by Ann. CC BY 4.0" in d
    assert "Music:" not in M.build(STORY, {"title": "t", "artist": "a", "file": "f"}, CFG)["description"]


def test_disclosure_once_even_if_summary_repeats_it():
    s = {**STORY, "summary": STORY["summary"] + " Narrated with a synthetic voice."}
    assert M.build(s, None, CFG)["description"].count(LINE) == 1
    assert M.reel_caption(s, None, CFG).count(LINE) == 1


def test_reel_caption():
    c = M.reel_caption(STORY, TRACK, CFG)
    assert "#Shorts" not in c and "http" not in c and "www." not in c
    assert "Sources: wikipedia.org, noaa.gov" in c
    assert "Music: Sea Song by Ann. CC BY 4.0" in c
    assert c.count(LINE) == 1 and len(c) < 2200
    assert c.split()[-1].startswith("#")


def test_title_cut_to_60():
    t = M.title({**STORY, "title": "Why " + "very " * 20 + "long"})
    assert len(t) <= 60 and not t.endswith(" ")
