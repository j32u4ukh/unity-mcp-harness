"""執行期記憶體狀態樹；整輪建構結束或中斷時一次 flush 至 project_state/。"""

from __future__ import annotations

import logging
from pathlib import Path

from core.pipeline.schema import HarnessTask
from core.project_state.delta import MarkdownAppend, TaskStateDelta, compute_task_delta
from core.project_state.index import StateIndex, load_index, save_index
from core.project_state.paths import CHANGELOG_FILENAME, default_project_state_root
from tasks import TaskResult

_logger = logging.getLogger(__name__)

_active_session: ProjectStateSession | None = None


class ProjectStateSession:
    """多任務執行期間在記憶體維護 project_state，減少每任務磁碟 IO。"""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.index: StateIndex = StateIndex(
            version=1,
            description="Unity 專案狀態索引（與 task_list.yaml 搭配）",
            entries=[],
        )
        self.changelog_pending: list[str] = []
        self.markdown_pending: dict[str, list[MarkdownAppend]] = {}
        self.dirty = False

    def load(self) -> None:
        loaded = load_index(self.root)
        if loaded is not None:
            self.index = loaded

    def record(self, task: HarnessTask, result: TaskResult) -> None:
        delta = compute_task_delta(task, result)
        self._apply_delta(delta)
        self.dirty = True

    def _apply_delta(self, delta: TaskStateDelta) -> None:
        self.changelog_pending.append(delta.changelog_line)
        for entry in delta.index_entries:
            self.index.upsert(entry)
        for append in delta.markdown_appends:
            self.markdown_pending.setdefault(append.rel_path, []).append(append)

    def markdown_excerpt(self, rel_path: str, *, max_chars: int) -> str:
        """磁碟既有內容 + 本 session 待寫入區塊的尾端摘要。"""
        path = self.root / rel_path
        base = ""
        if path.is_file():
            base = path.read_text(encoding="utf-8")
        pending_parts: list[str] = []
        for append in self.markdown_pending.get(rel_path, []):
            if append.full_replace_content is not None:
                pending_parts = [append.full_replace_content]
            else:
                pending_parts.append(append.block)
        text = (base + "".join(pending_parts)).strip()
        if pending_parts and self.markdown_pending.get(rel_path):
            last = self.markdown_pending[rel_path][-1]
            if last.full_replace_content is not None:
                text = last.full_replace_content.strip()
        if not text:
            return ""
        if len(text) <= max_chars:
            return text
        return text[-max_chars:].lstrip()

    def flush(self) -> None:
        if not self.dirty:
            return
        try:
            self._flush_changelog()
            self._flush_markdown()
            save_index(self.index, self.root)
            self.changelog_pending.clear()
            self.markdown_pending.clear()
            self.dirty = False
        except OSError as exc:
            _logger.warning("project_state flush 失敗: %s", exc)

    def _flush_changelog(self) -> None:
        path = self.root / CHANGELOG_FILENAME
        if path.is_file():
            content = path.read_text(encoding="utf-8")
            if not content.endswith("\n"):
                content += "\n"
        else:
            content = "# 變更流水帳\n\n"
        if self.changelog_pending:
            content += "".join(self.changelog_pending)
            path.write_text(content, encoding="utf-8")

    def _flush_markdown(self) -> None:
        for rel, appends in self.markdown_pending.items():
            if not appends:
                continue
            path = self.root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            last = appends[-1]
            if last.full_replace_content is not None:
                path.write_text(last.full_replace_content, encoding="utf-8")
            elif path.is_file():
                path.write_text(
                    path.read_text(encoding="utf-8") + "".join(a.block for a in appends),
                    encoding="utf-8",
                )
            else:
                title = path.stem.replace("_", " ").title()
                content = (
                    f"# {title}\n\n"
                    "> 由 Harness 任務完成後增量更新；非 ground truth。\n"
                    + "".join(a.block for a in appends)
                )
                path.write_text(content, encoding="utf-8")


def get_active_session() -> ProjectStateSession | None:
    return _active_session


def begin_session(root: Path | None = None) -> ProjectStateSession | None:
    """開始建構執行 session；載入既有 _index.yaml 至記憶體。"""
    global _active_session
    base = (root or default_project_state_root()).resolve()
    if not base.is_dir():
        return None
    session = ProjectStateSession(base)
    session.load()
    _active_session = session
    return session


def end_session(*, flush: bool = True) -> None:
    """結束 session；預設將記憶體狀態樹寫回 project_state/。"""
    global _active_session
    session = _active_session
    _active_session = None
    if session is None:
        return
    if flush:
        session.flush()


def record_in_session(task: HarnessTask, result: TaskResult) -> bool:
    """若 session 作用中則寫入記憶體；回傳是否已處理。"""
    session = get_active_session()
    if session is None:
        return False
    session.record(task, result)
    return True
