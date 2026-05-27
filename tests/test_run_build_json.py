"""run_build JSON 可觀測輸出測試。"""

from core.pipeline.schema import HarnessTask, PipelineRecords, TaskListDocument
from run_build import _results_to_json_payload
from tasks import TaskResult


def test_results_to_json_payload_includes_verification() -> None:
    results = [
        TaskResult(id="a", title="A", success=True, reply="ok"),
    ]
    task_list = TaskListDocument(
        tasks=[
            HarnessTask(
                id="a",
                description="d",
                prompt="p",
                status="completed",
                verification="verified",
                pipeline_records=PipelineRecords(),
            )
        ]
    )
    payload = _results_to_json_payload(results, task_list=task_list)
    assert payload[0]["id"] == "a"
    assert payload[0]["verification"] == "verified"
    assert payload[0]["status"] == "completed"
    assert payload[0]["operations_executed"] == 0
