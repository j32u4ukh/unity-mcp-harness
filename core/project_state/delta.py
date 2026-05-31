"""單任務 project_state 增量（記憶體合併後一次落盤）。"""

from __future__ import annotations

from dataclasses import dataclass, field

from core.pipeline.schema import HarnessTask
from core.project_state.index import StateIndexEntry, utc_now_iso
from core.project_state.ssot import (
    build_changelog_line,
    build_task_ssot_one_line,
    format_task_markdown_file,
    overview_keys_for_task,
    overview_rel_path,
    summarize_text,
    task_record_rel_path,
)
from tasks import TaskResult

__all__ = [
    "MarkdownAppend",
    "TaskStateDelta",
    "compute_task_delta",
    "markdown_section_block",
    "overview_keys_for_task",
    "overview_rel_path",
    "summarize_text",
    "task_record_rel_path",
]


def markdown_section_block(heading: str, body: str) -> str:
    """changelog / 歷史用追加區塊（任務檔已改為覆寫當前狀態）。"""
    stamp = utc_now_iso()
    return f"\n## {heading} ({stamp})\n\n{body.strip()}\n"


@dataclass
class MarkdownAppend:
    rel_path: str
    block: str = ""
    create_title: str | None = None
    full_replace_content: str | None = None


@dataclass
class TaskStateDelta:
    changelog_line: str
    markdown_appends: list[MarkdownAppend] = field(default_factory=list)
    index_entries: list[StateIndexEntry] = field(default_factory=list)


def compute_task_delta(task: HarnessTask, result: TaskResult) -> TaskStateDelta:
    one_line = build_task_ssot_one_line(task, result)
    task_rel = task_record_rel_path(task.id)

    changelog_line = build_changelog_line(task, result)

    entries = [
        StateIndexEntry(
            key=f"tasks/{task.id}",
            path=task_rel,
            summary=one_line,
            tags=["task", task.id],
            last_updated=utc_now_iso(),
            last_task_id=task.id,
        )
    ]

    appends: list[MarkdownAppend] = [
        MarkdownAppend(
            rel_path=task_rel,
            full_replace_content=format_task_markdown_file(task, result),
        )
    ]

    return TaskStateDelta(
        changelog_line=changelog_line,
        markdown_appends=appends,
        index_entries=entries,
    )
