#!/usr/bin/env python3
"""依 build_goals.yaml 順序執行 Unity 建構任務（LangGraph + aicentral + Unity MCP）。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from core.pipeline.execution import (
    build_plan_for_execution,
    find_sequential_blocker,
    get_next_runnable_task,
)
from core.pipeline.goals_writeback import write_back_task_list_goals
from core.pipeline.prepare import prepare_harness_queue
from core.pipeline.store import default_task_list_path, load_task_list
from unity_common import (
    add_harness_llm_config_args,
    handle_errors,
    print_banner,
    register_unity_servers,
    require_aicentral_config,
    resolve_server_specs,
    resolve_unity_llm_model,
)
from build_workflow import run_build_plan
from core.harness_log import configure_harness_log
from core.cli_plan import (
    CLI_EPILOG,
    add_plan_cli_arguments,
    print_deprecation_notices,
    resolve_plan_cli,
)
from core.mcp.server_lifecycle import UnityMcpServerSession


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="依任務清單順序透過 Unity MCP 建構場景（LangGraph 編排）",
        epilog=CLI_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "-g",
        "--goals",
        type=str,
        default=None,
        help="建構任務 YAML/JSON（預設 build_goals.yaml 或 example）",
    )
    parser.add_argument(
        "-c",
        "--unity-config",
        type=str,
        default=None,
        help="Unity MCP 設定 JSON（預設 unity_servers.json；無檔時 fallback IvanMurzak HTTP :22172）",
    )
    parser.add_argument(
        "--continue-on-error",
        action="store_true",
        help="任務失敗仍繼續後續任務（預設失敗即停止）",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只列出將執行的任務，不呼叫 LLM / MCP",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="以 JSON 輸出執行結果",
    )
    parser.add_argument(
        "--skip-plan-normalize",
        action="store_true",
        help="略過 LLM 規範化（除錯用；bootstrap 時使用 passthrough）",
    )
    add_plan_cli_arguments(parser)
    parser.add_argument(
        "--plan-with-mcp",
        action="store_true",
        help="規劃階段先唯讀 MCP 查詢專案（預設關閉）",
    )
    parser.add_argument(
        "--retry-failed",
        action="store_true",
        help="將 failed 任務納入本輪可執行清單（預設僅 pending/in_progress）",
    )
    parser.add_argument(
        "--plan-interactive",
        action="store_true",
        help="Plan Normalize 時對 JSON 未涵蓋的模糊項終端詢問，並可寫回 config/prompt_supplements.json",
    )
    parser.add_argument(
        "--supplements",
        type=str,
        default=None,
        help="規劃補充 prompt JSON（預設 config/prompt_supplements.json）",
    )
    parser.add_argument(
        "--init",
        nargs="?",
        const="",
        default=None,
        metavar="ROOT",
        help="初始化外部工作區（省略 ROOT 則為目前目錄）；完成後 exit，不跑建構",
    )
    parser.add_argument(
        "--init-force",
        action="store_true",
        help="與 --init 合用：覆寫已存在的非機密檔（含 secret.yaml，請謹慎）",
    )
    parser.add_argument(
        "--init-stdio",
        action="store_true",
        help="與 --init 合用：使用 Coplay stdio relay 範本（預設 IvanMurzak HTTP）",
    )
    parser.add_argument(
        "--init-http",
        action="store_true",
        help="（已為預設）與 --init 合用：使用 IvanMurzak HTTP MCP 範本",
    )
    parser.add_argument(
        "--bootstrap-state",
        action="store_true",
        help="唯讀 MCP 盤點既有 Unity 專案並寫入 project_state/（需先 --init 與設定 local.env.ps1）",
    )
    parser.add_argument(
        "--bootstrap-prompt",
        type=str,
        default=None,
        help="自訂基線盤點 prompt（預設 unity_explore.yaml probe_prompt 或內建範本）",
    )
    parser.add_argument(
        "--skip-verification",
        action="store_true",
        help="略過任務結束後的 MCP 事後驗證（除錯用；預設每任務獨立驗證 Editor 現場）",
    )
    parser.add_argument(
        "--verification-max-tool-rounds",
        type=int,
        default=None,
        metavar="N",
        help="Harness 事後驗證 MCP loop 上限（預設 build_goals.yaml 的 verification_max_tool_rounds，否則同 max_tool_rounds）",
    )
    parser.add_argument(
        "--no-autostart-mcp-server",
        action="store_true",
        help="勿自動啟動 Unity-MCP-Server（HTTP 須已在本機運行）",
    )
    parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="略過執行期進度日誌（預設會輸出任務 / LLM / MCP tool）",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="進度日誌含 MCP tool 回傳摘要",
    )
    add_harness_llm_config_args(parser)
    return parser.parse_args()


def _results_to_json_payload(results, *, task_list=None) -> list[dict]:
    """將任務結果轉為 JSON 輸出；可附帶 task_list 的驗證欄位。"""
    by_id = {}
    if task_list is not None:
        by_id = {t.id: t for t in task_list.tasks}
    payload = []
    for r in results:
        item = {
            "id": r.id,
            "title": r.title,
            "success": r.success,
            "reply": r.reply,
            "error": r.error,
        }
        task = by_id.get(r.id)
        if task is not None:
            item["status"] = task.status
            item["verification"] = task.verification
            item["operations_executed"] = len(task.pipeline_records.operations_executed)
        payload.append(item)
    return payload


def _print_plan_summary(plan) -> None:
    tasks = plan.enabled_tasks()
    print(f"專案: {plan.project}")
    print(f"藍圖任務數: {len(tasks)}")
    for i, t in enumerate(tasks, 1):
        print(f"  {i}. [{t.id}] {t.title}")


def _print_harness_summary(prepared) -> None:
    norm = prepared.normalized
    doc = prepared.task_list
    print(f"\nPlan Normalize: revision={norm.plan_revision}")
    if norm.plan_changelog:
        print(f"  changelog: {norm.plan_changelog}")
    print(f"執行隊列 ({prepared.task_list_path.name}): {len(doc.tasks)} 任務")
    if prepared.created_task_list:
        print("  （已建立/更新 task_list）")
    else:
        print("  （沿用既有 task_list）")
    for i, t in enumerate(doc.tasks, 1):
        print(f"  {i}. [{t.id}] status={t.status} priority={t.priority} — {t.description}")


def _print_results(results) -> None:
    print("-" * 40)
    print("執行結果")
    for r in results:
        mark = "OK" if r.success else "FAIL"
        print(f"[{mark}] {r.id} — {r.title}")
        if r.error:
            print(f"  錯誤: {r.error}")
        if r.reply:
            preview = r.reply[:1200] + ("…" if len(r.reply) > 1200 else "")
            label = "助理回覆" if r.error else "摘要"
            print(f"  {label}: {preview}")
        print()


def main() -> None:
    args = parse_args()
    configure_harness_log(quiet=args.quiet, verbose=args.verbose)
    if args.init is not None:
        from core.scaffold.init_workspace import format_init_report, init_workspace

        target = Path.cwd() if args.init == "" else Path(args.init)
        transport = "stdio" if args.init_stdio else "http"
        report = init_workspace(
            target,
            force=args.init_force,
            mcp_transport=transport,
        )
        print(format_init_report(report))
        sys.exit(0 if report.ok else 1)

    if args.bootstrap_state:
        require_aicentral_config(
            aicentral_config=args.aicentral_config,
            secret=args.secret,
        )
        from core.project_state.bootstrap import format_bootstrap_report, run_bootstrap_state

        try:
            report = run_bootstrap_state(
                unity_config_path=args.unity_config,
                prompt=args.bootstrap_prompt,
            )
        except Exception as exc:
            handle_errors(exc)
            sys.exit(1)
        print(format_bootstrap_report(report))
        sys.exit(0 if report.ok else 1)

    try:
        plan_cli = resolve_plan_cli(args)
    except SystemExit as exc:
        print(exc, file=sys.stderr)
        sys.exit(2)
    print_deprecation_notices()

    if plan_cli.standalone_export_from_task_list:
        task_list_path = default_task_list_path()
        try:
            task_list = load_task_list(task_list_path)
        except FileNotFoundError as exc:
            print(f"錯誤: {exc}\n請先執行 --goals-to-task-list 或 --replan-and-run 建立 task_list。", file=sys.stderr)
            sys.exit(1)
        except (ValueError, OSError) as exc:
            handle_errors(exc)
            sys.exit(1)
        try:
            out = write_back_task_list_goals(task_list, args.goals, backup=args.backup)
        except (FileNotFoundError, ValueError, OSError) as exc:
            handle_errors(exc)
            sys.exit(1)
        print(f"（--export-goals-from-task-list：已將 task_list 規劃欄位寫回 {out}）")
        return

    require_aicentral_config()
    try:
        from core.harness_log import log_prepare_phase
        from core.progress_hooks import harness_progress_hooks

        specs = resolve_server_specs(config_path=args.unity_config)
        log_prepare_phase("載入 build_goals / Plan Normalize / bootstrap task_list")
        with harness_progress_hooks():
            prepared = prepare_harness_queue(
                goals_path=args.goals,
                skip_plan_normalize=args.skip_plan_normalize,
                replan=plan_cli.need_replan,
                init_tasks=False,
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
        if task_list_path.is_file():
            task_list = load_task_list(task_list_path)
        else:
            task_list = prepared.task_list
        execution_plan = build_plan_for_execution(
            plan,
            task_list,
            retry_failed=args.retry_failed,
        )
        resume = not prepared.created_task_list
        next_task = get_next_runnable_task(task_list, retry_failed=args.retry_failed)
    except Exception as exc:
        handle_errors(exc)
        sys.exit(1)

    model = resolve_unity_llm_model(plan.model)
    print_banner(
        title="Unity 建構工作流（Harness + LangGraph）",
        model=model,
        server_names=plan.mcp_servers,
        detail="藍圖 build_goals → Plan Normalize → task_list → Unity MCP 執行",
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

    if plan_cli.goals_to_task_list:
        if plan_cli.export_goals_from_task_list:
            write_back_task_list_goals(task_list, args.goals, backup=args.backup)
            print("（已將 task_list 規劃欄位寫回 build_goals.yaml）")
        if plan_cli.export_goals_from_normalize and not plan_cli.write_back_in_prepare:
            print("（已於規劃階段將 Normalize 結果寫回 build_goals.yaml）")
        print(
            "\n（--goals-to-task-list：build_goals → task_list 已完成，未執行 Unity MCP 建構）"
        )
        return

    if args.dry_run:
        print("\n（dry-run：未執行 Unity MCP 建構）")
        return

    register_unity_servers(specs, config_path=args.unity_config)

    if args.verification_max_tool_rounds is not None:
        if args.verification_max_tool_rounds < 1:
            print("錯誤: --verification-max-tool-rounds 須 >= 1", file=sys.stderr)
            sys.exit(2)
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
        sys.exit(1)

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
        sys.exit(1)


if __name__ == "__main__":
    main()
