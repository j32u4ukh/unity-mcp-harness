"""bootstrap task_list 單元測試。"""

from core.pipeline.bootstrap import bootstrap_task_list
from core.pipeline.schema import HarnessTask, NormalizedPlan, NormalizedTask, PipelineRecords, TaskListDocument


def test_bootstrap_preserves_completed_on_replan() -> None:
    existing = TaskListDocument(
        project_name="P",
        tasks=[
            HarnessTask(
                id="done_task",
                description="done",
                status="completed",
                prompt="p",
                pipeline_records=PipelineRecords(actual_before={"x": 1}),
                verification="verified",
            )
        ],
    )
    normalized = NormalizedPlan(
        normalized_tasks=[
            NormalizedTask(id="done_task", description="done", prompt="new prompt", priority=10),
            NormalizedTask(id="new_task", description="new", prompt="n", priority=20),
        ],
        plan_revision=2,
    )
    doc = bootstrap_task_list(
        normalized,
        project_name="P",
        existing=existing,
        preserve_completed=True,
    )
    assert len(doc.tasks) == 2
    assert doc.tasks[0].status == "completed"
    assert doc.tasks[0].pipeline_records.actual_before == {"x": 1}
    assert doc.tasks[1].status == "pending"
