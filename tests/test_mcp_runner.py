"""harness.mcp_runner 單元測試。"""

from unittest.mock import MagicMock, patch

from harness.mcp_runner import UnityMCPRunner, create_unity_mcp_runner


@patch("unity_common.resolve_unity_llm_model", side_effect=lambda m: m or "gemini-flash")
@patch("harness.mcp_runner.Chat.with_mcp")
def test_create_unity_mcp_runner(mock_with_mcp: MagicMock, _mock_model: MagicMock) -> None:
    mock_chat = MagicMock()
    mock_with_mcp.return_value = mock_chat
    runner = create_unity_mcp_runner(
        ["unity"],
        model="local-chat",
        system="explore",
        max_tool_rounds=3,
    )
    assert isinstance(runner, UnityMCPRunner)
    mock_with_mcp.assert_called_once()
    kwargs = mock_with_mcp.call_args.kwargs
    assert kwargs["system"] == "explore"
    assert kwargs["max_tool_rounds"] == 3
    assert runner.ask("hi") == mock_chat.ask.return_value
    mock_chat.ask.assert_called_once_with("hi")
