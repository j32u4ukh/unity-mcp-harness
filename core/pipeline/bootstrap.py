"""由 ``NormalizedPlan`` 產生/更新 ``task_list.yaml``。"""

from __future__ import annotations

from datetime import datetime, timezone

from core.pipeline.schema import HarnessTask, NormalizedPlan, TaskListDocument
from core.pipeline.store import default_task_list_path, load_task_list, save_task_list


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def bootstrap_task_list(
    normalized: NormalizedPlan,
    *,
    project_name: str,
    existing: TaskListDocument | None = None,
    preserve_completed: bool = True,
) -> TaskListDocument:
    """將規範化任務寫入執行隊列結構；``completed`` 任務可保留 ``pipeline_records``。"""
    completed_by_id: dict[str, HarnessTask] = {}
    if existing and preserve_completed:
        for task in existing.tasks:
            if task.status == "completed":
                completed_by_id[task.id] = task

    ordered = sorted(normalized.normalized_tasks, key=lambda t: (t.priority, t.id))
    tasks: list[HarnessTask] = []
    for nt in ordered:
        if nt.id in completed_by_id:
            tasks.append(completed_by_id[nt.id])
        else:
            tasks.append(HarnessTask.from_normalized(nt, status="pending"))

    return TaskListDocument(
        project_name=project_name,
        harness_version=1,
        last_updated=_utc_now_iso(),
        source_plan=normalized.source_plan,
        plan_revision=normalized.plan_revision,
        plan_normalized_at=_utc_now_iso(),
        tasks=tasks,
    )


def ensure_task_list(
    normalized: NormalizedPlan,
    *,
    project_name: str,
    path=None,
    replan: bool = False,
    preserve_completed: bool = True,
) -> TaskListDocument:
    """若需建立/更新 task_list 則 bootstrap 並落盤；否則載入既有檔案。"""
    target = path or default_task_list_path()
    existing: TaskListDocument | None = None
    if target.is_file():
        existing = load_task_list(target)

    if existing is None or replan:
        doc = bootstrap_task_list(
            normalized,
            project_name=project_name,
            existing=existing if replan else None,
            preserve_completed=preserve_completed and replan,
        )
        save_task_list(doc, target)
        return doc

    return existing
