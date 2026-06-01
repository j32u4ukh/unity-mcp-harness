"""CLI 入口與 --tasks 解析。"""

import sys

import pytest

from core.cli_entry import has_cli_action, print_harness_entry_help
from run_build import parse_args


def test_bare_harness_has_no_action(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["unity-mcp-harness"])
    args = parse_args()
    assert not has_cli_action(args)


def test_goals_build_is_action(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["unity-mcp-harness", "--goals", "build"])
    args = parse_args()
    assert args.goals_mode == "build"
    assert has_cli_action(args)


def test_tasks_run_is_action(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["unity-mcp-harness", "--tasks", "run"])
    args = parse_args()
    assert args.tasks_mode == "run"
    assert has_cli_action(args)


def test_entry_help_prints(capsys) -> None:
    print_harness_entry_help()
    out = capsys.readouterr().out
    assert "--goals build" in out
    assert "--tasks run" in out
