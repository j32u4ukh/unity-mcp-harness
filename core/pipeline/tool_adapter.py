"""Phase 6: 執行期 Read/Write 慣例與紀錄輔助。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from core.pipeline.schema import HarnessTask, OperationRecord

DEFAULT_READ_TOOL = "unity__Unity_ListResources"
DEFAULT_VERIFY_TOOL = "unity__Unity_RunCommand"
DEFAULT_WRITE_TOOL = "unity__MCP_AgentExecute"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class ReadPlan:
    phase: str
    tool: str
    summary: str


def _build_read_summary(task: HarnessTask, hint: str | None, *, phase: str) -> str:
    parts: list[str] = []
    if hint:
        parts.append(hint.strip())
    if task.target.scene_path:
        parts.append(f"scene={task.target.scene_path}")
    if task.target.game_object:
        parts.append(f"go={task.target.game_object}")
    if not parts:
        parts.append(f"{task.id} {phase} read")
    return " | ".join(parts)


def plan_pre_read(task: HarnessTask) -> ReadPlan:
    """建立 Phase 1 讀取計畫（優先使用 harness.pre_read）。"""
    return ReadPlan(
        phase="pre_read",
        tool=DEFAULT_READ_TOOL,
        summary=_build_read_summary(task, task.harness.pre_read, phase="pre"),
    )


def plan_post_read(task: HarnessTask) -> ReadPlan:
    """建立 Phase 3 驗證讀取計畫（優先使用 harness.post_read）。"""
    return ReadPlan(
        phase="post_read",
        tool=DEFAULT_VERIFY_TOOL,
        summary=_build_read_summary(task, task.harness.post_read, phase="post"),
    )


def append_operation(
    task: HarnessTask,
    *,
    action: str,
    summary: str,
    tool: str | None = None,
) -> None:
    task.pipeline_records.operations_executed.append(
        OperationRecord(
            timestamp=utc_now_iso(),
            action=action,
            tool=tool,
            summary=summary,
        )
    )


def capture_pre_read_snapshot(task: HarnessTask) -> None:
    plan = plan_pre_read(task)
    task.pipeline_records.actual_before.setdefault("read_plan", plan.summary)
    append_operation(
        task,
        action="MCP_Read",
        tool=plan.tool,
        summary=plan.summary,
    )


def capture_post_read_snapshot(task: HarnessTask) -> None:
    plan = plan_post_read(task)
    task.pipeline_records.actual_after.setdefault("verify_plan", plan.summary)
    append_operation(
        task,
        action="MCP_VerifyRead",
        tool=plan.tool,
        summary=plan.summary,
    )

