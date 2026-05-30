"""project_state 文件樹：init、更新、prompt 摘要。"""

from __future__ import annotations

from pathlib import Path

from core.pipeline.schema import HarnessTask, TaskTarget
from core.project_state.context import (
    format_project_state_for_planning,
    format_project_state_for_task,
)
from core.project_state.session import begin_session, end_session, get_active_session
from core.project_state.update import record_task_completion
from core.project_state.index import load_index
from core.project_state.paths import default_project_state_root
from core.scaffold.init_workspace import init_workspace
from tasks import TaskResult


def test_init_creates_project_state_tree(tmp_path: Path) -> None:
    report = init_workspace(tmp_path)
    assert report.ok
    ps = tmp_path / "project_state"
    assert (ps / "_index.yaml").is_file()
    assert (ps / "scenes" / "_overview.md").is_file()
    assert (ps / "tasks").is_dir()


def test_record_task_completion_updates_files(
    tmp_path: Path, monkeypatch
) -> None:
    init_workspace(tmp_path)
    monkeypatch.setenv("UNITY_MCP_HOME", str(tmp_path))

    task = HarnessTask(
        id="inspect_scene",
        description="檢視場景",
        status="in_progress",
        priority=10,
        prompt="list hierarchy",
        target=TaskTarget(scene_path="Assets/Scenes/Demo.unity"),
    )
    result = TaskResult(
        id="inspect_scene",
        title="檢視場景",
        success=True,
        reply="場景 Demo，含 Ground 與 Player。",
    )
    record_task_completion(task, result)

    root = default_project_state_root()
    assert (root / "tasks" / "inspect_scene.md").is_file()
    assert (root / "changelog.md").read_text(encoding="utf-8").find("inspect_scene") >= 0

    index = load_index(root)
    assert index is not None
    entry = index.find("tasks/inspect_scene")
    assert entry is not None
    assert "Ground" in entry.summary or "Demo" in entry.summary


def test_format_project_state_for_task(tmp_path: Path, monkeypatch) -> None:
    init_workspace(tmp_path)
    monkeypatch.setenv("UNITY_MCP_HOME", str(tmp_path))

    task = HarnessTask(
        id="add_light",
        description="加光",
        status="pending",
        priority=40,
        prompt="add light",
    )
    record_task_completion(
        task,
        TaskResult(id="add_light", title="加光", success=True, reply="已加 Directional Light"),
    )

    text = format_project_state_for_task(task)
    assert "project_state" in text or "累積備忘" in text
    assert "add_light" in text or "Directional" in text


def test_format_project_state_for_planning_empty_without_init(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("UNITY_MCP_HOME", str(tmp_path))
    assert format_project_state_for_planning() == ""


def test_session_buffers_until_flush(tmp_path: Path, monkeypatch) -> None:
    init_workspace(tmp_path)
    monkeypatch.setenv("UNITY_MCP_HOME", str(tmp_path))
    root = default_project_state_root()
    changelog_before = (root / "changelog.md").read_text(encoding="utf-8")

    begin_session()
    try:
        for tid, reply in (("task_a", "alpha"), ("task_b", "beta")):
            record_task_completion(
                HarnessTask(
                    id=tid,
                    description=tid,
                    status="completed",
                    priority=10,
                    prompt="p",
                ),
                TaskResult(id=tid, title=tid, success=True, reply=reply),
            )
        assert get_active_session() is not None
        assert get_active_session().dirty
        assert "task_a" not in (root / "changelog.md").read_text(encoding="utf-8")
    finally:
        end_session(flush=True)

    changelog_after = (root / "changelog.md").read_text(encoding="utf-8")
    assert changelog_after != changelog_before
    assert "task_a" in changelog_after
    assert "task_b" in changelog_after
    assert (root / "tasks" / "task_a.md").is_file()


def test_context_sees_in_memory_before_flush(tmp_path: Path, monkeypatch) -> None:
    init_workspace(tmp_path)
    monkeypatch.setenv("UNITY_MCP_HOME", str(tmp_path))

    task = HarnessTask(
        id="add_player",
        description="玩家",
        status="pending",
        priority=30,
        prompt="add player",
    )
    begin_session()
    try:
        record_task_completion(
            task,
            TaskResult(id="add_player", title="玩家", success=True, reply="已建立 Player Cube"),
        )
        text = format_project_state_for_task(task)
        assert "Player" in text or "add_player" in text
        assert not (default_project_state_root() / "tasks" / "add_player.md").is_file()
    finally:
        end_session(flush=True)

    assert (default_project_state_root() / "tasks" / "add_player.md").is_file()
