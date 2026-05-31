"""EXECUTE.md §12 統一 CLI 入口。"""

from __future__ import annotations

import sys

import pytest

from core.cli_extended import (
    EXECUTE_SECTION_12_TAG,
    capabilities_marker_path,
    write_capabilities_marker,
)
from run_build import parse_args


def test_parse_args_execute12_flags(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["unity-mcp-harness", "--tools", "json"])
    args = parse_args()
    assert args.tools == "json"
    monkeypatch.setattr(sys, "argv", ["unity-mcp-harness", "--chat"])
    args = parse_args()
    assert args.chat is True
    monkeypatch.setattr(sys, "argv", ["unity-mcp-harness", "--sync"])
    args = parse_args()
    assert args.sync is True
    monkeypatch.setattr(sys, "argv", ["unity-mcp-harness", "--status"])
    args = parse_args()
    assert args.status is True
    monkeypatch.setattr(sys, "argv", ["unity-mcp-harness", "--goals", "init"])
    args = parse_args()
    assert args.goals_mode == "init"
    monkeypatch.setattr(sys, "argv", ["unity-mcp-harness", "--goals-file", "x.yaml"])
    args = parse_args()
    assert args.goals_file == "x.yaml"


def test_capabilities_marker(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        "core.cli_extended.project_root",
        lambda: tmp_path,
    )
    path = write_capabilities_marker()
    assert path.is_file()
    assert EXECUTE_SECTION_12_TAG in path.read_text(encoding="utf-8")
    assert capabilities_marker_path().name == "harness_capabilities.marker"
