"""Unity 專案探索：system prompt、MCP 連線驗證、啟動探查（供 chat / ask CLI）。"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from unity_common import (
    list_unity_tools,
    project_root,
    register_unity_servers,
    registered_server_names,
)

DEFAULT_EXPLORE_CONFIG = "config/unity_explore.yaml"

_FALLBACK_SYSTEM = """\
你是 Unity 專案探索助理。必須透過 Unity MCP 工具查詢 Editor 內真實現況後再回答，禁止臆測。
預設唯讀探索；修改資產前須先說明現況並確認。一律使用繁體中文。
"""

_FALLBACK_PROBE = (
    "唯讀：簡述目前開啟場景、Hierarchy 主要物件與可查到的 Sprite/元件資訊。"
    "不要修改任何東西。"
)


@dataclass(frozen=True)
class UnityExploreSettings:
    """``config/unity_explore.yaml`` 解析結果。"""

    system_prompt: str
    probe_prompt: str
    max_tool_rounds: int = 10
    probe_on_chat_start: bool = True


def explore_config_path() -> Path:
    """探索設定檔路徑（``UNITY_MCP_HOME/config/unity_explore.yaml``）。"""
    return project_root() / DEFAULT_EXPLORE_CONFIG


def load_explore_settings(path: Path | str | None = None) -> UnityExploreSettings:
    """載入探索設定；缺檔或欄位缺失時使用內建預設。"""
    p = Path(path) if path else explore_config_path()
    data: dict[str, Any] = {}
    if p.is_file():
        raw = yaml.safe_load(p.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            data = raw

    system = str(data.get("system_prompt") or "").strip() or _FALLBACK_SYSTEM.strip()
    probe = str(data.get("probe_prompt") or "").strip() or _FALLBACK_PROBE
    rounds = data.get("max_tool_rounds", 10)
    try:
        max_tool_rounds = max(1, int(rounds))
    except (TypeError, ValueError):
        max_tool_rounds = 10

    probe_on = data.get("probe_on_chat_start", True)
    probe_on_chat_start = bool(probe_on)

    return UnityExploreSettings(
        system_prompt=system,
        probe_prompt=probe,
        max_tool_rounds=max_tool_rounds,
        probe_on_chat_start=probe_on_chat_start,
    )


def format_tools_summary(tools_map: dict[str, list[dict[str, Any]]]) -> str:
    """將 ``list_unity_tools`` 結果格式化為可讀摘要。"""
    lines: list[str] = []
    for server, tools in sorted(tools_map.items()):
        names = [str(t.get("name", "?")) for t in tools]
        preview = ", ".join(names[:8])
        if len(names) > 8:
            preview += f", …（共 {len(names)} 個）"
        elif names:
            preview += f"（共 {len(names)} 個）"
        else:
            preview = "（無工具）"
        lines.append(f"  • [{server}] {preview}")
    return "\n".join(lines)


def verify_unity_mcp_connection(
    *,
    specs: dict[str, dict[str, Any]] | None = None,
    config_path: Path | str | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """
    註冊 MCP 並列出工具；若完全無工具則 ``SystemExit(1)``。

    回傳 ``{server_name: [tool, ...]}``。
    """
    register_unity_servers(specs, config_path=config_path)
    tools_map = list_unity_tools(specs=specs, config_path=config_path)
    total = sum(len(tools) for tools in tools_map.values())
    if total == 0:
        names = ", ".join(registered_server_names(specs, config_path=config_path)) or "?"
        print(
            f"Unity MCP 已連線但未取得任何工具（servers: {names}）。\n"
            "請確認 Unity Editor 已開啟、MCP 外掛已啟用，並執行 unity-mcp-list-tools --json 除錯。",
            file=sys.stderr,
        )
        sys.exit(1)
    return tools_map


def build_explore_system_prompt(
    *,
    server_names: list[str],
    settings: UnityExploreSettings | None = None,
) -> str:
    """組裝含 server 列表的 system prompt。"""
    cfg = settings or load_explore_settings()
    servers_line = "、".join(server_names) if server_names else "（未設定）"
    return (
        f"{cfg.system_prompt.rstrip()}\n\n"
        f"## 連線資訊\n"
        f"目前 Unity MCP servers：{servers_line}\n"
    )


REPL_HELP = """\
Unity 專案探索指令：
  /help     顯示此說明
  /tools    列出 MCP 工具名稱
  /status   重新探查 Editor 現況（唯讀，會呼叫 LLM + MCP）
  exit      結束對話
"""
