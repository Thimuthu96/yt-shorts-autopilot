"""Record of published editions: avoids double posts and repeating earlier stories.

One entry per run that published anywhere. It carries the id of each platform it reached:
"video_id" (YouTube), "fb_reel_id" (Facebook Reel), "fb_post_id" (Facebook news image post).
A run that publishes a platform the edition missed earlier (e.g. Facebook after a failure) adds a
second entry for the same edition, so each platform's guard is checked on its own.

Entries carry "trigger" (timed | manual) and "counts" (does it fill that day's edition slot?).
Manual runs don't count unless started with --as-edition, so they never stop the autopilot.

    python -m autopilot.history add output/*/history_entry.json   # merge (used by the workflow)
"""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ID_KEYS = ("video_id", "fb_reel_id", "fb_post_id")
PLATFORM_IDS = {"youtube": ("video_id",), "facebook": ("fb_reel_id", "fb_post_id")}


class History:
    def __init__(self, path: Path):
        self.path = Path(path)
        if self.path.exists():
            self.data = json.loads(self.path.read_text(encoding="utf-8"))
        else:
            self.data = {"videos": []}

    def uploaded(self) -> list[dict]:
        """Entries that reached at least one platform."""
        return [v for v in self.data["videos"] if any(v.get(k) for k in ID_KEYS)]

    def used_headlines(self) -> list[str]:
        """Headlines of recent video editions (news image posts are tracked separately)."""
        out = []
        for v in [v for v in self.uploaded() if v.get("kind") != "post"][-15:]:
            out += v.get("headlines", [])
        return out

    def published_on(self, date: str, session: str, platform: str) -> bool:
        # entries from before sessions existed count as the London edition; manual runs don't count
        keys = PLATFORM_IDS[platform]
        return any(v.get("brief_date") == date and v.get("session", "london") == session and v.get("counts", True)
                   and any(v.get(k) for k in keys) for v in self.uploaded())

    def uploaded_on(self, date: str, session: str) -> bool:
        """Is today's slot of this edition already on YouTube?"""
        return self.published_on(date, session, "youtube")

    def excluding_slot(self, date: str, session: str) -> "History":
        """A copy without the counting entries of that day's edition, so re-making an edition for a
        platform it missed sees the same history the first run saw (same lead, same review)."""
        h = History.__new__(History)
        h.path = self.path
        h.data = {**self.data, "videos": [v for v in self.data["videos"] if not (
            v.get("brief_date") == date and v.get("session", "london") == session and v.get("counts", True))]}
        return h

    def fb_post_headlines(self, hours: float | None = None) -> list[str]:
        """Story titles already used by Facebook news posts (optionally only the last `hours`)."""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours) if hours else None
        out = []
        for v in self.uploaded():
            if not v.get("fb_post_id"):
                continue
            if cutoff:
                try:
                    if datetime.fromisoformat(v["date"]) < cutoff:
                        continue
                except (KeyError, ValueError):
                    continue
            out += v.get("headlines", [])
        return out[-120:]

    def last(self, kind: str = "market") -> dict | None:
        """Most recent upload of that kind (old entries have no kind and are market briefs)."""
        for v in reversed(self.uploaded()):
            if v.get("kind", "market") == kind:
                return v
        return None

    def last_upload_time(self, kind: str = "market") -> datetime | None:
        times = []
        for v in self.uploaded():
            if v.get("kind", "market") != kind:
                continue
            try:
                times.append(datetime.fromisoformat(v["date"]))
            except (KeyError, ValueError):
                pass
        return max(times) if times else None

    def add(self, entry: dict) -> bool:
        """Append unless an entry with any of the same platform ids is logged (merging twice is harmless)."""
        for k in ID_KEYS:
            i = entry.get(k)
            if i and any(v.get(k) == i for v in self.data["videos"]):
                return False
        self.data["videos"].append(entry)
        return True

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    if len(sys.argv) < 3 or sys.argv[1] != "add":
        sys.exit("usage: python -m autopilot.history add <entry.json>...")
    h = History(Path(__file__).resolve().parents[1] / "data" / "history.json")
    added = [p for p in sys.argv[2:] if h.add(json.loads(Path(p).read_text(encoding="utf-8")))]
    h.save()
    print(f"history: {len(added)} new entr{'y' if len(added) == 1 else 'ies'}")
