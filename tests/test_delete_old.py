"""scripts/delete_old_content.py with fake API clients only (never a real network call)."""
import importlib.util
import json
import sys
from pathlib import Path

import httplib2
import pytest
from googleapiclient.errors import HttpError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
_spec = importlib.util.spec_from_file_location("delete_old_content", ROOT / "scripts" / "delete_old_content.py")
D = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(D)

from autopilot import facebook  # noqa: E402

BEFORE = "2026-11-20"


def item(i, date="2026-10-01", platform="youtube"):
    return {"platform": platform, "kind": "video", "id": f"{platform[:2]}{i}", "date": date, "title": f"old {i}"}


class Fake:
    def __init__(self, platform, items, fail_on=None, error=None):
        self.platform, self.items, self.deleted, self.fail_on, self.error = platform, list(items), [], fail_on, error

    def list(self, before):
        return [dict(i) for i in self.items]

    def delete(self, it):
        if self.fail_on == it["id"]:
            raise self.error
        self.deleted.append(it["id"])
        self.items = [i for i in self.items if i["id"] != it["id"]]


@pytest.fixture
def srcs():
    return {"youtube": Fake("youtube", [item(1), item(2)]),
            "facebook": Fake("facebook", [item(1, platform="facebook"), item(2, platform="facebook")])}


def run(args, srcs, out):
    return D.main(args + ["--before", BEFORE], sources=srcs, out=out)


def test_dry_run_lists_writes_plan_and_never_deletes(srcs, tmp_path, capsys):
    assert run([], srcs, tmp_path) == 0
    plan = json.loads((tmp_path / D.PLAN).read_text())
    assert [i["id"] for i in plan["items"]] == ["yo1", "yo2", "fa1", "fa2"]
    assert plan["before"] == BEFORE and plan["platforms"] == ["youtube", "facebook"]
    assert srcs["youtube"].deleted == [] and srcs["facebook"].deleted == []
    out = capsys.readouterr().out
    assert "4 item(s) in total" in out and "nothing deleted" in out
    assert not (tmp_path / D.LOG).exists()


def test_confirm_deletes_exactly_the_planned_ids(srcs, tmp_path):
    assert run(["--youtube"], srcs, tmp_path) == 0
    assert run(["--youtube", "--confirm"], srcs, tmp_path) == 0
    assert srcs["youtube"].deleted == ["yo1", "yo2"]
    assert srcs["facebook"].deleted == []  # not in the plan's platforms
    logged = json.loads((tmp_path / D.LOG).read_text())
    assert [(e["id"], e["result"]) for e in logged] == [("yo1", "deleted"), ("yo2", "deleted")]


def test_confirm_without_a_plan_refuses(srcs, tmp_path):
    assert run(["--confirm"], srcs, tmp_path) == 1
    assert srcs["youtube"].deleted == []


def test_confirm_with_other_options_than_the_plan_refuses(srcs, tmp_path):
    assert run(["--youtube"], srcs, tmp_path) == 0
    assert run(["--confirm"], srcs, tmp_path) == 1  # plan was YouTube only
    assert srcs["youtube"].deleted == [] and srcs["facebook"].deleted == []


def test_new_live_item_not_in_plan_refuses(srcs, tmp_path, capsys):
    assert run([], srcs, tmp_path) == 0
    srcs["facebook"].items.append(item(3, platform="facebook"))
    assert run(["--confirm"], srcs, tmp_path) == 1
    assert "plan out of date, re-run without --confirm" in capsys.readouterr().out
    assert srcs["youtube"].deleted == [] and srcs["facebook"].deleted == []


def test_planned_item_already_gone_is_skipped(srcs, tmp_path):
    assert run(["--youtube"], srcs, tmp_path) == 0
    srcs["youtube"].items = [item(2)]
    assert run(["--youtube", "--confirm"], srcs, tmp_path) == 0
    assert srcs["youtube"].deleted == ["yo2"]
    logged = json.loads((tmp_path / D.LOG).read_text())
    assert logged[0]["result"] == "already gone"


def _http_error(status, reason):
    body = json.dumps({"error": {"code": status, "message": reason, "errors": [{"reason": reason}]}}).encode()
    return HttpError(httplib2.Response({"status": status}), body)


def test_403_on_first_delete_stops_with_hint(tmp_path, capsys):
    calls = []

    def fake_delete(vid, log=print):
        calls.append(vid)
        raise _http_error(403, "insufficientPermissions")

    yt = D.YouTubeSource(client=object(), delete=fake_delete)
    yt.list = lambda before: [item(1), item(2)]
    srcs = {"youtube": yt}
    assert run(["--youtube"], srcs, tmp_path) == 0
    assert run(["--youtube", "--confirm"], srcs, tmp_path) == 1
    assert calls == ["yo1"]  # stopped: the second id is never tried
    out = capsys.readouterr().out
    assert "get_token.py --manage-scopes" in out
    logged = json.loads((tmp_path / D.LOG).read_text())
    assert len(logged) == 1 and logged[0]["result"].startswith("stopped")


def test_facebook_permission_error_stops_with_hint(tmp_path, capsys):
    err = facebook.GraphError("Facebook error 200: Permissions error", code=200)
    srcs = {"facebook": Fake("facebook", [item(1, platform="facebook"), item(2, platform="facebook")])}
    srcs["facebook"].fail_on, srcs["facebook"].error = "fa1", D.FacebookSource._stop(err)
    assert run(["--facebook"], srcs, tmp_path) == 0
    assert run(["--facebook", "--confirm"], srcs, tmp_path) == 1
    assert srcs["facebook"].deleted == []
    assert "pages_manage_posts" in capsys.readouterr().out


def test_other_delete_error_is_logged_and_the_rest_go_on(tmp_path):
    srcs = {"youtube": Fake("youtube", [item(1), item(2)], fail_on="yo1", error=RuntimeError("boom"))}
    assert run(["--youtube"], srcs, tmp_path) == 0
    assert run(["--youtube", "--confirm"], srcs, tmp_path) == 1
    assert srcs["youtube"].deleted == ["yo2"]


def test_items_on_or_after_before_are_never_listed(tmp_path):
    srcs = {"youtube": Fake("youtube", [item(1, "2026-11-19"), item(2, BEFORE), item(3, "2026-12-01")])}
    assert run(["--youtube"], srcs, tmp_path) == 0
    plan = json.loads((tmp_path / D.PLAN).read_text())
    assert [i["id"] for i in plan["items"]] == ["yo1"]


class _Req:
    def __init__(self, res):
        self.res = res

    def execute(self):
        return self.res


class FakeYT:
    """channels().list / playlistItems().list chain with two pages."""
    def __init__(self):
        self.pages = {None: {"items": [self._v("a", "2026-10-01T10:00:00Z"), self._v("b", "2026-11-20T17:00:00Z")],
                             "nextPageToken": "p2"},
                      "p2": {"items": [self._v("c", "2026-09-30T23:00:00Z", published=None)]}}

    @staticmethod
    def _v(vid, at, published="x"):
        cd = {"videoId": vid}
        if published:
            cd["videoPublishedAt"] = at
        return {"snippet": {"title": f"t{vid}", "publishedAt": at}, "contentDetails": cd}

    def channels(self):
        return self

    def playlistItems(self):
        return self

    def list(self, part, mine=None, playlistId=None, maxResults=None, pageToken=None):
        if mine:
            return _Req({"items": [{"contentDetails": {"relatedPlaylists": {"uploads": "UU1"}}}]})
        assert playlistId == "UU1"
        return _Req(self.pages[pageToken])


def test_youtube_source_pages_and_filters_by_date():
    got = D.YouTubeSource(client=FakeYT()).list(BEFORE)
    assert [(i["id"], i["date"]) for i in got] == [("a", "2026-10-01"), ("c", "2026-09-30")]


def test_youtube_listing_403_stops_with_hint():
    class Denied(FakeYT):
        def list(self, *a, **k):
            raise _http_error(403, "insufficientPermissions")

    with pytest.raises(D.StopError, match="manage-scopes"):
        D.YouTubeSource(client=Denied()).list(BEFORE)


def test_facebook_source_pages_dedupes_and_filters(monkeypatch):
    monkeypatch.setenv("FB_PAGE_ID", "P1")
    monkeypatch.setenv("FB_PAGE_TOKEN", "tok")
    seen = []

    def call(method, url, params=None, headers=None, log=print):
        seen.append((method, url, params))
        assert headers == {"Authorization": "OAuth tok"} and "tok" not in url
        if url.endswith("/P1/videos"):
            return {"data": [{"id": "1", "created_time": "2026-10-01T10:00:00+0000", "title": "a reel"},
                             {"id": "9", "created_time": "2026-11-21T10:00:00+0000", "title": "a gus reel"}],
                    "paging": {"next": "https://graph.facebook.com/v26.0/P1/videos?after=X"}}
        if "after=X" in url:
            return {"data": [{"id": "2", "created_time": "2026-10-02T10:00:00+0000", "description": "old"}]}
        if url.endswith("/P1/video_reels"):
            return {"data": [{"id": "1", "created_time": "2026-10-01T10:00:00+0000"}]}
        if url.endswith("/P1/posts"):
            return {"data": [{"id": "P1_5", "created_time": "2026-10-03T10:00:00+0000", "message": "news\npost"}]}
        raise AssertionError(url)

    got = D.FacebookSource({"facebook": {"graph_version": "v26.0"}}, call=call).list(BEFORE)
    assert [(i["id"], i["kind"]) for i in got] == [("1", "video"), ("2", "video"), ("P1_5", "post")]
    assert got[2]["title"] == "news post"
    assert all(m == "GET" for m, _, _ in seen)


def test_facebook_missing_secrets_stops(monkeypatch, tmp_path, capsys):
    monkeypatch.delenv("FB_PAGE_ID", raising=False)
    monkeypatch.delenv("FB_PAGE_TOKEN", raising=False)
    assert D.main(["--facebook", "--before", BEFORE], sources={"facebook": D.FacebookSource({})}, out=tmp_path) == 1
    assert "FB_PAGE_ID" in capsys.readouterr().out


def test_default_before_is_the_cutover_never_today(tmp_path):
    seen = []

    class Rec(Fake):
        def list(self, before):
            seen.append(before)
            return []

    srcs = {"youtube": Rec("youtube", [])}
    cfg = {"gus": {"cutover": "2026-11-13"}}
    assert D.main(["--youtube"], sources=srcs, out=tmp_path, cfg=cfg) == 0
    assert json.loads((tmp_path / D.PLAN).read_text())["before"] == "2026-11-13"
    # a later --confirm without --before uses the same default, so a saved plan is accepted on another day
    assert D.main(["--youtube", "--confirm"], sources=srcs, out=tmp_path, cfg=cfg) == 0
    assert seen == ["2026-11-13", "2026-11-13"]
    assert D.cutover({}) == D.DEFAULT_CUTOVER


def test_real_config_has_the_cutover():
    import yaml
    cfg = yaml.safe_load((ROOT / "config.yaml").read_text())
    assert D.cutover(cfg) == "2026-11-13"


def test_gus_ids_in_history_are_never_listed_even_with_a_later_before(tmp_path):
    hist = tmp_path / "history.json"
    hist.write_text(json.dumps({"videos": [{"video_id": "GUS1", "fb_reel_id": "777"}, {"video_id": "GUS2"}]}))
    keep = D.protected_ids(hist)
    assert keep == {"GUS1", "777", "GUS2"}
    yt = Fake("youtube", [item(1), {**item(9, "2026-11-14"), "id": "GUS1"}, {**item(8, "2026-11-15"), "id": "GUS2"}])
    fb = Fake("facebook", [item(1, platform="facebook"), {**item(7, "2026-11-14", "facebook"), "id": "777"},
                           {**item(6, "2026-11-14", "facebook"), "id": "P1_777", "kind": "post"}])
    srcs = {"youtube": yt, "facebook": fb}
    out = tmp_path / "out"
    assert D.main(["--before", "2027-01-01"], sources=srcs, out=out, keep=keep) == 0
    plan = json.loads((out / D.PLAN).read_text())
    assert [i["id"] for i in plan["items"]] == ["yo1", "fa1"]
    # even a hand-edited plan that names a Gus id never deletes it
    plan["items"].append({"platform": "youtube", "kind": "video", "id": "GUS1", "date": "2026-11-14", "title": "gus"})
    (out / D.PLAN).write_text(json.dumps(plan))
    assert D.main(["--before", "2027-01-01", "--confirm"], sources=srcs, out=out, keep=keep) == 0
    assert yt.deleted == ["yo1"] and fb.deleted == ["fa1"]


def test_protected_ids_reads_the_repo_history_shape(tmp_path):
    assert D.protected_ids(tmp_path / "missing.json") == set()
    assert D.protected_ids(ROOT / "data" / "history.json") is not None


def test_max_caps_youtube_deletions_and_a_next_day_rerun_finishes(tmp_path, capsys):
    srcs = {"youtube": Fake("youtube", [item(i) for i in range(1, 6)])}
    assert run(["--youtube", "--max", "2"], srcs, tmp_path) == 0
    assert "5 deletion(s) × 50 units = 250 units" in capsys.readouterr().out
    assert run(["--youtube", "--max", "2", "--confirm"], srcs, tmp_path) == 0
    assert srcs["youtube"].deleted == ["yo1", "yo2"]
    assert "--max 2 reached: 3 YouTube item(s) left" in capsys.readouterr().out
    assert run(["--youtube", "--max", "2", "--confirm"], srcs, tmp_path) == 0  # next day, same plan
    assert srcs["youtube"].deleted == ["yo1", "yo2", "yo3", "yo4"]
    assert run(["--youtube", "--max", "2", "--confirm"], srcs, tmp_path) == 0
    assert srcs["youtube"].deleted == ["yo1", "yo2", "yo3", "yo4", "yo5"]


def test_default_max_is_150(tmp_path):
    srcs = {"youtube": Fake("youtube", [item(i) for i in range(200)])}
    assert run(["--youtube"], srcs, tmp_path) == 0
    assert run(["--youtube", "--confirm"], srcs, tmp_path) == 0
    assert len(srcs["youtube"].deleted) == D.DEFAULT_MAX == 150


def test_facebook_already_gone_is_not_a_failure(monkeypatch, tmp_path):
    monkeypatch.setenv("FB_PAGE_ID", "P1")
    monkeypatch.setenv("FB_PAGE_TOKEN", "tok")

    def call(method, url, params=None, headers=None, log=print):
        if method == "GET":
            if url.endswith("/P1/posts"):
                return {"data": [{"id": "P1_5", "created_time": "2026-10-03T10:00:00+0000", "message": "m"}]}
            return {"data": [{"id": "5", "created_time": "2026-10-03T10:00:00+0000", "title": "v"}]} \
                if url.endswith("/P1/videos") else {"data": []}
        if url.endswith("/5"):
            return {"success": True}
        raise facebook.GraphError("Facebook error 100: Object with ID 'P1_5' does not exist, cannot be loaded due "
                                  "to missing permissions, or does not support this operation", code=100, subcode=33)

    fb = D.FacebookSource({"facebook": {"graph_version": "v26.0"}}, call=call)
    srcs = {"facebook": fb}
    assert run(["--facebook"], srcs, tmp_path) == 0
    assert run(["--facebook", "--confirm"], srcs, tmp_path) == 0
    logged = json.loads((tmp_path / D.LOG).read_text())
    assert [(e["id"], e["result"]) for e in logged] == [("5", "deleted"), ("P1_5", "already gone")]
    # a permission error is still a stop, never "gone"
    assert not D.FacebookSource._gone(facebook.GraphError("Facebook error 200: does not exist", code=200))
