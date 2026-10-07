"""Record of past videos, so topics and footage are not repeated."""
import json
from pathlib import Path


class History:
    def __init__(self, path: Path):
        self.path = Path(path)
        if self.path.exists():
            self.data = json.loads(self.path.read_text(encoding="utf-8"))
        else:
            self.data = {"videos": []}

    def topics(self) -> list[str]:
        return [v["topic"] for v in self.data["videos"] if v.get("topic")]

    def used_footage(self) -> set:
        ids = []
        for v in self.data["videos"][-120:]:
            ids += v.get("footage_ids", [])
        return set(ids)

    def add(self, entry: dict) -> None:
        self.data["videos"].append(entry)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
