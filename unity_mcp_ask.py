#!/usr/bin/env python3
"""Unity 專案探索：單次提問，透過 MCP 查詢 Editor 現況。"""

from __future__ import annotations

import argparse
import sys

from unity_common import (
    add_harness_llm_config_args,
    add_unity_mcp_config_arg,
    ask_unity,
    handle_errors,
    print_banner,
    registered_server_names,
    require_aicentral_config,
    resolve_server_specs,
    resolve_unity_llm_model,
)
from unity_explore import (
    build_explore_system_prompt,
    format_tools_summary,
    load_explore_settings,
    verify_unity_mcp_connection,
)

_DEFAULT_QUESTION = (
    "請透過 Unity MCP 工具查詢並說明：目前開啟的場景、Hierarchy 主要物件、"
    "以及範例 Sprite／2D 相關資產的名稱與路徑（若存在）。"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Unity 專案探索（單次）：連線 Unity MCP 查詢 Editor 現況",
    )
    add_harness_llm_config_args(parser)
    add_unity_mcp_config_arg(parser)
    parser.add_argument(
        "question",
        nargs="?",
        default=None,
        help="問題（省略則使用預設探索 prompt 或從 stdin 讀一行）",
    )
    parser.add_argument(
        "-s",
        "--servers",
        type=str,
        default=None,
        help="server 名稱，逗號分隔（預設：設定檔內全部）",
    )
    parser.add_argument(
        "--probe",
        action="store_true",
        help="使用 config/unity_explore.yaml 的 probe_prompt 作為問題",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    require_aicentral_config(
        aicentral_config=args.aicentral_config,
        secret=args.secret,
    )
    explore = load_explore_settings()

    specs = (
        resolve_server_specs(config_path=args.unity_config)
        if args.unity_config
        else resolve_server_specs()
    )
    tools_map = verify_unity_mcp_connection(
        specs=specs,
        config_path=args.unity_config,
    )

    if args.servers:
        mcp_servers = [s.strip() for s in args.servers.split(",") if s.strip()]
    else:
        mcp_servers = registered_server_names(specs)

    model = resolve_unity_llm_model(None)
    system = build_explore_system_prompt(server_names=mcp_servers, settings=explore)

    if args.probe:
        prompt = explore.probe_prompt
    elif args.question:
        prompt = args.question
    else:
        prompt = input("你: ").strip() or _DEFAULT_QUESTION

    print_banner(
        title="Unity 專案探索（單次）",
        model=model,
        server_names=mcp_servers if isinstance(mcp_servers, list) else [mcp_servers],
        detail="模式：先以 MCP 查詢 Editor 現況，再回答（非純聊天）",
        specs=specs,
        interactive=False,
        aicentral_config=args.aicentral_config,
        secret=args.secret,
    )
    print("可用 MCP 工具：")
    print(format_tools_summary(tools_map))
    print("-" * 40)

    try:
        reply = ask_unity(
            prompt,
            mcp_servers=mcp_servers,
            model=model,
            system=system,
            max_tool_rounds=explore.max_tool_rounds,
            specs=specs,
            config_path=args.unity_config,
        )
        print(f"\n助理: {reply}")
    except Exception as exc:
        handle_errors(exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
