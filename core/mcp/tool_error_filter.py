"""Unity MCP 工具錯誤過濾：預期「找不到物件」降級 vs 真實系統錯誤。"""

from __future__ import annotations

import json
import re
from typing import Any

from core.harness_log import harness_log
from core.prompts.unity_observer_protocol import (
    ROUTE_TO_CREATE,
    ROUTE_TO_SELF_CORRECTION,
)

NOT_FOUND_GAMEOBJECT_RE = re.compile(
    r"Not found GameObject with name '([^']*)'",
    re.IGNORECASE,
)
NOT_FOUND_GAMEOBJECT_PATH_RE = re.compile(
    r"Not found GameObject at path '([^']*)'",
    re.IGNORECASE,
)
NOT_FOUND_GAMEOBJECT_ID_RE = re.compile(
    r"Not found GameObject with instanceID '([^']*)'",
    re.IGNORECASE,
)

# 連線 / 協定級錯誤：必須向上拋出，不可降級為 tool 文字
NON_RECOVERABLE_PATTERNS: tuple[str, ...] = (
    "connection refused",
    "connection revoked",
    "connect call failed",
    "jsonrpc",
    "timeout",
    "timed out",
    "未知 MCP server",
    "不在白名單",
)


def is_non_recoverable_mcp_error(error_text: str) -> bool:
    lower = error_text.lower()
    return any(p in lower for p in NON_RECOVERABLE_PATTERNS)


def extract_target_name(arguments: dict[str, Any]) -> str:
    """從 IvanMurzak / Coplay 工具參數推斷目標名稱。"""
    for key in ("name", "objectName", "gameObjectName", "targetName"):
        val = arguments.get(key)
        if val is not None and str(val).strip():
            return str(val).strip()
    filter_obj = arguments.get("filter")
    if isinstance(filter_obj, dict):
        for key in ("Name", "name"):
            val = filter_obj.get(key)
            if val:
                return str(val).strip()
    params = arguments.get("inputParameters")
    if isinstance(params, list):
        for item in params:
            if not isinstance(item, dict):
                continue
            if str(item.get("name", "")).lower() == "name":
                val = item.get("value")
                if val is not None:
                    return str(val).strip()
    return "未知物件"


def _match_not_found(error_text: str) -> re.Match[str] | None:
    for pattern in (
        NOT_FOUND_GAMEOBJECT_RE,
        NOT_FOUND_GAMEOBJECT_PATH_RE,
        NOT_FOUND_GAMEOBJECT_ID_RE,
    ):
        match = pattern.search(error_text)
        if match:
            return match
    if "not found gameobject" in error_text.lower():
        return NOT_FOUND_GAMEOBJECT_RE.search(
            "Not found GameObject with name 'unknown'"
        )
    return None


def build_expected_not_found_payload(
    *,
    target: str,
    tool_name: str,
    raw_error: str,
) -> dict[str, Any]:
    return {
        "status": "expected_not_found",
        "harness_next_action": ROUTE_TO_CREATE,
        "target_object": target,
        "tool": tool_name,
        "message": (
            f"System Notice: GameObject '{target}' does not exist in the current "
            "hierarchy. This is EXPECTED during pre-creation verification. "
            "Proceed to CREATE / SPAWN this GameObject immediately."
        ),
        "raw_unity_notice": raw_error[:500],
    }


def build_fatal_error_payload(
    *,
    tool_name: str,
    raw_error: str,
) -> dict[str, Any]:
    return {
        "status": "system_fatal_error",
        "harness_next_action": ROUTE_TO_SELF_CORRECTION,
        "tool": tool_name,
        "message": (
            "System Fatal Error: unexpected Unity/MCP failure. "
            "Analyze parameters, syntax, or scene state and self-correct."
        ),
        "detail": raw_error[:2000],
    }


def try_downgrade_tool_error(
    error_text: str,
    *,
    tool_name: str,
    arguments: dict[str, Any],
) -> tuple[str | None, str | None]:
    """
    若為預期「找不到 GameObject」，回傳 (json_content, next_action)。
    否則回傳 (None, None) 表示呼叫方自行決定是否包成 fatal 或 re-raise。
    """
    if not error_text or is_non_recoverable_mcp_error(error_text):
        return None, None

    match = _match_not_found(error_text)
    if match is None:
        return None, None

    target = match.group(1) if match.lastindex else extract_target_name(arguments)
    if target in ("unknown", "未知物件", ""):
        target = extract_target_name(arguments)

    payload = build_expected_not_found_payload(
        target=target,
        tool_name=tool_name,
        raw_error=error_text,
    )
    harness_log(
        f"[Harness Filter] 場景中不存在 '{target}'（預期內）→ {ROUTE_TO_CREATE}"
    )
    return json.dumps(payload, ensure_ascii=False), ROUTE_TO_CREATE


def format_fatal_tool_content(
    error_text: str,
    *,
    tool_name: str,
) -> tuple[str, str]:
    payload = build_fatal_error_payload(tool_name=tool_name, raw_error=error_text)
    harness_log(
        f"[Harness Fatal] 未預期工具錯誤（{tool_name}）→ {ROUTE_TO_SELF_CORRECTION}",
        level="ERROR",
    )
    return json.dumps(payload, ensure_ascii=False), ROUTE_TO_SELF_CORRECTION


def extract_error_text_from_tool_result(result: Any) -> str | None:
    """從 MCP CallToolResult 或 dict 取出錯誤文字。"""
    if result is None:
        return None

    is_error = getattr(result, "isError", None)
    if is_error is None and isinstance(result, dict):
        is_error = result.get("isError") or result.get("is_error")

    content = getattr(result, "content", None)
    if content is None and isinstance(result, dict):
        content = result.get("content")

    parts: list[str] = []
    if isinstance(content, list):
        for block in content:
            text = getattr(block, "text", None)
            if text is None and isinstance(block, dict):
                text = block.get("text")
            if text:
                parts.append(str(text))
    elif isinstance(content, str):
        parts.append(content)

    structured = getattr(result, "structuredContent", None)
    if structured is None and isinstance(result, dict):
        structured = result.get("structuredContent") or result.get("structured_content")
    if structured is not None:
        try:
            parts.append(json.dumps(structured, ensure_ascii=False, default=str))
        except (TypeError, ValueError):
            parts.append(str(structured))

    if not parts and not is_error:
        text = str(result)
        if "Not found GameObject" in text:
            parts.append(text)

    if not parts:
        return None if not is_error else "MCP tool returned isError with empty content"

    combined = "\n".join(parts)
    if is_error or "Not found GameObject" in combined or "Exception" in combined:
        return combined
    return None
