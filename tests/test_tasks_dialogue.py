"""--tasks modify 對話。"""

import yaml

import pytest

from core.cli_extended import run_tasks_modify
from core.tasks_dialogue import TasksModifyState


def test_run_tasks_modify_no_mcp_quit(tmp_path, monkeypatch) -> None:
    task_path = tmp_path / "task_list.yaml"
    task_path.write_text(
        yaml.safe_dump(
            {
                "harness_version": 1,
                "source_plan": "build_goals.yaml",
                "plan_revision": 1,
                "tasks": [
                    {
                        "id": "t1",
                        "description": "d",
                        "status": "pending",
                        "priority": 10,
                        "prompt": "p",
                    }
                ],
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr("core.cli_extended.default_task_list_path", lambda: task_path)
    monkeypatch.setattr("builtins.input", lambda _prompt="": "/quit")
    monkeypatch.setattr("core.cli_extended.require_aicentral_config", lambda **_: None)

    assert (
        run_tasks_modify(
            model=None,
            aicentral_config=None,
            secret=None,
            no_mcp=True,
        )
        == 0
    )
