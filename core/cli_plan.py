"""建構 CLI：藍圖 ↔ task_list 旗標解析（含舊旗標相容）。"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass


@dataclass(frozen=True)
class PlanCliFlags:
    """解析後的規劃／寫回旗標。"""

    sync_blueprint_only: bool
    """僅 build_goals → Plan Normalize → task_list，不跑 Unity 建構。"""

    export_goals_from_normalize: bool
    """將 Plan Normalize 結果寫入 build_goals.yaml（非 task_list）。"""

    export_goals_from_task_list: bool
    """將 task_list 規劃欄位寫入 build_goals.yaml。"""

    standalone_export_from_task_list: bool
    """僅 --export-goals-from-task-list：讀既有 task_list 寫回藍圖，不規劃、不建構。"""

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
    """註冊規劃相關參數（進階寫回；日常請用 ``--goals build``）。"""
    plan = parser.add_argument_group(
        "藍圖寫回（進階）",
        "日常規劃請用：unity-mcp-harness --goals build",
    )
    plan.add_argument(
        "--export-goals-from-normalize",
        action="store_true",
        help="規劃時將 Plan Normalize 結果寫回 build_goals.yaml 的 tasks",
    )
    plan.add_argument(
        "--export-goals-from-task-list",
        action="store_true",
        help=(
            "將 task_list.yaml 規劃欄位寫回 build_goals.yaml（不含 status/verification）。"
            "可單獨使用；搭配 --goals build 則先藍圖→隊列再寫回。"
        ),
    )
    plan.add_argument(
        "--backup",
        action="store_true",
        help="與任一 --export-goals-* 合用：寫回 build_goals 前備份 .bak",
    )

    compat = parser.add_argument_group("相容舊參數（將移除）")
    compat.add_argument(
        "--goals-to-task-list",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    compat.add_argument(
        "--replan-and-run",
        action="store_true",
        help=argparse.SUPPRESS,
    )
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
    """解析旗標；舊參數映射到 ``--goals build`` 語意（僅規劃，不執行建構）。"""
    sync_only = False
    export_norm = bool(getattr(args, "export_goals_from_normalize", False))
    export_tl = bool(getattr(args, "export_goals_from_task_list", False))

    _LEGACY_SYNC = (
        ("sync_plan", "--sync-plan"),
        ("goals_to_task_list", "--goals-to-task-list"),
        ("replan", "--replan"),
        ("init_tasks", "--init-tasks"),
        ("replan_and_run", "--replan-and-run"),
    )
    for attr, flag in _LEGACY_SYNC:
        if getattr(args, attr, False):
            _warn_deprecated(
                f"{flag} 已改為 unity-mcp-harness --goals build（只更新 task_list，不會執行 Unity 建構）"
            )
            sync_only = True

    if getattr(args, "write_back_goals", False):
        _warn_deprecated(
            "--write-back-goals 已拆分："
            "規劃時寫回藍圖用 --export-goals-from-normalize；"
            "從 task_list 寫回藍圖用 --export-goals-from-task-list"
        )
        if getattr(args, "replan", False) or getattr(args, "replan_and_run", False):
            export_norm = True
        elif sync_only:
            export_tl = True
        else:
            export_norm = True

    standalone_export = export_tl and not sync_only
    write_back_in_prepare = export_norm

    return PlanCliFlags(
        sync_blueprint_only=sync_only,
        export_goals_from_normalize=export_norm,
        export_goals_from_task_list=export_tl,
        standalone_export_from_task_list=standalone_export,
        write_back_in_prepare=write_back_in_prepare,
    )


CLI_EPILOG = """
EXECUTE §12 統一入口（無參數時顯示速查）:
  unity-mcp-harness --goals build     ← build_goals → task_list
  unity-mcp-harness --goals init|modify
  unity-mcp-harness --tasks run       ← 執行 task_list（Unity MCP）
  unity-mcp-harness --tasks modify   ← 討論累積草案，/write 合併寫入
  unity-mcp-harness --tools [--tools json]
  unity-mcp-harness --chat
  unity-mcp-harness --sync
  unity-mcp-harness --status

常見流程:
  1. 編輯 build_goals.yaml
  2. unity-mcp-harness --goals build
  3. unity-mcp-harness --tasks run
"""
