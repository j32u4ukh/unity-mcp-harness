"""執行期任務生命週期：on_task_start / on_task_end + task_list 落盤。"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.harness_log import log_verification_end, log_verification_start

from core.pipeline.schema import HarnessTask, OperationRecord, TaskListDocument
from core.pipeline.store import inject_subtask, save_task_list
from core.pipeline.tool_adapter import (
    DEFAULT_VERIFY_TOOL,
    DEFAULT_WRITE_TOOL,
    append_operation,
    capture_post_read_snapshot,
    capture_pre_read_snapshot,
    plan_post_read,
)
from core.pipeline.verification import (
    VerificationResult,
    run_task_verification,
    should_skip_verification,
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


def classify_task_outcome(
    result: TaskResult,
    *,
    verification: VerificationResult | None = None,
    skip_verification: bool = False,
) -> tuple[str, str]:
    """回傳 (status, verification)。``verified`` 僅在 MCP 事後驗證通過時設定。"""
    if not result.success:
        return "failed", "failed"

    idempotent = reply_indicates_idempotent_skip(result.reply)

    if skip_verification or verification is None:
        if idempotent:
            return "completed", "skipped_by_idempotent"
        return "completed", "verified"

    if not verification.passed:
        return "failed", "failed"

    if idempotent:
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
        model: str | None = None,
        mcp_servers: list[str] | None = None,
        unity_config_path: str | Path | None = None,
        skip_verification: bool = False,
        definition_of_done: list[str] | None = None,
        verification_max_tool_rounds: int = 10,
        specs: dict[str, Any] | None = None,
    ) -> None:
        self.document = document
        self.path = Path(path)
        self.unity_runner = unity_runner
        self.model = model
        self.mcp_servers = list(mcp_servers or ["unity"])
        self.unity_config_path = (
            str(unity_config_path) if unity_config_path is not None else None
        )
        self.skip_verification = skip_verification
        self.definition_of_done = definition_of_done
        self.verification_max_tool_rounds = verification_max_tool_rounds
        self.specs = specs

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

    def _run_post_task_verification(
        self, task: HarnessTask, result: TaskResult
    ) -> VerificationResult | None:
        if should_skip_verification(task, skip_verification=self.skip_verification):
            return None
        if not result.success or not (result.reply or "").strip():
            return None

        log_verification_start(task.id)
        verification = run_task_verification(
            task,
            agent_reply=result.reply,
            model=self.model,
            mcp_servers=self.mcp_servers,
            max_tool_rounds=self.verification_max_tool_rounds,
            specs=self.specs,
            config_path=self.unity_config_path,
            definition_of_done=self.definition_of_done,
            idempotent_skip=reply_indicates_idempotent_skip(result.reply),
        )
        log_verification_end(
            task.id,
            passed=verification.passed,
            summary=verification.summary,
        )
        return verification

    def on_task_end(self, task_id: str, result: TaskResult) -> tuple[HarnessTask, TaskResult]:
        task = self.get_task(task_id)

        summary = _summarize_reply(result)
        if summary:
            append_operation(
                task,
                action="MCP_Execute",
                tool=DEFAULT_WRITE_TOOL,
                summary=summary,
            )

        verification: VerificationResult | None = None
        if result.success and not should_skip_verification(
            task, skip_verification=self.skip_verification
        ):
            verification = self._run_post_task_verification(task, result)
            if verification is not None and not verification.passed:
                result = TaskResult(
                    id=result.id,
                    title=result.title,
                    success=False,
                    reply=result.reply,
                    error=verification.summary,
                )

        status, verification_label = classify_task_outcome(
            result,
            verification=verification,
            skip_verification=self.skip_verification,
        )
        task.status = status
        task.verification = verification_label

        if verification is not None:
            post_plan = plan_post_read(task)
            task.pipeline_records.actual_after.setdefault("verify_plan", post_plan.summary)
            task.pipeline_records.actual_after.update(verification.to_actual_after())
            append_operation(
                task,
                action="MCP_VerifyRead",
                tool=DEFAULT_VERIFY_TOOL,
                summary=verification.summary[:2000],
            )
        else:
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
        return task, result
