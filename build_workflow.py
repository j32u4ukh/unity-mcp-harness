"""LangGraph 工作流：依序執行建構任務，每步經 harness MCP runner + aicentral。"""

from __future__ import annotations

import operator
from pathlib import Path
from typing import Annotated, Any, Literal

from langgraph.graph import END, START, StateGraph
from typing_extensions import TypedDict

from aicentral.exceptions import ProviderError
from aicentral.mcp import MCPError

from harness.mcp_runner import UnityMCPRunner, create_unity_mcp_runner

from core.harness_log import (
    harness_log,
    log_prompt_excerpt,
    log_task_end,
    log_task_start,
)
from core.progress_hooks import harness_progress_hooks
from core.pipeline.execution import get_next_runnable_task, harness_task_to_build_task, harness_tasks_by_id
from core.pipeline.runner import HarnessTaskRunner
from core.pipeline.schema import HarnessTask, TaskListDocument
from core.pipeline.store import default_task_list_path
from core.project_state import begin_session, end_session
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
    harness_by_id: dict[str, HarnessTask]
    resume: bool
    has_next: bool


def _run_single_task(
    task: BuildTask,
    *,
    plan: BuildPlan,
    prior: list[TaskResult],
    runner: UnityMCPRunner,
    default_servers: list[str],
    harness_task: HarnessTask | None = None,
    resume: bool = False,
    pipeline_runner: HarnessTaskRunner | None = None,
    task_index: int | None = None,
) -> TaskResult:
    """執行單一任務：UnityMCPRunner → aicentral Chat.with_mcp。"""
    log_task_start(task.id, task.title, index=task_index)
    if pipeline_runner is not None:
        harness_task = pipeline_runner.on_task_start(task.id)

    prompt = format_task_prompt(
        task,
        plan=plan,
        prior_results=prior,
        harness_task=harness_task,
        resume=resume,
    )
    log_prompt_excerpt(prompt)
    try:
        if task.mcp_servers:
            reply = ask_unity(
                prompt,
                mcp_servers=task.mcp_servers,
                model=plan.model,
                max_tool_rounds=plan.max_tool_rounds,
            )
        else:
            reply = runner.ask(prompt)
        if task_reply_indicates_failure(reply):
            result = TaskResult(
                id=task.id,
                title=task.title,
                success=False,
                reply=reply,
                error=task_failure_summary(reply),
            )
        else:
            result = TaskResult(
                id=task.id,
                title=task.title,
                success=True,
                reply=reply,
            )
    except (MCPError, ProviderError) as exc:
        harness_log(str(exc), level="ERROR")
        result = TaskResult(
            id=task.id,
            title=task.title,
            success=False,
            reply="",
            error=str(exc),
        )

    if pipeline_runner is not None:
        pipeline_runner.on_task_end(task.id, result)
        ht = pipeline_runner.get_task(task.id)
        log_task_end(
            task.id,
            success=result.success,
            verification=ht.verification,
            error=result.error,
        )
    else:
        log_task_end(task.id, success=result.success, error=result.error)
    return result


def _make_run_task_node(
    runner: UnityMCPRunner,
    mcp_servers: list[str],
    *,
    harness_by_id: dict[str, HarnessTask],
    resume: bool,
    pipeline_runner: HarnessTaskRunner | None = None,
):
    """建立閉包節點：讀取 state 中當前 task_index 並執行。"""

    def run_task(state: BuildState) -> dict[str, Any]:
        plan = state["plan"]
        task: BuildTask
        ht: HarnessTask | None
        if pipeline_runner is not None:
            next_ht = get_next_runnable_task(pipeline_runner.document)
            if next_ht is None:
                return {"has_next": False}
            task = harness_task_to_build_task(next_ht)
            ht = next_ht
        else:
            tasks = plan.enabled_tasks()
            index = state["task_index"]
            if index >= len(tasks):
                return {"has_next": False}
            task = tasks[index]
            ht = harness_by_id.get(task.id)
        prior = list(state.get("results", []))
        result = _run_single_task(
            task,
            plan=plan,
            prior=prior,
            runner=runner,
            default_servers=mcp_servers,
            harness_task=ht,
            resume=state.get("resume", resume),
            pipeline_runner=pipeline_runner,
            task_index=state.get("task_index", 0) + 1,
        )
        if pipeline_runner is not None:
            harness_by_id[task.id] = pipeline_runner.get_task(task.id)
            has_next = get_next_runnable_task(pipeline_runner.document) is not None
            next_index = state.get("task_index", 0) + 1
        else:
            has_next = (state["task_index"] + 1) < len(plan.enabled_tasks())
            next_index = state["task_index"] + 1
        return {
            "results": [result],
            "task_index": next_index,
            "has_next": has_next,
        }

    return run_task


def _route_after_task(state: BuildState) -> Literal["run_task", "done"]:
    """決定繼續下一任務或結束。"""
    if not state.get("has_next", False):
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
    task_list: TaskListDocument | None = None,
    task_list_path: str | Path | None = None,
    resume: bool = False,
    skip_verification: bool = False,
) -> Any:
    """編譯 LangGraph：依 plan / task_list 順序執行任務。"""
    register_unity_servers(specs, config_path=unity_config_path)
    mcp_servers = plan.mcp_servers
    runner = create_unity_mcp_runner(
        mcp_servers,
        model=plan.model,
        max_tool_rounds=plan.max_tool_rounds,
        include_tool_messages_in_history=True,
    )

    harness_by_id = harness_tasks_by_id(task_list) if task_list else {}
    pipeline_runner: HarnessTaskRunner | None = None
    if task_list is not None:
        list_path = Path(task_list_path) if task_list_path is not None else default_task_list_path()
        pipeline_runner = HarnessTaskRunner(
            task_list,
            list_path,
            unity_runner=runner,
            model=plan.model,
            mcp_servers=mcp_servers,
            unity_config_path=unity_config_path,
            skip_verification=skip_verification,
            definition_of_done=plan.definition_of_done,
            specs=specs,
        )

    graph = StateGraph(BuildState)
    run_node = _make_run_task_node(
        runner,
        mcp_servers,
        harness_by_id=harness_by_id,
        resume=resume,
        pipeline_runner=pipeline_runner,
    )
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
    task_list: TaskListDocument | None = None,
    task_list_path: str | Path | None = None,
    resume: bool = False,
    skip_verification: bool = False,
) -> list[TaskResult]:
    """執行整份建構計畫並回傳各任務結果。

    若提供 ``task_list``，任務順序與 prompt 以 SSOT 為準（``build_plan_for_execution``）。
    """
    graph = build_sequential_workflow(
        plan,
        specs=specs,
        unity_config_path=unity_config_path,
        stop_on_error=stop_on_error,
        task_list=task_list,
        task_list_path=task_list_path,
        resume=resume,
        skip_verification=skip_verification,
    )
    harness_by_id = harness_tasks_by_id(task_list) if task_list else {}
    initial: BuildState = {
        "plan": plan,
        "task_index": 0,
        "results": [],
        "stop_on_error": stop_on_error,
        "harness_by_id": harness_by_id,
        "resume": resume,
        "has_next": True,
    }
    begin_session()
    try:
        with harness_progress_hooks():
            harness_log("LangGraph 建構工作流開始")
            final = graph.invoke(initial)
            harness_log("LangGraph 建構工作流結束")
        return list(final.get("results", []))
    finally:
        end_session(flush=True)
