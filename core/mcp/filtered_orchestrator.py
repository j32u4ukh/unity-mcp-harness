"""Harness 版 MCP run_tool_calls：攔截 Unity 預期錯誤，不震碎 tool loop。"""

from __future__ import annotations

import json
from typing import Any

from aicentral.mcp.manager import MCPError
from aicentral.mcp.orchestrator import serialize_tool_result

from core.mcp.read_cache import (
    on_write_tool,
    record_read_result,
    try_cache_read,
)
from core.mcp.tool_error_filter import (
    extract_error_text_from_tool_result,
    format_fatal_tool_content,
    is_non_recoverable_mcp_error,
    try_downgrade_tool_error,
)


def run_tool_calls_with_harness_filter(
    tool_calls: list[dict[str, Any]],
    *,
    mgr: Any,
    name_to_server: dict[str, str],
) -> list[dict[str, Any]]:
    """
    等同 aicentral ``run_tool_calls``，但將「找不到 GameObject」降級為成功 tool 回覆。

    其他工具錯誤封裝為 JSON ``system_fatal_error`` 回傳給 LLM（不拋 MCPError），
    讓 LangGraph 外層 task 節點生命週期得以繼續，由模型自我修正。
    僅連線級錯誤仍拋出 MCPError。
    """
    tool_messages: list[dict[str, Any]] = []

    for tc in tool_calls:
        tc_id = tc.get("id")
        if not tc_id:
            raise MCPError(f"tool_call 缺少 id: {tc!r}")
        fn = tc.get("function")
        if not isinstance(fn, dict):
            raise MCPError(f"tool_call 缺少 function: {tc!r}")

        tool_name = str(fn.get("name", ""))
        server = name_to_server.get(tool_name)
        if not server:
            raise MCPError(f"無法對應 MCP server 的工具名稱: {tool_name!r}")

        raw_args = fn.get("arguments", "{}")
        if isinstance(raw_args, str):
            try:
                arguments = json.loads(raw_args) if raw_args.strip() else {}
            except json.JSONDecodeError as exc:
                raise MCPError(f"工具參數非合法 JSON: {raw_args!r}") from exc
        elif isinstance(raw_args, dict):
            arguments = raw_args
        else:
            arguments = {}

        on_write_tool(tool_name, arguments)

        cached_content = try_cache_read(tool_name, arguments)
        if cached_content is not None:
            tool_messages.append(
                {
                    "role": "tool",
                    "tool_call_id": str(tc_id),
                    "content": cached_content,
                }
            )
            continue

        result: Any
        try:
            result = mgr.call_tool(server, tool_name, arguments)
        except Exception as exc:
            error_text = str(exc)
            if is_non_recoverable_mcp_error(error_text):
                raise
            downgraded, _action = try_downgrade_tool_error(
                error_text,
                tool_name=tool_name,
                arguments=arguments,
            )
            if downgraded is not None:
                result = downgraded
            else:
                result, _ = format_fatal_tool_content(
                    error_text,
                    tool_name=tool_name,
                )
        else:
            err_text = extract_error_text_from_tool_result(result)
            if err_text:
                downgraded, _action = try_downgrade_tool_error(
                    err_text,
                    tool_name=tool_name,
                    arguments=arguments,
                )
                if downgraded is not None:
                    result = downgraded
                else:
                    result, _ = format_fatal_tool_content(
                        err_text,
                        tool_name=tool_name,
                    )

        content = serialize_tool_result(result)
        record_read_result(tool_name, arguments, content)
        tool_messages.append(
            {
                "role": "tool",
                "tool_call_id": str(tc_id),
                "content": content,
            }
        )

    return tool_messages
