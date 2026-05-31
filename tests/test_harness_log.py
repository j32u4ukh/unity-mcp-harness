"""Harness 進度日誌與 progress hooks 測試。"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from core.harness_log import configure_harness_log, harness_log, log_mcp_tool
from core.progress_hooks import harness_progress_hooks


def test_harness_log_quiet(capsys: pytest.CaptureFixture[str]) -> None:
    configure_harness_log(quiet=True)
    harness_log("hidden")
    harness_log("shown", level="ERROR")
    err = capsys.readouterr().err
    assert "hidden" not in err
    assert "shown" in err
    configure_harness_log(quiet=False)


def test_harness_log_default(capsys: pytest.CaptureFixture[str]) -> None:
    configure_harness_log(quiet=False)
    harness_log("progress")
    assert "progress" in capsys.readouterr().err


def test_log_mcp_tool_verbose_preview(capsys: pytest.CaptureFixture[str]) -> None:
    configure_harness_log(verbose=True)
    log_mcp_tool("unity", "assets-find", {"filter": "t:Sprite"}, result_preview="found 3")
    err = capsys.readouterr().err
    assert "assets-find" in err
    assert "回傳" in err
    configure_harness_log(verbose=False)


def test_progress_hooks_restores_call_tool() -> None:
    import aicentral.mcp.manager as mgr_mod

    original = mgr_mod.MCPManager.call_tool
    with harness_progress_hooks():
        assert mgr_mod.MCPManager.call_tool is not original
    assert mgr_mod.MCPManager.call_tool is original


def test_progress_hooks_logs_invoke_resolved(capsys: pytest.CaptureFixture[str]) -> None:
    import aicentral.mcp.orchestrator as orch

    configure_harness_log(quiet=False)
    original = orch.invoke_resolved

    def fake_invoke(*_args: Any, **_kwargs: Any) -> dict:
        return {
            "choices": [
                {"message": {"role": "assistant", "content": "ok", "tool_calls": []}}
            ]
        }

    orch.invoke_resolved = fake_invoke
    try:
        with harness_progress_hooks():
            orch.invoke_resolved(MagicMock(), [], raw=True)
    finally:
        orch.invoke_resolved = original

    err = capsys.readouterr().err
    assert "LLM 第 1 輪請求" in err
    assert "LLM 第 1 輪完成" in err
