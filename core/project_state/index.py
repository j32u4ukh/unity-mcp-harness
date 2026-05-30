"""project_state/_index.yaml 讀寫。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from core.project_state.paths import INDEX_FILENAME, default_project_state_root


@dataclass
class StateIndexEntry:
    key: str
    path: str
    summary: str = ""
    tags: list[str] = field(default_factory=list)
    last_updated: str | None = None
    last_task_id: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StateIndexEntry:
        tags = data.get("tags") or []
        if not isinstance(tags, list):
            tags = []
        return cls(
            key=str(data.get("key", "")),
            path=str(data.get("path", "")),
            summary=str(data.get("summary") or ""),
            tags=[str(t) for t in tags],
            last_updated=data.get("last_updated"),
            last_task_id=data.get("last_task_id"),
        )

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "key": self.key,
            "path": self.path,
            "summary": self.summary,
        }
        if self.tags:
            out["tags"] = self.tags
        if self.last_updated:
            out["last_updated"] = self.last_updated
        if self.last_task_id:
            out["last_task_id"] = self.last_task_id
        return out


@dataclass
class StateIndex:
    version: int = 1
    description: str = ""
    updated_at: str | None = None
    entries: list[StateIndexEntry] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StateIndex:
        entries = [
            StateIndexEntry.from_dict(item)
            for item in data.get("entries") or []
            if isinstance(item, dict)
        ]
        return cls(
            version=int(data.get("version") or 1),
            description=str(data.get("description") or ""),
            updated_at=data.get("updated_at"),
            entries=entries,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "description": self.description,
            "updated_at": self.updated_at,
            "entries": [e.to_dict() for e in self.entries],
        }

    def find(self, key: str) -> StateIndexEntry | None:
        for entry in self.entries:
            if entry.key == key:
                return entry
        return None

    def upsert(self, entry: StateIndexEntry) -> None:
        for i, existing in enumerate(self.entries):
            if existing.key == entry.key:
                self.entries[i] = entry
                return
        self.entries.append(entry)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_index(root: Path | None = None) -> StateIndex | None:
    path = (root or default_project_state_root()) / INDEX_FILENAME
    if not path.is_file():
        return None
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return None
    return StateIndex.from_dict(data)


def save_index(index: StateIndex, root: Path | None = None) -> Path:
    base = root or default_project_state_root()
    base.mkdir(parents=True, exist_ok=True)
    index.updated_at = utc_now_iso()
    path = base / INDEX_FILENAME
    path.write_text(
        yaml.dump(index.to_dict(), allow_unicode=True, sort_keys=False, default_flow_style=False),
        encoding="utf-8",
    )
    return path
