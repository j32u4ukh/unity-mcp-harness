"""core.pipeline.verification 單元測試。"""

import json

from core.pipeline.runner import classify_task_outcome
from core.pipeline.schema import HarnessTask, TaskTarget
from core.pipeline.verification import (
    VerificationResult,
    build_verification_prompt,
    evaluate_verification_payload,
    infer_game_object_name,
    infer_scene_path,
    parse_verification_json,
    should_skip_verification,
)
from tasks import TaskResult


def test_parse_verification_json_plain() -> None:
    payload = {"verified": True, "checks": [], "active_scene_path": "Assets/_Scenes/A.unity"}
    text = json.dumps(payload, ensure_ascii=False)
    assert parse_verification_json(text) == payload


def test_parse_verification_json_codeblock() -> None:
    inner = '{"verified": false, "failure_reason": "no Player"}'
    text = f"說明\n```json\n{inner}\n```"
    data = parse_verification_json(text)
    assert data is not None
    assert data["verified"] is False


def test_evaluate_verification_fails_when_check_failed() -> None:
    data = {
        "verified": True,
        "checks": [{"name": "Player", "passed": False, "detail": "not found"}],
    }
    result = evaluate_verification_payload(data)
    assert not result.passed


def test_infer_targets_from_prompt() -> None:
    task = HarnessTask(
        id="add_player_sprite",
        description="d",
        prompt='在場景 (Assets/_Scenes/Example2DScene.unity) 建立名為 "Player" 的物件',
    )
    assert infer_scene_path(task) == "Assets/_Scenes/Example2DScene.unity"
    assert infer_game_object_name(task) == "Player"


def test_should_skip_verification_flag() -> None:
    task = HarnessTask(id="t", description="d", expected={"skip_harness_verification": True})
    assert should_skip_verification(task)
    assert should_skip_verification(task, skip_verification=True)


def test_build_verification_prompt_includes_scene_and_go() -> None:
    task = HarnessTask(
        id="t",
        description="建立玩家",
        prompt='名為 "Player"',
        target=TaskTarget(game_object="Player", scene_path="Assets/_Scenes/Main.unity"),
    )
    prompt = build_verification_prompt(task, agent_reply_excerpt="done")
    assert "Main.unity" in prompt
    assert "Player" in prompt


def test_classify_task_outcome_requires_verification_pass() -> None:
    ok = TaskResult(id="a", title="A", success=True, reply="完成")
    assert classify_task_outcome(ok, skip_verification=True) == ("completed", "verified")

    passed = VerificationResult(passed=True, summary="ok")
    assert classify_task_outcome(ok, verification=passed) == ("completed", "verified")

    failed = VerificationResult(passed=False, summary="no Player")
    assert classify_task_outcome(ok, verification=failed) == ("failed", "failed")

    skip_reply = TaskResult(id="a", title="A", success=True, reply="Camera 已存在，跳過建立")
    assert classify_task_outcome(
        skip_reply, verification=passed, skip_verification=False
    ) == ("completed", "skipped_by_idempotent")
