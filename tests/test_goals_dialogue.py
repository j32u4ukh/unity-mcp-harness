"""goals init/modify 對話：里程碑邊界與 system 規則。"""

from core.goals_dialogue import (
    GOALS_INIT_SYSTEM,
    GOALS_MODIFY_SYSTEM,
    GoalsDialogueState,
    _ask_with_boundary,
)


def test_milestone_pattern_and_first_message() -> None:
    state = GoalsDialogueState()
    assert state.note_milestone_from_user("里程碑：完成 2D 攻擊點擊整合")
    assert state.milestone is not None
    assert "攻擊" in state.boundary_prefix()


def test_boundary_prefix_without_milestone() -> None:
    state = GoalsDialogueState()
    assert "尚未固定里程碑" in state.boundary_prefix()


def test_init_system_convergence_and_mcp() -> None:
    assert "收斂" in GOALS_INIT_SYSTEM or "里程碑" in GOALS_INIT_SYSTEM
    assert "禁止" in GOALS_INIT_SYSTEM and "擴散" in GOALS_INIT_SYSTEM
    assert "assets-find" in GOALS_INIT_SYSTEM
    assert "MCP" in GOALS_INIT_SYSTEM


def test_modify_system_convergence() -> None:
    assert "里程碑" in GOALS_MODIFY_SYSTEM or "收斂" in GOALS_MODIFY_SYSTEM
    assert "唯讀" in GOALS_MODIFY_SYSTEM


def test_ask_with_boundary_mcp_command() -> None:
    class _FakeChat:
        last_prompt = ""

        def ask(self, prompt: str) -> str:
            self.last_prompt = prompt
            return "ok"

    chat = _FakeChat()
    state = GoalsDialogueState(milestone="測試里程碑")
    _ask_with_boundary(chat, state, "/mcp 列出 Assets/Scripts/Attack 下腳本")
    assert "測試里程碑" in chat.last_prompt
    assert "MCP 查詢" in chat.last_prompt
    assert "Assets/Scripts/Attack" in chat.last_prompt
