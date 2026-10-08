"""Create or fix the cron-job.org timers (the "outside timer") for every edition in config.yaml.

Each edition gets one job titled "CryptoFX · <edition>" that POSTs workflow_dispatch to GitHub at
its start_utc (gold: Monday-Friday). Jobs with that title are updated, missing ones are created,
so running it again after changing a time in config.yaml is safe. Other jobs are left alone.

    python setup_cronjobs.py --dry-run          # show what it would do (no keys needed)
    python setup_cronjobs.py                    # asks for both keys (hidden input)
    python setup_cronjobs.py --disable news_morning,news_midday,news_evening   # create them paused

Keys (asked for if not set as environment variables; never stored):
  CRONJOB_API_KEY   cron-job.org → Settings → API → Create API key
  GH_DISPATCH_TOKEN GitHub fine-grained token, this repo only, Actions: Read and write
"""
import argparse
import getpass
import json
import os
import sys
import time
from pathlib import Path

import requests
import yaml

ROOT = Path(__file__).parent
API = "https://api.cron-job.org"
REPO = "Thimuthu96/yt-shorts-autopilot"
DISPATCH = f"https://api.github.com/repos/{REPO}/actions/workflows/autopilot.yml/dispatches"
PREFIX = "CryptoFX · "
POST = 1  # cron-job.org requestMethod code


def job_for(key: str, session: dict, token: str, enabled: bool) -> dict:
    h, m = (int(x) for x in str(session["start_utc"]).split(":"))
    weekdays = [1, 2, 3, 4, 5] if session.get("kind") == "gold" else [-1]  # 0 = Sunday
    return {
        "title": PREFIX + key,
        "url": DISPATCH,
        "enabled": enabled,
        "saveResponses": True,
        "requestMethod": POST,
        "schedule": {"timezone": "UTC", "expiresAt": 0, "hours": [h], "minutes": [m],
                     "mdays": [-1], "months": [-1], "wdays": weekdays},
        "extendedData": {
            "headers": {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
                        "Content-Type": "application/json", "X-GitHub-Api-Version": "2022-11-28"},
            "body": json.dumps({"ref": "main", "inputs": {"session": key, "scheduled": "true"}}),
        },
        "notification": {"onFailure": True, "onFailureCount": 1, "onDisable": True},
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--dry-run", action="store_true", help="print the plan, change nothing")
    p.add_argument("--disable", default="", help="comma-separated editions to create/update as paused")
    args = p.parse_args()

    cfg = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    sessions = {k: v for k, v in (cfg.get("sessions") or {}).items() if v.get("start_utc")}
    paused = {s.strip() for s in args.disable.split(",") if s.strip()}
    unknown = paused - set(sessions)
    if unknown:
        sys.exit(f"Unknown edition(s) in --disable: {sorted(unknown)}. Choose from: {', '.join(sessions)}")

    print("Timers (UTC; Sri Lanka = UTC+5:30):")
    for k, s in sorted(sessions.items(), key=lambda kv: kv[1]["start_utc"]):
        days = "Mon-Fri" if s.get("kind") == "gold" else "every day"
        print(f"  {PREFIX + k:<26} {s['start_utc']} UTC, {days}{'  (paused)' if k in paused else ''}")
    if args.dry_run:
        print("Dry run: nothing changed.")
        return 0

    api_key = os.environ.get("CRONJOB_API_KEY") or getpass.getpass("cron-job.org API key (hidden): ").strip()
    gh_token = os.environ.get("GH_DISPATCH_TOKEN") or getpass.getpass("GitHub token github_pat_… (hidden): ").strip()
    if not api_key or not gh_token:
        sys.exit("Both keys are needed.")
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"})

    r = s.get(f"{API}/jobs", timeout=30)
    if r.status_code == 401:
        sys.exit("cron-job.org refused the API key (401). Create one under Settings → API "
                 "(if you limited it to IP addresses, add this computer's IP).")
    r.raise_for_status()
    existing = {j.get("title"): j["jobId"] for j in r.json().get("jobs", [])}

    created = 0
    for k, sess in sessions.items():
        job = job_for(k, sess, gh_token, enabled=k not in paused)
        if job["title"] in existing:
            r = s.patch(f"{API}/jobs/{existing[job['title']]}", json={"job": job}, timeout=30)
            action = "updated"
        else:
            if created:
                time.sleep(13)  # cron-job.org allows 5 new jobs a minute
            r = s.put(f"{API}/jobs", json={"job": job}, timeout=30)
            action = "created"
            created += 1
        if r.status_code >= 400:
            print(f"  ✗ {job['title']}: HTTP {r.status_code} {r.text[:200]}")
            continue
        print(f"  ✓ {job['title']} {action}")
        time.sleep(0.3)
    print("Done. In cron-job.org: open a job → Test run. 204 = works; 422 = this edition isn't on the "
          "main branch yet (push/merge first); 401/403/404 = check the GitHub token's repo + Actions access.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
