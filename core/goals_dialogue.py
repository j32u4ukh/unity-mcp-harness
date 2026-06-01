"""--goals init / modify 對話：收斂式澄清 + 可選 Unity MCP 現場查詢。"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from tasks import resolve_build_plan, resolve_goals_path
from unity_common import (
    handle_errors,
    project_root,
    registered_server_names,
    require_aicentral_config,
    resolve_server_specs,
    resolve_unity_llm_model,
)

GOALS_INIT_HELP = """
指令：
  /help      顯示說明
  /mcp TEXT  強制以 Unity MCP 唯讀查詢現場（查腳本/場景/資產）
  /write     輸出並寫入 build_goals.yaml
  /quit      離開不儲存
"""

GOALS_MODIFY_HELP = """
指令：
  /help      顯示說明
  /mcp TEXT  強制以 Unity MCP 唯讀查詢現場
  /write     合併寫回 tasks
  /quit      離開不儲存
"""

_GOALS_DIALOGUE_MCP_RULES = """
## Unity MCP（唯讀 — 討論「專案裡有什麼」時必用）
- 當話題涉及**現有**腳本、場景、GameObject、資產、目錄結構時，**先**呼叫唯讀 MCP 工具再發言。
- 優先：`assets-find`（filter 用 Unity Search，如 `t:Script AttackManager`、`l:Assets/Scripts/Attack`）、`gameobject-find`。
- **禁止**把 `Assets/.../Foo.cs` 整段路徑當 assets-find 的唯一 filter。
- **禁止**在未查證前斷言「專案沒有／已有」某檔案或元件；須在回覆中引用工具回傳摘要。
- 本模式**不可**建立、修改、刪除任何 Editor 內容。
"""

_GOALS_CONVERGENCE_RULES = """
## 澄清方式（收斂 — 必守）
- 先與使用者固定**單一里程碑**（一句話邊界）；之後所有提問只為釐清**該里程碑內**子目標的模糊處。
- **禁止**把話題擴散到里程碑外的新系統、新玩法、未要求的長期規劃；若使用者偏題，禮貌拉回里程碑。
- 每輪至多 **1～3 個**具體問題；優先「確認假設」而非腦力激盪式發散。
- 子目標維持**粗粒度**（供 Plan Normalize 再拆）；不要在 init 階段無限細化實作步驟。
- 若資訊已足夠產出 tasks，主動建議使用者輸入 `/write`，勿為問而問。
"""

GOALS_INIT_SYSTEM = f"""你是 Unity MCP Harness 藍圖規劃助手（**init** 模式）。

{_GOALS_CONVERGENCE_RULES}
{_GOALS_DIALOGUE_MCP_RULES}

## 流程
1. 請使用者用一兩句話定義**本輪里程碑**（寫入你的內部筆記，之後每輪回覆開頭用一行重述里程碑當邊界）。
2. 提出 3～6 個**里程碑內**粗子目標草案，對仍模糊的點用收斂式提問。
3. 討論涉及專案現況時用 MCP 查證後再描述。
4. 使用者 `/write` 時輸出完整 build_goals.yaml（```yaml fence），含 project、goal、system_context、mcp_servers、tasks；
   mcp_servers 建議 `["unity"]`（與 Harness 執行一致）；勿含 status/verification。
"""

GOALS_MODIFY_SYSTEM = f"""你是 Unity MCP Harness 藍圖編輯助手（**modify** 模式）。

{_GOALS_CONVERGENCE_RULES}
{_GOALS_DIALOGUE_MCP_RULES}

## 流程
- 在**既有藍圖範圍**內增刪改 tasks；不擅自改寫整個專案方向，除非使用者明確要求。
- 列出編號子目標後，針對使用者選擇的項目做收斂式澄清；涉及現有程式/場景時先 MCP 查證。
- `/write` 時只輸出更新後的 **tasks** 陣列（```yaml fence）。
"""

_MILESTONE_PATTERN = re.compile(
    r"(?:里程碑|milestone)\s*[:：]\s*(.+)",
    re.I,
)


@dataclass
class GoalsDialogueState:
    """對話狀態（里程碑邊界）。"""

    milestone: str | None = None
    history: list[str] = field(default_factory=list)

    def note_milestone_from_user(self, text: str) -> bool:
        m = _MILESTONE_PATTERN.search(text)
        if m:
            self.milestone = m.group(1).strip()
            return True
        if self.milestone is None and len(text) > 10 and not text.startswith("/"):
            # 首段較長描述視為里程碑草稿（尚未正式標記時）
            if any(k in text for k in ("實作", "完成", "建立", "整合", "驗證", "修復")):
                self.milestone = text.strip()[:500]
                return True
        return False

    def boundary_prefix(self) -> str:
        if not self.milestone:
            return "【尚未固定里程碑 — 請使用者先用一兩句話定義本輪範圍，勿發散提問】"
        return f"【本輪里程碑邊界 — 僅討論此範圍內】{self.milestone}"


def _load_auxiliary_context() -> str:
    parts: list[str] = []
    try:
        from core.project_state.context import format_project_state_for_planning

        ps = format_project_state_for_planning(max_chars=1500)
        if ps.strip():
            parts.append("【project_state 摘要 — 可能過期，現場以 MCP 為準】\n" + ps.strip())
    except Exception:
        pass

    goals_path = resolve_goals_path()
    if goals_path.is_file():
        try:
            plan = resolve_build_plan(plan_path=goals_path)
            if plan.goal:
                parts.append(f"【既有 build_goals.goal】{plan.goal[:400]}")
        except Exception:
            pass
    return "\n\n".join(parts)


def _create_mcp_chat(
    *,
    system: str,
    model: str | None,
    unity_config_path: str | None,
    specs: dict[str, dict[str, Any]] | None,
    max_tool_rounds: int = 10,
):
    from unity_common import create_unity_chat

    resolved_specs = specs or resolve_server_specs(config_path=unity_config_path)
    names = registered_server_names(resolved_specs, config_path=unity_config_path)
    if not names:
        names = ["unity"]
    aux = _load_auxiliary_context()
    full_system = system
    if aux:
        full_system = system + "\n\n" + aux
    return create_unity_chat(
        names,
        model=resolve_unity_llm_model(model),
        system=full_system,
        max_tool_rounds=max_tool_rounds,
        include_tool_messages_in_history=True,
        specs=resolved_specs,
        config_path=unity_config_path,
    )


def _ask_with_boundary(chat, state: GoalsDialogueState, user_text: str) -> str:
    prefix = state.boundary_prefix()
    if user_text.lower().startswith("/mcp "):
        query = user_text[5:].strip()
        prompt = (
            f"{prefix}\n\n"
            "【使用者要求 MCP 查詢】\n"
            f"{query}\n\n"
            "請僅用唯讀 MCP 工具查證後回答；引用工具回傳；勿修改 Editor。"
        )
    else:
        prompt = f"{prefix}\n\n【使用者】\n{user_text}"
    return chat.ask(prompt)


def run_goals_dialogue_loop(
    chat,
    *,
    state: GoalsDialogueState,
    help_text: str,
    on_write,
) -> int:
    print(help_text.strip())
    print("-" * 40)
    print(
        "提示：先說明本輪**里程碑**（一句話範圍）；討論現有腳本/場景時我會用 MCP 查證。"
        " 可用 /mcp 強制查詢。"
    )
    print("-" * 40)

    while True:
        try:
            user_input = input("你: ").strip()
        except EOFError:
            print()
            break
        if not user_input:
            continue
        lower = user_input.lower()
        if lower in ("/quit", "/exit", "quit", "exit"):
            print("已取消，未寫入檔案。")
            return 0
        if lower in ("/help", "help", "?"):
            print(help_text)
            continue
        if lower == "/write":
            try:
                on_write(chat, state)
                return 0
            except Exception as exc:
                handle_errors(exc)
                continue

        state.note_milestone_from_user(user_input)
        state.history.append(f"使用者: {user_input}")
        try:
            reply = _ask_with_boundary(chat, state, user_input)
            print(f"助理: {reply}\n")
            state.history.append(f"助理: {reply[:3000]}")
        except Exception as exc:
            handle_errors(exc)
    return 0
