import copy
import json
import sys
import types
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import autopilot  # noqa: E402
import main as M  # noqa: E402
from autopilot import timeline, topics, writer  # noqa: E402
from autopilot.history import History  # noqa: E402

SAMPLE = json.loads((ROOT / "stories/sample/lighthouse.json").read_text())
DUE = datetime(2026, 11, 20, 16, 30, tzinfo=timezone.utc)  # 5 min after short_a's start_utc
TODAY = "2026-11-20"
REAL_MAKE = M.make_short


@pytest.fixture
def env(tmp_path, monkeypatch):
    cfg = M.load_config()
    cfg["gus"] = {**cfg["gus"], "enabled": True}
    state = {"cfg": cfg, "made": 0, "yt": [], "fb": []}
    monkeypatch.setattr(M, "load_config", lambda path=None: state["cfg"])
    monkeypatch.setattr(M, "HISTORY", tmp_path / "history.json")
    monkeypatch.setattr(M, "BACKLOG", tmp_path / "backlog.yaml")
    monkeypatch.setattr(M, "OUTPUT", tmp_path / "output")
    monkeypatch.setattr(M, "PUBLISHED", tmp_path / "published")
    monkeypatch.setattr(M, "now_utc", lambda: DUE)
    monkeypatch.setattr(M, "platform_off", lambda plat, cfg: "")

    def fake_make(cfg, history, session, date, story_path=None, topic_text=None, log=M.log, persist=True,
                  reuse=False):
        state["persist"], state["reuse"] = persist, reuse
        state["made"] += 1
        state["story_path"] = story_path
        wd = tmp_path / "output" / f"run{state['made']}"
        wd.mkdir(parents=True)
        return {"video": wd / "short.mp4", "video_fb": wd / "short_fb.mp4", "thumbnail": wd / "thumbnail.jpg",
                "meta": {"title": "T"}, "fb_caption": "C", "story": copy.deepcopy(SAMPLE), "topic": None,
                "backlog": None, "workdir": wd,
                "entry": {"date": date, "brief_date": date, "session": session, "kind": "short",
                          "slug": SAMPLE["slug"], "title": "T"}}
    state["fake_make"] = fake_make
    monkeypatch.setattr(M, "make_short", fake_make)

    def yt_upload(video, meta, cfg, log=print):
        if state.get("yt_fail"):
            raise RuntimeError("quota")
        state["yt"].append(video)
        return "YT1"

    def fb_reel(video, caption, cfg, cover=None, log=print):
        state["fb"].append(video)
        return "FB1"
    monkeypatch.setattr(autopilot, "youtube", types.SimpleNamespace(upload=yt_upload, set_thumbnail=lambda *a, **k: False),
                        raising=False)
    monkeypatch.setattr(autopilot, "facebook", types.SimpleNamespace(publish_reel=fb_reel), raising=False)
    monkeypatch.setitem(sys.modules, "autopilot.youtube", autopilot.youtube)
    monkeypatch.setitem(sys.modules, "autopilot.facebook", autopilot.facebook)
    state["tmp"] = tmp_path
    return state


def test_unknown_session(env):
    assert M.main(["--session", "news_morning"]) == 1


def test_gate_off_timed_skips(env, capsys):
    env["cfg"]["gus"]["enabled"] = False
    assert M.main(["--session", "short_a", "--scheduled"]) == 0
    assert env["made"] == 0
    assert "gus.enabled is false: timed runs skip" in capsys.readouterr().out


def test_gate_off_manual_no_upload_makes(env):
    env["cfg"]["gus"]["enabled"] = False
    assert M.main(["--session", "short_a", "--no-upload"]) == 0
    assert env["made"] == 1 and env["yt"] == [] and env["fb"] == []
    assert not M.HISTORY.exists()


def test_late_and_early_timed_runs_skip(env, monkeypatch):
    monkeypatch.setattr(M, "now_utc", lambda: datetime(2026, 11, 20, 18, 40, tzinfo=timezone.utc))
    assert M.main(["--session", "short_a", "--scheduled"]) == 0
    monkeypatch.setattr(M, "now_utc", lambda: datetime(2026, 11, 20, 15, 40, tzinfo=timezone.utc))
    assert M.main(["--session", "short_a", "--scheduled"]) == 0
    assert env["made"] == 0


def test_timed_publishes_both_and_logs_history(env):
    assert M.main(["--session", "short_a", "--scheduled"]) == 0
    h = History(M.HISTORY)
    e = h.data["videos"][-1]
    assert e["video_id"] == "YT1" and e["fb_reel_id"] == "FB1" and e["counts"] and e["trigger"] == "timed"
    assert env["yt"][0].name == "short.mp4" and env["fb"][0].name == "short_fb.mp4"
    assert (env["tmp"] / "output" / "run1" / "history_entry.json").exists()
    assert (M.PUBLISHED / f"{SAMPLE['slug']}.json").exists()


def test_already_published_today_skips(env):
    M.HISTORY.write_text(json.dumps({"videos": [{"brief_date": TODAY, "session": "short_a", "slug": "x", "video_id": "a",
                                                 "fb_reel_id": "b", "counts": True}]}))
    assert M.main(["--session", "short_a", "--scheduled"]) == 0
    assert env["made"] == 0


def test_missed_platform_rerun_reuses_story(env):
    M.HISTORY.write_text(json.dumps({"videos": [{"brief_date": TODAY, "session": "short_a", "slug": "old-one",
                                                 "video_id": "a", "counts": True}]}))
    M.PUBLISHED.mkdir()
    (M.PUBLISHED / "old-one.json").write_text("{}")
    assert M.main(["--session", "short_a", "--scheduled"]) == 0
    assert env["story_path"] == str(M.PUBLISHED / "old-one.json") and env["reuse"] and env["persist"]
    assert env["yt"] == [] and len(env["fb"]) == 1


def test_youtube_failure_still_publishes_facebook(env):
    env["yt_fail"] = True
    assert M.main(["--session", "short_b"]) == 1
    e = History(M.HISTORY).data["videos"][-1]
    assert e["fb_reel_id"] == "FB1" and "video_id" not in e and e["counts"] is False and e["trigger"] == "manual"


def _backlog(n=4):
    topics.save(M.BACKLOG, [{"id": f"t{i}", "title_idea": f"Topic number {i} here", "category": c, "format": "explainer",
                             "angle": "a", "status": "queued", "used_on": None, "reason": None}
                            for i, c in zip(range(n), ("history", "science", "psychology", "engineering", "what_if"))])


def test_write_failed_three_topics_exits_1(env, monkeypatch):
    monkeypatch.setattr(M, "make_short", REAL_MAKE)
    _backlog()
    calls = []

    def fail(topic, cfg, catalog, log=print):
        calls.append(topic.id)
        raise writer.WriteFailed("not enough sources")
    monkeypatch.setattr(writer, "write", fail)
    assert M.main(["--session", "short_a", "--scheduled"]) == 1
    assert calls == ["t0", "t1", "t2"]
    bl = topics.load(M.BACKLOG)
    assert [e["status"] for e in bl] == ["failed", "failed", "failed", "queued"]
    assert bl[0]["reason"] == "not enough sources" and bl[0]["used_on"] == TODAY
    assert not M.HISTORY.exists()
    # the workflow resets to origin/main and re-applies the run's changes: same backlog
    _backlog()
    (changes,) = list(M.OUTPUT.glob("*/backlog_changes.json"))
    assert topics.apply(topics.load(M.BACKLOG), json.loads(changes.read_text())) == bl


def test_too_long_marks_topic_failed(env, monkeypatch):
    monkeypatch.setattr(M, "make_short", REAL_MAKE)
    _backlog()
    monkeypatch.setattr(writer, "write", lambda topic, cfg, catalog, log=print: copy.deepcopy(SAMPLE))

    def too_long(*a, **k):
        raise timeline.TooLong(64.0)
    monkeypatch.setattr(timeline, "build", too_long)
    assert M.main(["--session", "short_a"]) == 1
    assert [e["status"] for e in topics.load(M.BACKLOG)][:3] == ["failed"] * 3
    assert "too long" in topics.load(M.BACKLOG)[0]["reason"]


def test_no_upload_failing_run_leaves_backlog_unchanged(env, monkeypatch):
    monkeypatch.setattr(M, "make_short", REAL_MAKE)
    _backlog(5)
    before = M.BACKLOG.read_bytes()
    calls = []

    def fail(topic, cfg, catalog, log=print):
        calls.append(topic.id)
        raise writer.WriteFailed("invalid story: x")
    monkeypatch.setattr(writer, "write", fail)
    monkeypatch.setattr(writer, "propose_topics", lambda *a, **k: [])
    assert M.main(["--session", "short_a", "--no-upload"]) == 1
    assert calls == ["t0", "t1", "t2"]  # the in-memory marks still move the loop on
    assert M.BACKLOG.read_bytes() == before
    assert not list(M.OUTPUT.glob("*/backlog_changes.json"))


def test_story_path_slug_made_unique(env, monkeypatch, tmp_path):
    monkeypatch.setattr(M, "make_short", REAL_MAKE)
    M.HISTORY.write_text(json.dumps({"videos": [{"brief_date": "2026-11-01", "session": "short_a",
                                                 "slug": SAMPLE["slug"], "video_id": "a"}]}))
    seen = {}

    def stop(story, *a, **k):
        seen["slug"] = story["slug"]
        raise timeline.TooLong(70)
    monkeypatch.setattr(timeline, "build", stop)
    assert M.main(["--session", "short_a", "--no-upload", "--story", str(ROOT / "stories/sample/lighthouse.json")]) == 1
    assert seen["slug"] == SAMPLE["slug"] + "-2"



def test_facebook_paused_in_config_skips_facebook_only():
    """Owner paused Facebook (facebook.enabled: false): YouTube stays on, Facebook is skipped with a reason."""
    cfg = M.load_config()
    assert cfg["facebook"]["enabled"] is False
    assert "facebook.enabled is false" in M.platform_off("facebook", cfg)
    assert M.platform_off("youtube", cfg) == ""
