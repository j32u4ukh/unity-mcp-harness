"""core.pipeline.tool_adapter 單元測試。"""

from core.pipeline.schema import HarnessHints, HarnessTask
from core.pipeline.tool_adapter import (
    capture_post_read_snapshot,
    capture_pre_read_snapshot,
    plan_post_read,
    plan_pre_read,
)


def test_plan_pre_post_read_uses_harness_hints() -> None:
    task = HarnessTask(
        id="t1",
        description="d",
        prompt="p",
        harness=HarnessHints(pre_read="list resources", post_read="verify camera"),
    )
    pre = plan_pre_read(task)
    post = plan_post_read(task)
    assert "list resources" in pre.summary
    assert "verify camera" in post.summary


def test_capture_snapshots_record_operations() -> None:
    task = HarnessTask(
        id="t1",
        description="d",
        prompt="p",
    )
    capture_pre_read_snapshot(task)
    capture_post_read_snapshot(task)
    assert "read_plan" in task.pipeline_records.actual_before
    assert "verify_plan" in task.pipeline_records.actual_after
    assert [op.action for op in task.pipeline_records.operations_executed] == [
        "MCP_Read",
        "MCP_VerifyRead",
    ]
