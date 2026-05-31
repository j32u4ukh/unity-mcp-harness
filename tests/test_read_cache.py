"""MCP 唯讀快取（單一 agent loop）測試。"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

from core.mcp.filtered_orchestrator import run_tool_calls_with_harness_filter
from core.mcp.read_cache import (
    McpReadCache,
    build_lookup_key,
    reset_read_cache,
    try_cache_read,
)


def test_build_lookup_key_component_requires_instance_id() -> None:
    assert (
        build_lookup_key(
            "unity__gameobject-component-get",
            {
                "gameObjectRef": {"name": "Ground"},
                "componentRef": {},
            },
        )
        is None
    )
    key = build_lookup_key(
        "unity__gameobject-component-get",
        {
            "gameObjectRef": {"name": "Ground"},
            "componentRef": {"instanceID": 66114},
        },
    )
    assert key is not None
    assert key.secondary == "comp:66114"


def test_cache_hit_skips_second_call() -> None:
    reset_read_cache()
    mgr = MagicMock()
    mgr.call_tool.return_value = {"content": [{"type": "text", "text": '{"ok": true}'}]}

    tool_calls = [
        {
            "id": "tc1",
            "function": {
                "name": "unity__object-get-data",
                "arguments": json.dumps({"objectRef": {"instanceID": 66114}}),
            },
        },
        {
            "id": "tc2",
            "function": {
                "name": "unity__object-get-data",
                "arguments": json.dumps({"objectRef": {"instanceID": 66114}}),
            },
        },
    ]
    messages = run_tool_calls_with_harness_filter(
        tool_calls,
        mgr=mgr,
        name_to_server={"unity__object-get-data": "unity"},
    )
    assert mgr.call_tool.call_count == 1
    assert len(messages) == 2
    hit = json.loads(messages[1]["content"])
    assert hit["harness_cache_hit"] is True


def test_write_tool_clears_cache() -> None:
    cache = reset_read_cache()
    cache.store(
        "unity__object-get-data",
        {"objectRef": {"instanceID": 1}},
        '{"data": 1}',
    )
    assert cache.lookup("unity__object-get-data", {"objectRef": {"instanceID": 1}})

    from core.mcp.read_cache import on_write_tool

    on_write_tool("unity__gameobject-create", {"name": "Player"})
    assert not cache.entries
    assert try_cache_read(
        "unity__object-get-data",
        {"objectRef": {"instanceID": 1}},
    ) is None


def test_detail_covers_shallow_component_get() -> None:
    cache = McpReadCache()
    cache.store(
        "unity__gameobject-component-get",
        {
            "gameObjectRef": {"name": "Ground"},
            "componentRef": {"instanceID": 66114},
            "includeProperties": True,
            "includeFields": True,
        },
        '{"sprite": "x"}',
    )
    hit = cache.lookup(
        "unity__gameobject-component-get",
        {
            "gameObjectRef": {"name": "Ground"},
            "componentRef": {"instanceID": 66114},
        },
    )
    assert hit is not None
