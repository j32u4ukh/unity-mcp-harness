#!/usr/bin/env python3
"""Unity 專案探索：多輪 REPL，透過 MCP 查詢 Editor 現況並討論。"""

from __future__ import annotations

import argparse

from aicentral import Chat

from unity_common import (
    EXIT_COMMANDS,
    add_harness_llm_config_args,
    add_unity_mcp_config_arg,
    handle_errors,
    print_banner,
    registered_server_names,
    require_aicentral_config,
    resolve_server_specs,
    resolve_unity_llm_model,
)
from unity_explore import (
    REPL_HELP,
    build_explore_system_prompt,
    format_tools_summary,
    load_explore_settings,
    verify_unity_mcp_connection,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Unity 專案探索（多輪）：連線 Unity MCP，查詢場景／資產現況並討論",
    )
    add_harness_llm_config_args(parser)
    add_unity_mcp_config_arg(parser)
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
    parser.add_argument(
        "--no-probe",
        action="store_true",
        help="啟動時不做唯讀現況探查（仍會驗證 MCP 工具可用）",
    )
    parser.add_argument(
        "--probe",
        action="store_true",
        help="啟動時強制做一次唯讀現況探查（覆寫 config 的 probe_on_chat_start）",
    )
    return parser.parse_args()


def _resolve_servers(args: argparse.Namespace, specs: dict) -> list[str]:
    if args.servers:
        return [s.strip() for s in args.servers.split(",") if s.strip()]
    return registered_server_names(specs)


def _print_tools(tools_map: dict) -> None:
    print("可用 MCP 工具：")
    print(format_tools_summary(tools_map))
    print()


def _run_probe(chat: Chat, probe_prompt: str) -> None:
    print("【Editor 現況探查】")
    try:
        reply = chat.ask(probe_prompt)
        print(f"助理: {reply}")
    except Exception as exc:
        handle_errors(exc)
    print()


def run_repl(
    chat: Chat,
    *,
    tools_map: dict,
    probe_prompt: str,
) -> None:
    """互動 REPL：支援 /help、/tools、/status。"""
    print(REPL_HELP.strip())
    print("-" * 40)

    while True:
        try:
            user_input = input("你: ").strip()
        except EOFError:
            print()
            break
        if not user_input:
            continue
        lower = user_input.lower()
        if lower in EXIT_COMMANDS:
            print("再見。")
            break
        if lower in ("/help", "help", "?"):
            print(REPL_HELP.strip())
            continue
        if lower == "/tools":
            _print_tools(tools_map)
            continue
        if lower == "/status":
            _run_probe(chat, probe_prompt)
            continue

        try:
            reply = chat.ask(user_input)
            print(f"助理: {reply}")
        except KeyboardInterrupt:
            print("\n（已取消本輪）")
        except Exception as exc:
            handle_errors(exc)
        print()


def run_interactive_chat(
    *,
    unity_config: str | None = None,
    servers: str | None = None,
    no_tool_history: bool = False,
    no_probe: bool = False,
    probe: bool = False,
    aicentral_config: str | None = None,
    secret: str | None = None,
) -> None:
    """執行探索 REPL（供 unity-mcp-chat 與 unity-mcp-harness --chat 共用）。"""
    require_aicentral_config(aicentral_config=aicentral_config, secret=secret)
    explore = load_explore_settings()

    specs = (
        resolve_server_specs(config_path=unity_config)
        if unity_config
        else resolve_server_specs()
    )
    tools_map = verify_unity_mcp_connection(specs=specs, config_path=unity_config)
    if servers:
        server_names = [s.strip() for s in servers.split(",") if s.strip()]
    else:
        server_names = registered_server_names(specs)

    from unity_common import create_unity_chat

    model = resolve_unity_llm_model(None)
    system = build_explore_system_prompt(server_names=server_names, settings=explore)

    print_banner(
        title="Unity 專案探索（多輪 REPL）",
        model=model,
        server_names=server_names,
        detail="模式：先以 MCP 查詢 Editor 現況，再回答與討論（非純聊天）",
        specs=specs,
        interactive=True,
        aicentral_config=aicentral_config,
        secret=secret,
    )
    print("可用 MCP 工具：")
    print(format_tools_summary(tools_map))

    chat = create_unity_chat(
        server_names,
        model=model,
        system=system,
        max_tool_rounds=explore.max_tool_rounds,
        specs=specs,
        config_path=unity_config,
        include_tool_messages_in_history=not no_tool_history,
    )

    do_probe = probe or (explore.probe_on_chat_start and not no_probe)
    if do_probe:
        _run_probe(chat, explore.probe_prompt)

    try:
        run_repl(chat, tools_map=tools_map, probe_prompt=explore.probe_prompt)
    except KeyboardInterrupt:
        print("\n再見。")


def main() -> None:
    args = parse_args()
    print(
        "提示: 亦可使用 unity-mcp-harness --chat（統一入口）。",
        file=__import__("sys").stderr,
    )
    run_interactive_chat(
        unity_config=args.unity_config,
        servers=args.servers,
        no_tool_history=args.no_tool_history,
        no_probe=args.no_probe,
        probe=args.probe,
        aicentral_config=args.aicentral_config,
        secret=args.secret,
    )


if __name__ == "__main__":
    main()
