"""aicentral MCP / LLM 執行期 hook：即時輸出 tool 與 LLM 輪次日誌。"""

from __future__ import annotations

import json
from contextlib import contextmanager
from typing import Any, Iterator

from core.harness_log import (
    log_agent_start,
    log_llm_request,
    log_llm_round,
    log_mcp_tool,
)
from core.mcp.filtered_orchestrator import run_tool_calls_with_harness_filter


@contextmanager
def harness_progress_hooks() -> Iterator[None]:
    """在 ``unity-mcp-harness`` 執行期間 patch aicentral，輸出 LLM / MCP 進度。"""
    import aicentral.mcp.manager as mgr_mod
    import aicentral.mcp.orchestrator as orch
    import aicentral.routing.router as router

    orig_complete = orch.complete_with_mcp_loop
    orig_run_tool_calls = orch.run_tool_calls
    orig_invoke = router.invoke_resolved
    orig_call_tool = mgr_mod.MCPManager.call_tool

    llm_round = [0]
    pending_tools = [0]

    def logged_invoke_resolved(*args: Any, **kwargs: Any) -> Any:
        llm_round[0] += 1
        log_llm_request(llm_round[0])
        return orig_invoke(*args, **kwargs)

    def logged_call_tool(
        self: Any,
        server_name: str,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
    ) -> Any:
        args = arguments or {}
        try:
            result = orig_call_tool(self, server_name, tool_name, args)
        except Exception as exc:
            log_mcp_tool(server_name, tool_name, args, error=str(exc))
            raise
        from aicentral.mcp.orchestrator import serialize_tool_result

        from core.mcp.tool_error_filter import extract_error_text_from_tool_result

        preview = serialize_tool_result(result)
        err = extract_error_text_from_tool_result(result)
        if err and "expected_not_found" in preview:
            log_mcp_tool(
                server_name,
                tool_name,
                args,
                result_preview="[filtered] expected_not_found",
            )
        else:
            log_mcp_tool(server_name, tool_name, args, result_preview=preview)
        return result

    def logged_run_tool_calls(
        tool_calls: list[dict[str, Any]],
        *,
        mgr: Any,
        name_to_server: dict[str, str],
    ) -> list[dict[str, Any]]:
        pending_tools[0] = len(tool_calls)
        messages = run_tool_calls_with_harness_filter(
            tool_calls,
            mgr=mgr,
            name_to_server=name_to_server,
        )
        log_llm_round(llm_round[0], tool_count=pending_tools[0])
        return messages

    def logged_complete_with_mcp_loop(
        messages: list[Any],
        model: str | None,
        *,
        mcp_servers: Any = None,
        max_tool_rounds: int = 5,
        **kwargs: Any,
    ) -> Any:
        llm_round[0] = 0
        log_agent_start(model=model, max_tool_rounds=max_tool_rounds)
        router.invoke_resolved = logged_invoke_resolved
        try:
            return orig_complete(
                messages,
                model,
                mcp_servers=mcp_servers,
                max_tool_rounds=max_tool_rounds,
                **kwargs,
            )
        finally:
            router.invoke_resolved = orig_invoke

    mgr_mod.MCPManager.call_tool = logged_call_tool
    orch.complete_with_mcp_loop = logged_complete_with_mcp_loop
    orch.run_tool_calls = logged_run_tool_calls
    try:
        yield
    finally:
        mgr_mod.MCPManager.call_tool = orig_call_tool
        orch.complete_with_mcp_loop = orig_complete
        orch.run_tool_calls = orig_run_tool_calls
        router.invoke_resolved = orig_invoke
