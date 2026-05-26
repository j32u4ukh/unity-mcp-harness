"""執行期 Harness 上下文摘要（注入 LLM prompt，Token 友善）。"""

from __future__ import annotations

import json
from typing import Any

from core.pipeline.schema import HarnessTask, PipelineRecords

HARNESS_EXECUTION_COT = """【Harness 執行契約 — 本輪必須遵守】
1. Phase 1（感知）：修改前先以 MCP 讀取現場，更新對 actual_before 的理解。
2. Phase 2（行動）：僅在需要時寫入；若已滿足目標，回報「已存在，跳過」。
3. Phase 3（驗證）：寫入後再次讀取，比對預期後再宣告完成。"""

RESUME_PHASE1_REMINDER = (
    "【重啟提醒】即使下方 SSOT 有上一輪摘要，本輪仍須重新執行 Phase 1 MCP 讀取"
    "（Unity 現場可能已變）。"
)


def _compact_json(data: Any, *, max_chars: int = 400) -> str:
    if not data:
        return "（空）"
    text = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1] + "…"


def format_pipeline_records_summary(
    records: PipelineRecords,
    *,
    max_field_chars: int = 400,
) -> str:
    """將 pipeline_records 格式化為短摘要。"""
    lines = [
        f"actual_before: {_compact_json(records.actual_before, max_chars=max_field_chars)}",
    ]
    if records.operations_executed:
        lines.append(f"operations_executed: {len(records.operations_executed)} 筆")
        last = records.operations_executed[-1]
        lines.append(f"  最近: {last.action} ({last.tool or 'n/a'})")
    else:
        lines.append("operations_executed: （尚無）")
    lines.append(
        f"actual_after: {_compact_json(records.actual_after, max_chars=max_field_chars)}"
    )
    return "\n".join(lines)


def format_harness_task_context(
    task: HarnessTask,
    *,
    resume: bool = False,
    include_cot: bool = True,
) -> str:
    """單任務 Harness SSOT 區塊（status、verification、harness 提示、pipeline 摘要）。"""
    lines = [
        "【Harness 執行期狀態（task_list SSOT）】",
        f"status: {task.status}",
        f"verification: {task.verification}",
    ]
    if task.injected_by:
        lines.append(f"injected_by: {task.injected_by}")
    if task.target.game_object or task.target.scene_path:
        target_parts = []
        if task.target.scene_path:
            target_parts.append(f"scene={task.target.scene_path}")
        if task.target.game_object:
            target_parts.append(f"go={task.target.game_object}")
        lines.append("target: " + ", ".join(target_parts))
    if task.harness.pre_read:
        lines.append(f"建議 Phase 1 讀取: {task.harness.pre_read}")
    if task.harness.post_read:
        lines.append(f"建議 Phase 3 驗證: {task.harness.post_read}")
    if task.expected:
        lines.append(f"expected: {_compact_json(task.expected, max_chars=300)}")
    lines.append(format_pipeline_records_summary(task.pipeline_records))
    if resume:
        lines.append(RESUME_PHASE1_REMINDER)
    if include_cot:
        lines.append(HARNESS_EXECUTION_COT)
    return "\n".join(lines)
