"""``task_list.yaml`` 讀寫（原子寫入）。"""

from __future__ import annotations

from pathlib import Path

import yaml

from core.pipeline.schema import TaskListDocument

TASK_LIST_FILENAME = "task_list.yaml"


def default_task_list_path() -> Path:
    from unity_common import project_root

    return project_root() / TASK_LIST_FILENAME


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
