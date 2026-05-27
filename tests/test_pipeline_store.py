"""core.pipeline schema / store 單元測試。"""

from pathlib import Path

import pytest
import yaml

from core.pipeline.schema import (
    HarnessTask,
    NormalizedPlan,
    NormalizedTask,
    PipelineRecords,
    TaskListDocument,
)
from core.pipeline.store import inject_subtask, load_task_list, save_task_list


def test_normalized_plan_roundtrip() -> None:
    plan = NormalizedPlan(
        normalized_tasks=[
            NormalizedTask(
                id="a",
                description="task a",
                prompt="do a",
                plan_source_id="coarse_a",
            )
        ],
        plan_changelog="split coarse_a",
        plan_revision=2,
    )
    restored = NormalizedPlan.from_dict(plan.to_dict())
    assert restored.plan_revision == 2
    assert len(restored.normalized_tasks) == 1
    assert restored.normalized_tasks[0].plan_source_id == "coarse_a"


def test_harness_task_from_normalized() -> None:
    norm = NormalizedTask(id="x", description="d", prompt="p", priority=5)
    task = HarnessTask.from_normalized(norm)
    assert task.status == "pending"
    assert task.verification == "pending"
    assert task.priority == 5


def test_task_list_save_load_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "task_list.yaml"
    doc = TaskListDocument(
        project_name="TestProj",
        plan_revision=1,
        tasks=[
            HarnessTask(
                id="create_2d_scene",
                description="scene",
                status="in_progress",
                prompt="read then write",
                pipeline_records=PipelineRecords(
                    actual_before={"scene": "missing"},
                    actual_after={},
                ),
                verification="pending",
            )
        ],
    )
    save_task_list(doc, path)
    loaded = load_task_list(path)
    assert loaded.project_name == "TestProj"
    assert len(loaded.tasks) == 1
    assert loaded.tasks[0].status == "in_progress"
    assert loaded.tasks[0].pipeline_records.actual_before == {"scene": "missing"}


def test_load_example_yaml() -> None:
    example = Path(__file__).resolve().parent.parent / "task_list.example.yaml"
    if not example.is_file():
        pytest.skip("task_list.example.yaml not present")
    data = yaml.safe_load(example.read_text(encoding="utf-8"))
    doc = TaskListDocument.from_dict(data)
    assert len(doc.tasks) == 6
    ids = {t.id for t in doc.tasks}
    assert "validate_2d_scene" in ids


def test_inject_subtask_inserts_after_parent() -> None:
    doc = TaskListDocument(
        tasks=[
            HarnessTask(id="parent", description="p", prompt="p", priority=20),
            HarnessTask(id="later", description="l", prompt="l", priority=20),
        ]
    )
    sub = inject_subtask(
        doc,
        "parent",
        {
            "id": "child",
            "description": "c",
            "prompt": "do child",
        },
    )
    assert sub.injected_by == "parent"
    assert [t.id for t in doc.tasks] == ["parent", "child", "later"]
