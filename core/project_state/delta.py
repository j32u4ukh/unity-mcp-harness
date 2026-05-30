"""單任務 project_state 增量（記憶體合併後一次落盤）。"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from core.pipeline.schema import HarnessTask
from core.project_state.index import StateIndexEntry, utc_now_iso
from tasks import TaskResult

_TASK_ID_SCENE = re.compile(r"scene|hierarchy|inspect", re.I)
_TASK_ID_ASSET = re.compile(r"sprite|asset|texture|png|psd|import", re.I)
_TASK_ID_SYSTEM = re.compile(r"camera|light|render|urp|input|audio", re.I)


def summarize_text(text: str, *, max_len: int = 500) -> str:
    body = (text or "").strip().replace("\r\n", "\n")
    if len(body) <= max_len:
        return body
    return body[: max_len - 1] + "…"


def overview_keys_for_task(task: HarnessTask) -> list[str]:
    keys: list[str] = []
    tid = task.id or ""
    if task.target.scene_path or _TASK_ID_SCENE.search(tid):
        keys.append("scenes/overview")
    if _TASK_ID_ASSET.search(tid):
        keys.append("assets/overview")
    if _TASK_ID_SYSTEM.search(tid):
        keys.append("systems/overview")
    if not keys:
        keys.append("scenes/overview")
    return keys


def overview_rel_path(key: str) -> str:
    mapping = {
        "scenes/overview": "scenes/_overview.md",
        "assets/overview": "assets/_overview.md",
        "systems/overview": "systems/_overview.md",
    }
    return mapping.get(key, "scenes/_overview.md")


def task_record_rel_path(task_id: str) -> str:
    safe = re.sub(r"[^\w\-]+", "_", task_id).strip("_") or "task"
    return f"tasks/{safe}.md"


def markdown_section_block(heading: str, body: str) -> str:
    stamp = utc_now_iso()
    return f"\n## {heading} ({stamp})\n\n{body.strip()}\n"


@dataclass
class MarkdownAppend:
    rel_path: str
    block: str
    create_title: str | None = None


@dataclass
class TaskStateDelta:
    changelog_line: str
    markdown_appends: list[MarkdownAppend] = field(default_factory=list)
    index_entries: list[StateIndexEntry] = field(default_factory=list)


def compute_task_delta(task: HarnessTask, result: TaskResult) -> TaskStateDelta:
    summary = summarize_text(result.reply or result.error or "")
    status = "completed" if result.success else "failed"
    verification = task.verification
    one_line = summarize_text(summary, max_len=120)

    task_rel = task_record_rel_path(task.id)
    task_body = (
        f"- **status**: {status}\n"
        f"- **verification**: {verification}\n"
        f"- **description**: {task.description}\n\n"
        f"{summary}\n"
    )
    if task.target.game_object or task.target.scene_path:
        task_body += "\n**target**:\n"
        if task.target.scene_path:
            task_body += f"- scene_path: `{task.target.scene_path}`\n"
        if task.target.game_object:
            task_body += f"- game_object: `{task.target.game_object}`\n"

    changelog_line = (
        f"- {utc_now_iso()} | `{task.id}` | {status} | "
        f"{summarize_text(result.reply or result.error or '', max_len=200)}\n"
    )

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
            block=markdown_section_block(f"任務 {task.id}", task_body),
            create_title="Task Record",
        )
    ]

    for key in overview_keys_for_task(task):
        rel = overview_rel_path(key)
        overview_note = f"**{task.id}** ({status}): {one_line}"
        title = rel.split("/")[-1].replace("_", " ").replace(".md", "").title()
        appends.append(
            MarkdownAppend(
                rel_path=rel,
                block=markdown_section_block(task.id, overview_note),
                create_title=title,
            )
        )
        entries.append(
            StateIndexEntry(
                key=key,
                path=rel,
                summary=one_line,
                tags=key.split("/"),
                last_updated=utc_now_iso(),
                last_task_id=task.id,
            )
        )

    return TaskStateDelta(
        changelog_line=changelog_line,
        markdown_appends=appends,
        index_entries=entries,
    )
