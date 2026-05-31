"""Harness 執行期進度日誌（stderr、即時 flush）。"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from typing import Any

ENV_QUIET = "HARNESS_QUIET"
ENV_VERBOSE = "HARNESS_VERBOSE"

_quiet = False
_verbose_detail = False


def configure_harness_log(
    *,
    quiet: bool = False,
    verbose: bool = False,
) -> None:
    """設定日誌層級；預設為一般進度（任務 / LLM 輪 / MCP tool）。"""
    global _quiet, _verbose_detail
    env_quiet = os.environ.get(ENV_QUIET, "").strip().lower() in ("1", "true", "yes")
    env_verbose = os.environ.get(ENV_VERBOSE, "").strip().lower() in ("1", "true", "yes")
    _quiet = quiet or env_quiet
    _verbose_detail = verbose or env_verbose


def is_quiet() -> bool:
    return _quiet


def is_verbose_detail() -> bool:
    return _verbose_detail


def _timestamp() -> str:
    return datetime.now().strftime("%H:%M:%S")


def harness_log(message: str, *, level: str = "INFO") -> None:
    """寫入 stderr 並立即 flush。"""
    if _quiet and level not in ("ERROR", "WARN"):
        return
    print(f"[{_timestamp()}] [{level}] {message}", file=sys.stderr, flush=True)


def log_task_start(task_id: str, title: str, *, index: int | None = None) -> None:
    prefix = f"({index}) " if index is not None else ""
    harness_log(f"▶ 任務開始 {prefix}[{task_id}] {title}")


def log_task_end(
    task_id: str,
    *,
    success: bool,
    verification: str | None = None,
    error: str | None = None,
) -> None:
    status = "OK" if success else "FAIL"
    parts = [f"■ 任務結束 [{task_id}] {status}"]
    if verification:
        parts.append(f"verification={verification}")
    if error:
        parts.append(error[:200])
    level = "INFO" if success else "ERROR"
    harness_log(" | ".join(parts), level=level)


def log_llm_round(round_no: int, *, tool_count: int = 0) -> None:
    if tool_count:
        harness_log(f"  ↳ LLM 第 {round_no} 輪完成，模型要求 {tool_count} 個 tool")
    else:
        harness_log(f"  ↳ LLM 第 {round_no} 輪完成（無 tool_calls）")


def log_llm_request(round_no: int) -> None:
    harness_log(f"  → LLM 第 {round_no} 輪請求中…")


def log_mcp_tool(
    server: str,
    tool_name: str,
    arguments: dict[str, Any] | None,
    *,
    result_preview: str | None = None,
    error: str | None = None,
) -> None:
    args_text = _preview_json(arguments or {})
    if error:
        harness_log(
            f"  ✗ MCP [{server}] {tool_name}({args_text}) — {error[:300]}",
            level="ERROR",
        )
        return
    preview = result_preview or ""
    if len(preview) > 240:
        preview = preview[:239] + "…"
    harness_log(f"  ✓ MCP [{server}] {tool_name}({args_text})")
    if _verbose_detail and preview:
        harness_log(f"      回傳: {preview}")


def log_agent_start(*, model: str | None, max_tool_rounds: int) -> None:
    harness_log(f"Agent 開始（model={model or 'default'}, max_tool_rounds={max_tool_rounds}）")


def log_verification_start(task_id: str) -> None:
    harness_log(f"  ◎ Harness 驗證開始 [{task_id}]…")


def log_verification_end(task_id: str, *, passed: bool, summary: str) -> None:
    level = "INFO" if passed else "WARN"
    harness_log(
        f"  ◎ Harness 驗證結束 [{task_id}] {'通過' if passed else '未通過'}: {summary[:200]}",
        level=level,
    )


def log_prompt_excerpt(prompt: str, *, max_len: int = 120) -> None:
    text = " ".join((prompt or "").split())
    if len(text) > max_len:
        text = text[: max_len - 1] + "…"
    harness_log(f"  prompt: {text}")


def log_plan_normalize_start(
    *,
    model: str,
    blueprint_tasks: int,
    plan_revision: int,
) -> None:
    harness_log(
        f"Plan Normalize 開始（model={model}，藍圖任務={blueprint_tasks}，revision={plan_revision}）"
    )


def log_plan_normalize_llm_attempt(*, mode: str, attempt: int) -> None:
    harness_log(f"  → Plan Normalize LLM 請求（mode={mode}，第 {attempt} 次）…")


def log_plan_normalize_llm_done(*, mode: str, task_count: int) -> None:
    harness_log(f"  ↳ Plan Normalize LLM 完成（mode={mode}，{task_count} 條 normalized_tasks）")


def log_plan_normalize_fallback(reason: str) -> None:
    text = " ".join((reason or "").split())
    if len(text) > 400:
        text = text[:399] + "…"
    harness_log(f"Plan Normalize 失敗，改用 passthrough: {text}", level="WARN")


def log_prepare_phase(phase: str) -> None:
    harness_log(f"▶ {phase}")


def _preview_json(value: Any, *, max_len: int = 160) -> str:
    try:
        text = json.dumps(value, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        text = str(value)
    if len(text) > max_len:
        return text[: max_len - 1] + "…"
    return text
