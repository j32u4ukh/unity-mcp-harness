"""LangGraph 工作流：依序執行建構任務，每步經 aicentral-agent + aicentral MCP。"""

from __future__ import annotations

import operator
from pathlib import Path
from typing import Annotated, Any, Literal

from langgraph.graph import END, START, StateGraph
from typing_extensions import TypedDict

from aicentral.exceptions import ProviderError
from aicentral.mcp import MCPError

from aicentral_agent.mcp_build import UnityMCPRunner, create_unity_mcp_runner

from tasks import BuildPlan, BuildTask, TaskResult, format_task_prompt
from unity_common import (
    ask_unity,
    register_unity_servers,
    task_failure_summary,
    task_reply_indicates_failure,
)


class BuildState(TypedDict):
    """建構執行狀態（LangGraph）。"""

    plan: BuildPlan
    task_index: int
    results: Annotated[list[TaskResult], operator.add]
    stop_on_error: bool


def _run_single_task(
    task: BuildTask,
    *,
    plan: BuildPlan,
    prior: list[TaskResult],
    runner: UnityMCPRunner,
    default_servers: list[str],
) -> TaskResult:
    """執行單一任務：aicentral-agent runner → aicentral Chat.with_mcp。"""
    prompt = format_task_prompt(task, plan=plan, prior_results=prior)
    try:
        if task.mcp_servers:
            # 任務指定不同 MCP server 時獨立呼叫（不共用 Chat 歷史）
            reply = ask_unity(
                prompt,
                mcp_servers=task.mcp_servers,
                model=plan.model,
                max_tool_rounds=plan.max_tool_rounds,
            )
        else:
            # 使用同一 Chat 工作階段，保留跨任務 MCP / 對話脈絡
            reply = runner.ask(prompt)
        if task_reply_indicates_failure(reply):
            return TaskResult(
                id=task.id,
                title=task.title,
                success=False,
                reply=reply,
                error=task_failure_summary(reply),
            )
        return TaskResult(
            id=task.id,
            title=task.title,
            success=True,
            reply=reply,
        )
    except (MCPError, ProviderError) as exc:
        return TaskResult(
            id=task.id,
            title=task.title,
            success=False,
            reply="",
            error=str(exc),
        )


def _make_run_task_node(runner: UnityMCPRunner, mcp_servers: list[str]):
    """建立閉包節點：讀取 state 中當前 task_index 並執行。"""

    def run_task(state: BuildState) -> dict[str, Any]:
        plan = state["plan"]
        tasks = plan.enabled_tasks()
        index = state["task_index"]
        if index >= len(tasks):
            return {}
        task = tasks[index]
        prior = list(state.get("results", []))
        result = _run_single_task(
            task,
            plan=plan,
            prior=prior,
            runner=runner,
            default_servers=mcp_servers,
        )
        return {
            "results": [result],
            "task_index": index + 1,
        }

    return run_task


def _route_after_task(state: BuildState) -> Literal["run_task", "done"]:
    """決定繼續下一任務或結束。"""
    plan = state["plan"]
    tasks = plan.enabled_tasks()
    index = state["task_index"]

    if index >= len(tasks):
        return "done"

    if state.get("stop_on_error", True) and state.get("results"):
        last = state["results"][-1]
        if not last.success:
            return "done"

    return "run_task"


def build_sequential_workflow(
    plan: BuildPlan,
    *,
    specs: dict | None = None,
    unity_config_path: str | Path | None = None,
    stop_on_error: bool = True,
) -> Any:
    """編譯 LangGraph：依 plan 順序執行任務；執行層為 aicentral-agent ``UnityMCPRunner``。

    編排：LangGraph（unity-mcp）+ LLM/MCP：aicentral-agent → aicentral ``Chat.with_mcp``。
    """
    register_unity_servers(specs, config_path=unity_config_path)
    mcp_servers = plan.mcp_servers
    runner = create_unity_mcp_runner(
        mcp_servers,
        model=plan.model,
        max_tool_rounds=plan.max_tool_rounds,
        include_tool_messages_in_history=True,
    )

    graph = StateGraph(BuildState)
    run_node = _make_run_task_node(runner, mcp_servers)
    graph.add_node("run_task", run_node)
    graph.add_edge(START, "run_task")
    graph.add_conditional_edges(
        "run_task",
        _route_after_task,
        {"run_task": "run_task", "done": END},
    )
    return graph.compile()


def run_build_plan(
    plan: BuildPlan,
    *,
    specs: dict | None = None,
    unity_config_path: str | Path | None = None,
    stop_on_error: bool = True,
) -> list[TaskResult]:
    """執行整份建構計畫並回傳各任務結果。"""
    graph = build_sequential_workflow(
        plan,
        specs=specs,
        unity_config_path=unity_config_path,
        stop_on_error=stop_on_error,
    )
    initial: BuildState = {
        "plan": plan,
        "task_index": 0,
        "results": [],
        "stop_on_error": stop_on_error,
    }
    final = graph.invoke(initial)
    return list(final.get("results", []))
