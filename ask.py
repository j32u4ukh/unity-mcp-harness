#!/usr/bin/env python3
"""單次提問：aicentral + 一至多個 Unity MCP Server。"""

from __future__ import annotations

import argparse
import sys

from unity_common import (
    ask_unity,
    handle_errors,
    print_banner,
    registered_server_names,
    require_aicentral_config,
    resolve_server_specs,
    resolve_unity_llm_model,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Unity MCP 單次問答")
    parser.add_argument("question", nargs="?", default=None, help="問題（省略則從 stdin 讀一行）")
    parser.add_argument("-c", "--config", type=str, default=None, help="Unity MCP 設定 JSON")
    parser.add_argument(
        "-s",
        "--servers",
        type=str,
        default=None,
        help="server 名稱，逗號分隔（預設：設定檔內全部）",
    )
    return parser.parse_args()


def main() -> None:
    require_aicentral_config()
    args = parse_args()

    specs = resolve_server_specs(config_path=args.config) if args.config else resolve_server_specs()
    if args.servers:
        mcp_servers = [s.strip() for s in args.servers.split(",") if s.strip()]
    else:
        mcp_servers = registered_server_names(specs)

    model = resolve_unity_llm_model(None)
    prompt = args.question
    if not prompt:
        prompt = input("你: ").strip() or "列出目前 Unity 專案可用的 MCP 工具"

    server_list = mcp_servers if isinstance(mcp_servers, list) else [mcp_servers]
    print_banner(
        title="Unity MCP 單次問答",
        model=model,
        server_names=server_list,
        specs=specs,
        interactive=False,
    )

    try:
        reply = ask_unity(
            prompt,
            mcp_servers=mcp_servers,
            model=model,
            specs=specs,
            config_path=args.config,
        )
        print(f"\n助理: {reply}")
    except Exception as exc:
        handle_errors(exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
