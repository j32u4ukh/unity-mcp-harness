#!/usr/bin/env python3
"""列出已註冊 Unity MCP server 的工具（不呼叫 LLM）。"""

from __future__ import annotations

import argparse
import json
import sys

from unity_common import (
    handle_errors,
    list_unity_tools,
    registered_server_names,
    require_aicentral_config,
    resolve_server_specs,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="列出 Unity MCP 工具")
    parser.add_argument("-c", "--config", type=str, default=None, help="Unity MCP 設定 JSON")
    parser.add_argument(
        "--json",
        action="store_true",
        help="以 JSON 輸出（否則為可讀文字）",
    )
    return parser.parse_args()


def main() -> None:
    require_aicentral_config()
    args = parse_args()

    try:
        specs = resolve_server_specs(config_path=args.config) if args.config else resolve_server_specs()
        tools_map = list_unity_tools(specs=specs, config_path=args.config)
    except Exception as exc:
        handle_errors(exc)
        sys.exit(1)

    if args.json:
        print(json.dumps(tools_map, ensure_ascii=False, indent=2))
        return

    names = registered_server_names(specs)
    print(f"Unity MCP servers: {', '.join(names)}")
    print("-" * 40)
    for server, tools in tools_map.items():
        print(f"[{server}] {len(tools)} 個工具")
        for tool in tools:
            tname = tool.get("name", "?")
            desc = (tool.get("description") or "")[:80]
            line = f"  - {tname}: {desc}"
            try:
                print(line)
            except UnicodeEncodeError:
                enc = getattr(sys.stdout, "encoding", None) or "utf-8"
                print(line.encode(enc, errors="replace").decode(enc))


if __name__ == "__main__":
    main()
