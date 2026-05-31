"""core.pipeline.verify_hints 單元測試。"""

from core.pipeline.schema import HarnessHints, HarnessTask, TaskTarget
from core.pipeline.verify_hints import (
    VERIFY_READ_STANDARD,
    apply_verify_hints_to_normalized_tasks,
    build_default_verify_read,
    ensure_task_verify_hints,
    infer_game_object_name,
)
from core.pipeline.verification import build_verification_prompt


def test_infer_game_object_from_target() -> None:
    task = HarnessTask(
        id="t",
        description="d",
        prompt='名為 "Player"',
        target=TaskTarget(game_object="Ground", scene_path="Assets/Scenes/A.unity"),
    )
    assert infer_game_object_name(task) == "Ground"


def test_ensure_task_verify_hints_fills_harness() -> None:
    task = HarnessTask(
        id="create_ground",
        description="建立 Ground",
        prompt='Phase 1: 檢查 "Ground"',
        target=TaskTarget(game_object="Ground", scene_path="Assets/Scenes/Main.unity"),
        harness=HarnessHints(post_read="check scale"),
    )
    assert ensure_task_verify_hints(task)
    assert task.harness.verify_read
    assert VERIFY_READ_STANDARD.splitlines()[0] in task.harness.verify_read
    assert "Ground" in task.harness.verify_read
    assert not ensure_task_verify_hints(task)


def test_build_verification_prompt_uses_verify_read() -> None:
    task = HarnessTask(
        id="t",
        description="d",
        prompt="p",
        harness=HarnessHints(verify_read="自訂驗證：僅 1 次 find。"),
    )
    prompt = build_verification_prompt(task, agent_reply_excerpt="done")
    assert "自訂驗證：僅 1 次 find。" in prompt
    assert "Harness 驗證 MCP 預算" in prompt or "自訂驗證" in prompt


def test_idempotent_skip_uses_compact_budget() -> None:
    task = HarnessTask(
        id="t",
        description="d",
        prompt="p",
        harness=HarnessHints(verify_read=build_default_verify_read(
            HarnessTask(id="t", description="d", prompt='名為 "Ground"')
        )),
    )
    prompt = build_verification_prompt(
        task, agent_reply_excerpt="已存在，跳過", idempotent_skip=True
    )
    assert "冪等驗證" in prompt or "冪等" in prompt


def test_apply_verify_hints_adds_agent_read_line() -> None:
    task = HarnessTask(id="t", description="d", prompt="Phase 1 only")
    apply_verify_hints_to_normalized_tasks([task])
    assert "gameobject-find" in task.prompt
    assert task.harness.verify_read
