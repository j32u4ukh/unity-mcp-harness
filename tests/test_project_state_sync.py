"""project_state SSOT 同步與摘要建構。"""

from __future__ import annotations

from pathlib import Path

from core.pipeline.schema import HarnessTask, TaskListDocument, TaskTarget
from core.project_state.delta import compute_task_delta
from core.project_state.index import load_index
from core.project_state.paths import default_project_state_root
from core.project_state.ssot import (
    CURRENT_SECTION,
    build_task_ssot_one_line,
    format_task_list_for_planning,
    sync_project_state_from_task_list,
)
from core.pipeline.plan_normalize import build_normalize_user_prompt
from core.scaffold.init_workspace import init_workspace
from tasks import BuildPlan, BuildTask, TaskResult


def _doc(*tasks: HarnessTask) -> TaskListDocument:
    return TaskListDocument(project_name="test", tasks=list(tasks))


def test_failed_optimistic_reply_not_in_index_summary(tmp_path: Path, monkeypatch) -> None:
    init_workspace(tmp_path)
    monkeypatch.setenv("UNITY_MCP_HOME", str(tmp_path))

    task = HarnessTask(
        id="add_sprite",
        description="加精靈",
        status="failed",
        verification="failed",
        priority=10,
        prompt="add sprite",
    )
    result = TaskResult(
        id="add_sprite",
        title="加精靈",
        success=False,
        reply="已成功掛載 SpriteRenderer 至 Player。",
        error="驗證未通過",
    )
    delta = compute_task_delta(task, result)
    summary = delta.index_entries[0].summary
    assert "failed" in summary
    assert "已成功掛載" not in summary


def test_verified_harness_summary_in_one_line() -> None:
    task = HarnessTask(
        id="add_ground",
        description="地面",
        status="completed",
        verification="verified",
        priority=1,
        prompt="ground",
    )
    task.pipeline_records.actual_after = {
        "harness_verification": {
            "verified": True,
            "summary": "Ground 存在且含 BoxCollider2D",
        }
    }
    line = build_task_ssot_one_line(task)
    assert "verified" in line
    assert "Ground" in line or "BoxCollider" in line


def test_sync_prunes_old_task_sections(tmp_path: Path, monkeypatch) -> None:
    init_workspace(tmp_path)
    monkeypatch.setenv("UNITY_MCP_HOME", str(tmp_path))
    root = default_project_state_root()
    task_md = root / "tasks" / "foo.md"
    task_md.parent.mkdir(parents=True, exist_ok=True)
    task_md.write_text(
        "# Foo\n\n## 任務 foo (2020-01-01)\n\n已成功完成一切。\n\n## 當前狀態\n\n舊內容\n",
        encoding="utf-8",
    )

    doc = _doc(
        HarnessTask(
            id="foo",
            description="foo task",
            status="failed",
            verification="failed",
            priority=5,
            prompt="p",
        )
    )
    sync_project_state_from_task_list(doc, root=root)

    text = task_md.read_text(encoding="utf-8")
    assert "## 任務 foo" not in text
    assert CURRENT_SECTION in text
    assert "failed" in text
    assert "已成功完成" not in text


def test_format_task_list_for_planning_marks_done() -> None:
    doc = _doc(
        HarnessTask(
            id="a",
            description="done",
            status="completed",
            verification="verified",
            priority=1,
            prompt="p",
        ),
        HarnessTask(
            id="b",
            description="retry",
            status="failed",
            verification="failed",
            priority=2,
            prompt="p",
        ),
    )
    text = format_task_list_for_planning(doc)
    assert "SSOT" in text
    assert "`a`" in text and "可省略" in text
    assert "`b`" in text and "須規劃" in text


def test_normalize_prompt_includes_ssot_block() -> None:
    doc = _doc(
        HarnessTask(
            id="add_player",
            description="玩家",
            status="failed",
            verification="failed",
            priority=1,
            prompt="p",
        ),
    )
    plan = BuildPlan(
        project="p",
        goal="g",
        tasks=[BuildTask(id="add_player", title="玩家", objective="o", prompt="p")],
    )
    prompt = build_normalize_user_prompt(plan, task_list_doc=doc)
    assert "執行隊列 SSOT" in prompt
    assert "add_player" in prompt
    assert "failed" in prompt


def test_sync_rebuilds_index(tmp_path: Path, monkeypatch) -> None:
    init_workspace(tmp_path)
    monkeypatch.setenv("UNITY_MCP_HOME", str(tmp_path))
    root = default_project_state_root()

    doc = _doc(
        HarnessTask(
            id="t1",
            description="one",
            status="completed",
            verification="verified",
            priority=1,
            prompt="p",
        ),
    )
    sync_project_state_from_task_list(doc, root=root)
    index = load_index(root)
    assert index is not None
    entry = index.find("tasks/t1")
    assert entry is not None
    assert "t1" in entry.summary
