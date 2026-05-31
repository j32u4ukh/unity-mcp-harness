"""core.pipeline.verify_hints 單元測試。"""

from core.pipeline.schema import HarnessHints, HarnessTask, TaskTarget
from core.pipeline.verify_hints import (
    VERIFY_READ_STANDARD,
    apply_verify_hints_to_normalized_tasks,
    build_default_verify_read,
    classify_script_task,
    ensure_task_verify_hints,
    infer_game_object_name,
    upgrade_script_task_verify_hints,
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


def test_script_file_task_uses_assets_find_verify_read() -> None:
    task = HarnessTask(
        id="ensure_scripts_folder_and_player_controller_script",
        description="確保腳本目錄與 PlayerController.cs 檔案",
        prompt="Phase 1: 檢查 Assets/Scripts/PlayerController.cs 是否存在。",
        harness=HarnessHints(
            verify_read="gameobject-find(name=Player, includeComponents=[PlayerController])"
        ),
    )
    assert classify_script_task(task) == "file"
    assert upgrade_script_task_verify_hints(task)
    assert "t:Script" in task.harness.verify_read
    assert "不驗證 GameObject 掛載" in task.harness.verify_read or "不驗證" in task.harness.verify_read
    assert task.expected.get("file_exists") == "Assets/Scripts/PlayerController.cs"


def test_script_mount_task_verify_read() -> None:
    task = HarnessTask(
        id="implement_player_controller_logic",
        description="實作移動並掛載",
        prompt="Phase 3: 驗證 Player 已附加 PlayerController 腳本。",
        harness=HarnessHints(verify_read="gameobject-find only"),
    )
    assert classify_script_task(task) == "mount"
    assert upgrade_script_task_verify_hints(task)
    assert "t:Script" in task.harness.verify_read
    assert "PlayerController" in task.harness.verify_read
