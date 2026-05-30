"""將 project_state 摘要注入規劃與執行 prompt。"""

from __future__ import annotations

from pathlib import Path

from core.pipeline.schema import HarnessTask
from core.project_state.delta import overview_keys_for_task, overview_rel_path, task_record_rel_path
from core.project_state.index import StateIndex, load_index
from core.project_state.paths import default_project_state_root
from core.project_state.session import get_active_session

_DISCLAIMER = (
    "【Unity 專案狀態文件樹 — 累積備忘，非 ground truth；"
    "本輪仍須 Phase 1 MCP 讀取驗證現場】"
)


def _read_excerpt_disk(path: Path, *, max_chars: int) -> str:
    if not path.is_file():
        return ""
    text = path.read_text(encoding="utf-8").strip()
    if len(text) <= max_chars:
        return text
    return text[-max_chars:].lstrip()


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


def _collect_paths_for_task(task: HarnessTask | None) -> list[str]:
    if task is None:
        return []
    rels: list[str] = [task_record_rel_path(task.id)]
    for key in overview_keys_for_task(task):
        rels.append(overview_rel_path(key))
    seen: set[str] = set()
    out: list[str] = []
    for rel in rels:
        if rel not in seen:
            seen.add(rel)
            out.append(rel)
    return out


def _format_index_section(index: StateIndex, *, max_entries: int = 12) -> list[str]:
    lines = ["索引摘要:"]
    for entry in index.entries[:max_entries]:
        summary = entry.summary or "（無摘要）"
        lines.append(f"  - [{entry.key}] {summary} (→ {entry.path})")
    if len(index.entries) > max_entries:
        lines.append(f"  … 另有 {len(index.entries) - max_entries} 筆")
    return lines


def format_project_state_for_planning(*, max_chars: int = 2500) -> str:
    """Plan Normalize 用：索引 + 各 overview 尾端摘要。"""
    root = default_project_state_root()
    if not root.is_dir():
        return ""

    index = _effective_index(root)
    parts = [_DISCLAIMER, f"根目錄: {root}"]
    session = get_active_session()
    if session is not None and session.dirty:
        parts.append("（本輪建構尚有未落盤的記憶體更新）")

    if index and index.entries:
        parts.extend(_format_index_section(index))

    for name in ("scenes/_overview.md", "assets/_overview.md", "systems/_overview.md"):
        excerpt = _read_excerpt(root, name, max_chars=max_chars // 4)
        if excerpt:
            parts.append(f"\n--- {name} (尾端) ---\n{excerpt}")

    text = "\n".join(parts)
    if len(text) > max_chars:
        return text[: max_chars - 1] + "…"
    return text


def format_project_state_for_task(
    task: HarnessTask | None,
    *,
    max_chars: int = 1800,
) -> str:
    """單任務執行用：相關分項文件尾端 + 索引中同 task 條目。"""
    root = default_project_state_root()
    if not root.is_dir():
        return ""

    parts = [_DISCLAIMER]
    index = _effective_index(root)
    if index and task is not None:
        entry = index.find(f"tasks/{task.id}")
        if entry and entry.summary:
            parts.append(f"本任務上次紀錄: {entry.summary}")

    rel_paths = _collect_paths_for_task(task)
    budget = max_chars // max(len(rel_paths), 1)
    for rel in rel_paths:
        excerpt = _read_excerpt(root, rel, max_chars=budget)
        if excerpt:
            parts.append(f"\n--- {rel} ---\n{excerpt}")

    text = "\n".join(parts)
    if len(text) > max_chars:
        return text[: max_chars - 1] + "…"
    return text
