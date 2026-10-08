"""Record of uploaded briefs: avoids double posts and repeating earlier stories.

Entries carry "trigger" (timed | manual) and "counts" (does it fill that day's edition slot?).
Manual runs don't count unless started with --as-edition, so they never stop the autopilot.

    python -m autopilot.history add output/*/history_entry.json   # merge (used by the workflow)
"""
import json
import sys
from datetime import datetime
from pathlib import Path


class History:
    def __init__(self, path: Path):
        self.path = Path(path)
        if self.path.exists():
            self.data = json.loads(self.path.read_text(encoding="utf-8"))
        else:
            self.data = {"videos": []}

    def uploaded(self) -> list[dict]:
        return [v for v in self.data["videos"] if v.get("video_id")]

    def used_headlines(self) -> list[str]:
        out = []
        for v in self.uploaded()[-15:]:
            out += v.get("headlines", [])
        return out

    def uploaded_on(self, date: str, session: str) -> bool:
        # briefs from before sessions existed count as the London edition; manual runs don't count
        return any(v.get("brief_date") == date and v.get("session", "london") == session and v.get("counts", True)
                   for v in self.uploaded())

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
        """Append unless this video is already logged (so merging twice is harmless)."""
        vid = entry.get("video_id")
        if vid and any(v.get("video_id") == vid for v in self.data["videos"]):
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
