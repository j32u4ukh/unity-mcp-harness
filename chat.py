#!/usr/bin/env python3
"""多輪對話：透過 aicentral.Chat 呼叫一至多個 Unity MCP Server。"""

from __future__ import annotations

import argparse

from aicentral import Chat

from unity_common import (
    EXIT_COMMANDS,
    create_unity_chat,
    handle_errors,
    print_banner,
    register_unity_servers,
    registered_server_names,
    require_aicentral_config,
    resolve_server_specs,
    resolve_unity_llm_model,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Unity MCP 多輪對話（aicentral Chat）")
    parser.add_argument(
        "-c",
        "--config",
        type=str,
        default=None,
        help="Unity MCP 設定 JSON（預設 unity_servers.json；無檔時 fallback HTTP :8080）",
    )
    parser.add_argument(
        "-s",
        "--servers",
        type=str,
        default=None,
        help="要使用的 server 名稱，逗號分隔（預設：設定檔內全部）",
    )
    parser.add_argument(
        "--no-tool-history",
        action="store_true",
        help="不將 MCP tool 訊息寫入 Chat 歷史（預設會寫入）",
    )
    return parser.parse_args()


def run_repl(chat: Chat) -> None:
    """互動 REPL：每輪 ``chat.ask``。"""
    while True:
        try:
            user_input = input("你: ").strip()
        except EOFError:
            print()
            break
        if not user_input:
            continue
        if user_input.lower() in EXIT_COMMANDS:
            print("再見。")
            break
        try:
            reply = chat.ask(user_input)
            print(f"助理: {reply}")
        except KeyboardInterrupt:
            print("\n（已取消本輪）")
        except Exception as exc:
            handle_errors(exc)
        print()


def main() -> None:
    require_aicentral_config()
    args = parse_args()

    # 載入並執行期註冊 Unity MCP（不修改 aicentral/config/aicentral.yaml）
    config_path = args.config
    specs = resolve_server_specs(config_path=config_path) if config_path else resolve_server_specs()
    register_unity_servers(specs)

    if args.servers:
        server_names = [s.strip() for s in args.servers.split(",") if s.strip()]
    else:
        server_names = registered_server_names(specs)

    model = resolve_unity_llm_model(None)
    print_banner(
        title="Unity MCP 多輪對話",
        model=model,
        server_names=server_names,
        specs=specs,
        interactive=True,
    )

    chat = create_unity_chat(
        server_names,
        model=model,
        specs=specs,
        include_tool_messages_in_history=not args.no_tool_history,
    )
    try:
        run_repl(chat)
    except KeyboardInterrupt:
        print("\n再見。")


if __name__ == "__main__":
    main()
