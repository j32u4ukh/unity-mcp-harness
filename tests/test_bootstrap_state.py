"""--bootstrap-state CLI 與 run_bootstrap_state。"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from core.project_state.bootstrap import run_bootstrap_state
from core.project_state.paths import default_project_state_root
from core.scaffold.init_workspace import init_workspace


def test_bootstrap_state_requires_project_state_dir(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("UNITY_MCP_HOME", str(tmp_path))
    report = run_bootstrap_state(verify_mcp=False)
    assert not report.ok
    assert "init" in (report.message or "").lower() or "不存在" in (report.error or "")


def test_bootstrap_state_writes_files(tmp_path: Path, monkeypatch) -> None:
    init_workspace(tmp_path)
    monkeypatch.setenv("UNITY_MCP_HOME", str(tmp_path))

    fake_reply = (
        "場景: Assets/_Scenes/Demo.unity\n"
        "Hierarchy: Main Camera, Player\n"
        "2D: SpriteRenderer on Player"
    )

    with patch("core.project_state.bootstrap.ask_unity", return_value=fake_reply):
        with patch("core.project_state.bootstrap.verify_unity_mcp_connection"):
            report = run_bootstrap_state(verify_mcp=False)

    assert report.ok
    root = default_project_state_root()
    assert (root / "tasks" / "bootstrap_state.md").is_file()
    text = (root / "scenes" / "_overview.md").read_text(encoding="utf-8")
    assert "Demo" in text or "Player" in text
    assert (root / "assets" / "_overview.md").read_text(encoding="utf-8").find("基線盤點") >= 0


def test_parse_args_bootstrap_state_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["unity-mcp-harness", "--bootstrap-state"])
    from run_build import parse_args

    args = parse_args()
    assert args.bootstrap_state is True
