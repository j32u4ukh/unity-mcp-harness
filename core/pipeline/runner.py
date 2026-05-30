"""執行期任務生命週期：on_task_start / on_task_end + task_list 落盤。"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from harness.mcp_runner import UnityMCPRunner

from core.pipeline.schema import HarnessTask, OperationRecord, TaskListDocument
from core.pipeline.store import inject_subtask, save_task_list
from core.pipeline.tool_adapter import (
    DEFAULT_WRITE_TOOL,
    append_operation,
    capture_post_read_snapshot,
    capture_pre_read_snapshot,
)
from core.project_state.update import record_task_completion
from tasks import TaskResult
from unity_common import task_reply_indicates_failure

IDEMPOTENT_SKIP_MARKERS = (
    "已存在，跳過",
    "已存在，跳过",
    "already exists, skip",
    "already exist, skip",
)
INJECT_MARKER_PATTERN = re.compile(r"\[HARNESS_INJECT:(?P<payload>.+?)\]")


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


def parse_harness_injections(reply: str) -> list[dict]:
    """解析回覆中的 ``[HARNESS_INJECT:...]`` 標記（目前支援 JSON）。"""
    matches = INJECT_MARKER_PATTERN.findall(reply or "")
    specs: list[dict] = []
    for payload in matches:
        raw = payload.strip()
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and data.get("id") and data.get("prompt"):
            specs.append(data)
    return specs


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
            injected = parse_harness_injections(result.reply)
            for spec in injected:
                subtask = inject_subtask(
                    self.document,
                    task.id,
                    spec,
                    priority=spec.get("priority"),
                )
                append_operation(
                    task,
                    action="Dynamic_Task_Injection",
                    summary=f"inject {subtask.id}",
                )

        record_task_completion(task, result)

        self._touch_document()
        self._persist()
        return task
