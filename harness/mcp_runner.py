"""Unity MCP 建構橋接：LangGraph / unity-mcp-harness 經本模組使用 aicentral ``Chat.with_mcp``。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from aicentral import Chat
from aicentral.routing.router import effective_model


class UnityMCPRunner:
    """封裝已啟用 MCP 的 aicentral ``Chat`` 工作階段（供多輪建構任務共用）。"""

    def __init__(self, chat: Chat, *, mcp_servers: list[str]) -> None:
        self._chat = chat
        self.mcp_servers = list(mcp_servers)

    def ask(self, prompt: str) -> str:
        """單輪提問（含 MCP tool loop）。"""
        return self._chat.ask(prompt)

    @property
    def chat(self) -> Chat:
        return self._chat


def create_unity_mcp_runner(
    mcp_servers: list[str] | str,
    *,
    model: str | None = None,
    max_tool_rounds: int = 8,
    include_tool_messages_in_history: bool = True,
    specs: dict[str, dict[str, Any]] | None = None,
    config_path: Path | str | None = None,
) -> UnityMCPRunner:
    """建立 runner；MCP 註冊委派 ``unity_common.register_unity_servers``。"""
    if specs is not None:
        from unity_common import register_unity_servers

        register_unity_servers(specs, config_path=config_path)
    servers = mcp_servers if isinstance(mcp_servers, list) else [mcp_servers]
    chat = Chat.with_mcp(
        servers,
        model=model or effective_model(None),
        max_tool_rounds=max_tool_rounds,
        include_tool_messages_in_history=include_tool_messages_in_history,
    )
    return UnityMCPRunner(chat, mcp_servers=servers)


def ask_unity_mcp(
    question: str,
    *,
    runner: UnityMCPRunner | None = None,
    mcp_servers: list[str] | str | None = None,
    model: str | None = None,
    max_tool_rounds: int = 8,
    specs: dict[str, dict[str, Any]] | None = None,
    config_path: Path | str | None = None,
) -> str:
    """單次 Unity MCP 問答。"""
    session = runner or create_unity_mcp_runner(
        mcp_servers or ["unity"],
        model=model,
        max_tool_rounds=max_tool_rounds,
        specs=specs,
        config_path=config_path,
    )
    return session.ask(question)
