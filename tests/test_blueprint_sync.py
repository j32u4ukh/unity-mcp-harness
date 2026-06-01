"""build_goals 與 task_list 漂移偵測。"""

from pathlib import Path
from unittest.mock import patch

import yaml

from core.pipeline.blueprint_sync import task_list_matches_blueprint
from core.pipeline.prepare import prepare_harness_queue
from core.pipeline.schema import HarnessTask, TaskListDocument
from tasks import BuildPlan, BuildTask


def _attack_plan() -> BuildPlan:
    return BuildPlan(
        project="P",
        goal="g",
        tasks=[
            BuildTask(id="1", title="T1", prompt="p1"),
            BuildTask(id="2", title="T2", prompt="p2"),
        ],
    )


def test_task_list_matches_blueprint_when_ids_align() -> None:
    plan = _attack_plan()
    doc = TaskListDocument(
        tasks=[
            HarnessTask(id="1", description="d", prompt="p", status="pending"),
            HarnessTask(id="2", description="d", prompt="p", status="completed"),
        ]
    )
    assert task_list_matches_blueprint(plan, doc)


def test_task_list_stale_when_blueprint_ids_missing() -> None:
    plan = _attack_plan()
    doc = TaskListDocument(
        tasks=[HarnessTask(id="a", description="old", prompt="p", status="completed")]
    )
    assert not task_list_matches_blueprint(plan, doc)


def test_prepare_rebootstraps_on_goals_drift(tmp_path: Path) -> None:
    task_path = tmp_path / "task_list.yaml"
    task_path.write_text(
        yaml.safe_dump(
            {
                "harness_version": 1,
                "source_plan": "build_goals.yaml",
                "plan_revision": 1,
                "tasks": [
                    {
                        "id": "a",
                        "description": "old",
                        "status": "completed",
                        "priority": 10,
                        "prompt": "p",
                    }
                ],
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    plan = _attack_plan()

    with patch("core.pipeline.prepare.resolve_build_plan", return_value=plan):
        with patch("core.pipeline.prepare.default_task_list_path", return_value=task_path):
            result = prepare_harness_queue(skip_plan_normalize=True)

    assert result.created_task_list is True
    assert {t.id for t in result.task_list.tasks} == {"1", "2"}
    assert all(t.status == "pending" for t in result.task_list.tasks)
    assert "不一致" in result.normalized.plan_changelog
