"""unity-mcp-harness 無子指令時的入口說明。"""

from __future__ import annotations

import argparse

HARNESS_ENTRY_HELP = """
Unity MCP Harness — 統一入口

藍圖（build_goals.yaml）
  unity-mcp-harness --goals build      藍圖 → task_list（Plan Normalize，不跑 Unity）
  unity-mcp-harness --goals init       對話建立藍圖
  unity-mcp-harness --goals modify     對話調整藍圖 tasks

執行隊列（task_list.yaml）
  unity-mcp-harness --tasks run        依 task_list 執行 Unity MCP 建構
  unity-mcp-harness --tasks modify     對話調整 task_list 任務描述

其他
  unity-mcp-harness --tools [json]     列出 MCP 工具
  unity-mcp-harness --chat             專案探索 REPL
  unity-mcp-harness --sync             task_list → build_goals
  unity-mcp-harness --status           MCP 盤點 + project_state 同步

常見流程
  1. 編輯 build_goals.yaml
  2. unity-mcp-harness --goals build
  3. unity-mcp-harness --tasks run

完整參數：unity-mcp-harness --help
"""


def print_harness_entry_help() -> None:
    print(HARNESS_ENTRY_HELP.strip())


_LEGACY_ACTION_ATTRS = (
    "goals_to_task_list",
    "replan_and_run",
    "replan",
    "init_tasks",
    "sync_plan",
    "write_back_goals",
    "export_goals_from_task_list",
    "export_goals_from_normalize",
)


def has_cli_action(args: argparse.Namespace) -> bool:
    """是否已指定子指令或會觸發工作的舊旗標。"""
    if getattr(args, "tools", None) is not None:
        return True
    if getattr(args, "chat", False) or getattr(args, "sync", False) or getattr(args, "status", False):
        return True
    if getattr(args, "goals_mode", None) is not None:
        return True
    if getattr(args, "tasks_mode", None) is not None:
        return True
    if getattr(args, "init", None) is not None:
        return True
    if getattr(args, "bootstrap_state", False) or getattr(args, "sync_project_state", False):
        return True
    if any(getattr(args, name, False) for name in _LEGACY_ACTION_ATTRS):
        return True
    return False
