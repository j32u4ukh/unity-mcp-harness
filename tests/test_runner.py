"""core.pipeline.runner 單元測試。"""

from pathlib import Path
from unittest.mock import patch

from core.pipeline.runner import (
    HarnessTaskRunner,
    classify_task_outcome,
    parse_harness_injections,
    reply_indicates_idempotent_skip,
)
from core.pipeline.schema import HarnessTask, TaskListDocument
from core.pipeline.store import load_task_list
from core.pipeline.verification import VerificationResult
from tasks import TaskResult


def _mock_verification_pass(*_args, **_kwargs) -> VerificationResult:
    return VerificationResult(passed=True, summary="mock ok")


def test_reply_indicates_idempotent_skip() -> None:
    assert reply_indicates_idempotent_skip("Camera 已存在，跳過建立")
    assert not reply_indicates_idempotent_skip("已在場景建立 Cube。")


def test_classify_task_outcome() -> None:
    ok = TaskResult(id="a", title="A", success=True, reply="完成")
    assert classify_task_outcome(ok, skip_verification=True) == ("completed", "verified")
    vr = VerificationResult(passed=True, summary="ok")
    assert classify_task_outcome(ok, verification=vr) == ("completed", "verified")
    skip = TaskResult(id="a", title="A", success=True, reply="2D Light 已存在，跳過建立")
    assert classify_task_outcome(skip, verification=vr) == ("completed", "skipped_by_idempotent")
    fail = TaskResult(id="a", title="A", success=False, reply="", error="x")
    assert classify_task_outcome(fail) == ("failed", "failed")


@patch("core.pipeline.runner.run_task_verification", side_effect=_mock_verification_pass)
def test_harness_task_runner_persists_lifecycle(_mock_verify, tmp_path: Path) -> None:
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
    assert loaded.tasks[0].pipeline_records.actual_before["read_plan"]
    assert loaded.tasks[0].pipeline_records.operations_executed[0].action == "MCP_Read"

    result = TaskResult(id="t1", title="T", success=True, reply="場景已建立完成")
    runner.on_task_end("t1", result)
    loaded = load_task_list(path)
    task = loaded.tasks[0]
    assert task.status == "completed"
    assert task.verification == "verified"
    assert task.pipeline_records.actual_after["verify_plan"]
    assert len(task.pipeline_records.operations_executed) == 3
    assert [op.action for op in task.pipeline_records.operations_executed] == [
        "MCP_Read",
        "MCP_Execute",
        "MCP_VerifyRead",
    ]
    assert "harness_verification" in task.pipeline_records.actual_after


@patch("core.pipeline.runner.run_task_verification", side_effect=_mock_verification_pass)
def test_harness_task_runner_verification_fail_marks_failed(_mock_verify, tmp_path: Path) -> None:
    path = tmp_path / "task_list.yaml"
    doc = TaskListDocument(
        project_name="P",
        tasks=[HarnessTask(id="t1", description="d", prompt="p", status="pending")],
    )
    runner = HarnessTaskRunner(doc, path)

    def _fail(*_a, **_k):
        return VerificationResult(passed=False, summary="Player 不存在")

    with patch("core.pipeline.runner.run_task_verification", side_effect=_fail):
        runner.on_task_start("t1")
        runner.on_task_end(
            "t1",
            TaskResult(id="t1", title="T", success=True, reply="已建立 Player"),
        )
    loaded = load_task_list(path)
    task = loaded.tasks[0]
    assert task.status == "failed"
    assert task.verification == "failed"


@patch("core.pipeline.runner.run_task_verification", side_effect=_mock_verification_pass)
def test_harness_task_runner_failed_sets_verification_failed(_mock_verify, tmp_path: Path) -> None:
    path = tmp_path / "task_list.yaml"
    doc = TaskListDocument(
        project_name="P",
        tasks=[HarnessTask(id="t1", description="d", prompt="p", status="pending")],
    )
    runner = HarnessTaskRunner(doc, path)
    runner.on_task_start("t1")
    runner.on_task_end(
        "t1",
        TaskResult(id="t1", title="T", success=False, reply="", error="boom"),
    )
    loaded = load_task_list(path)
    task = loaded.tasks[0]
    assert task.status == "failed"
    assert task.verification == "failed"


@patch("core.pipeline.runner.run_task_verification", side_effect=_mock_verification_pass)
def test_harness_task_runner_idempotent_skip_marks_verification(_mock_verify, tmp_path: Path) -> None:
    path = tmp_path / "task_list.yaml"
    doc = TaskListDocument(
        project_name="P",
        tasks=[HarnessTask(id="t1", description="d", prompt="p", status="pending")],
    )
    runner = HarnessTaskRunner(doc, path)
    runner.on_task_start("t1")
    runner.on_task_end(
        "t1",
        TaskResult(id="t1", title="T", success=True, reply="2D Light 已存在，跳過建立"),
    )
    loaded = load_task_list(path)
    task = loaded.tasks[0]
    assert task.status == "completed"
    assert task.verification == "skipped_by_idempotent"


def test_parse_harness_injections_json_marker() -> None:
    reply = (
        'done [HARNESS_INJECT:{"id":"add_sprite_renderer","description":"補組件",'
        '"prompt":"add SpriteRenderer","priority":5}]'
    )
    specs = parse_harness_injections(reply)
    assert len(specs) == 1
    assert specs[0]["id"] == "add_sprite_renderer"
