"""任務完成後更新 project_state（立即落盤或經 session 延遲 flush）。"""

from __future__ import annotations

import logging
from pathlib import Path

from core.pipeline.schema import HarnessTask
from core.project_state.delta import TaskStateDelta, compute_task_delta
from core.project_state.index import load_index, save_index
from core.project_state.paths import CHANGELOG_FILENAME, default_project_state_root
from tasks import TaskResult

_logger = logging.getLogger(__name__)


def _flush_delta_to_disk(root: Path, delta: TaskStateDelta) -> None:
    """單次任務立即落盤（無 session 時使用）。"""
    path = root / CHANGELOG_FILENAME
    if path.is_file():
        content = path.read_text(encoding="utf-8")
        if not content.endswith("\n"):
            content += "\n"
    else:
        content = "# 變更流水帳\n\n"
    content += delta.changelog_line
    path.write_text(content, encoding="utf-8")

    index = load_index(root)
    if index is None:
        from core.project_state.index import StateIndex

        index = StateIndex(
            version=1,
            description="Unity 專案狀態索引（與 task_list.yaml 搭配）",
            entries=[],
        )
    for entry in delta.index_entries:
        index.upsert(entry)

    for append in delta.markdown_appends:
        mpath = root / append.rel_path
        mpath.parent.mkdir(parents=True, exist_ok=True)
        if append.full_replace_content is not None:
            mpath.write_text(append.full_replace_content, encoding="utf-8")
        elif mpath.is_file():
            mpath.write_text(mpath.read_text(encoding="utf-8") + append.block, encoding="utf-8")
        else:
            title = append.create_title or mpath.stem.replace("_", " ").title()
            content = (
                f"# {title}\n\n"
                "> 由 Harness 任務完成後增量更新；非 ground truth。\n"
                + append.block
            )
            mpath.write_text(content, encoding="utf-8")

    save_index(index, root)


def record_task_completion(task: HarnessTask, result: TaskResult) -> None:
    """
    任務結束後更新 project_state。

    - 建構執行 session 作用中：僅更新記憶體，由 ``end_session()`` flush。
    - 否則：立即寫入磁碟（單次呼叫 / 測試）。
    """
    root = default_project_state_root()
    if not root.is_dir():
        return

    from core.project_state.session import record_in_session

    if record_in_session(task, result):
        return

    try:
        delta = compute_task_delta(task, result)
        _flush_delta_to_disk(root, delta)
    except OSError as exc:
        _logger.warning("project_state 更新失敗: %s", exc)
