#!/usr/bin/env python3
"""依 build_goals.yaml 順序執行 Unity 建構任務（LangGraph + aicentral + Unity MCP）。"""

from __future__ import annotations

import argparse
import json
import sys

from tasks import resolve_build_plan
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
    return parser.parse_args()


def _print_plan_summary(plan) -> None:
    tasks = plan.enabled_tasks()
    print(f"專案: {plan.project}")
    print(f"任務數: {len(tasks)}")
    for i, t in enumerate(tasks, 1):
        print(f"  {i}. [{t.id}] {t.title}")


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

    try:
        plan = resolve_build_plan(plan_path=args.goals)
        specs = resolve_server_specs(config_path=args.unity_config)
    except Exception as exc:
        handle_errors(exc)
        sys.exit(1)

    model = resolve_unity_llm_model(plan.model)
    print_banner(
        title="Unity 建構工作流（LangGraph 依序執行）",
        model=model,
        server_names=plan.mcp_servers,
        detail="任務檔定義目標；每步由 aicentral-agent → aicentral Chat.with_mcp 驅動 Unity MCP",
        specs=specs,
        interactive=False,
    )
    _print_plan_summary(plan)

    if args.dry_run:
        print("\n（dry-run：未執行）")
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
