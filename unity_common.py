"""unity-mcp 共用：執行期註冊 Unity MCP Server、Chat 多輪對話。"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

ENV_PROJECT_HOME = "UNITY_MCP_HOME"
ENV_AICENTRAL_HOME = "AICENTRAL_HOME"

from aicentral import Chat, MCPManager, register_mcp_server, register_mcp_servers
from aicentral.config.schema import MCPServerEntry
from aicentral.exceptions import ProviderError
from aicentral.mcp import MCPError
from aicentral.routing.router import effective_model

EXIT_COMMANDS = frozenset({"exit", "quit", "/exit", "/quit"})

# aicentral.yaml model_list 別名（gemini_pools.default 輪換；需 config/secret.yaml 的 gemini.api_key）
DEFAULT_LLM_MODEL = "gemini-flash"

# 單一 server 時的預設名稱與 URL（Coplay MCP for Unity 預設 HTTP）
DEFAULT_SERVER_NAME = "unity"
DEFAULT_UNITY_MCP_URL = "http://localhost:8080/mcp"

# 本專案目錄下的設定檔（複製 example 後修改，勿提交含機密的 json）
LOCAL_SERVERS_FILE = "unity_servers.json"
ENV_CONFIG_PATH = "UNITY_MCP_CONFIG"
ENV_SINGLE_URL = "UNITY_MCP_URL"


def _is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def project_root() -> Path:
    """
    unity-mcp 工作目錄：放 ``build_goals.yaml``、``unity_servers.json`` 的位置。

    優先序：``UNITY_MCP_HOME`` > PyInstaller 執行檔所在目錄 > 原始碼目錄。
    打包成 exe 時請將上述設定檔與 exe 放在同一資料夾（或設環境變數），
    **不必**為修改任務而重新編譯。
    """
    env = os.environ.get(ENV_PROJECT_HOME, "").strip()
    if env:
        return Path(env).expanduser().resolve()
    if _is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def resolve_aicentral_config_dir() -> Path:
    """
    LLM / aicentral 設定目錄（``secret.yaml``、``aicentral.yaml``、``rate_limit_store.json``）。

    優先序：``AICENTRAL_HOME/config`` > ``project_root()/config``（Harness 專案自有設定）。
    """
    env = os.environ.get(ENV_AICENTRAL_HOME, "").strip()
    if env:
        return Path(env).expanduser().resolve() / "config"
    return project_root() / "config"


def resolve_harness_llm_config_paths(
    *,
    aicentral_config: Path | str | None = None,
    secret: Path | str | None = None,
) -> tuple[Path, Path]:
    """
    解析 LLM 設定路徑（預設 ``project_root()/config/`` 或 ``AICENTRAL_HOME/config/``）。

    回傳 ``(aicentral.yaml, secret.yaml)`` 絕對路徑。
    """
    cfg_dir = resolve_aicentral_config_dir()
    main = (
        Path(aicentral_config).expanduser().resolve()
        if aicentral_config
        else (cfg_dir / "aicentral.yaml").resolve()
    )
    secret_p = (
        Path(secret).expanduser().resolve()
        if secret
        else (cfg_dir / "secret.yaml").resolve()
    )
    return main, secret_p


def bootstrap_aicentral_config(
    *,
    aicentral_config: Path | str | None = None,
    secret: Path | str | None = None,
) -> Path:
    """依 harness 設定目錄或明確路徑載入 aicentral（``reload=True``）。"""
    from aicentral.config.loader import load_config

    main, secret_p = resolve_harness_llm_config_paths(
        aicentral_config=aicentral_config,
        secret=secret,
    )
    if not secret_p.is_file() and not main.is_file():
        return main.parent
    load_config(
        path=main,
        secrets_path=secret_p if secret_p.is_file() else None,
        reload=True,
    )
    return main.parent


def require_aicentral_config(
    *,
    aicentral_config: Path | str | None = None,
    secret: Path | str | None = None,
) -> Path:
    """確認 secret.yaml 存在並載入 harness LLM 設定（非 aicentral repo 預設路徑）。"""
    bootstrap_aicentral_config(aicentral_config=aicentral_config, secret=secret)
    main, secret_p = resolve_harness_llm_config_paths(
        aicentral_config=aicentral_config,
        secret=secret,
    )
    if not secret_p.is_file():
        example = main.parent / "secret.yaml.example"
        hint = (
            f"Copy-Item .\\config\\secret.yaml.example .\\config\\secret.yaml"
            if example.is_file()
            else "建立 config\\secret.yaml（可從 config\\secret.yaml.example 複製）"
        )
        print(
            f"找不到 {secret_p}\n"
            f"請在 unity-mcp-harness 目錄執行：{hint}\n"
            f"或設定環境變數 {ENV_AICENTRAL_HOME} 指向含 config/ 的目錄根，"
            f"或使用 --secret 指定路徑。",
            file=sys.stderr,
        )
        sys.exit(1)
    return main.parent


def resolve_unity_llm_model(model: str | None = None) -> str:
    """
    Unity MCP 工作流使用的 LLM 別名。

    未傳入時使用 ``DEFAULT_LLM_MODEL``（gemini-flash），
    不採 aicentral ``defaults.model``（通常為 local-chat）。
    """
    return effective_model(model if model is not None and str(model).strip() else DEFAULT_LLM_MODEL)


def default_server_spec(
    *,
    url: str = DEFAULT_UNITY_MCP_URL,
    name: str = DEFAULT_SERVER_NAME,
) -> dict[str, dict[str, Any]]:
    """單一 Unity MCP（HTTP）的預設規格。"""
    return {
        name: {
            "transport": "http",
            "url": url,
            "auth_type": "none",
            "description": "Unity MCP（執行期註冊）",
        }
    }


def _normalize_server_specs(data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """正規化 MCP 設定：支援 Cursor ``mcpServers`` 外層，並推斷 ``transport``。"""
    if "mcpServers" in data and isinstance(data["mcpServers"], dict):
        data = dict(data["mcpServers"])
    if not data:
        raise ValueError("設定檔須為非空物件")
    normalized: dict[str, dict[str, Any]] = {}
    for name, raw in data.items():
        if not isinstance(raw, dict):
            raise ValueError(f"server {name!r} 須為物件")
        entry = dict(raw)
        if "transport" not in entry:
            if entry.get("command"):
                entry["transport"] = "stdio"
            elif entry.get("url"):
                entry["transport"] = "http"
            else:
                raise ValueError(f"server {name!r} 缺少 transport（或 command / url）")
        if entry.get("auth_type") is None:
            entry["auth_type"] = "none"
        normalized[name] = entry
    return normalized


def load_server_specs(path: Path | str) -> dict[str, dict[str, Any]]:
    """從 JSON 載入 server 定義（aicentral 格式或 Cursor ``mcpServers`` 格式）。"""
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"找不到 Unity MCP 設定檔: {p}")
    data = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"設定檔須為 JSON 物件: {p}")
    return _normalize_server_specs(data)


def format_mcp_prerequisites(specs: dict[str, dict[str, Any]]) -> list[str]:
    """依目前 ``unity_servers`` 的 transport 產生前置條件說明（供 CLI banner）。"""
    lines = ["前置條件（依 unity_servers 設定）："]
    for name, entry in specs.items():
        transport = entry.get("transport", "?")
        if transport == "stdio":
            cmd = entry.get("command", "?")
            lines.append(
                f"  • [{name}] stdio：Unity Editor 已開啟，MCP 外掛已連線；"
                f"relay/子行程可執行（{cmd}）"
            )
        elif transport in ("http", "sse"):
            url = entry.get("url", "?")
            lines.append(
                f"  • [{name}] {transport}：Unity 內已啟動 MCP HTTP/SSE（{url}）"
            )
        else:
            lines.append(f"  • [{name}] transport={transport}")
    lines.append("  • LLM 需支援 function calling（MCP tool loop）")
    lines.append("  • 驗證連線：unity-mcp-list-tools --json")
    return lines


# 模型回覆中表示「未實際完成任務」的常見語句（啟發式，非完美）
_TASK_REFUSAL_MARKERS: tuple[str, ...] = (
    "無法完成",
    "無法直接",
    "無法操作",
    "無法執行",
    "無法像人一樣",
    "無法成功",
    "無法提供",
    "無法滿足",
    "沒有足夠的工具",
    "沒有對應工具",
    "無法模擬",
    "未能成功",
    "工具調用失敗",
    "環境限制",
    "在沒有提供",
    "請提供",
    "i cannot",
    "i can't",
    "unable to",
    "don't have tools",
    "do not have tools",
)

# 單一命中即視為失敗（MCP 核准 / 連線問題或明確宣告未完成）
_STRONG_FAILURE_MARKERS: tuple[str, ...] = (
    "connection revoked",
    "連接被撤銷",
    "連線被撤銷",
    "approval",
    "未能成功建立",
    "未能成功建立符合",
    "工具調用失敗",
    "無法與 unity editor",
)


def task_reply_indicates_failure(reply: str) -> bool:
    """啟發式判斷：LLM 是否僅文字拒絕、未實際完成任務（無 MCP 例外時）。"""
    text = reply.strip().lower()
    if len(text) < 40:
        return False
    if any(marker in text for marker in _STRONG_FAILURE_MARKERS):
        return True
    hits = sum(1 for m in _TASK_REFUSAL_MARKERS if m in text)
    return hits >= 2


def task_failure_summary(reply: str) -> str:
    """依回覆內容產生較具體的失敗說明（供 CLI 顯示）。"""
    text = reply.lower()
    if "connection revoked" in text or "連接被撤銷" in text or "連線被撤銷" in text:
        return (
            "Unity MCP 工具遭拒絕（Connection revoked）。"
            "請至 Unity：Project Settings > AI > Unity MCP 核准或啟用自動核准後重試。"
        )
    if "工具調用失敗" in text or "未能成功" in text:
        return "模型回覆表示 MCP 工具未成功執行或未達任務目標；請檢查 Unity 核准與 Editor 連線。"
    return (
        "模型回覆表示未完成任務（未呼叫 MCP 工具或拒絕執行）；"
        "請確認模型支援 function calling。"
    )


def resolve_server_specs(
    *,
    config_path: Path | str | None = None,
) -> dict[str, dict[str, Any]]:
    """解析要註冊的 Unity MCP 規格（優先序：參數 > 環境變數 > 本目錄 json > 內建預設）。"""
    if config_path is not None:
        return load_server_specs(config_path)

    env_path = os.environ.get(ENV_CONFIG_PATH, "").strip()
    if env_path:
        return load_server_specs(env_path)

    local = project_root() / LOCAL_SERVERS_FILE
    if local.is_file():
        return load_server_specs(local)

    env_url = os.environ.get(ENV_SINGLE_URL, "").strip()
    if env_url:
        return default_server_spec(url=env_url)

    return default_server_spec()


def register_unity_servers(
    specs: dict[str, dict[str, Any]] | None = None,
    *,
    config_path: Path | str | None = None,
) -> dict[str, MCPServerEntry]:
    """執行期註冊一至多個 Unity MCP Server（不寫入 aicentral.yaml）。"""
    resolved = specs if specs is not None else resolve_server_specs(config_path=config_path)
    register_mcp_servers(resolved)
    return {name: MCPServerEntry.model_validate(entry) for name, entry in resolved.items()}


def registered_server_names(
    specs: dict[str, dict[str, Any]] | None = None,
    *,
    config_path: Path | str | None = None,
) -> list[str]:
    """已註冊的 server 名稱列表（供 ``mcp_servers=[...]`` 使用）。"""
    resolved = (
        specs
        if specs is not None
        else resolve_server_specs(config_path=config_path)
    )
    return sorted(resolved.keys())


def create_unity_chat(
    mcp_servers: list[str] | str,
    *,
    model: str | None = None,
    system: str | None = None,
    max_tool_rounds: int = 8,
    include_tool_messages_in_history: bool = True,
    specs: dict[str, dict[str, Any]] | None = None,
    config_path: Path | str | None = None,
) -> Chat:
    """註冊 Unity MCP 並建立已啟用 tool loop 的 Chat（經 harness ``UnityMCPRunner``）。"""
    from harness.mcp_runner import create_unity_mcp_runner

    resolved = specs if specs is not None else resolve_server_specs(config_path=config_path)
    register_unity_servers(resolved, config_path=config_path)
    runner = create_unity_mcp_runner(
        mcp_servers,
        model=resolve_unity_llm_model(model),
        system=system,
        max_tool_rounds=max_tool_rounds,
        include_tool_messages_in_history=include_tool_messages_in_history,
        specs=resolved,
        config_path=config_path,
    )
    return runner.chat


def ask_unity(
    question: str,
    *,
    mcp_servers: list[str] | str | None = None,
    model: str | None = None,
    system: str | None = None,
    chat: Chat | None = None,
    max_tool_rounds: int = 8,
    specs: dict[str, dict[str, Any]] | None = None,
    config_path: Path | str | None = None,
) -> str:
    """單次提問；``mcp_servers`` 預設為目前設定檔中的全部 server 名稱。"""
    if mcp_servers is None:
        register_unity_servers(specs, config_path=config_path)
        mcp_servers = registered_server_names(specs, config_path=config_path)
    session = chat or create_unity_chat(
        mcp_servers,
        model=model,
        system=system,
        max_tool_rounds=max_tool_rounds,
        specs=specs,
        config_path=config_path,
    )
    return session.ask(question)


def list_unity_tools(
    *,
    specs: dict[str, dict[str, Any]] | None = None,
    config_path: Path | str | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """註冊後列出各 Unity MCP server 的工具。"""
    register_unity_servers(specs, config_path=config_path)
    mgr = MCPManager.from_config()
    return {name: mgr.list_tools(name) for name in registered_server_names(specs)}


def add_harness_llm_config_args(parser: Any) -> None:
    """CLI：``--aicentral-config`` / ``--secret``（預設 harness ``config/``）。"""
    cfg_dir = resolve_aicentral_config_dir()
    parser.add_argument(
        "--aicentral-config",
        type=str,
        default=None,
        metavar="PATH",
        help=f"LLM 主設定 aicentral.yaml（預設 {cfg_dir / 'aicentral.yaml'}）",
    )
    parser.add_argument(
        "--secret",
        type=str,
        default=None,
        metavar="PATH",
        help=f"API 金鑰 secret.yaml（預設 {cfg_dir / 'secret.yaml'}）",
    )


def add_unity_mcp_config_arg(parser: Any) -> None:
    """CLI：``-c`` / ``--unity-config``（Unity MCP JSON，非 LLM secret）。"""
    parser.add_argument(
        "-c",
        "--unity-config",
        dest="unity_config",
        type=str,
        default=None,
        metavar="PATH",
        help="Unity MCP 設定 JSON（預設 unity_servers.json；無檔時 fallback HTTP :8080）",
    )


def format_llm_config_paths(
    *,
    aicentral_config: Path | str | None = None,
    secret: Path | str | None = None,
) -> str:
    main, secret_p = resolve_harness_llm_config_paths(
        aicentral_config=aicentral_config,
        secret=secret,
    )
    return f"LLM 設定: {main}\nSecret: {secret_p}"


def print_banner(
    *,
    title: str,
    model: str,
    server_names: list[str],
    detail: str = "",
    specs: dict[str, dict[str, Any]] | None = None,
    interactive: bool = False,
    aicentral_config: Path | str | None = None,
    secret: Path | str | None = None,
) -> None:
    print(f"unity-mcp — {title}")
    print(f"模型: {model}")
    print(format_llm_config_paths(aicentral_config=aicentral_config, secret=secret))
    print(f"Unity MCP servers: {', '.join(server_names)}")
    if detail:
        print(detail)
    if specs:
        for line in format_mcp_prerequisites(specs):
            print(line)
    else:
        print("前置：請設定 unity_servers.json 或見 unity_servers.example.json")
    if interactive:
        print("輸入 exit 或 quit 結束")
    print("-" * 40)


def handle_errors(exc: BaseException) -> None:
    if isinstance(exc, MCPError):
        print(f"MCP 錯誤: {exc}", file=sys.stderr)
    elif isinstance(exc, ProviderError):
        print(f"LLM 錯誤: {exc}", file=sys.stderr)
    elif isinstance(exc, FileNotFoundError):
        print(f"設定: {exc}", file=sys.stderr)
    else:
        raise
