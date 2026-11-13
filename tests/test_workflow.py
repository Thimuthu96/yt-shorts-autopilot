"""The workflow, its setup action and the cron-job.org script agree with config.yaml (no network)."""
import re
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import setup_cronjobs as C  # noqa: E402

WF = ROOT / ".github" / "workflows" / "autopilot.yml"
SECRETS = {"GEMINI_API_KEY", "YT_CLIENT_ID", "YT_CLIENT_SECRET", "YT_REFRESH_TOKEN", "FB_PAGE_ID", "FB_PAGE_TOKEN"}


@pytest.fixture(scope="module")
def wf():
    return yaml.safe_load(WF.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def sessions():
    return yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))["sessions"]


def _on(wf):
    return wf.get("on", wf.get(True))  # PyYAML reads the bare key `on` as True


def _mapping(expr: str) -> dict:
    """{cron: edition} from "github.event.schedule == '<cron>' && '<edition>'" pairs."""
    return dict(re.findall(r"github\.event\.schedule == '([^']+)' && '([a-z_]+)'", expr))


def test_only_the_gus_workflow_is_left():
    assert sorted(p.name for p in WF.parent.iterdir()) == ["autopilot.yml"]


def test_backup_crons_match_edition_and_concurrency(wf, sessions):
    crons = [c["cron"] for c in _on(wf)["schedule"]]
    assert crons == ["42 16 * * *", "42 22 * * *"]
    job = wf["jobs"]["make-and-upload"]
    edition = _mapping(next(s for s in job["steps"] if s.get("name") == "Make and publish")["env"]["EDITION"])
    group = _mapping(job["concurrency"]["group"])
    assert edition == group == {"42 16 * * *": "short_a", "42 22 * * *": "short_b"}
    for cron, key in edition.items():  # backup = start_utc + 17 min, every day
        m, h, *rest = cron.split()
        sh, sm = (int(x) for x in sessions[key]["start_utc"].split(":"))
        assert (int(h) * 60 + int(m)) - (sh * 60 + sm) == 17 and rest == ["*", "*", "*"]
    assert set(edition.values()) == set(sessions)


def test_inputs_secrets_and_timeout(wf, sessions):
    inputs = _on(wf)["workflow_dispatch"]["inputs"]
    assert set(inputs) == {"session", "platforms", "as_edition", "scheduled", "story", "topic", "no_upload"}
    assert inputs["session"]["options"] == list(sessions)
    job = wf["jobs"]["make-and-upload"]
    assert job["timeout-minutes"] == 90
    used = set(re.findall(r"secrets\.([A-Z_]+)", WF.read_text(encoding="utf-8")))
    assert used == SECRETS
    run = next(s for s in job["steps"] if s.get("name") == "Make and publish")["run"]
    for flag in ("--scheduled", "--as-edition", "--no-upload", "--story", "--topic", "--platforms"):
        assert flag in run
    assert "${{" not in run  # inputs reach the script only through env (no injection)


def test_save_step_commits_history_backlog_and_stories(wf):
    save = next(s for s in wf["jobs"]["make-and-upload"]["steps"] if s.get("name") == "Save history")
    run = save["run"]
    assert save["if"] == "always()"
    for part in ("python -m autopilot.history add", "python -m autopilot.history stories",
                 "python -m autopilot.topics apply", "git add data/history.json topics/backlog.yaml",
                 "stories/published/", 'git reset -q --hard "origin/$GITHUB_REF_NAME"'):
        assert part in run, part


def test_setup_action():
    act = yaml.safe_load((ROOT / ".github" / "actions" / "setup" / "action.yml").read_text(encoding="utf-8"))
    assert act["runs"]["using"] == "composite"
    text = yaml.safe_dump(act)
    for part in ("node-version: '22'", "npm ci", "playwright install --with-deps chromium", "python-version: '3.12'",
                 "pip install -r requirements.txt", "ffmpeg", "ms-playwright", "cache: npm", "cache: pip"):
        assert part in text, part


def test_cronjobs_dry_run_no_network(monkeypatch, capsys, sessions):
    def boom(*a, **k):
        raise AssertionError("network call in a dry run")
    monkeypatch.setattr(C.requests, "Session", boom)
    monkeypatch.setattr(C.getpass, "getpass", boom)
    assert C.main(["--dry-run", "--delete-retired"]) == 0
    out = capsys.readouterr().out
    assert "Gus Explains · short_a     16:25 UTC, every day" in out
    assert "Gus Explains · short_b     22:25 UTC, every day" in out
    assert "CryptoFX · news_morning" in out and "Dry run: nothing changed." in out


def test_cronjobs_jobs_and_retired(sessions):
    job = C.job_for("short_a", sessions["short_a"], "tok", enabled=True)
    assert job["title"] == "Gus Explains · short_a"
    assert job["schedule"]["hours"] == [16] and job["schedule"]["minutes"] == [25] and job["schedule"]["wdays"] == [-1]
    assert '"session": "short_a"' in job["extendedData"]["body"] and '"scheduled": "true"' in job["extendedData"]["body"]
    existing = {"CryptoFX · short_a": 1, "CryptoFX · gold": 2, "Gus Explains · short_a": 3, "Other job": 4}
    assert C.retired(existing, sessions) == ["CryptoFX · gold", "CryptoFX · short_a"]


def test_history_copy_stories(tmp_path):
    import json
    from autopilot.history import copy_stories
    run = tmp_path / "output" / "run1"
    run.mkdir(parents=True)
    (run / "history_entry.json").write_text(json.dumps({"slug": "why-x", "video_id": "a"}))
    (run / "story.json").write_text('{"slug": "why-x"}')
    lone = tmp_path / "output" / "run2"
    lone.mkdir()
    (lone / "history_entry.json").write_text(json.dumps({"slug": "why-y", "video_id": "b"}))
    logs = []
    dest = tmp_path / "stories" / "published"
    assert copy_stories([run / "history_entry.json", lone / "history_entry.json"], dest, log=logs.append) == 1
    assert (dest / "why-x.json").read_text() == '{"slug": "why-x"}' and len(logs) == 1
