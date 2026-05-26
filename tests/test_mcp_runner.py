"""harness.mcp_runner 單元測試。"""

from unittest.mock import MagicMock, patch

from harness.mcp_runner import UnityMCPRunner, create_unity_mcp_runner


@patch("harness.mcp_runner.Chat.with_mcp")
def test_create_unity_mcp_runner(mock_with_mcp: MagicMock) -> None:
    mock_chat = MagicMock()
    mock_with_mcp.return_value = mock_chat
    runner = create_unity_mcp_runner(["unity"], model="local-chat", max_tool_rounds=3)
    assert isinstance(runner, UnityMCPRunner)
    mock_with_mcp.assert_called_once()
    assert runner.ask("hi") == mock_chat.ask.return_value
    mock_chat.ask.assert_called_once_with("hi")
