"""--tasks modify 對話：調整 task_list 規劃欄位 + MCP 查證。"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from core.dialogue_config import DIALOGUE_HISTORY_ENTRY_MAX_CHARS, DIALOGUE_HISTORY_MAX_ENTRIES
from core.goals_dialogue import GoalsDialogueState, _MILESTONE_PATTERN
from core.pipeline.schema import HarnessTask, TaskListDocument
from core.pipeline.store import default_task_list_path, load_task_list, save_task_list
from core.task_list_merge import extract_tasks_yaml_from_text, merge_task_list_from_dialogue
from tasks import resolve_build_plan, resolve_goals_path

TASKS_MODIFY_HELP = """
指令：
  /help      顯示說明
  /mcp TEXT  強制以 Unity MCP 唯讀查詢現場
  /draft     顯示目前修改草案（討論中累積的 tasks YAML）
  /write     依修改草案合併寫入 task_list.yaml（不再另起 LLM 重寫）
  /quit      離開不儲存
"""

TASKS_MODIFY_SYSTEM = """你是 Unity MCP Harness 執行隊列編輯助手（**task_list modify** 模式）。

## 工作方式（必守）
1. **開場已載入**完整 `task_list.yaml`（見下方【目前 task_list 全文】）— 以此為基準，不要假設未載入。
2. 與使用者討論要如何**增刪改**各任務的 description / prompt / priority / harness 等**規劃欄位**。
3. 每當達成一段共識、或使用者要求列出腳本/修改清單時，輸出 **修改草案**：```yaml 內的 `tasks:` 陣列**（完整列出調整後的任務列表）。
4. 使用者輸入 `/write` 時，Harness 會將**最後一份修改草案**合併寫入磁碟（保留 status、verification、pipeline_records），**不會**在 /write 時重新生成內容。
5. 若尚未輸出過含 `tasks` 的 yaml 草案就無法寫入— 請在討論中主動給出草案。

## Unity MCP（唯讀）
- 討論**現有**腳本、場景、資產時，**必須**先呼叫唯讀 MCP，並把查到的 asset path 寫進對應任務的 description（如 **修改腳本:**）與 prompt。
- 優先 `assets-find`（filter 如 `t:Script`、`l:Assets/Scripts/Attack`）、`gameobject-find`。
- 本模式不可修改 Editor。

## 修改草案 YAML 格式
- 僅輸出 ```yaml fence 內的 **tasks** 陣列（或含 tasks 鍵的映射）。
- 每筆含 id、description、prompt、priority；可含 title、target、expected、harness。
- **勿**輸出 status、verification、pipeline_records。
- 若要刪除任務，在 tasks 中省略該 id。
- 腳本清單請寫入各任務 description / prompt，勿只在 prose 裡列清單而不寫進 yaml。
"""


@dataclass
class TasksModifyState(GoalsDialogueState):
    """task_list modify 對話狀態：討論中累積修改草案。"""

    draft_tasks: list[dict[str, Any]] | None = None
    initial_plan_revision: int = 1

    def append_history(self, role: str, text: str) -> None:
        cap = DIALOGUE_HISTORY_ENTRY_MAX_CHARS
        entry = f"{role}: {text[:cap]}{'…' if len(text) > cap else ''}"
        self.history.append(entry)
        if len(self.history) > DIALOGUE_HISTORY_MAX_ENTRIES:
            self.history = self.history[-DIALOGUE_HISTORY_MAX_ENTRIES:]

    def note_draft_from_reply(self, reply: str) -> bool:
        tasks = extract_tasks_yaml_from_text(reply)
        if not tasks:
            return False
        self.draft_tasks = tasks
        return True

    def draft_summary(self) -> str:
        if not self.draft_tasks:
            return "（尚無修改草案 — 請在討論中輸出含 tasks 的 ```yaml 區塊）"
        ids = [str(t.get("id", "?")) for t in self.draft_tasks]
        return f"（修改草案：{len(self.draft_tasks)} 項任務 — {', '.join(ids)}）"


def print_numbered_harness_tasks(doc: TaskListDocument) -> None:
    if not doc.tasks:
        print("（目前無任務）")
        return
    for i, t in enumerate(doc.tasks, 1):
        desc = (t.description or t.id)[:120]
        print(f"  {i}. [{t.id}] status={t.status} priority={t.priority}")
        print(f"     {desc}{'…' if len(desc) >= 120 else ''}")


def format_task_detail(t: HarnessTask) -> str:
    lines = [
        f"id: {t.id}",
        f"status: {t.status}  verification: {t.verification}",
        f"priority: {t.priority}",
        f"description: {t.description}",
    ]
    if t.title:
        lines.append(f"title: {t.title}")
    if t.prompt:
        lines.append(f"prompt:\n{t.prompt}")
    harness = t.harness.to_dict()
    if harness:
        lines.append(f"harness: {yaml.safe_dump(harness, allow_unicode=True).strip()}")
    return "\n".join(lines)


def format_full_task_list_for_system(doc: TaskListDocument) -> str:
    """啟動時注入完整 task_list（規劃 + 執行期欄位摘要）。"""
    payload = doc.to_dict()
    text = yaml.safe_dump(payload, allow_unicode=True, sort_keys=False, default_flow_style=False)
    max_chars = 80_000
    if len(text) > max_chars:
        text = text[:max_chars] + "\n…（其餘內容請用 /detail N 查看單一任務）"
    return text


def load_tasks_modify_system_context(doc: TaskListDocument, *, path: Path) -> str:
    parts = [
        f"【task_list 路徑】{path.resolve()}",
        f"【plan_revision】{doc.plan_revision}",
        f"【目前 task_list 全文 — 討論與草案皆以此為準】\n{format_full_task_list_for_system(doc)}",
    ]
    goals_path = resolve_goals_path()
    if goals_path.is_file():
        try:
            plan = resolve_build_plan(plan_path=goals_path)
            if plan.goal:
                parts.append(f"【build_goals.goal — 邊界參考】\n{plan.goal[:800]}")
        except Exception:
            pass
    try:
        from core.project_state.context import format_project_state_for_planning

        ps = format_project_state_for_planning(max_chars=2000)
        if ps.strip():
            parts.append("【project_state 摘要 — 可能過期，現場以 MCP 為準】\n" + ps.strip())
    except Exception:
        pass
    return "\n\n".join(parts)


def apply_draft_to_task_list(
    doc: TaskListDocument,
    state: TasksModifyState,
    *,
    path: Path,
) -> None:
    if not state.draft_tasks:
        raise ValueError(
            "尚無修改草案。請在討論中讓助理輸出含 tasks 的 ```yaml 區塊；"
            "可用 /draft 查看是否已累積草案。"
        )
    merge_task_list_from_dialogue(doc, {"tasks": state.draft_tasks})
    save_task_list(doc, path)
    from core.cli_extended import write_capabilities_marker

    write_capabilities_marker()


def run_tasks_modify_dialogue(
    chat,
    *,
    doc: TaskListDocument,
    path: Path,
    state: TasksModifyState,
    mcp_available: bool,
) -> int:
    goal_hint = ""
    try:
        gp = resolve_goals_path()
        if gp.is_file():
            plan = resolve_build_plan(plan_path=gp)
            if plan.goal and not state.milestone:
                state.milestone = plan.goal[:500]
            goal_hint = plan.goal or plan.project or ""
    except Exception:
        pass

    if goal_hint and not state.milestone:
        state.milestone = goal_hint[:500]

    state.initial_plan_revision = doc.plan_revision
    print(f"已載入 {path.name}（plan_revision={doc.plan_revision}，{len(doc.tasks)} 項任務）")
    print("討論中助理輸出的 ```yaml tasks``` 會累積為修改草案；/write 僅將草案合併寫入，不會另起一輪生成。")
    print(state.draft_summary())
    print("\n【--tasks modify】目前子目標：")
    print_numbered_harness_tasks(doc)
    print("\n可輸入編號或 id 討論；/detail N 查看完整描述。")
    if not mcp_available:
        print("（目前無 MCP — 討論程式/場景前請先連線 Unity）")

    help_text = TASKS_MODIFY_HELP

    print(help_text.strip())
    print("-" * 40)
    print("提示：達成共識時請助理輸出 tasks 的 yaml 草案；/write 寫入的是該草案。")
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
        if lower in ("/draft", "/show"):
            if state.draft_tasks:
                print(yaml.safe_dump(
                    {"tasks": state.draft_tasks},
                    allow_unicode=True,
                    sort_keys=False,
                    default_flow_style=False,
                ))
            else:
                print(state.draft_summary())
            continue
        if lower.startswith("/detail"):
            parts = user_input.split()
            if len(parts) < 2:
                print("用法: /detail <編號>")
                continue
            try:
                idx = int(parts[1]) - 1
                if 0 <= idx < len(doc.tasks):
                    print(format_task_detail(doc.tasks[idx]))
                else:
                    print("編號超出範圍")
            except ValueError:
                print("用法: /detail <編號>")
            continue
        if lower == "/write":
            try:
                apply_draft_to_task_list(doc, state, path=path)
                print(
                    f"已依修改草案合併寫入 {path}（{len(doc.tasks)} 項，"
                    f"plan_revision {state.initial_plan_revision} → {doc.plan_revision}）"
                )
                return 0
            except Exception as exc:
                from unity_common import handle_errors

                handle_errors(exc)
                continue

        m = _MILESTONE_PATTERN.search(user_input)
        if m:
            state.milestone = m.group(1).strip()
        elif state.milestone is None and len(user_input) > 10 and not user_input.startswith("/"):
            if any(k in user_input for k in ("實作", "完成", "建立", "整合", "驗證", "修復")):
                state.milestone = user_input.strip()[:500]

        state.append_history("使用者", user_input)

        from core.goals_dialogue import _ask_with_boundary

        try:
            reply = _ask_with_boundary(chat, state, user_input)
            print(f"助理: {reply}\n")
            state.append_history("助理", reply)
            if state.note_draft_from_reply(reply):
                print(state.draft_summary())
                print("（已更新修改草案 — /write 將寫入此版本）\n")
        except Exception as exc:
            from unity_common import handle_errors

            handle_errors(exc)
    return 0
