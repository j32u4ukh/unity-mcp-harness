"""unity_common 單元測試（不連線真實 Unity MCP）。"""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from unity_common import (
    ENV_AICENTRAL_HOME,
    ENV_PROJECT_HOME,
    DEFAULT_LLM_MODEL,
    ask_unity,
    bootstrap_aicentral_config,
    create_unity_chat,
    default_server_spec,
    format_mcp_prerequisites,
    load_server_specs,
    register_unity_servers,
    registered_server_names,
    resolve_aicentral_config_dir,
    resolve_harness_llm_config_paths,
    resolve_server_specs,
    project_root,
    resolve_unity_llm_model,
    task_failure_summary,
    task_reply_indicates_failure,
)


def test_project_root_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv(ENV_PROJECT_HOME, str(tmp_path))
    assert project_root() == tmp_path.resolve()


def test_project_root_frozen_exe_dir(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    exe = tmp_path / "unity-mcp-build.exe"
    exe.write_text("", encoding="utf-8")
    monkeypatch.delenv(ENV_PROJECT_HOME, raising=False)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(exe))
    assert project_root() == tmp_path.resolve()


def test_resolve_aicentral_config_dir_defaults_to_project_config(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv(ENV_AICENTRAL_HOME, raising=False)
    monkeypatch.setattr("unity_common.project_root", lambda: tmp_path)
    assert resolve_aicentral_config_dir() == (tmp_path / "config").resolve()


def test_resolve_aicentral_config_dir_env_override(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv(ENV_AICENTRAL_HOME, str(tmp_path))
    assert resolve_aicentral_config_dir() == (tmp_path / "config").resolve()


@patch("unity_common.effective_model", side_effect=lambda m: m)
def test_resolve_unity_llm_model_default(_mock_eff: MagicMock) -> None:
    assert resolve_unity_llm_model(None) == DEFAULT_LLM_MODEL
    assert resolve_unity_llm_model("cloud-chat") == "cloud-chat"


def test_default_server_spec() -> None:
    specs = default_server_spec()
    assert "unity" in specs
    assert specs["unity"]["url"] == "http://localhost:8080/mcp"


def test_load_server_specs_cursor_mcp_servers_wrapper(tmp_path: Path) -> None:
    p = tmp_path / "cursor.json"
    p.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "unity": {
                        "command": "C:\\relay.exe",
                        "args": ["--mcp"],
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    specs = load_server_specs(p)
    assert specs["unity"]["transport"] == "stdio"
    assert specs["unity"]["command"].endswith("relay.exe")


def test_format_mcp_prerequisites_stdio() -> None:
    lines = format_mcp_prerequisites(
        {"unity": {"transport": "stdio", "command": "C:\\relay.exe", "args": []}}
    )
    text = "\n".join(lines)
    assert "stdio" in text
    assert "8080" not in text


def test_task_reply_indicates_failure_refusal() -> None:
    reply = (
        "非常抱歉，我沒有足夠的工具來直接操作 Unity Editor。"
        "我無法完成您要求的建立場景任務。請提供 C# 腳本。"
    )
    assert task_reply_indicates_failure(reply)


def test_task_reply_indicates_failure_short_ok() -> None:
    assert not task_reply_indicates_failure("已在場景建立 Cube，位置 (0,1,0)。")


def test_task_reply_indicates_failure_connection_revoked() -> None:
    reply = (
        "工具返回 Connection revoked. Go to Unity Editor > Project Settings > AI > Unity MCP. "
        "未能成功建立場景。"
    )
    assert task_reply_indicates_failure(reply)
    assert "Unity MCP" in task_failure_summary(reply)


def test_task_reply_indicates_failure_tool_failure_narrative() -> None:
    reply = (
        "由於工具調用失敗，未能成功建立符合完成定義的場景。"
        "在環境限制下我無法提供可驗證的結果。"
    )
    assert task_reply_indicates_failure(reply)


def test_load_server_specs(tmp_path: Path) -> None:
    p = tmp_path / "servers.json"
    p.write_text(
        json.dumps(
            {
                "a": {"transport": "http", "url": "http://127.0.0.1:9000/mcp"},
                "b": {"transport": "http", "url": "http://127.0.0.1:9001/mcp"},
            }
        ),
        encoding="utf-8",
    )
    specs = load_server_specs(p)
    assert set(specs) == {"a", "b"}


def test_resolve_server_specs_from_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    p = tmp_path / "unity_servers.json"
    p.write_text(
        json.dumps({"u": {"transport": "http", "url": "http://x/mcp"}}),
        encoding="utf-8",
    )
    monkeypatch.setattr("unity_common.project_root", lambda: tmp_path)
    monkeypatch.delenv("UNITY_MCP_CONFIG", raising=False)
    monkeypatch.delenv("UNITY_MCP_URL", raising=False)
    specs = resolve_server_specs()
    assert "u" in specs


def test_resolve_harness_llm_config_paths_explicit(tmp_path: Path) -> None:
    main = tmp_path / "custom" / "aicentral.yaml"
    secret = tmp_path / "keys" / "secret.yaml"
    main.parent.mkdir(parents=True)
    secret.parent.mkdir(parents=True)
    resolved_main, resolved_secret = resolve_harness_llm_config_paths(
        aicentral_config=main,
        secret=secret,
    )
    assert resolved_main == main.resolve()
    assert resolved_secret == secret.resolve()


def test_bootstrap_explicit_secret_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from aicentral.config.loader import config_dir, get_secret

    secret = tmp_path / "my_secret.yaml"
    secret.write_text("gemini:\n  api_key: from-explicit\n", encoding="utf-8")
    main = tmp_path / "config" / "aicentral.yaml"
    main.parent.mkdir(parents=True)
    main.write_text("defaults:\n  model: gemini-flash\n", encoding="utf-8")

    bootstrap_aicentral_config(aicentral_config=main, secret=secret)
    assert config_dir() == main.parent.resolve()
    assert get_secret("gemini.api_key") == "from-explicit"


def test_bootstrap_uses_harness_config_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from aicentral.config.loader import config_dir
    from aicentral.routing.gemini_rate_limit_store import resolve_store_path
    from unity_common import bootstrap_aicentral_config

    cfg = tmp_path / "config"
    cfg.mkdir()
    (cfg / "secret.yaml").write_text("gemini:\n  api_key: test\n", encoding="utf-8")
    (cfg / "aicentral.yaml").write_text(
        "gemini_pools:\n  default:\n"
        "    rate_limit_store_path: config/rate_limit_store.json\n"
        "    models:\n      - model_id: m\n        rpm_limit: 5\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("unity_common.project_root", lambda: tmp_path)

    bootstrap_aicentral_config()
    assert config_dir() == cfg.resolve()
    assert resolve_store_path("config/rate_limit_store.json") == (
        tmp_path / "config" / "rate_limit_store.json"
    ).resolve()


@patch("unity_common.register_mcp_servers")
def test_register_unity_servers(mock_reg: MagicMock) -> None:
    specs = default_server_spec()
    register_unity_servers(specs)
    mock_reg.assert_called_once_with(specs)


@patch("unity_common.register_mcp_servers")
@patch("unity_common.Chat.with_mcp")
def test_create_unity_chat(mock_with_mcp: MagicMock, mock_reg: MagicMock) -> None:
    specs = default_server_spec()
    create_unity_chat(["unity"], specs=specs, model="local")
    mock_reg.assert_called_once()
    mock_with_mcp.assert_called_once()
    assert mock_with_mcp.call_args.kwargs["include_tool_messages_in_history"] is True


@patch("unity_common.create_unity_chat")
def test_ask_unity(mock_create: MagicMock) -> None:
    mock_chat = MagicMock()
    mock_chat.ask.return_value = "ok"
    mock_create.return_value = mock_chat
    assert ask_unity("hi", mcp_servers=["unity"], specs=default_server_spec()) == "ok"
    mock_chat.ask.assert_called_once_with("hi")
