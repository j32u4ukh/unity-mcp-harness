"""Unity-MCP-Server（IvanMurzak HTTP）生命週期：啟動前檢查、必要時 autostart、結束時清理。"""

from __future__ import annotations

import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from core.harness_log import harness_log

ENV_SERVER_HOME = "UNITY_MCP_SERVER_HOME"
ENV_AUTOSTART = "UNITY_MCP_AUTOSTART"
ENV_DEFAULT_PORT = "UNITY_MCP_SERVER_PORT"

HARNESS_SERVER_KEYS = frozenset({"autostart"})

DEFAULT_READY_TIMEOUT_SEC = 90.0
DEFAULT_POLL_INTERVAL_SEC = 0.5


class UnityMcpServerError(RuntimeError):
    """Unity MCP HTTP server 無法連線或 autostart 失敗。"""


@dataclass(frozen=True)
class AutostartSpec:
    command: str
    args: list[str]
    cwd: str | None = None
    env: dict[str, str] | None = None
    ready_timeout_sec: float = DEFAULT_READY_TIMEOUT_SEC


@dataclass
class _ManagedProcess:
    name: str
    url: str
    process: subprocess.Popen[Any] | None
    started_by_harness: bool


def strip_harness_server_fields(entry: dict[str, Any]) -> dict[str, Any]:
    """移除 harness 專用欄位，供 aicentral ``MCPServerEntry`` 註冊。"""
    return {k: v for k, v in entry.items() if k not in HARNESS_SERVER_KEYS}


def specs_for_aicentral(specs: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """整份 ``unity_servers.json`` 去掉 harness 擴充欄位。"""
    return {name: strip_harness_server_fields(entry) for name, entry in specs.items()}


def parse_http_endpoint(url: str) -> tuple[str, int, str]:
    """自 MCP URL 解析 host、port、scheme。"""
    parsed = urlparse(url.strip())
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"HTTP transport 需要 http(s) URL，收到: {url!r}")
    host = parsed.hostname or "localhost"
    if parsed.port is not None:
        port = parsed.port
    elif parsed.scheme == "https":
        port = 443
    else:
        port = 80
    return host, port, parsed.scheme


def is_tcp_port_open(host: str, port: int, *, timeout: float = 1.0) -> bool:
    import socket

    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _http_probe(url: str, *, timeout: float = 2.0) -> bool:
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return 200 <= resp.status < 500
    except urllib.error.HTTPError as exc:
        return 200 <= exc.code < 500
    except OSError:
        return False


def wait_for_http_server(
    url: str,
    *,
    timeout_sec: float = DEFAULT_READY_TIMEOUT_SEC,
    poll_interval_sec: float = DEFAULT_POLL_INTERVAL_SEC,
) -> None:
    """等待 HTTP MCP 端點可連（TCP + 可選 GET /help）。"""
    host, port, scheme = parse_http_endpoint(url)
    base = f"{scheme}://{host}:{port}"
    probe_urls = [
        f"{base}/help",
        url.rstrip("/"),
        base,
    ]
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        if is_tcp_port_open(host, port):
            for probe in probe_urls:
                if _http_probe(probe):
                    return
        time.sleep(poll_interval_sec)
    raise UnityMcpServerError(
        f"等待 Unity MCP HTTP server 就緒逾時（{timeout_sec:.0f}s）：{url}\n"
        "請確認 Unity-MCP-Server 已啟動，且 Unity Editor 內 Plugin 已連上同一 port。"
    )


def resolve_unity_mcp_server_home() -> str | None:
    """
    解析 Unity-MCP-Server 原始碼目錄。

    優先序：``UNITY_MCP_SERVER_HOME`` > 與 harness 同 repo 的 ``../Unity-MCP/Unity-MCP-Server``。
    """
    env = os.environ.get(ENV_SERVER_HOME, "").strip()
    if env:
        return env
    harness_root = Path(__file__).resolve().parents[2]
    candidate = harness_root.parent / "Unity-MCP" / "Unity-MCP-Server"
    if candidate.is_dir():
        return str(candidate)
    return None


def resolve_autostart_spec(
    entry: dict[str, Any],
    *,
    server_name: str,
    autostart_enabled: bool,
) -> AutostartSpec | None:
    """解析 autostart 設定（json ``autostart`` 或 ``UNITY_MCP_SERVER_HOME``）。"""
    raw = entry.get("autostart")
    if isinstance(raw, dict):
        command = str(raw.get("command", "")).strip()
        if not command:
            raise UnityMcpServerError(
                f"server {server_name!r} 的 autostart.command 不可為空"
            )
        args = [str(a) for a in raw.get("args", [])]
        cwd = raw.get("cwd") or resolve_unity_mcp_server_home()
        env = raw.get("env")
        timeout = float(raw.get("ready_timeout_sec", DEFAULT_READY_TIMEOUT_SEC))
        if not cwd:
            raise UnityMcpServerError(
                f"server {server_name!r} 的 autostart 缺少 cwd，"
                f"且未設定 {ENV_SERVER_HOME} 或找不到 ../Unity-MCP/Unity-MCP-Server"
            )
        return AutostartSpec(
            command=command,
            args=args,
            cwd=str(cwd),
            env={str(k): str(v) for k, v in env.items()} if isinstance(env, dict) else None,
            ready_timeout_sec=timeout,
        )

    if not autostart_enabled:
        return None

    home = resolve_unity_mcp_server_home()
    if not home:
        return None

    url = str(entry.get("url", "")).strip()
    if not url:
        return None

    _, port, _ = parse_http_endpoint(url)
    env_port = os.environ.get(ENV_DEFAULT_PORT, "").strip()
    if env_port.isdigit():
        port = int(env_port)

    return AutostartSpec(
        command="dotnet",
        args=[
            "run",
            "--",
            f"--port={port}",
            "--client-transport=streamableHttp",
        ],
        cwd=home,
        ready_timeout_sec=DEFAULT_READY_TIMEOUT_SEC,
    )


def _env_autostart_enabled() -> bool:
    raw = os.environ.get(ENV_AUTOSTART, "").strip().lower()
    if raw in ("0", "false", "no", "off"):
        return False
    if raw in ("1", "true", "yes", "on"):
        return True
    return bool(os.environ.get(ENV_SERVER_HOME, "").strip())


def _start_process(spec: AutostartSpec) -> subprocess.Popen[Any]:
    env = os.environ.copy()
    if spec.env:
        env.update(spec.env)
    kwargs: dict[str, Any] = {
        "cwd": spec.cwd,
        "env": env,
    }
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    try:
        return subprocess.Popen([spec.command, *spec.args], **kwargs)
    except OSError as exc:
        raise UnityMcpServerError(
            f"無法啟動 Unity-MCP-Server：{spec.command} {' '.join(spec.args)}\n"
            f"cwd={spec.cwd!r}\n{exc}"
        ) from exc


def _connection_refused_hint(url: str, server_name: str) -> str:
    return (
        f"Unity MCP HTTP server [{server_name}] 連線被拒（port 未監聽）：{url}\n"
        "LangGraph 執行前必須先讓 Unity-MCP-Server 在背景運行。\n"
        "做法擇一：\n"
        "  1. 手動：dotnet run -- --port=<port> --client-transport=streamableHttp "
        "（見 docs/IvanMurzak-Unity-MCP.md）\n"
        "  2. 設定 UNITY_MCP_SERVER_HOME 指向 Unity-MCP-Server 目錄（Harness 可 autostart）\n"
        "  3. 在 unity_servers.json 的 server 項目加入 autostart 區塊\n"
        "驗證：unity-mcp-list-tools --json"
    )


def _specs_have_autostart(specs: dict[str, dict[str, Any]]) -> bool:
    return any(isinstance(entry.get("autostart"), dict) for entry in specs.values())


class UnityMcpServerSession:
    """
    確保 HTTP/SSE MCP server 在 Harness 執行期可連。

    - port 已開：沿用外部程序，不關閉
    - port 未開且有 autostart：由 Harness 啟動，``__exit__`` 時 terminate
    - port 未開且無 autostart：拋 ``UnityMcpServerError``（避免 ConnectionRefused 直接崩潰）
    """

    def __init__(
        self,
        specs: dict[str, dict[str, Any]],
        *,
        autostart: bool | None = None,
    ) -> None:
        self._specs = specs
        if autostart is None:
            self._autostart = _env_autostart_enabled() or _specs_have_autostart(specs)
        else:
            self._autostart = autostart
        self._managed: list[_ManagedProcess] = []

    def __enter__(self) -> UnityMcpServerSession:
        self._ensure_http_servers()
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        for item in reversed(self._managed):
            proc = item.process
            if not item.started_by_harness or proc is None:
                continue
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()
        self._managed.clear()

    def _ensure_http_servers(self) -> None:
        for name, entry in self._specs.items():
            transport = entry.get("transport")
            if transport not in ("http", "sse"):
                continue
            url = str(entry.get("url", "")).strip()
            if not url:
                continue
            host, port, _ = parse_http_endpoint(url)
            if is_tcp_port_open(host, port):
                harness_log(f"Unity-MCP-Server [{name}] 已運行：{url}")
                self._managed.append(
                    _ManagedProcess(name=name, url=url, process=None, started_by_harness=False)
                )
                continue

            autostart_spec = resolve_autostart_spec(
                entry,
                server_name=name,
                autostart_enabled=self._autostart,
            )
            if autostart_spec is None:
                raise UnityMcpServerError(_connection_refused_hint(url, name))

            harness_log(f"Unity-MCP-Server [{name}] port 未開，autostart 啟動中…")
            proc = _start_process(autostart_spec)
            self._managed.append(
                _ManagedProcess(name=name, url=url, process=proc, started_by_harness=True)
            )
            if proc.poll() is not None:
                raise UnityMcpServerError(
                    f"Unity-MCP-Server [{name}] 啟動後立即結束（exit={proc.returncode}）。"
                    "請在本機終端機手動 dotnet run 查看錯誤。"
                )
            wait_for_http_server(url, timeout_sec=autostart_spec.ready_timeout_sec)
            harness_log(f"Unity-MCP-Server [{name}] 已就緒：{url}")
