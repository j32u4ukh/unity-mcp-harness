"""建構 CLI：藍圖 ↔ task_list 旗標解析（含舊旗標相容）。"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass


@dataclass(frozen=True)
class PlanCliFlags:
    """解析後的規劃／寫回旗標。"""

    goals_to_task_list: bool
    """僅 build_goals → normalize → task_list，不跑 Unity 建構。"""

    replan_and_run: bool
    """normalize 並更新 task_list 後繼續執行 Harness。"""

    export_goals_from_normalize: bool
    """將 Plan Normalize 結果寫入 build_goals.yaml（非 task_list）。"""

    export_goals_from_task_list: bool
    """將 task_list 規劃欄位寫入 build_goals.yaml。"""

    standalone_export_from_task_list: bool
    """僅 --export-goals-from-task-list：讀既有 task_list 寫回藍圖，不規劃、不建構。"""

    need_replan: bool
    """是否觸發 normalize + bootstrap task_list。"""

    write_back_in_prepare: bool
    """prepare 階段是否 write_back_build_goals(normalized)。"""


_DEPRECATED_MESSAGES: list[str] = []


def _warn_deprecated(message: str) -> None:
    _DEPRECATED_MESSAGES.append(message)
    print(f"警告: {message}", file=sys.stderr)


def print_deprecation_notices() -> None:
    for msg in _DEPRECATED_MESSAGES:
        print(f"（已棄用）{msg}", file=sys.stderr)


def add_plan_cli_arguments(parser: argparse.ArgumentParser) -> None:
    """註冊規劃相關參數（含舊名稱相容）。"""
    plan = parser.add_argument_group(
        "藍圖與執行隊列",
        "build_goals.yaml（人類藍圖）↔ task_list.yaml（執行 SSOT）",
    )
    plan.add_argument(
        "--goals-to-task-list",
        action="store_true",
        help=(
            "僅規劃：讀 build_goals → Plan Normalize → 更新 task_list.yaml（保留 completed 紀錄），"
            "不連 Unity 建構。改藍圖後先用此指令。"
        ),
    )
    plan.add_argument(
        "--replan-and-run",
        action="store_true",
        help=(
            "規劃並執行：同上更新 task_list 後，繼續跑 pending 的 Unity MCP 任務。"
            "（等同舊版 --replan）"
        ),
    )
    plan.add_argument(
        "--export-goals-from-normalize",
        action="store_true",
        help=(
            "將「Plan Normalize 輸出」寫回 build_goals.yaml 的 tasks（非 task_list）。"
            "適用於 --replan-and-run 或首次建立隊列時。"
        ),
    )
    plan.add_argument(
        "--export-goals-from-task-list",
        action="store_true",
        help=(
            "將「task_list.yaml 規劃欄位」寫回 build_goals.yaml（不含 status/verification/pipeline）。"
            "可單獨使用；若同時加 --goals-to-task-list 則先同步藍圖再寫回。"
        ),
    )
    plan.add_argument(
        "--backup",
        action="store_true",
        help="與任一 --export-goals-* 合用：寫回 build_goals 前備份 .bak",
    )

    compat = parser.add_argument_group("相容舊參數（將移除）")
    compat.add_argument(
        "--replan",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    compat.add_argument(
        "--init-tasks",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    compat.add_argument(
        "--sync-plan",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    compat.add_argument(
        "--write-back-goals",
        action="store_true",
        help=argparse.SUPPRESS,
    )


def resolve_plan_cli(args: argparse.Namespace) -> PlanCliFlags:
    """解析旗標；舊參數映射到新語意並發出警告。"""
    goals_to_task_list = bool(getattr(args, "goals_to_task_list", False))
    replan_and_run = bool(getattr(args, "replan_and_run", False))
    export_norm = bool(getattr(args, "export_goals_from_normalize", False))
    export_tl = bool(getattr(args, "export_goals_from_task_list", False))

    if getattr(args, "sync_plan", False):
        _warn_deprecated("--sync-plan 已改為 --goals-to-task-list（語意相同）")
        goals_to_task_list = True

    if getattr(args, "replan", False):
        _warn_deprecated("--replan 已改為 --replan-and-run（規劃後會繼續跑建構）")
        replan_and_run = True

    if getattr(args, "init_tasks", False):
        _warn_deprecated("--init-tasks 已改為 --replan-and-run")
        replan_and_run = True

    if getattr(args, "write_back_goals", False):
        _warn_deprecated(
            "--write-back-goals 已拆分："
            "規劃時寫回藍圖用 --export-goals-from-normalize；"
            "從 task_list 寫回藍圖用 --export-goals-from-task-list（可單獨使用）"
        )
        if goals_to_task_list or not replan_and_run:
            export_tl = True
        else:
            export_norm = True

    if goals_to_task_list and replan_and_run:
        raise SystemExit(
            "不可同時使用 --goals-to-task-list（只規劃）與 --replan-and-run（規劃並執行）。"
        )

    need_replan = goals_to_task_list or replan_and_run
    standalone_export = export_tl and not need_replan
    write_back_in_prepare = export_norm

    return PlanCliFlags(
        goals_to_task_list=goals_to_task_list,
        replan_and_run=replan_and_run,
        export_goals_from_normalize=export_norm,
        export_goals_from_task_list=export_tl,
        standalone_export_from_task_list=standalone_export,
        need_replan=need_replan,
        write_back_in_prepare=write_back_in_prepare,
    )


CLI_EPILOG = """
EXECUTE §12 統一入口:
  unity-mcp-harness --goals init|modify   ← 對話編輯 build_goals.yaml
  unity-mcp-harness --tools [--tools json]
  unity-mcp-harness --chat
  unity-mcp-harness --sync                ← task_list → build_goals
  unity-mcp-harness --status              ← MCP 盤點 + project_state 同步

藍圖 ↔ 執行隊列（常見流程）:
  1. 編輯 build_goals.yaml
  2. unity-mcp-harness --goals-to-task-list
     → 只更新 task_list.yaml，不跑 Unity
  3. unity-mcp-harness
     → 依 task_list 執行（沿用既有隊列，不會自動重規劃）
  改藍圖後要重算隊列並開工:
     unity-mcp-harness --replan-and-run

寫回 build_goals.yaml:
  --export-goals-from-task-list   ← 來源：既有 task_list（單獨指令即可）
  --export-goals-from-normalize   ← 來源：LLM 規範化（搭配 --replan-and-run）
  --goals-to-task-list --export-goals-from-task-list  ← 先藍圖→隊列，再寫回藍圖
"""
