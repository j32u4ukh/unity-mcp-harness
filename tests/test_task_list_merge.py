"""task_list 對話合併寫回。"""

from core.pipeline.schema import HarnessTask, PipelineRecords, TaskListDocument
from core.task_list_merge import merge_task_list_from_dialogue


def test_merge_preserves_completed_pipeline() -> None:
    doc = TaskListDocument(
        plan_revision=1,
        tasks=[
            HarnessTask(
                id="a",
                description="old",
                status="completed",
                prompt="old p",
                pipeline_records=PipelineRecords(actual_before={"x": 1}),
                verification="verified",
            ),
            HarnessTask(id="b", description="keep", status="pending", prompt="p"),
        ],
    )
    merge_task_list_from_dialogue(
        doc,
        {
            "tasks": [
                {"id": "a", "description": "new desc", "prompt": "new p", "priority": 5},
                {"id": "c", "description": "added", "prompt": "np", "priority": 20},
            ]
        },
    )
    assert len(doc.tasks) == 2
    assert doc.tasks[0].id == "a"
    assert doc.tasks[0].description == "new desc"
    assert doc.tasks[0].status == "completed"
    assert doc.tasks[0].pipeline_records.actual_before == {"x": 1}
    assert doc.tasks[1].id == "c"
    assert doc.tasks[1].status == "pending"
    assert doc.plan_revision == 2
