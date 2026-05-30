"""Unity 建構目標與任務清單載入。"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from unity_common import project_root

LOCAL_GOALS_FILE = "build_goals.yaml"
ENV_GOALS_PATH = "UNITY_BUILD_GOALS"
VALIDATE_TASK_ID = "validate_scene"
VALIDATE_TASK_IDS = frozenset({VALIDATE_TASK_ID, "validate_2d_scene"})


def is_validate_task(task_id: str) -> bool:
    return task_id in VALIDATE_TASK_IDS


@dataclass
class BuildTask:
    """單一 Unity 建構任務（由 LLM + MCP 在 Editor 內執行）。"""

    id: str
    title: str
    prompt: str
    objective: str = ""
    enabled: bool = True
    mcp_servers: list[str] | None = None  # None = 使用建構檔頂層 mcp_servers


@dataclass
class BuildPlan:
    """整份建構計畫（對應 build_goals.yaml 頂層欄位）。"""

    project: str = "UnityProject"
    model: str | None = None
    max_tool_rounds: int = 10
    mcp_servers: list[str] = field(default_factory=lambda: ["unity"])
    tasks: list[BuildTask] = field(default_factory=list)
    goal: str = ""
    definition_of_done: list[str] = field(default_factory=list)
    execution_strategy: dict[str, Any] = field(default_factory=dict)
    system_context: str = ""

    def enabled_tasks(self) -> list[BuildTask]:
        return [t for t in self.tasks if t.enabled]


@dataclass
class TaskResult:
    """單一任務執行結果。"""

    id: str
    title: str
    success: bool
    reply: str
    error: str | None = None


def _strip_multiline(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _parse_string_list(raw: Any) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        return [line.strip() for line in raw.strip().splitlines() if line.strip()]
    if isinstance(raw, list):
        return [str(item).strip() for item in raw if str(item).strip()]
    return []


def _parse_execution_strategy(raw: Any) -> dict[str, Any]:
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return dict(raw)
    if isinstance(raw, str) and raw.strip():
        return {"description": raw.strip()}
    return {}


def format_execution_strategy(strategy: dict[str, Any]) -> str:
    """將 execution_strategy 物件轉成可讀文字（送進 prompt）。"""
    if not strategy:
        return ""
    if "description" in strategy and len(strategy) == 1:
        return str(strategy["description"])

    lines: list[str] = []
    mode = strategy.get("mode")
    if mode:
        lines.append(f"模式: {mode}")
    for key, label in (("priorities", "優先順序"), ("behavior", "行為")):
        items = strategy.get(key)
        if isinstance(items, list) and items:
            lines.append(f"{label}:")
            lines.extend(f"  - {item}" for item in items)
    for key, value in strategy.items():
        if key in {"mode", "priorities", "behavior", "description"}:
            continue
        lines.append(f"{key}: {value}")
    return "\n".join(lines)


def format_definition_of_done(items: list[str], *, heading: str) -> list[str]:
    if not items:
        return []
    return [heading, *[f"  - {item}" for item in items]]


def _parse_task(raw: dict[str, Any]) -> BuildTask:
    tid = str(raw.get("id", "")).strip()
    if not tid:
        raise ValueError("任務缺少 id")
    title = str(raw.get("title", tid)).strip()
    prompt = str(raw.get("prompt", "")).strip()
    if not prompt:
        raise ValueError(f"任務 {tid!r} 缺少 prompt")
    enabled = bool(raw.get("enabled", True))
    objective = _strip_multiline(raw.get("objective"))
    servers = raw.get("mcp_servers")
    mcp_list = None
    if isinstance(servers, list):
        mcp_list = [str(s).strip() for s in servers if str(s).strip()]
    return BuildTask(
        id=tid,
        title=title,
        prompt=prompt,
        objective=objective,
        enabled=enabled,
        mcp_servers=mcp_list,
    )


def load_build_plan(path: Path | str) -> BuildPlan:
    """從 YAML 或 JSON 載入建構計畫。"""
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"找不到建構任務檔: {p}")

    text = p.read_text(encoding="utf-8")
    if p.suffix.lower() in {".json"}:
        data = json.loads(text)
    else:
        data = yaml.safe_load(text)
    if not isinstance(data, dict):
        raise ValueError(f"建構檔須為物件: {p}")

    plan = BuildPlan(
        project=str(data.get("project", "UnityProject")),
        model=data.get("model"),
        max_tool_rounds=int(data.get("max_tool_rounds", 10)),
        goal=_strip_multiline(data.get("goal")),
        definition_of_done=_parse_string_list(data.get("definition_of_done")),
        execution_strategy=_parse_execution_strategy(data.get("execution_strategy")),
        system_context=_strip_multiline(data.get("system_context")),
    )

    servers = data.get("mcp_servers")
    if isinstance(servers, list):
        plan.mcp_servers = [str(s).strip() for s in servers if str(s).strip()]
    elif isinstance(servers, str) and servers.strip():
        plan.mcp_servers = [servers.strip()]

    raw_tasks = data.get("tasks")
    if not isinstance(raw_tasks, list) or not raw_tasks:
        raise ValueError(f"建構檔須包含非空 tasks 列表: {p}")
    plan.tasks = [_parse_task(t) for t in raw_tasks if isinstance(t, dict)]
    return plan


def resolve_build_plan(*, plan_path: Path | str | None = None) -> BuildPlan:
    """解析建構檔路徑（參數 > 環境變數 > 本目錄 build_goals.yaml > example）。"""
    import os

    if plan_path is not None:
        return load_build_plan(plan_path)

    env = os.environ.get(ENV_GOALS_PATH, "").strip()
    if env:
        return load_build_plan(env)

    local = project_root() / LOCAL_GOALS_FILE
    if local.is_file():
        return load_build_plan(local)

    example = project_root() / "build_goals.example.yaml"
    if example.is_file():
        return load_build_plan(example)

    raise FileNotFoundError(
        f"找不到 {LOCAL_GOALS_FILE}；請複製 build_goals.example.yaml 並編輯任務"
    )


def format_task_prompt(
    task: BuildTask,
    *,
    plan: BuildPlan,
    prior_results: list[TaskResult],
    harness_task: Any | None = None,
    resume: bool = False,
) -> str:
    """組裝送給 Unity MCP Chat 的單任務提示（含 goal、DoD、Harness SSOT 與已完成摘要）。

    當提供 ``harness_task`` 時，【本任務要求】使用 task_list 內已規範化的 ``prompt``（見
    ``harness_task_to_build_task``），並注入 ``pipeline_records`` 摘要。
    """
    from core.pipeline.context import format_harness_task_context
    from core.pipeline.schema import HarnessTask

    lines = [
        f"【Unity 建構任務】{task.id} — {task.title}",
        f"【專案】{plan.project}",
    ]

    if plan.goal:
        lines.extend(["", "【總體目標】", plan.goal])

    strategy_text = format_execution_strategy(plan.execution_strategy)
    if strategy_text:
        lines.extend(["", "【執行策略】", strategy_text])

    dod_heading = "【完成定義（Definition of Done）】"
    if is_validate_task(task.id) and plan.definition_of_done:
        lines.extend(
            [
                "",
                dod_heading,
                "請逐項透過 MCP 工具核對；未滿足者須自動修復後再回報。",
                *[f"  - {item}" for item in plan.definition_of_done],
            ]
        )
    elif plan.definition_of_done:
        lines.extend(
            format_definition_of_done(
                plan.definition_of_done,
                heading=dod_heading + "（本建構全程須滿足）",
            )
        )

    if plan.system_context:
        lines.extend(["", "【Agent 憲法 / 整體情境】", plan.system_context])

    if harness_task is not None and isinstance(harness_task, HarnessTask):
        from core.project_state.context import format_project_state_for_task

        state_ctx = format_project_state_for_task(harness_task)
        if state_ctx:
            lines.extend(["", state_ctx])
        lines.extend(
            [
                "",
                format_harness_task_context(harness_task, resume=resume),
            ]
        )
    elif resume:
        lines.extend(
            [
                "",
                "【Harness】",
                "重啟後須重新 Phase 1 感知（即使先前文字摘要存在）。",
            ]
        )

    if task.objective:
        lines.extend(["", "【本任務目標】", task.objective])

    req_heading = (
        "【本任務要求（來自 task_list 規範化 prompt）】"
        if harness_task is not None
        else "【本任務要求】"
    )
    lines.extend(["", req_heading, task.prompt])

    if prior_results:
        lines.append("")
        lines.append("【已完成任務（請延續同一 Unity 專案狀態）】")
        for r in prior_results:
            status = "成功" if r.success else "失敗"
            snippet = (r.reply[:800] + "…") if len(r.reply) > 800 else r.reply
            if r.error:
                snippet = f"{r.error}"
            lines.append(f"- {r.id} ({status}): {snippet}")

    lines.extend(
        [
            "",
            "請透過 Unity MCP 工具實際修改 Editor 內容完成任務。",
            "Scene 一律使用 Assets/_Scenes/（勿用 Assets/Scenes）。",
            "若發現缺前置條件，請在回覆加入 "
            "[HARNESS_INJECT:{\"id\":\"...\",\"description\":\"...\",\"prompt\":\"...\",\"priority\":9}]。",
            "回覆須包含工具回傳結果（成功/失敗、路徑、物件名），勿只寫「嘗試」。",
            "完成後用繁體中文簡述你執行了哪些操作與目前場景狀態。",
        ]
    )
    return "\n".join(lines)
