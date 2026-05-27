#!/usr/bin/env python3
"""依 build_goals.yaml 順序執行 Unity 建構任務（LangGraph + aicentral + Unity MCP）。"""

from __future__ import annotations

import argparse
import json
import sys

from core.pipeline.execution import build_plan_for_execution, get_next_runnable_task
from core.pipeline.goals_writeback import write_back_task_list_goals
from core.pipeline.prepare import prepare_harness_queue
from core.pipeline.store import load_task_list
from unity_common import (
    handle_errors,
    print_banner,
    register_unity_servers,
    require_aicentral_config,
    resolve_server_specs,
    resolve_unity_llm_model,
)
from build_workflow import run_build_plan


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="依任務清單順序透過 Unity MCP 建構場景（LangGraph 編排）",
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
        help="Unity MCP 設定 JSON（預設 unity_servers.json；無檔時 fallback HTTP :8080）",
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
    parser.add_argument(
        "--replan",
        action="store_true",
        help="強制重跑 Plan Normalize 並重建 task_list（保留 completed 紀錄）",
    )
    parser.add_argument(
        "--init-tasks",
        action="store_true",
        help="強制 bootstrap task_list.yaml（等同 --replan）",
    )
    parser.add_argument(
        "--write-back-goals",
        action="store_true",
        help="將規範化後 tasks 寫回 build_goals.yaml",
    )
    parser.add_argument(
        "--backup",
        action="store_true",
        help="與 --write-back-goals 合用：寫回前備份 .bak",
    )
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
        "--sync-plan",
        action="store_true",
        help="以最新 build_goals 規範化並同步合併至 task_list（保留 completed 紀錄）",
    )
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
    require_aicentral_config()
    args = parse_args()
    replan = args.replan or args.init_tasks or args.sync_plan

    try:
        specs = resolve_server_specs(config_path=args.unity_config)
        prepared = prepare_harness_queue(
            goals_path=args.goals,
            skip_plan_normalize=args.skip_plan_normalize,
            replan=replan,
            init_tasks=args.init_tasks,
            write_back_goals=args.write_back_goals and not args.sync_plan,
            backup_goals=args.backup,
            plan_with_mcp=args.plan_with_mcp,
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
        print("\n（無待執行任務：全部 completed / skipped）")

    if args.sync_plan:
        if args.write_back_goals:
            write_back_task_list_goals(task_list, args.goals, backup=args.backup)
            print("（已將 task_list 的規劃欄位寫回 build_goals）")
        print("\n（sync-plan：已完成藍圖與 task_list 同步，未執行 Unity MCP 建構）")
        return

    if args.dry_run:
        print("\n（dry-run：未執行 Unity MCP 建構）")
        return

    register_unity_servers(specs, config_path=args.unity_config)

    try:
        results = run_build_plan(
            execution_plan,
            specs=specs,
            unity_config_path=args.unity_config,
            stop_on_error=not args.continue_on_error,
            task_list=task_list,
            task_list_path=task_list_path,
            resume=resume,
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
