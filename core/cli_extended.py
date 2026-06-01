"""EXECUTE.md §12 擴充 CLI：--goals、--tools、--chat、--sync、--status。"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

import yaml

from core.pipeline.goals_writeback import write_back_task_list_goals
from core.pipeline.store import default_task_list_path, load_task_list
from core.project_state.bootstrap import format_bootstrap_report, run_bootstrap_state
from core.project_state.paths import default_project_state_root
from core.project_state.ssot import sync_project_state_from_task_list
from tasks import resolve_build_plan, resolve_goals_path
from unity_common import (
    handle_errors,
    list_unity_tools,
    project_root,
    registered_server_names,
    require_aicentral_config,
    resolve_server_specs,
    resolve_unity_llm_model,
)
from core.goals_dialogue import (
    GOALS_INIT_HELP,
    GOALS_INIT_SYSTEM,
    GOALS_MODIFY_HELP,
    GOALS_MODIFY_SYSTEM,
    GoalsDialogueState,
    run_goals_dialogue_loop,
)
from core.tasks_dialogue import (
    TASKS_MODIFY_SYSTEM,
    TasksModifyState,
    load_tasks_modify_system_context,
    run_tasks_modify_dialogue,
)
from core.mcp.server_lifecycle import UnityMcpServerError, UnityMcpServerSession

CAPABILITIES_MARKER_FILE = "harness_capabilities.marker"
EXECUTE_SECTION_12_TAG = "HARNESS_EXECUTE_12_IMPLEMENTED"


def capabilities_marker_path() -> Path:
    from unity_common import workspace_root

    return workspace_root() / "config" / CAPABILITIES_MARKER_FILE


def write_capabilities_marker() -> Path:
    """寫入完成標記（供使用者與 Agent 確認 §12 已實作）。"""
    path = capabilities_marker_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    body = {
        "tag": EXECUTE_SECTION_12_TAG,
        "features": [
            "--goals [build|init|modify]",
            "--tools [--json]",
            "--chat",
            "--sync",
            "--status",
        ],
        "notes": "舊 unity-mcp-list-tools / unity-mcp-chat 仍可用；建議改用統一入口。",
    }
    path.write_text(yaml.safe_dump(body, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return path


def run_list_tools(*, unity_config: str | None, as_json: bool) -> int:
    require_aicentral_config()
    try:
        specs = resolve_server_specs(config_path=unity_config)
        with UnityMcpServerSession(specs):
            tools_map = list_unity_tools(specs=specs, config_path=unity_config)
    except Exception as exc:
        handle_errors(exc)
        return 1

    if as_json:
        print(json.dumps(tools_map, ensure_ascii=False, indent=2))
        return 0

    names = registered_server_names(specs)
    print(f"Unity MCP servers: {', '.join(names)}")
    print("-" * 40)
    for server, tools in tools_map.items():
        print(f"[{server}] {len(tools)} 個工具")
        for tool in tools:
            tname = tool.get("name", "?")
            desc = (tool.get("description") or "")[:80]
            line = f"  - {tname}: {desc}"
            try:
                print(line)
            except UnicodeEncodeError:
                enc = getattr(sys.stdout, "encoding", None) or "utf-8"
                print(line.encode(enc, errors="replace").decode(enc))
    return 0


def run_sync_goals(*, goals_file: str | None, backup: bool) -> int:
    """task_list.yaml → build_goals.yaml（規劃欄位摘要）。"""
    task_path = default_task_list_path()
    if not task_path.is_file():
        print(f"錯誤: 找不到 {task_path}", file=sys.stderr)
        return 1
    try:
        doc = load_task_list(task_path)
        out = write_back_task_list_goals(doc, goals_file, backup=backup)
    except (FileNotFoundError, ValueError, OSError) as exc:
        handle_errors(exc)
        return 1
    print(f"已將 task_list 規劃欄位寫回 {out}")
    return 0


def run_status_update(
    *,
    unity_config: str | None,
    bootstrap_prompt: str | None,
    aicentral_config: str | None,
    secret: str | None,
) -> int:
    """全面更新 project_state：MCP 盤點 + task_list SSOT 同步。"""
    root = default_project_state_root()
    if not root.is_dir():
        print("錯誤: 找不到 project_state/，請先 unity-mcp-harness --init", file=sys.stderr)
        return 1

    require_aicentral_config(aicentral_config=aicentral_config, secret=secret)
    try:
        report = run_bootstrap_state(
            unity_config_path=unity_config,
            prompt=bootstrap_prompt,
        )
    except Exception as exc:
        handle_errors(exc)
        return 1
    print(format_bootstrap_report(report))
    if not report.ok:
        return 1

    task_path = default_task_list_path()
    if task_path.is_file():
        try:
            doc = load_task_list(task_path)
            n = sync_project_state_from_task_list(doc)
            print(f"已依 task_list 同步 project_state（{n} 個任務檔）")
        except (ValueError, OSError) as exc:
            handle_errors(exc)
            return 1
    else:
        print("（無 task_list.yaml，略過 SSOT 同步）")

    marker = write_capabilities_marker()
    print(f"狀態更新完成。能力標記: {marker} ({EXECUTE_SECTION_12_TAG})")
    return 0


def run_chat_mode(args: Any) -> int:
    from unity_mcp_chat import run_interactive_chat

    try:
        run_interactive_chat(
            unity_config=getattr(args, "unity_config", None),
            servers=getattr(args, "servers", None),
            no_tool_history=getattr(args, "no_tool_history", False),
            no_probe=getattr(args, "no_probe", False),
            probe=getattr(args, "probe", False),
            aicentral_config=getattr(args, "aicentral_config", None),
            secret=getattr(args, "secret", None),
        )
        return 0
    except SystemExit as code:
        return int(code) if isinstance(code, int) else 0


def _extract_yaml_block(text: str) -> dict[str, Any]:
    raw = text.strip()
    fence = re.search(r"```(?:yaml)?\s*([\s\S]*?)```", raw, re.I)
    if fence:
        raw = fence.group(1).strip()
    data = yaml.safe_load(raw)
    if isinstance(data, list):
        return {"tasks": data}
    if not isinstance(data, dict):
        raise ValueError("須為 YAML 映射（頂層含 project、tasks 等）或 tasks 陣列")
    return data


def _goals_path(goals_file: str | None) -> Path:
    return resolve_goals_path(goals_file)


def _print_numbered_tasks(plan) -> None:
    tasks = plan.enabled_tasks()
    if not tasks:
        print("（目前無子目標）")
        return
    for i, t in enumerate(tasks, 1):
        obj = (t.objective or t.prompt or "")[:120]
        print(f"  {i}. [{t.id}] {t.title}")
        if obj:
            print(f"     {obj}{'…' if len(obj) >= 120 else ''}")


def _run_goals_with_mcp(
    *,
    unity_config_path: str | None,
    model: str | None,
    system: str,
    dialogue_fn,
    initial_state=None,
    no_mcp: bool = False,
) -> int:
    """在 Unity MCP 連線下執行 goals 對話（no_mcp 僅供測試）。"""
    from aicentral import Chat
    from core.goals_dialogue import _create_mcp_chat

    state = initial_state if initial_state is not None else GoalsDialogueState()

    if no_mcp:
        chat = Chat.stateless(system=system, model=resolve_unity_llm_model(model))
        return dialogue_fn(chat, state, mcp_available=False)

    specs = resolve_server_specs(config_path=unity_config_path)
    try:
        with UnityMcpServerSession(specs, autostart=True):
            chat = _create_mcp_chat(
                system=system,
                model=model,
                unity_config_path=unity_config_path,
                specs=specs,
                max_tool_rounds=12,
            )
    except (UnityMcpServerError, OSError, ConnectionError) as exc:
        print(
            f"警告: Unity MCP 無法連線（{exc}），改為無 MCP 模式；"
            "討論現況可能不準確。可用 /mcp 在連線恢復後重試。",
            file=sys.stderr,
        )
        chat = Chat.stateless(system=system, model=resolve_unity_llm_model(model))
        return dialogue_fn(chat, state, mcp_available=False)

    print("（已連線 Unity MCP — 討論現有專案內容時將以唯讀工具查證）")
    return dialogue_fn(chat, state, mcp_available=True)


def run_goals_init(
    *,
    goals_file: str | None,
    model: str | None,
    aicentral_config: str | None,
    secret: str | None,
    unity_config_path: str | None = None,
    no_mcp: bool = False,
) -> int:
    """對話建立 build_goals.yaml（收斂澄清 + MCP 查證）。"""
    require_aicentral_config(aicentral_config=aicentral_config, secret=secret)
    path = _goals_path(goals_file)
    print(f"藍圖檔：{path}")

    def _dialogue(chat, state: GoalsDialogueState, *, mcp_available: bool) -> int:
        print("【--goals init】定義里程碑與子目標（收斂於里程碑邊界內）。")
        if not mcp_available:
            print("（目前無 MCP — 請先啟動 Unity Editor 與 MCP Server）")

        def on_write(write_chat, write_state: GoalsDialogueState) -> None:
            parts = [
                write_state.boundary_prefix(),
                "請根據以上討論輸出完整 build_goals.yaml（YAML，```yaml fence）。",
                "mcp_servers 使用 [unity]；system_context 須反映專案現況（以 MCP 查證為準）。",
            ]
            if write_state.history:
                parts.insert(1, "討論摘要：\n" + "\n".join(write_state.history[-24:]))
            reply = write_chat.ask("\n\n".join(parts))
            data = _extract_yaml_block(reply)
            if isinstance(data.get("mcp_servers"), list) and data["mcp_servers"]:
                first = data["mcp_servers"][0]
                if isinstance(first, dict) and "name" in first:
                    data["mcp_servers"] = ["unity"]
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                yaml.safe_dump(data, allow_unicode=True, sort_keys=False, default_flow_style=False),
                encoding="utf-8",
            )
            print(f"已寫入 {path}")
            write_capabilities_marker()

        return run_goals_dialogue_loop(
            chat, state=state, help_text=GOALS_INIT_HELP, on_write=on_write
        )

    return _run_goals_with_mcp(
        unity_config_path=unity_config_path,
        model=model,
        system=GOALS_INIT_SYSTEM,
        dialogue_fn=_dialogue,
        no_mcp=no_mcp,
    )


def run_goals_modify(
    *,
    goals_file: str | None,
    model: str | None,
    aicentral_config: str | None,
    secret: str | None,
    unity_config_path: str | None = None,
    no_mcp: bool = False,
) -> int:
    """對話調整既有 build_goals tasks（收斂 + MCP）。"""
    require_aicentral_config(aicentral_config=aicentral_config, secret=secret)
    path = _goals_path(goals_file)
    print(f"藍圖檔：{path}")
    if not path.is_file():
        print(f"錯誤: 找不到 {path}，請先 --goals init 或手動建立。", file=sys.stderr)
        return 1

    plan = resolve_build_plan(plan_path=path)
    base_yaml = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(base_yaml, dict):
        print("錯誤: build_goals 格式無效", file=sys.stderr)
        return 1

    context = yaml.safe_dump(
        {
            "project": plan.project,
            "goal": plan.goal,
            "tasks": [
                {
                    "id": t.id,
                    "title": t.title,
                    "objective": t.objective,
                    "prompt": t.prompt,
                }
                for t in plan.tasks
            ],
        },
        allow_unicode=True,
        sort_keys=False,
    )
    system = GOALS_MODIFY_SYSTEM + f"\n\n【目前藍圖 — 僅在此範圍內修改】\n{context}"
    state_seed = GoalsDialogueState(milestone=(plan.goal or plan.project or "")[:500])

    def _dialogue(chat, state: GoalsDialogueState, *, mcp_available: bool) -> int:
        if state_seed.milestone and not state.milestone:
            state.milestone = state_seed.milestone
        print("【--goals modify】調整既有 build_goals（收斂於既有 goal 範圍）。先列出子目標：")
        _print_numbered_tasks(plan)
        if not mcp_available:
            print("（目前無 MCP — 討論程式/場景前請先連線 Unity）")

        def on_write(write_chat, write_state: GoalsDialogueState) -> None:
            prompt = "\n\n".join(
                [
                    write_state.boundary_prefix(),
                    "討論摘要：\n" + "\n".join(write_state.history[-30:]),
                    "請輸出更新後的 tasks（YAML ```yaml fence），僅 tasks 陣列或含 tasks 鍵的映射。",
                ]
            )
            reply = write_chat.ask(prompt)
            parsed = _extract_yaml_block(reply)
            if "tasks" in parsed:
                new_tasks = parsed["tasks"]
            elif isinstance(parsed, list):
                new_tasks = parsed
            else:
                raise ValueError("回應須含 tasks 陣列")
            if not isinstance(new_tasks, list):
                raise ValueError("tasks 須為列表")
            base_yaml["tasks"] = new_tasks
            path.write_text(
                yaml.safe_dump(
                    base_yaml, allow_unicode=True, sort_keys=False, default_flow_style=False
                ),
                encoding="utf-8",
            )
            print(f"已更新 {path} 的 tasks（{len(new_tasks)} 項）")
            write_capabilities_marker()

        return run_goals_dialogue_loop(
            chat, state=state, help_text=GOALS_MODIFY_HELP, on_write=on_write
        )

    return _run_goals_with_mcp(
        unity_config_path=unity_config_path,
        model=model,
        system=system,
        dialogue_fn=_dialogue,
        initial_state=state_seed,
        no_mcp=no_mcp,
    )


def run_tasks_modify(
    *,
    model: str | None,
    aicentral_config: str | None,
    secret: str | None,
    unity_config_path: str | None = None,
    task_list_path: Path | str | None = None,
    no_mcp: bool = False,
) -> int:
    """對話調整 task_list 規劃欄位（合併寫回，保留執行期狀態）。"""
    require_aicentral_config(aicentral_config=aicentral_config, secret=secret)
    path = Path(task_list_path) if task_list_path else default_task_list_path()
    print(f"執行隊列：{path.resolve()}")
    if not path.is_file():
        print(f"錯誤: 找不到 {path}，請先 --goals build。", file=sys.stderr)
        return 1
    try:
        doc = load_task_list(path)
    except (ValueError, OSError) as exc:
        handle_errors(exc)
        return 1

    system = TASKS_MODIFY_SYSTEM + "\n\n" + load_tasks_modify_system_context(doc, path=path)
    state_seed = TasksModifyState()

    def _dialogue(chat, state: GoalsDialogueState, *, mcp_available: bool) -> int:
        if not isinstance(state, TasksModifyState):
            state = state_seed
        if state_seed.milestone and not state.milestone:
            state.milestone = state_seed.milestone
        return run_tasks_modify_dialogue(
            chat,
            doc=doc,
            path=path,
            state=state,
            mcp_available=mcp_available,
        )

    return _run_goals_with_mcp(
        unity_config_path=unity_config_path,
        model=model,
        system=system,
        dialogue_fn=_dialogue,
        initial_state=state_seed,
        no_mcp=no_mcp,
    )


def run_goals_build_mode() -> int:
    """build 模式由 run_build 主流程處理。"""
    return -1  # sentinel: continue main
