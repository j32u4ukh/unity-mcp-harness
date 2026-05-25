"""tasks 模組測試。"""

from pathlib import Path

import pytest

from tasks import (
    VALIDATE_TASK_ID,
    BuildPlan,
    BuildTask,
    TaskResult,
    format_execution_strategy,
    format_task_prompt,
    load_build_plan,
)


def test_load_build_plan_yaml(tmp_path: Path) -> None:
    p = tmp_path / "goals.yaml"
    p.write_text(
        """
project: TestGame
mcp_servers: [unity]
tasks:
  - id: t1
    title: 任務一
    prompt: 做某件事
""",
        encoding="utf-8",
    )
    plan = load_build_plan(p)
    assert plan.project == "TestGame"
    assert len(plan.enabled_tasks()) == 1
    assert plan.enabled_tasks()[0].id == "t1"


def test_load_build_plan_extended_fields(tmp_path: Path) -> None:
    p = tmp_path / "goals.yaml"
    p.write_text(
        """
project: Demo
goal: |
  建立範例場景
definition_of_done:
  - Cube 為紅色
  - Scene 已保存
execution_strategy:
  mode: goal_driven
  priorities:
    - correctness
system_context: 使用 MCP 工具
tasks:
  - id: create_cube
    title: Cube
    objective: 建立方塊
    prompt: 建立 Cube
  - id: validate_scene
    title: 驗證
    prompt: 檢查場景
""",
        encoding="utf-8",
    )
    plan = load_build_plan(p)
    assert plan.goal.startswith("建立範例")
    assert plan.definition_of_done == ["Cube 為紅色", "Scene 已保存"]
    assert plan.execution_strategy["mode"] == "goal_driven"
    assert plan.tasks[0].objective == "建立方塊"


def test_format_execution_strategy() -> None:
    text = format_execution_strategy(
        {
            "mode": "goal_driven",
            "priorities": ["correctness"],
            "behavior": ["inspect_before_modify"],
        }
    )
    assert "goal_driven" in text
    assert "correctness" in text
    assert "inspect_before_modify" in text


def test_format_task_prompt_includes_goal_and_objective() -> None:
    plan = BuildPlan(
        project="P",
        goal="總目標",
        definition_of_done=["項目 A"],
        execution_strategy={"mode": "goal_driven"},
        system_context="憲法",
    )
    task = BuildTask(id="create_cube", title="Cube", objective="放一個方塊", prompt="建立 Cube")
    text = format_task_prompt(task, plan=plan, prior_results=[])
    assert "總目標" in text
    assert "goal_driven" in text
    assert "項目 A" in text
    assert "憲法" in text
    assert "放一個方塊" in text
    assert "建立 Cube" in text


def test_format_task_prompt_validate_includes_dod_checklist() -> None:
    plan = BuildPlan(
        definition_of_done=["Camera 存在", "Cube 為紅色"],
    )
    task = BuildTask(id=VALIDATE_TASK_ID, title="驗證", prompt="檢查")
    text = format_task_prompt(task, plan=plan, prior_results=[])
    assert "逐項" in text
    assert "Camera 存在" in text
    assert "Cube 為紅色" in text


def test_format_task_prompt_includes_prior() -> None:
    plan = BuildPlan(project="P")
    task = BuildTask(id="t2", title="二", prompt="繼續")
    prior = [
        TaskResult(id="t1", title="一", success=True, reply="已建立 Cube"),
    ]
    text = format_task_prompt(task, plan=plan, prior_results=prior)
    assert "t1" in text
    assert "已建立 Cube" in text
    assert "t2" in text
