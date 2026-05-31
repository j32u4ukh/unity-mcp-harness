"""執行期：由 task_list 驅動 LangGraph 任務與 prompt。"""

from __future__ import annotations

from dataclasses import replace

from core.pipeline.schema import HarnessTask, TaskListDocument
from tasks import BuildPlan, BuildTask

DEFAULT_RUNNABLE_STATUSES = frozenset({"pending", "in_progress"})
RETRY_FAILED_RUNNABLE_STATUSES = frozenset({"pending", "in_progress", "failed"})
TERMINAL_OK_STATUSES = frozenset({"completed", "skipped"})


def ordered_task_entries(doc: TaskListDocument) -> list[tuple[int, HarnessTask]]:
    """依 priority、再依 task_list 插入序排列（含動態注入子任務）。"""
    return sorted(
        list(enumerate(doc.tasks)),
        key=lambda item: (item[1].priority, item[0]),
    )


def find_sequential_blocker(
    doc: TaskListDocument,
    *,
    block_after_failed: bool = True,
) -> HarnessTask | None:
    """
    若順序上存在 ``failed`` 且後方仍有未完成的後續任務，回傳該 failed 任務。

    表示後續任務應被阻擋，直到以 ``--retry-failed`` 重試此項。
    """
    if not block_after_failed:
        return None
    seen_runnable_ahead = False
    for _, task in reversed(ordered_task_entries(doc)):
        if task.status in DEFAULT_RUNNABLE_STATUSES:
            seen_runnable_ahead = True
            continue
        if task.status == "failed" and seen_runnable_ahead:
            return task
    return None


def sorted_runnable_tasks(
    doc: TaskListDocument,
    *,
    retry_failed: bool = False,
    block_after_failed: bool = True,
) -> list[HarnessTask]:
    """
    依 priority 排序可執行任務。

    預設 **嚴格順序**：若前方任務 ``failed`` 且後方仍有 ``pending`` / ``in_progress``，整隊列阻擋
    （除非 ``--retry-failed`` 重試 failed 項）。``block_after_failed=False`` 供 ``--continue-on-error``。
    """
    if block_after_failed and not retry_failed:
        if find_sequential_blocker(doc, block_after_failed=True) is not None:
            return []

    ordered = [task for _, task in ordered_task_entries(doc)]

    if not block_after_failed:
        return [t for t in ordered if t.status in DEFAULT_RUNNABLE_STATUSES]

    result: list[HarnessTask] = []
    for task in ordered:
        if task.status in TERMINAL_OK_STATUSES:
            continue
        if task.status == "failed":
            if retry_failed and not result:
                result.append(task)
            break
        if task.status in DEFAULT_RUNNABLE_STATUSES:
            result.append(task)
    return result


def harness_task_to_build_task(harness_task: HarnessTask) -> BuildTask:
    """將 SSOT 任務轉為 ``BuildTask``（prompt 來自 task_list，非藍圖）。"""
    return BuildTask(
        id=harness_task.id,
        title=harness_task.title or harness_task.description,
        prompt=harness_task.prompt,
        objective=harness_task.description,
        enabled=harness_task.status not in ("completed", "skipped"),
    )


def harness_tasks_by_id(doc: TaskListDocument) -> dict[str, HarnessTask]:
    return {t.id: t for t in doc.tasks}


def get_next_runnable_task(
    doc: TaskListDocument,
    *,
    retry_failed: bool = False,
    block_after_failed: bool = True,
) -> HarnessTask | None:
    """下一個待執行任務（嚴格順序）；無則 ``None``。"""
    runnable = sorted_runnable_tasks(
        doc,
        retry_failed=retry_failed,
        block_after_failed=block_after_failed,
    )
    return runnable[0] if runnable else None


def build_plan_for_execution(
    blueprint: BuildPlan,
    task_list: TaskListDocument,
    *,
    retry_failed: bool = False,
    block_after_failed: bool = True,
) -> BuildPlan:
    """以 task_list 的 prompt/順序建立執行用 ``BuildPlan``（憲法欄位仍來自藍圖）。"""
    tasks = [
        harness_task_to_build_task(ht)
        for ht in sorted_runnable_tasks(
            task_list,
            retry_failed=retry_failed,
            block_after_failed=block_after_failed,
        )
    ]
    return replace(blueprint, tasks=tasks)
