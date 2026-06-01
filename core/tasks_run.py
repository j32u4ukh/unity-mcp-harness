"""--tasks run：依 task_list 執行 Unity MCP 建構。"""

from __future__ import annotations

import argparse
import json
import sys
from typing import TYPE_CHECKING

from core.pipeline.execution import (
    build_plan_for_execution,
    find_sequential_blocker,
    get_next_runnable_task,
)
from core.pipeline.prepare import prepare_harness_queue
from core.pipeline.store import default_task_list_path, load_task_list
from unity_common import (
    handle_errors,
    print_banner,
    register_unity_servers,
    require_aicentral_config,
    resolve_server_specs,
    resolve_unity_llm_model,
)
from build_workflow import run_build_plan
from core.harness_log import configure_harness_log, log_prepare_phase
from core.progress_hooks import harness_progress_hooks
from core.cli_plan import print_deprecation_notices, resolve_plan_cli
from core.mcp.server_lifecycle import UnityMcpServerSession
from core.cli_extended import EXECUTE_SECTION_12_TAG, write_capabilities_marker

if TYPE_CHECKING:
    from run_build import _print_harness_summary, _print_plan_summary, _print_results, _results_to_json_payload


def _resolve_goals_path(args: argparse.Namespace):
    return getattr(args, "goals_file", None)


def run_tasks_run(args: argparse.Namespace) -> int:
    """執行 task_list.yaml 中的 pending 任務（原預設建構流程）。"""
    configure_harness_log(quiet=args.quiet, verbose=args.verbose)
    try:
        plan_cli = resolve_plan_cli(args)
    except SystemExit as exc:
        print(exc, file=sys.stderr)
        return 2
    print_deprecation_notices()

    require_aicentral_config(
        aicentral_config=args.aicentral_config,
        secret=args.secret,
    )

    from run_build import (
        _print_harness_summary,
        _print_plan_summary,
        _print_results,
        _results_to_json_payload,
    )

    try:
        specs = resolve_server_specs(config_path=args.unity_config)
        log_prepare_phase("載入 task_list / 必要時同步藍圖")
        with harness_progress_hooks():
            prepared = prepare_harness_queue(
                goals_path=_resolve_goals_path(args),
                skip_plan_normalize=args.skip_plan_normalize,
                force_sync_from_blueprint=False,
                dry_run=args.dry_run,
                write_back_goals=plan_cli.write_back_in_prepare,
                backup_goals=args.backup,
                plan_with_mcp=args.plan_with_mcp,
                plan_interactive=args.plan_interactive,
                supplements_path=args.supplements,
                unity_config_path=args.unity_config,
                specs=specs,
            )
        plan = prepared.build_plan
        task_list_path = prepared.task_list_path
        task_list = (
            load_task_list(task_list_path)
            if task_list_path.is_file()
            else prepared.task_list
        )
        execution_plan = build_plan_for_execution(
            plan,
            task_list,
            retry_failed=args.retry_failed,
        )
        resume = not prepared.created_task_list
        next_task = get_next_runnable_task(task_list, retry_failed=args.retry_failed)
    except Exception as exc:
        handle_errors(exc)
        return 1

    model = resolve_unity_llm_model(plan.model)
    print_banner(
        title="Unity 建構工作流（Harness + LangGraph）",
        model=model,
        server_names=plan.mcp_servers,
        detail="依 task_list.yaml 執行 Unity MCP 建構",
        specs=specs,
        interactive=False,
    )
    _print_plan_summary(plan)
    _print_harness_summary(prepared)
    if next_task is not None:
        runnable = execution_plan.enabled_tasks()
        print(
            f"\n下一個執行任務: [{next_task.id}] status={next_task.status} "
            f"（本輪共 {len(runnable)} 個待跑）"
        )
        if args.retry_failed:
            print("（已啟用 --retry-failed：failed 任務會納入本輪）")
    else:
        blocker = find_sequential_blocker(task_list)
        if blocker is not None and not args.retry_failed:
            print(
                f"\n（順序阻擋：前置任務 [{blocker.id}] status=failed，"
                f"後續任務暫不執行；請先 --retry-failed 或修正 task_list）"
            )
        else:
            print("\n（無待執行任務：全部 completed / skipped）")

    if args.dry_run:
        print("\n（dry-run：未執行 Unity MCP 建構）")
        return 0

    if not task_list_path.is_file() and not task_list.tasks:
        print(
            f"錯誤: 找不到 {default_task_list_path()}，請先執行 --goals build。",
            file=sys.stderr,
        )
        return 1

    register_unity_servers(specs, config_path=args.unity_config)

    if args.verification_max_tool_rounds is not None:
        if args.verification_max_tool_rounds < 1:
            print("錯誤: --verification-max-tool-rounds 須 >= 1", file=sys.stderr)
            return 2
        execution_plan.verification_max_tool_rounds = args.verification_max_tool_rounds

    try:
        with UnityMcpServerSession(
            specs,
            autostart=not args.no_autostart_mcp_server,
        ):
            results = run_build_plan(
                execution_plan,
                specs=specs,
                unity_config_path=args.unity_config,
                stop_on_error=not args.continue_on_error,
                task_list=task_list,
                task_list_path=task_list_path,
                resume=resume,
                skip_verification=args.skip_verification,
                retry_failed=args.retry_failed,
            )
    except Exception as exc:
        handle_errors(exc)
        return 1

    if args.json:
        final_doc = load_task_list(task_list_path) if task_list_path.is_file() else task_list
        payload = _results_to_json_payload(results, task_list=final_doc)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        _print_results(results)

    if task_list_path.is_file():
        final_doc = load_task_list(task_list_path)
        print("task_list 狀態（落盤後）:")
        for t in final_doc.tasks:
            ops = len(t.pipeline_records.operations_executed)
            print(f"  [{t.id}] status={t.status} verification={t.verification} ops={ops}")

    if results and not all(r.success for r in results):
        return 1

    marker = write_capabilities_marker()
    print(f"（{EXECUTE_SECTION_12_TAG} 能力已就緒；標記: {marker.name}）")
    return 0
