"""Delete the crypto-era videos and posts, only after the owner confirms. Irreversible; dry-run by default.

    python scripts/delete_old_content.py [--youtube] [--facebook] [--before YYYY-MM-DD] [--confirm]

Without --confirm (the default) it only lists: every item (platform, id, date, title) and the count, and writes the
plan to output/deletion-plan.json. Read that file. Then, if you still want it gone, run the same command with
--confirm: it lists again and refuses when the live list has an item the plan doesn't ("plan out of date, re-run
without --confirm"), then deletes the planned ids one by one, logging each to output/deletion-log.json. It stops on
the first auth / permission / quota error with a fix hint.

--before (default: today, UTC): only items published before that date are listed, so the Gus Explains videos (which
start after the cutover) are never touched. Neither --youtube nor --facebook = both.

YouTube: the channel's uploads playlist (channels.list mine → playlistItems.list); deleting needs the `youtube`
scope: run `python get_token.py --manage-scopes` on your computer and put the new YT_REFRESH_TOKEN in the
environment (and the GitHub secret). videos.delete costs 50 quota units (about 200 deletions a day).
Facebook: /{page}/videos, /{page}/video_reels and /{page}/posts; DELETE /{id}. The Page token needs
pages_manage_posts (delete) and pages_read_engagement (list).
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from autopilot import facebook, youtube  # noqa: E402

OUTPUT = ROOT / "output"
PLAN, LOG = "deletion-plan.json", "deletion-log.json"
YT_HINT = ("YouTube refused (missing permission): the refresh token needs the `youtube` scope. On your computer run "
           "`python get_token.py --manage-scopes`, sign in with the channel's account, and set YT_REFRESH_TOKEN "
           "to the new value (environment and GitHub secret).")
YT_QUOTA = "YouTube API quota used up for today (videos.delete = 50 units); run --confirm again tomorrow."
FB_HINT = ("Facebook refused (token / permission): the Page token needs pages_manage_posts (to delete) and "
           "pages_read_engagement (to list), from an admin of the Page (README → Facebook Page).")


def log(msg: str) -> None:
    print(msg, flush=True)


class StopError(RuntimeError):
    """An auth, permission or quota error: nothing more can be done until the owner fixes it (message = the hint)."""


def _day(stamp: str) -> str:
    """'2026-10-08T12:30:00Z' / '2026-10-08T12:30:00+0000' → '2026-10-08'."""
    return str(stamp or "")[:10]


# ─── YouTube ─────────────────────────────────────────────────────────────────

class YouTubeSource:
    platform = "youtube"

    def __init__(self, client=None, delete=None):
        self._yt, self._delete = client, delete or youtube.delete_video

    def _client(self):
        if self._yt is None:
            self._yt = youtube._client(youtube.MANAGE_SCOPES)
        return self._yt

    @staticmethod
    def _stop(e):
        """An HttpError → StopError when it is about access or quota, else the error itself."""
        text = str(e)
        status = getattr(getattr(e, "resp", None), "status", None)
        if "quotaExceeded" in text or "dailyLimitExceeded" in text:
            return StopError(YT_QUOTA)
        if status in (401, 403) or "insufficientPermissions" in text or "invalid_scope" in text \
                or "invalid_grant" in text:
            return StopError(f"{YT_HINT} ({status or ''} {text[:160]})")
        return e

    def list(self, before: str) -> list[dict]:
        try:
            yt = self._client()
            ch = yt.channels().list(part="contentDetails", mine=True).execute()
            items = ch.get("items") or []
            if not items:
                raise StopError("YouTube: this token has no channel (sign in with the channel's account)")
            uploads = items[0]["contentDetails"]["relatedPlaylists"]["uploads"]
            out, token = [], None
            while True:
                res = yt.playlistItems().list(part="snippet,contentDetails", playlistId=uploads, maxResults=50,
                                              pageToken=token).execute()
                for it in res.get("items") or []:
                    sn, cd = it.get("snippet") or {}, it.get("contentDetails") or {}
                    vid = cd.get("videoId") or (sn.get("resourceId") or {}).get("videoId")
                    date = _day(cd.get("videoPublishedAt") or sn.get("publishedAt"))
                    if vid and date and date < before:
                        out.append({"platform": "youtube", "kind": "video", "id": vid, "date": date,
                                    "title": sn.get("title") or ""})
                token = res.get("nextPageToken")
                if not token:
                    return out
        except StopError:
            raise
        except Exception as e:  # HttpError, google auth RefreshError
            raise self._stop(e) from e

    def delete(self, item: dict) -> None:
        try:
            self._delete(item["id"], log=log)
        except Exception as e:
            raise self._stop(e) from e


# ─── Facebook ────────────────────────────────────────────────────────────────

FB_EDGES = (("videos", "video", "id,created_time,title,description"),
            ("video_reels", "reel", "id,created_time,description"),
            ("posts", "post", "id,created_time,message"))


class FacebookSource:
    platform = "facebook"

    def __init__(self, cfg: dict | None = None, call=None):
        self.cfg = cfg or {}
        self._call = call or facebook._call

    def _base(self) -> tuple[str, str, str]:
        page, token = os.environ.get("FB_PAGE_ID"), os.environ.get("FB_PAGE_TOKEN")
        if not page or not token:
            raise StopError("Facebook: set FB_PAGE_ID and FB_PAGE_TOKEN (or pass --youtube to skip Facebook)")
        return facebook.GRAPH.format(v=facebook._version(self.cfg)), page, token

    @staticmethod
    def _stop(e):
        code = getattr(e, "code", None)
        if code in (190, 10) or (isinstance(code, int) and 200 <= code <= 299):
            return StopError(f"{FB_HINT} ({e})")
        return e

    def list(self, before: str) -> list[dict]:
        graph, page, token = self._base()
        out, seen = [], set()
        for edge, kind, fields in FB_EDGES:
            url, params = f"{graph}/{page}/{edge}", {"fields": fields, "limit": 100}
            while url:
                try:
                    res = self._call("GET", url, params=params, headers={"Authorization": f"OAuth {token}"}, log=log)
                except Exception as e:
                    raise self._stop(e) from e
                for it in res.get("data") or []:
                    oid, date = str(it.get("id") or ""), _day(it.get("created_time"))
                    if not oid or oid in seen or not date or date >= before:
                        continue
                    seen.add(oid)  # a Reel is also listed under /videos
                    text = it.get("title") or it.get("description") or it.get("message") or ""
                    out.append({"platform": "facebook", "kind": kind, "id": oid, "date": date,
                                "title": " ".join(text.split())[:80]})
                url = (res.get("paging") or {}).get("next")
                params = None  # the next link carries its own query
        return out

    def delete(self, item: dict) -> None:
        graph, _, token = self._base()
        try:
            res = self._call("DELETE", f"{graph}/{item['id']}", headers={"Authorization": f"OAuth {token}"}, log=log)
        except Exception as e:
            raise self._stop(e) from e
        if res.get("success") is False:
            raise RuntimeError(f"Facebook did not delete {item['id']}: {res}")


# ─── plan / confirm ─────────────────────────────────────────────────────────

def _key(item: dict) -> tuple[str, str]:
    return item["platform"], item["id"]


def gather(sources: dict, platforms: list[str], before: str) -> list[dict]:
    items = []
    for p in platforms:
        found = [i for i in sources[p].list(before) if i["date"] < before]  # never anything on/after --before
        log(f"{p}: {len(found)} item(s) published before {before}")
        items += found
    return items


def show(items: list[dict]) -> None:
    for i in items:
        log(f"  {i['platform']:<8} {i.get('kind', ''):<5} {i['id']:<28} {i['date']}  {i['title']}")
    log(f"{len(items)} item(s) in total")


def _append_log(path: Path, entry: dict) -> None:
    done = json.loads(path.read_text()) if path.exists() else []
    done.append(entry)
    path.write_text(json.dumps(done, indent=1, ensure_ascii=False))


def confirm(sources: dict, platforms: list[str], before: str, out: Path) -> int:
    plan_path = out / PLAN
    if not plan_path.exists():
        log(f"No plan at {plan_path}: run without --confirm first and read the plan")
        return 1
    plan = json.loads(plan_path.read_text())
    if plan.get("before") != before or sorted(plan.get("platforms") or []) != sorted(platforms):
        log(f"The plan was made for --before {plan.get('before')} and {', '.join(plan.get('platforms') or [])}; "
            "re-run without --confirm with the options you want, then --confirm with the same ones")
        return 1
    planned = {_key(i): i for i in plan.get("items") or []}
    live = gather(sources, platforms, before)
    extra = [i for i in live if _key(i) not in planned]
    if extra:
        show(extra)
        log(f"plan out of date, re-run without --confirm ({len(extra)} live item(s) above are not in the plan)")
        return 1
    live_keys = {_key(i) for i in live}
    log_path, failed = out / LOG, 0
    log(f"Deleting {len(planned)} planned item(s); each one is logged to {log_path}")
    for key, item in planned.items():
        at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        if key not in live_keys:
            log(f"{item['platform']} {item['id']}: already gone")
            _append_log(log_path, {**item, "result": "already gone", "at": at})
            continue
        try:
            sources[item["platform"]].delete(item)
        except StopError as e:
            _append_log(log_path, {**item, "result": f"stopped: {e}", "at": at})
            log(f"Stopped at {item['platform']} {item['id']}: {e}")
            return 1
        except Exception as e:  # one item failed for another reason: log it, go on with the rest
            failed += 1
            _append_log(log_path, {**item, "result": f"failed: {e}", "at": at})
            log(f"{item['platform']} {item['id']}: not deleted ({e})")
            continue
        _append_log(log_path, {**item, "result": "deleted", "at": at})
        log(f"{item['platform']} {item['id']}: deleted ({item['date']} {item['title']})")
    log(f"Done: {len(planned) - failed} of {len(planned)} handled" + (f", {failed} failed (see the log)" if failed else ""))
    return 1 if failed else 0


def main(argv: list[str] | None = None, sources: dict | None = None, out: Path | None = None) -> int:
    ap = argparse.ArgumentParser(description="List (default) or delete the old channel content.")
    ap.add_argument("--youtube", action="store_true", help="only YouTube")
    ap.add_argument("--facebook", action="store_true", help="only Facebook")
    ap.add_argument("--before", default=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                    help="only items published before this date (YYYY-MM-DD; default today, UTC)")
    ap.add_argument("--confirm", action="store_true", help="delete the items in output/deletion-plan.json")
    a = ap.parse_args(argv)
    try:
        datetime.strptime(a.before, "%Y-%m-%d")
    except ValueError:
        log(f"--before must be YYYY-MM-DD, not {a.before}")
        return 2
    platforms = [p for p, on in (("youtube", a.youtube), ("facebook", a.facebook)) if on] or ["youtube", "facebook"]
    out = Path(out or OUTPUT)
    out.mkdir(parents=True, exist_ok=True)
    if sources is None:
        import yaml
        cfg = yaml.safe_load((ROOT / "config.yaml").read_text()) or {}
        sources = {"youtube": YouTubeSource(), "facebook": FacebookSource(cfg)}
    try:
        if a.confirm:
            return confirm(sources, platforms, a.before, out)
        items = gather(sources, platforms, a.before)
    except StopError as e:
        log(f"Stopped: {e}")
        return 1
    except Exception as e:  # a listing failed for another reason: nothing was deleted
        log(f"Stopped: listing failed ({type(e).__name__}: {e}); nothing deleted")
        return 1
    show(items)
    plan = {"made": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "before": a.before,
            "platforms": platforms, "items": items}
    (out / PLAN).write_text(json.dumps(plan, indent=1, ensure_ascii=False))
    log(f"Dry run: nothing deleted. Plan written to {out / PLAN}. Read it; to delete exactly these items run the "
        f"same command with --confirm.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
