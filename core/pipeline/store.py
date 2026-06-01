"""``task_list.yaml`` 讀寫（原子寫入）。"""

from __future__ import annotations

from pathlib import Path

import yaml

from core.pipeline.schema import HarnessTask, TaskListDocument

TASK_LIST_FILENAME = "task_list.yaml"


def default_task_list_path() -> Path:
    from unity_common import workspace_root

    return workspace_root() / TASK_LIST_FILENAME


def load_task_list(path: Path | str | None = None) -> TaskListDocument:
    """載入執行期 SSOT；檔案不存在時拋 ``FileNotFoundError``。"""
    p = Path(path) if path is not None else default_task_list_path()
    if not p.is_file():
        raise FileNotFoundError(f"找不到 task list: {p}")
    data = yaml.safe_load(p.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"task list 須為 YAML 映射: {p}")
    return TaskListDocument.from_dict(data)


def save_task_list(
    document: TaskListDocument,
    path: Path | str | None = None,
) -> Path:
    """原子寫入：先寫 ``.tmp`` 再 replace。"""
    p = Path(path) if path is not None else default_task_list_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    payload = yaml.safe_dump(
        document.to_dict(),
        allow_unicode=True,
        sort_keys=False,
        default_flow_style=False,
    )
    tmp.write_text(payload, encoding="utf-8")
    tmp.replace(p)
    return p


def inject_subtask(
    document: TaskListDocument,
    parent_id: str,
    subtask_spec: HarnessTask | dict,
    *,
    priority: int | None = None,
) -> HarnessTask:
    """注入執行期子任務（預設插在父任務後方）。"""
    parent_index = -1
    parent_task: HarnessTask | None = None
    for idx, task in enumerate(document.tasks):
        if task.id == parent_id:
            parent_index = idx
            parent_task = task
            break
    if parent_task is None:
        raise KeyError(f"找不到父任務: {parent_id}")

    if isinstance(subtask_spec, HarnessTask):
        task = subtask_spec
    elif isinstance(subtask_spec, dict):
        payload = dict(subtask_spec)
        payload.setdefault("status", "pending")
        task = HarnessTask.from_dict(payload)
    else:
        raise TypeError("subtask_spec 必須為 HarnessTask 或 dict")

    if any(t.id == task.id for t in document.tasks):
        raise ValueError(f"重複任務 id: {task.id}")

    task.injected_by = parent_id
    if priority is not None:
        task.priority = int(priority)
    elif task.priority == 10:
        task.priority = max(0, parent_task.priority - 1)

    document.tasks.insert(parent_index + 1, task)
    return task
