"""Plan Normalize 單元測試（mock LLM，無 Unity）。"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import yaml

from core.pipeline.goals_writeback import write_back_build_goals
from core.pipeline.plan_normalize import (
    PlanNormalizeResponse,
    NormalizedTaskOut,
    build_normalize_user_prompt,
    normalize_plan,
    normalize_plan_passthrough,
    parse_normalize_response,
)
from core.pipeline.prepare import prepare_harness_queue
from core.pipeline.schema import NormalizedPlan, NormalizedTask
from tasks import BuildPlan, BuildTask


def _sample_plan(*, task_count: int = 2) -> BuildPlan:
    tasks = [
        BuildTask(
            id="coarse_scene",
            title="場景",
            prompt="建立場景",
            objective="建立 2D 場景",
        ),
        BuildTask(
            id="coarse_validate",
            title="驗證",
            prompt="驗證場景",
            objective="驗證",
        ),
    ]
    if task_count == 3:
        tasks.insert(
            1,
            BuildTask(
                id="coarse_sprite",
                title="精靈",
                prompt="建立方塊",
                objective="建立 sprite",
            ),
        )
    return BuildPlan(
        project="Test",
        goal="2D demo",
        system_context="2D only",
        definition_of_done=["scene exists"],
        tasks=tasks[:task_count],
    )


def test_passthrough_adds_harness_cot() -> None:
    plan = _sample_plan()
    normalized = normalize_plan_passthrough(plan)
    assert len(normalized.normalized_tasks) == 2
    assert "Phase 1" in normalized.normalized_tasks[0].prompt


def test_normalized_task_out_coerces_invalid_harness() -> None:
    task = NormalizedTaskOut.model_validate(
        {
            "id": "t1",
            "description": "d",
            "prompt": "p",
            "harness": "",
            "target": "not-an-object",
        }
    )
    assert task.harness is None
    assert task.target is None


def test_plan_normalize_response_rejects_empty_tasks() -> None:
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        PlanNormalizeResponse.model_validate(
            {"normalized_tasks": [], "plan_changelog": "empty"}
        )


def test_parse_json_response_with_fence() -> None:
    raw = """```json
{
  "normalized_tasks": [
    {
      "id": "a",
      "description": "d",
      "prompt": "do",
      "priority": 10,
      "harness": {"pre_read": "list"}
    }
  ],
  "plan_changelog": "split"
}
```"""
    plan = parse_normalize_response(raw)
    assert plan.normalized_tasks[0].harness.pre_read == "list"
    assert plan.plan_changelog == "split"


@patch("core.pipeline.plan_normalize.Chat")
def test_normalize_plan_structured_three_to_six(mock_chat_cls: MagicMock) -> None:
    plan = _sample_plan(task_count=3)
    six = [
        NormalizedTaskOut(
            id=f"task_{i}",
            description=f"d{i}",
            prompt=f"p{i} Phase 1 then Phase 3",
            priority=(i + 1) * 10,
            plan_source_id="coarse_scene" if i < 2 else "coarse_sprite",
        )
        for i in range(6)
    ]
    mock_session = MagicMock()
    mock_session.complete_structured.return_value = PlanNormalizeResponse(
        normalized_tasks=six,
        plan_changelog="3→6",
    )
    mock_chat_cls.stateless.return_value = mock_session

    normalized = normalize_plan(plan, model="local-chat")
    assert len(normalized.normalized_tasks) == 6
    assert normalized.plan_changelog == "3→6"
    mock_session.complete_structured.assert_called_once()
    assert mock_session.complete_structured.call_args.kwargs.get("mode") == "auto"


@patch("core.pipeline.plan_normalize.Chat")
def test_normalize_plan_falls_back_on_structured_validation_error(mock_chat_cls: MagicMock) -> None:
    from aicentral.core.errors import StructuredValidationError

    plan = _sample_plan()
    mock_session = MagicMock()
    mock_session.complete_structured.side_effect = StructuredValidationError(
        "bad schema",
        response_model=PlanNormalizeResponse,
        validation_detail="normalized_tasks.0: invalid",
    )
    mock_chat_cls.stateless.return_value = mock_session

    normalized = normalize_plan(plan, model="local-chat")
    assert len(normalized.normalized_tasks) == 2
    assert "passthrough" in normalized.plan_changelog


def test_build_normalize_user_prompt_includes_goals() -> None:
    plan = _sample_plan()
    text = build_normalize_user_prompt(plan)
    assert "coarse_scene" in text
    assert "2D only" in text


def test_write_back_goals_roundtrip(tmp_path: Path) -> None:
    goals = tmp_path / "build_goals.yaml"
    goals.write_text(
        yaml.safe_dump(
            {
                "project": "P",
                "goal": "g",
                "tasks": [{"id": "old", "title": "t", "prompt": "p"}],
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    normalized = NormalizedPlan(
        normalized_tasks=[
            NormalizedTask(id="new_task", description="d", prompt="p", priority=10)
        ],
        plan_changelog="test",
    )
    write_back_build_goals(normalized, goals, backup=True)
    data = yaml.safe_load(goals.read_text(encoding="utf-8"))
    assert data["tasks"][0]["id"] == "new_task"
    assert (tmp_path / "build_goals.yaml.bak").is_file()


def test_prepare_harness_skip_normalize_uses_passthrough(tmp_path: Path) -> None:
    plan = _sample_plan()
    task_path = tmp_path / "task_list.yaml"
    with patch("core.pipeline.prepare.resolve_build_plan", return_value=plan):
        with patch("core.pipeline.prepare.default_task_list_path", return_value=task_path):
            result = prepare_harness_queue(skip_plan_normalize=True, init_tasks=True)
    assert len(result.normalized.normalized_tasks) == 2
    assert result.created_task_list is True
    assert task_path.is_file()
