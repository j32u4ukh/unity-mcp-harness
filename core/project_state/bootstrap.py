"""``--bootstrap-state``：唯讀 MCP 盤點既有 Unity 專案並寫入 project_state/。"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from core.pipeline.schema import HarnessTask
from core.project_state.delta import markdown_section_block, summarize_text
from core.project_state.index import StateIndexEntry, utc_now_iso
from core.project_state.paths import default_project_state_root
from core.project_state.session import ProjectStateSession, begin_session, end_session
from tasks import TaskResult
from unity_common import (
    ask_unity,
    registered_server_names,
    resolve_server_specs,
    resolve_unity_llm_model,
    task_reply_indicates_failure,
)
from unity_explore import build_explore_system_prompt, load_explore_settings, verify_unity_mcp_connection

_logger = logging.getLogger(__name__)

BOOTSTRAP_TASK_ID = "bootstrap_state"

DEFAULT_BOOTSTRAP_PROMPT = """\
唯讀基線盤點（禁止建立、修改、刪除任何場景物件或資產）：

1. 目前 Active 場景的檔案路徑與名稱
2. Hierarchy 主要 GameObject（名稱、Active 狀態、關鍵元件類型）
3. Main Camera：Projection、位置等與可視化相關設定
4. 光照方式（2D Global Light / 3D Directional 等，若存在）
5. 重要資產路徑（尤其 Assets/_Scenes/、Assets/_Generated/ 或專案內自訂資料夾）
6. 與 2D Sprite / URP 2D 相關的現有物件或資產（若存在）
7. 明顯的 Missing Reference 或空場景說明

請用繁體中文條列，並標明從 MCP 工具得到的具體名稱與路徑；查不到則寫「未回傳」。"""


@dataclass
class BootstrapStateReport:
    ok: bool
    project_state_root: Path
    reply: str = ""
    error: str | None = None
    files_touched: list[str] = field(default_factory=list)
    message: str = ""

    @property
    def success(self) -> bool:
        return self.ok


def _load_bootstrap_prompt(custom: str | None) -> str:
    if custom and custom.strip():
        return custom.strip()
    explore = load_explore_settings()
    probe = (explore.probe_prompt or "").strip()
    if probe:
        return probe + "\n\n" + (
            "（Harness --bootstrap-state：請將以上探索結果整理為完整條列，"
            "供寫入 project_state 文件樹；仍禁止任何寫入操作。）"
        )
    return DEFAULT_BOOTSTRAP_PROMPT


def _record_bootstrap_reply(session: ProjectStateSession, reply: str, *, success: bool) -> list[str]:
    """將盤點結果寫入 session（含 tasks/ 與三個 overview）。"""
    status = "completed" if success else "failed"
    summary = summarize_text(reply, max_len=120)
    task = HarnessTask(
        id=BOOTSTRAP_TASK_ID,
        description="CLI 基線盤點（--bootstrap-state）",
        status=status,
        priority=0,
        prompt="唯讀 MCP 盤點",
        verification="verified" if success else "failed",
    )
    result = TaskResult(
        id=BOOTSTRAP_TASK_ID,
        title="初始化狀態樹",
        success=success,
        reply=reply,
        error=None if success else summarize_text(reply, max_len=300),
    )
    session.record(task, result)

    overview_block = markdown_section_block("基線盤點（--bootstrap-state）", reply)
    touched: list[str] = [
        f"tasks/{BOOTSTRAP_TASK_ID}.md",
        "changelog.md",
        "_index.yaml",
    ]
    for key, rel in (
        ("assets/overview", "assets/_overview.md"),
        ("systems/overview", "systems/_overview.md"),
    ):
        session.markdown_pending.setdefault(rel, []).append(overview_block)
        session.index.upsert(
            StateIndexEntry(
                key=key,
                path=rel,
                summary=summary,
                tags=key.split("/") + ["bootstrap"],
                last_updated=utc_now_iso(),
                last_task_id=BOOTSTRAP_TASK_ID,
            )
        )
        if rel not in touched:
            touched.append(rel)
    session.dirty = True
    return touched


def run_bootstrap_state(
    *,
    unity_config_path: str | None = None,
    prompt: str | None = None,
    max_tool_rounds: int | None = None,
    model: str | None = None,
    verify_mcp: bool = True,
) -> BootstrapStateReport:
    """
    唯讀連線 Unity MCP，盤點現況並寫入 ``project_state/``。

    前置：``--init``、``config/secret.yaml``、``config/local.env.ps1``，Unity Editor 已開啟。
    不修改 ``task_list.yaml``、不跑 Plan Normalize / LangGraph。
    """
    root = default_project_state_root()
    if not root.is_dir():
        return BootstrapStateReport(
            ok=False,
            project_state_root=root,
            error="project_state 目錄不存在",
            message="請先在工作區執行 unity-mcp-harness --init",
        )

    user_prompt = _load_bootstrap_prompt(prompt)
    specs = resolve_server_specs(config_path=unity_config_path)
    if verify_mcp:
        try:
            verify_unity_mcp_connection(specs=specs, config_path=unity_config_path)
        except Exception as exc:
            return BootstrapStateReport(
                ok=False,
                project_state_root=root,
                error=str(exc),
                message="Unity MCP 連線失敗",
            )

    mcp_servers = registered_server_names(specs)
    explore = load_explore_settings()
    resolved_model = resolve_unity_llm_model(model)
    system = build_explore_system_prompt(server_names=mcp_servers, settings=explore)
    rounds = max_tool_rounds if max_tool_rounds is not None else explore.max_tool_rounds

    try:
        reply = ask_unity(
            user_prompt,
            mcp_servers=mcp_servers,
            model=resolved_model,
            system=system,
            max_tool_rounds=rounds,
            specs=specs,
            config_path=unity_config_path,
        )
    except Exception as exc:
        _logger.warning("bootstrap-state MCP 失敗: %s", exc)
        return BootstrapStateReport(
            ok=False,
            project_state_root=root,
            error=str(exc),
            message="MCP 盤點失敗",
        )

    success = bool(reply.strip()) and not task_reply_indicates_failure(reply)
    session = begin_session(root)
    if session is None:
        return BootstrapStateReport(
            ok=False,
            project_state_root=root,
            reply=reply,
            error="無法建立 project_state session",
        )

    try:
        touched = _record_bootstrap_reply(session, reply, success=success)
        end_session(flush=True)
    except Exception as exc:
        end_session(flush=False)
        return BootstrapStateReport(
            ok=False,
            project_state_root=root,
            reply=reply,
            error=str(exc),
            message="寫入 project_state 失敗",
        )

    return BootstrapStateReport(
        ok=success,
        project_state_root=root,
        reply=reply,
        files_touched=touched,
        message="已寫入 project_state（基線盤點）" if success else "盤點回覆可能不完整或含錯誤標記",
    )


def format_bootstrap_report(report: BootstrapStateReport) -> str:
    lines = [f"project_state 基線盤點: {report.project_state_root}"]
    if report.ok:
        lines.append(f"  狀態: 成功 — {report.message}")
        if report.files_touched:
            lines.append(f"  已更新: {', '.join(report.files_touched)}")
    else:
        lines.append(f"  狀態: 失敗 — {report.message or '未知錯誤'}")
        if report.error:
            lines.append(f"  錯誤: {report.error}")
    if report.reply:
        preview = summarize_text(report.reply, max_len=600)
        lines.append(f"  摘要: {preview}")
    lines.extend(
        [
            "下一步:",
            "  1. 檢視 project_state\\ 各分項（可手動補充）",
            "  2. 編輯 build_goals.yaml 定義建構任務",
            "  3. .\\scripts\\harness-dry-run.ps1",
            "  4. .\\scripts\\harness-run.ps1",
        ]
    )
    return "\n".join(lines)
