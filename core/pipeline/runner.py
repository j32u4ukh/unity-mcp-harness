"""執行期任務生命週期：on_task_start / on_task_end + task_list 落盤。"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from harness.mcp_runner import UnityMCPRunner

from core.pipeline.schema import HarnessTask, OperationRecord, TaskListDocument
from core.pipeline.store import save_task_list
from core.pipeline.tool_adapter import (
    DEFAULT_WRITE_TOOL,
    append_operation,
    capture_post_read_snapshot,
    capture_pre_read_snapshot,
)
from tasks import TaskResult
from unity_common import task_reply_indicates_failure

IDEMPOTENT_SKIP_MARKERS = (
    "已存在，跳過",
    "已存在，跳过",
    "already exists, skip",
    "already exist, skip",
)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def find_harness_task(document: TaskListDocument, task_id: str) -> HarnessTask:
    for task in document.tasks:
        if task.id == task_id:
            return task
    raise KeyError(f"task_list 中找不到任務: {task_id}")


def reply_indicates_idempotent_skip(reply: str) -> bool:
    text = (reply or "").strip().lower()
    if not text:
        return False
    return any(marker.lower() in text for marker in IDEMPOTENT_SKIP_MARKERS)


def classify_task_outcome(result: TaskResult) -> tuple[str, str]:
    """回傳 (status, verification)。"""
    if not result.success:
        return "failed", "failed"
    if reply_indicates_idempotent_skip(result.reply):
        return "completed", "skipped_by_idempotent"
    return "completed", "verified"


def _summarize_reply(result: TaskResult, *, max_len: int = 400) -> str:
    text = (result.reply or result.error or "").strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "…"


class HarnessTaskRunner:
    """單次建構執行的工作階段：更新 SSOT 並原子寫入 ``task_list.yaml``。"""

    def __init__(
        self,
        document: TaskListDocument,
        path: Path | str,
        *,
        unity_runner: UnityMCPRunner | None = None,
    ) -> None:
        self.document = document
        self.path = Path(path)
        self.unity_runner = unity_runner

    def get_task(self, task_id: str) -> HarnessTask:
        return find_harness_task(self.document, task_id)

    def _touch_document(self) -> None:
        self.document.last_updated = utc_now_iso()

    def _persist(self) -> None:
        save_task_list(self.document, self.path)

    def on_task_start(self, task_id: str) -> HarnessTask:
        task = self.get_task(task_id)
        task.status = "in_progress"
        task.verification = "pending"
        capture_pre_read_snapshot(task)
        self._touch_document()
        self._persist()
        return task

    def on_task_end(self, task_id: str, result: TaskResult) -> HarnessTask:
        task = self.get_task(task_id)
        status, verification = classify_task_outcome(result)
        task.status = status
        task.verification = verification

        summary = _summarize_reply(result)
        if summary:
            append_operation(
                task,
                action="MCP_Execute",
                tool=DEFAULT_WRITE_TOOL,
                summary=summary,
            )
        capture_post_read_snapshot(task)

        if result.success and result.reply and not task_reply_indicates_failure(result.reply):
            task.pipeline_records.actual_after.setdefault(
                "last_reply_excerpt",
                summary[:200] if summary else "",
            )

        self._touch_document()
        self._persist()
        return task
