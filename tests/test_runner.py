"""core.pipeline.runner 單元測試。"""

from pathlib import Path

from core.pipeline.runner import (
    HarnessTaskRunner,
    classify_task_outcome,
    reply_indicates_idempotent_skip,
)
from core.pipeline.schema import HarnessTask, TaskListDocument
from core.pipeline.store import load_task_list
from tasks import TaskResult


def test_reply_indicates_idempotent_skip() -> None:
    assert reply_indicates_idempotent_skip("Camera 已存在，跳過建立")
    assert not reply_indicates_idempotent_skip("已在場景建立 Cube。")


def test_classify_task_outcome() -> None:
    ok = TaskResult(id="a", title="A", success=True, reply="完成")
    assert classify_task_outcome(ok) == ("completed", "verified")
    skip = TaskResult(id="a", title="A", success=True, reply="2D Light 已存在，跳過建立")
    assert classify_task_outcome(skip) == ("completed", "skipped_by_idempotent")
    fail = TaskResult(id="a", title="A", success=False, reply="", error="x")
    assert classify_task_outcome(fail) == ("failed", "failed")


def test_harness_task_runner_persists_lifecycle(tmp_path: Path) -> None:
    path = tmp_path / "task_list.yaml"
    doc = TaskListDocument(
        project_name="P",
        tasks=[
            HarnessTask(id="t1", description="d", prompt="p", status="pending"),
        ],
    )
    runner = HarnessTaskRunner(doc, path)

    runner.on_task_start("t1")
    loaded = load_task_list(path)
    assert loaded.tasks[0].status == "in_progress"
    assert loaded.last_updated is not None

    result = TaskResult(id="t1", title="T", success=True, reply="場景已建立完成")
    runner.on_task_end("t1", result)
    loaded = load_task_list(path)
    task = loaded.tasks[0]
    assert task.status == "completed"
    assert task.verification == "verified"
    assert len(task.pipeline_records.operations_executed) == 1
    assert task.pipeline_records.operations_executed[0].action == "MCP_Execute"
