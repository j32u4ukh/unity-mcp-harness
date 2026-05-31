"""Unity-MCP-Server 生命週期（port 檢查 / autostart 解析）。"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from core.mcp.server_lifecycle import (
    UnityMcpServerError,
    UnityMcpServerSession,
    parse_http_endpoint,
    resolve_autostart_spec,
    specs_for_aicentral,
    strip_harness_server_fields,
)


def test_strip_harness_server_fields() -> None:
    entry = {
        "transport": "http",
        "url": "http://localhost:22172",
        "autostart": {"command": "dotnet", "args": []},
    }
    cleaned = strip_harness_server_fields(entry)
    assert "autostart" not in cleaned
    assert cleaned["url"] == "http://localhost:22172"


def test_specs_for_aicentral() -> None:
    specs = {
        "unity": {
            "transport": "http",
            "url": "http://localhost:22172",
            "autostart": {"command": "dotnet"},
        }
    }
    out = specs_for_aicentral(specs)
    assert "autostart" not in out["unity"]


def test_parse_http_endpoint_default_port() -> None:
    host, port, scheme = parse_http_endpoint("http://localhost:22172")
    assert host == "localhost"
    assert port == 22172
    assert scheme == "http"


def test_resolve_autostart_from_json() -> None:
    entry = {
        "url": "http://localhost:22172",
        "autostart": {
            "command": "dotnet",
            "args": ["run", "--", "--port=22172"],
            "cwd": "C:/server",
        },
    }
    spec = resolve_autostart_spec(entry, server_name="unity", autostart_enabled=True)
    assert spec is not None
    assert spec.command == "dotnet"
    assert spec.cwd == "C:/server"


def test_resolve_autostart_from_env_home(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("UNITY_MCP_SERVER_HOME", "C:/Unity-MCP-Server")
    entry = {"url": "http://localhost:22172"}
    spec = resolve_autostart_spec(entry, server_name="unity", autostart_enabled=True)
    assert spec is not None
    assert spec.cwd == "C:/Unity-MCP-Server"
    assert "--port=22172" in spec.args


def test_session_raises_when_port_closed_no_autostart(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("UNITY_MCP_SERVER_HOME", raising=False)
    specs = {
        "unity": {
            "transport": "http",
            "url": "http://127.0.0.1:59999",
        }
    }
    with patch("core.mcp.server_lifecycle.is_tcp_port_open", return_value=False):
        with pytest.raises(UnityMcpServerError, match="連線被拒"):
            with UnityMcpServerSession(specs, autostart=False):
                pass


def test_session_skips_start_when_port_open() -> None:
    specs = {
        "unity": {
            "transport": "http",
            "url": "http://127.0.0.1:22172",
            "autostart": {"command": "dotnet", "args": []},
        }
    }
    with patch("core.mcp.server_lifecycle.is_tcp_port_open", return_value=True):
        with patch("core.mcp.server_lifecycle._start_process") as mock_start:
            with UnityMcpServerSession(specs):
                pass
            mock_start.assert_not_called()


def test_session_autostart_from_json_without_env_home(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("UNITY_MCP_SERVER_HOME", raising=False)
    specs = {
        "unity": {
            "transport": "http",
            "url": "http://127.0.0.1:59998",
            "autostart": {
                "command": "dotnet",
                "args": ["run"],
                "cwd": "C:/server",
            },
        }
    }
    with patch("core.mcp.server_lifecycle.is_tcp_port_open", return_value=False):
        with patch("core.mcp.server_lifecycle._start_process") as mock_start:
            proc = MagicMock()
            proc.poll.return_value = None
            mock_start.return_value = proc
            with patch("core.mcp.server_lifecycle.wait_for_http_server"):
                with UnityMcpServerSession(specs):
                    pass
            mock_start.assert_called_once()


def test_register_unity_servers_strips_autostart(tmp_path) -> None:
    p = tmp_path / "servers.json"
    p.write_text(
        json.dumps(
            {
                "unity": {
                    "transport": "http",
                    "url": "http://localhost:22172",
                    "auth_type": "none",
                    "autostart": {"command": "dotnet", "args": []},
                }
            }
        ),
        encoding="utf-8",
    )
    from unity_common import load_server_specs, register_unity_servers

    specs = load_server_specs(p)
    with patch("unity_common.register_mcp_servers") as mock_reg:
        register_unity_servers(specs)
        call_specs = mock_reg.call_args[0][0]
        assert "autostart" not in call_specs["unity"]
