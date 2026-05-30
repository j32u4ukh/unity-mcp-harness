"""prompt_supplements 單元測試。"""

from __future__ import annotations

import json
from pathlib import Path

from core.pipeline.prompt_supplements import (
    apply_clarification_answers,
    apply_prompt_supplements,
    enrich_normalized_plan,
    find_open_clarifications,
    load_prompt_supplements,
    match_supplements_for_task,
    run_interactive_clarifications,
)
from core.pipeline.schema import NormalizedPlan, NormalizedTask
from tasks import BuildPlan, BuildTask


def _sample_supplements_json() -> dict:
    return {
        "version": 1,
        "supplements": [
            {
                "id": "sprite_procedural_general",
                "match_keywords": ["sprite", "SpriteRenderer"],
                "match_task_id_substrings": ["sprite"],
                "prompt_block": "使用 Texture2D + Sprite.Create；禁止近似匹配。",
                "expected": {"forbid_approximate_asset_match": True},
            }
        ],
        "clarification_templates": [
            {
                "id": "sprite_geometry_unspecified",
                "question": "幾何形狀？",
                "when_keywords": ["sprite"],
                "when_task_id_substrings": ["sprite"],
                "unless_supplement_ids": [],
                "unless_task_keywords": ["方形", "square", "三角形", "triangle"],
            }
        ],
    }


def test_match_and_inject_general_sprite_supplement(tmp_path: Path) -> None:
    path = tmp_path / "prompt_supplements.json"
    path.write_text(json.dumps(_sample_supplements_json(), ensure_ascii=False), encoding="utf-8")
    doc = load_prompt_supplements(path)
    task = NormalizedTask(
        id="create_2d_sprite_object",
        description="建立 RedSquare2D sprite",
        prompt="建立 sprite",
        priority=40,
    )
    matched = match_supplements_for_task(task, doc)
    assert len(matched) == 1
    assert matched[0].id == "sprite_procedural_general"

    plan = NormalizedPlan(normalized_tasks=[task])
    injected = apply_prompt_supplements(plan, doc)
    assert injected == ["sprite_procedural_general"]
    assert "【規劃補充：sprite_procedural_general】" in task.prompt
    assert task.expected.get("forbid_approximate_asset_match") is True


def test_find_open_clarification_when_geometry_unspecified(tmp_path: Path) -> None:
    path = tmp_path / "prompt_supplements.json"
    path.write_text(json.dumps(_sample_supplements_json(), ensure_ascii=False), encoding="utf-8")
    doc = load_prompt_supplements(path)
    build_plan = BuildPlan(
        project="P",
        tasks=[
            BuildTask(
                id="create_generic_sprite",
                title="sprite",
                prompt="建立一個 sprite 物件",
                objective="sprite",
            )
        ],
    )
    normalized = NormalizedPlan(
        normalized_tasks=[
            NormalizedTask(
                id="create_generic_sprite",
                description="sprite",
                prompt="建立 sprite",
                priority=10,
            )
        ]
    )
    open_items = find_open_clarifications(build_plan, normalized, doc)
    assert len(open_items) == 1
    assert open_items[0][0].id == "sprite_geometry_unspecified"


def test_skip_clarification_when_shape_in_task(tmp_path: Path) -> None:
    path = tmp_path / "prompt_supplements.json"
    path.write_text(json.dumps(_sample_supplements_json(), ensure_ascii=False), encoding="utf-8")
    doc = load_prompt_supplements(path)
    normalized = NormalizedPlan(
        normalized_tasks=[
            NormalizedTask(
                id="create_2d_sprite_object",
                description="方形 sprite",
                prompt="建立方形 sprite",
                priority=10,
            )
        ]
    )
    build_plan = BuildPlan(project="P", tasks=[])
    open_items = find_open_clarifications(build_plan, normalized, doc)
    assert open_items == []


def test_interactive_clarification_persists_to_json(tmp_path: Path) -> None:
    path = tmp_path / "prompt_supplements.json"
    path.write_text(json.dumps(_sample_supplements_json(), ensure_ascii=False), encoding="utf-8")
    build_plan = BuildPlan(
        project="P",
        tasks=[
            BuildTask(
                id="create_generic_sprite",
                title="sprite",
                prompt="建立 sprite",
                objective="sprite",
            )
        ],
    )
    normalized = NormalizedPlan(
        normalized_tasks=[
            NormalizedTask(
                id="create_generic_sprite",
                description="sprite",
                prompt="建立 sprite",
                priority=10,
            )
        ]
    )
    doc = load_prompt_supplements(path)
    open_items = find_open_clarifications(build_plan, normalized, doc)
    answers = run_interactive_clarifications(
        open_items,
        input_fn=lambda _prompt: "使用 triangle 程序化生成",
    )
    apply_clarification_answers(normalized, answers, doc, persist=True, supplements_path=path)
    reloaded = load_prompt_supplements(path)
    user_entries = [s for s in reloaded.supplements if s.source == "plan_interactive"]
    assert user_entries
    assert "triangle" in user_entries[-1].prompt_block.lower()


def test_enrich_normalized_plan_changelog(tmp_path: Path) -> None:
    path = tmp_path / "prompt_supplements.json"
    path.write_text(json.dumps(_sample_supplements_json(), ensure_ascii=False), encoding="utf-8")
    build_plan = BuildPlan(project="P", tasks=[])
    normalized = NormalizedPlan(
        normalized_tasks=[
            NormalizedTask(
                id="create_2d_sprite_object",
                description="sprite 物件",
                prompt="建立",
                priority=10,
            )
        ],
        plan_changelog="base",
    )
    out = enrich_normalized_plan(
        build_plan,
        normalized,
        supplements_path=path,
        plan_interactive=False,
    )
    assert "sprite_procedural_general" in out.plan_changelog
