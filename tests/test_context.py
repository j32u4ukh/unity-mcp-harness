"""core.pipeline.context 單元測試。"""

from core.pipeline.context import format_harness_task_context, format_pipeline_records_summary
from core.pipeline.schema import HarnessHints, HarnessTask, OperationRecord, PipelineRecords


def test_format_pipeline_records_summary_empty() -> None:
    text = format_pipeline_records_summary(PipelineRecords())
    assert "actual_before" in text
    assert "（空）" in text
    assert "尚無" in text


def test_format_pipeline_records_with_ops() -> None:
    records = PipelineRecords(
        actual_before={"scene": "missing"},
        operations_executed=[
            OperationRecord(
                timestamp="2026-01-01T00:00:00Z",
                action="MCP_Read",
                tool="unity__Unity_ListResources",
            )
        ],
        actual_after={"scene": "ok"},
    )
    text = format_pipeline_records_summary(records)
    assert "missing" in text
    assert "MCP_Read" in text
    assert "ok" in text


def test_format_harness_task_context_includes_cot_and_resume() -> None:
    task = HarnessTask(
        id="t1",
        description="d",
        prompt="p",
        status="pending",
        harness=HarnessHints(pre_read="list scenes"),
        pipeline_records=PipelineRecords(actual_before={"x": 1}),
    )
    text = format_harness_task_context(task, resume=True)
    assert "Phase 1" in text
    assert "list scenes" in text
    assert "重啟提醒" in text
    assert '"x":1' in text or '"x": 1' in text
