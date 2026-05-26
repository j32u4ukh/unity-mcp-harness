"""執行期：由 task_list 驅動 LangGraph 任務與 prompt。"""

from __future__ import annotations

from dataclasses import replace

from core.pipeline.schema import HarnessTask, TaskListDocument
from tasks import BuildPlan, BuildTask

RUNNABLE_STATUSES = frozenset({"pending", "in_progress", "failed"})


def harness_task_to_build_task(harness_task: HarnessTask) -> BuildTask:
    """將 SSOT 任務轉為 ``BuildTask``（prompt 來自 task_list，非藍圖）。"""
    return BuildTask(
        id=harness_task.id,
        title=harness_task.title or harness_task.description,
        prompt=harness_task.prompt,
        objective=harness_task.description,
        enabled=harness_task.status not in ("completed", "skipped"),
    )


def sorted_runnable_tasks(doc: TaskListDocument) -> list[HarnessTask]:
    """依 priority 排序、略過 completed / skipped。"""
    runnable = [t for t in doc.tasks if t.status in RUNNABLE_STATUSES]
    return sorted(runnable, key=lambda t: (t.priority, t.id))


def harness_tasks_by_id(doc: TaskListDocument) -> dict[str, HarnessTask]:
    return {t.id: t for t in doc.tasks}


def get_next_runnable_task(doc: TaskListDocument) -> HarnessTask | None:
    """下一個待執行任務（依 priority）；無則 ``None``。"""
    runnable = sorted_runnable_tasks(doc)
    return runnable[0] if runnable else None


def build_plan_for_execution(
    blueprint: BuildPlan,
    task_list: TaskListDocument,
) -> BuildPlan:
    """以 task_list 的 prompt/順序建立執行用 ``BuildPlan``（憲法欄位仍來自藍圖）。"""
    tasks = [harness_task_to_build_task(ht) for ht in sorted_runnable_tasks(task_list)]
    return replace(blueprint, tasks=tasks)
