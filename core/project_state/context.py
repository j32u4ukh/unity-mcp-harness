"""將 project_state 摘要注入規劃與執行 prompt。"""

from __future__ import annotations

from pathlib import Path

from core.pipeline.schema import HarnessTask
from core.pipeline.store import default_task_list_path, load_task_list
from core.project_state.delta import overview_keys_for_task, overview_rel_path, task_record_rel_path
from core.project_state.index import StateIndex, load_index
from core.project_state.paths import default_project_state_root
from core.project_state.session import get_active_session
from core.project_state.ssot import (
    CURRENT_SECTION,
    SNAPSHOT_SECTION,
    read_section_from_markdown,
)

_DISCLAIMER_PLANNING = (
    "【Unity 專案狀態文件樹 — 輔助摘要】"
    "完成與否**以 task_list.yaml（SSOT）為準**；以下索引由 SSOT 同步生成。"
    "規劃時仍須遵守 Phase 1 MCP 讀取驗證現場。"
)

_DISCLAIMER_TASK = (
    "【Unity 專案狀態 — 輔助】"
    "本任務在 task_list 的 status/verification 為權威；"
    "以下 `## 當前狀態` 由 Harness 同步，非 Agent 樂觀宣稱。"
)


def _read_excerpt_disk(path: Path, *, max_chars: int) -> str:
    if not path.is_file():
        return ""
    text = path.read_text(encoding="utf-8").strip()
    if len(text) <= max_chars:
        return text
    return text[-max_chars:].lstrip()


def _read_file_section(root: Path, rel_path: str, section_heading: str, *, max_chars: int) -> str:
    path = root / rel_path
    if not path.is_file():
        return ""
    text = path.read_text(encoding="utf-8")
    section = read_section_from_markdown(text, section_heading)
    if not section:
        return ""
    if len(section) <= max_chars:
        return section
    return section[: max_chars - 1] + "…"


def _read_excerpt(root: Path, rel_path: str, *, max_chars: int) -> str:
    session = get_active_session()
    if session is not None and session.root == root.resolve():
        return session.markdown_excerpt(rel_path, max_chars=max_chars)
    return _read_excerpt_disk(root / rel_path, max_chars=max_chars)


def _effective_index(root: Path) -> StateIndex | None:
    session = get_active_session()
    if session is not None and session.root == root.resolve():
        return session.index
    return load_index(root)


def _task_list_line(task_id: str) -> str:
    path = default_task_list_path()
    if not path.is_file():
        return ""
    try:
        doc = load_task_list(path)
    except (ValueError, OSError):
        return ""
    for t in doc.tasks:
        if t.id == task_id:
            return f"task_list SSOT: status=`{t.status}`, verification=`{t.verification}`"
    return ""


def _format_index_section(index: StateIndex, *, max_entries: int = 12) -> list[str]:
    lines = ["索引摘要（SSOT 同步後）:"]
    for entry in index.entries[:max_entries]:
        summary = entry.summary or "（無摘要）"
        lines.append(f"  - [{entry.key}] {summary} (→ {entry.path})")
    if len(index.entries) > max_entries:
        lines.append(f"  … 另有 {len(index.entries) - max_entries} 筆")
    return lines


def format_project_state_for_planning(*, max_chars: int = 2500) -> str:
    """Plan Normalize 用：索引 + overview 的 `## 當前快照`（不讀 tasks 尾端歷史）。"""
    root = default_project_state_root()
    if not root.is_dir():
        return ""

    index = _effective_index(root)
    parts = [_DISCLAIMER_PLANNING, f"根目錄: {root}"]
    session = get_active_session()
    if session is not None and session.dirty:
        parts.append("（本輪建構尚有未落盤的記憶體更新）")

    if index and index.entries:
        parts.extend(_format_index_section(index))

    for name in ("scenes/_overview.md", "assets/_overview.md", "systems/_overview.md"):
        section = _read_file_section(root, name, SNAPSHOT_SECTION, max_chars=max_chars // 4)
        if section:
            parts.append(f"\n--- {name} ({SNAPSHOT_SECTION}) ---\n{section}")

    text = "\n".join(parts)
    if len(text) > max_chars:
        return text[: max_chars - 1] + "…"
    return text


def format_project_state_for_task(
    task: HarnessTask | None,
    *,
    max_chars: int = 1800,
) -> str:
    """單任務執行用：task_list 一行 + 該任務 `## 當前狀態` + 相關 overview 快照。"""
    root = default_project_state_root()
    if not root.is_dir():
        return ""

    parts = [_DISCLAIMER_TASK]
    if task is not None:
        ssot_line = _task_list_line(task.id)
        if ssot_line:
            parts.append(ssot_line)

    index = _effective_index(root)
    if index and task is not None:
        entry = index.find(f"tasks/{task.id}")
        if entry and entry.summary:
            parts.append(f"索引摘要: {entry.summary}")

    rel_paths = []
    if task is not None:
        rel_paths.append(task_record_rel_path(task.id))
        for key in overview_keys_for_task(task):
            rel_paths.append(overview_rel_path(key))
    seen: set[str] = set()
    ordered: list[str] = []
    for rel in rel_paths:
        if rel not in seen:
            seen.add(rel)
            ordered.append(rel)

    budget = max_chars // max(len(ordered), 1)
    for rel in ordered:
        if rel.startswith("tasks/"):
            section = _read_file_section(root, rel, CURRENT_SECTION, max_chars=budget)
            if not section:
                section = _read_excerpt(root, rel, max_chars=budget)
        else:
            section = _read_file_section(root, rel, SNAPSHOT_SECTION, max_chars=budget)
        if section:
            label = CURRENT_SECTION if rel.startswith("tasks/") else SNAPSHOT_SECTION
            parts.append(f"\n--- {rel} ({label}) ---\n{section}")

    text = "\n".join(parts)
    if len(text) > max_chars:
        return text[: max_chars - 1] + "…"
    return text
