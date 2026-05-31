"""Unity MCP 工具錯誤過濾測試。"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from core.mcp.filtered_orchestrator import run_tool_calls_with_harness_filter
from core.mcp.tool_error_filter import (
    try_downgrade_tool_error,
    format_fatal_tool_content,
    is_non_recoverable_mcp_error,
)


def test_downgrade_not_found_gameobject_by_name() -> None:
    err = "Exception: Not found GameObject with name 'Player'"
    content, action = try_downgrade_tool_error(
        err,
        tool_name="unity__game-object-find",
        arguments={"name": "Player"},
    )
    assert action == "route_to_create"
    assert content is not None
    payload = json.loads(content)
    assert payload["status"] == "expected_not_found"
    assert payload["target_object"] == "Player"
    assert payload["harness_next_action"] == "route_to_create"


def test_fatal_error_wrapped_not_raised() -> None:
    content, action = format_fatal_tool_content(
        "NullReferenceException: something broke",
        tool_name="unity__script-execute",
    )
    assert action == "route_to_self_correction"
    payload = json.loads(content)
    assert payload["status"] == "system_fatal_error"


def test_connection_refused_not_downgraded() -> None:
    assert is_non_recoverable_mcp_error("Connection refused")
    content, action = try_downgrade_tool_error(
        "Connection refused",
        tool_name="x",
        arguments={},
    )
    assert content is None and action is None


def test_run_tool_calls_filter_catches_exception() -> None:
    mgr = MagicMock()
    mgr.call_tool.side_effect = Exception("Not found GameObject with name 'Player'")
    tool_calls = [
        {
            "id": "tc1",
            "function": {
                "name": "unity__game-object-find",
                "arguments": json.dumps({"name": "Player"}),
            },
        }
    ]
    messages = run_tool_calls_with_harness_filter(
        tool_calls,
        mgr=mgr,
        name_to_server={"unity__game-object-find": "unity"},
    )
    assert len(messages) == 1
    payload = json.loads(messages[0]["content"])
    assert payload["status"] == "expected_not_found"


def test_run_tool_calls_re_raises_connection_error() -> None:
    mgr = MagicMock()
    mgr.call_tool.side_effect = Exception("Connection refused")
    tool_calls = [
        {
            "id": "tc1",
            "function": {"name": "t", "arguments": "{}"},
        }
    ]
    with pytest.raises(Exception, match="Connection refused"):
        run_tool_calls_with_harness_filter(
            tool_calls,
            mgr=mgr,
            name_to_server={"t": "unity"},
        )


def test_run_tool_calls_fatal_becomes_tool_message() -> None:
    mgr = MagicMock()
    mgr.call_tool.side_effect = Exception("NullReferenceException: bad")
    tool_calls = [
        {
            "id": "tc1",
            "function": {"name": "unity__x", "arguments": "{}"},
        }
    ]
    messages = run_tool_calls_with_harness_filter(
        tool_calls,
        mgr=mgr,
        name_to_server={"unity__x": "unity"},
    )
    payload = json.loads(messages[0]["content"])
    assert payload["status"] == "system_fatal_error"
