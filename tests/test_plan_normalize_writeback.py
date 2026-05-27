"""goals write-back 單元測試（phase 8）。"""

from pathlib import Path

import yaml

from core.pipeline.goals_writeback import write_back_task_list_goals
from core.pipeline.schema import HarnessHints, HarnessTask, PipelineRecords, TaskListDocument


def test_write_back_task_list_goals_only_writes_planning_fields(tmp_path: Path) -> None:
    goals = tmp_path / "build_goals.yaml"
    goals.write_text(
        yaml.safe_dump(
            {
                "project": "P",
                "goal": "G",
                "system_context": "C",
                "tasks": [{"id": "old", "title": "Old", "prompt": "old"}],
            },
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    task_list = TaskListDocument(
        plan_revision=7,
        tasks=[
            HarnessTask(
                id="a",
                description="desc-a",
                title="A",
                prompt="do-a",
                priority=10,
                harness=HarnessHints(pre_read="list", post_read="verify"),
                pipeline_records=PipelineRecords(
                    actual_before={"scene": "before"},
                    actual_after={"scene": "after"},
                ),
                verification="verified",
                status="completed",
            )
        ],
    )

    write_back_task_list_goals(task_list, goals)

    data = yaml.safe_load(goals.read_text(encoding="utf-8"))
    assert data["plan_revision"] == 7
    assert data["goal"] == "G"
    assert data["system_context"] == "C"
    assert len(data["tasks"]) == 1
    task = data["tasks"][0]
    assert task["id"] == "a"
    assert task["prompt"] == "do-a"
    assert "harness" in task
    assert "pipeline_records" not in task
    assert "verification" not in task
    assert "status" not in task
