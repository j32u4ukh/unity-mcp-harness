#!/usr/bin/env python3
"""依 build_goals.yaml 順序執行 Unity 建構任務（LangGraph + aicentral + Unity MCP）。"""

from __future__ import annotations

import argparse
import json
import sys

from core.pipeline.prepare import prepare_harness_queue
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
    return parser.parse_args()


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
    replan = args.replan or args.init_tasks

    try:
        specs = resolve_server_specs(config_path=args.unity_config)
        prepared = prepare_harness_queue(
            goals_path=args.goals,
            skip_plan_normalize=args.skip_plan_normalize,
            replan=replan,
            init_tasks=args.init_tasks,
            write_back_goals=args.write_back_goals,
            backup_goals=args.backup,
            plan_with_mcp=args.plan_with_mcp,
            unity_config_path=args.unity_config,
            specs=specs,
        )
        plan = prepared.build_plan
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

    if args.dry_run:
        print("\n（dry-run：未執行 Unity MCP 建構）")
        return

    register_unity_servers(specs, config_path=args.unity_config)

    try:
        results = run_build_plan(
            plan,
            specs=specs,
            unity_config_path=args.unity_config,
            stop_on_error=not args.continue_on_error,
        )
    except Exception as exc:
        handle_errors(exc)
        sys.exit(1)

    if args.json:
        payload = [
            {
                "id": r.id,
                "title": r.title,
                "success": r.success,
                "reply": r.reply,
                "error": r.error,
            }
            for r in results
        ]
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        _print_results(results)

    if results and not all(r.success for r in results):
        sys.exit(1)


if __name__ == "__main__":
    main()
