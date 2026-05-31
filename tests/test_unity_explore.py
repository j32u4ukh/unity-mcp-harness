"""unity_explore 單元測試。"""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from unity_explore import (
    build_explore_system_prompt,
    format_tools_summary,
    load_explore_settings,
    verify_unity_mcp_connection,
)


def test_load_explore_settings_fallback(tmp_path: Path) -> None:
    cfg = load_explore_settings(tmp_path / "missing.yaml")
    assert "Unity 專案探索" in cfg.system_prompt or "Unity" in cfg.system_prompt
    assert cfg.max_tool_rounds >= 1
    assert cfg.probe_prompt


def test_load_explore_settings_from_file(tmp_path: Path) -> None:
    p = tmp_path / "unity_explore.yaml"
    p.write_text(
        "max_tool_rounds: 5\n"
        "probe_on_chat_start: false\n"
        "system_prompt: |\n  自訂 system\n"
        "probe_prompt: |\n  自訂 probe\n",
        encoding="utf-8",
    )
    cfg = load_explore_settings(p)
    assert cfg.max_tool_rounds == 5
    assert cfg.probe_on_chat_start is False
    assert "自訂 system" in cfg.system_prompt
    assert "自訂 probe" in cfg.probe_prompt


def test_build_explore_system_prompt_includes_servers() -> None:
    text = build_explore_system_prompt(
        server_names=["unity", "other"],
        settings=load_explore_settings(Path("/nonexistent")),
    )
    assert "unity" in text
    assert "other" in text


def test_format_tools_summary() -> None:
    text = format_tools_summary(
        {
            "unity": [
                {"name": "get_scene"},
                {"name": "list_assets"},
            ]
        }
    )
    assert "get_scene" in text
    assert "共 2 個" in text


def test_verify_unity_mcp_connection_exits_when_no_tools(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "unity_explore.UnityMcpServerSession",
        lambda *a, **k: MagicMock(__enter__=lambda s: s, __exit__=lambda *a: None),
    )
    monkeypatch.setattr(
        "unity_explore.register_unity_servers",
        lambda *a, **k: None,
    )
    monkeypatch.setattr(
        "unity_explore.list_unity_tools",
        lambda **k: {"unity": []},
    )
    monkeypatch.setattr(
        "unity_explore.registered_server_names",
        lambda *a, **k: ["unity"],
    )
    with pytest.raises(SystemExit) as exc:
        verify_unity_mcp_connection(specs={"unity": {}})
    assert exc.value.code == 1
