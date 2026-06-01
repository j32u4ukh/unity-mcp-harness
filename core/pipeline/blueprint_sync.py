"""build_goals 與 task_list 一致性檢查。"""

from __future__ import annotations

from tasks import BuildPlan
from core.pipeline.schema import TaskListDocument


def _blueprint_task_ids(plan: BuildPlan) -> frozenset[str]:
    return frozenset(t.id for t in plan.enabled_tasks())


def _queue_task_keys(doc: TaskListDocument) -> frozenset[str]:
    keys: set[str] = set()
    for t in doc.tasks:
        keys.add(t.id)
        if t.plan_source_id:
            keys.add(t.plan_source_id)
    return frozenset(keys)


def task_list_matches_blueprint(plan: BuildPlan, doc: TaskListDocument) -> bool:
    """
    執行隊列是否仍涵蓋目前藍圖的全部任務 id。

    藍圖已改（例如僅剩測試任務 ``a`` → 攻擊系統 ``1``–``4``）時回傳 False，觸發重新 bootstrap。
    """
    blueprint_ids = _blueprint_task_ids(plan)
    if not blueprint_ids:
        return not doc.tasks

    queue_keys = _queue_task_keys(doc)
    if not blueprint_ids.issubset(queue_keys):
        return False

    active_statuses = frozenset({"pending", "running", "in_progress"})
    for t in doc.tasks:
        if t.status not in active_statuses:
            continue
        keys = {t.id}
        if t.plan_source_id:
            keys.add(t.plan_source_id)
        if not keys & blueprint_ids:
            return False
    return True
