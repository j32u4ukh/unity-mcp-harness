"""藍圖 Plan Normalize：將 ``build_goals.yaml`` 粗任務規範化為可執行任務列表。"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from pydantic import BaseModel, Field

from aicentral import Chat
from aicentral.core.errors import StructuredNoPayloadError, StructuredValidationError
from aicentral.exceptions import ProviderError

from core.pipeline.schema import HarnessHints, NormalizedPlan, NormalizedTask, TaskTarget
from tasks import BuildPlan, BuildTask
from unity_common import resolve_unity_llm_model

_logger = logging.getLogger(__name__)

PLAN_NORMALIZE_SYSTEM = """你是 Unity MCP Harness 的規劃器（Plan Normalize）。
你的輸出將寫入 task_list.yaml 並由執行 Agent 依序執行；你**不**直接操作 Unity。

## 任務契約（每條 normalized_tasks 必須滿足）
1. id：穩定 snake_case，可為子任務（如 ensure_2d_camera）。
2. description：一句話說明。
3. prompt：必須包含
   - 具體路徑/物件名（若適用）
   - 冪等語句（已存在則 MCP 驗證後回報「已存在，跳過」）
   - 明確 Phase：先讀現場(Phase1) → 再寫入(Phase2) → 再讀驗證(Phase3)
   - 遵守 system_context 中的 2D 憲法（禁止 MeshRenderer 改色等）
4. priority：整數，越小越先執行。
5. harness（建議）：pre_read / post_read 簡短提示（唯讀 MCP 或 C# 片段）。
6. plan_source_id：若由藍圖粗任務拆分，填寫粗任務 id；否則與 id 相同。
7. target（可選）：game_object、scene_path。

## 規則
- 可將少量粗任務拆成多條可執行子任務（例如 3 條 → 6 條），順序符合依賴。
- 禁止輸出自由散文；僅輸出符合 schema 的 JSON。
- plan_changelog：簡述相對輸入的拆分/合併/改寫（繁體中文）。

## 領域補充（重要）
- 具體領域規則（如 Sprite 幾何、資產生成策略）**不在**本 system prompt。
- 若使用者訊息含【規劃補充片段】，僅將對應片段併入**相關**任務的 prompt / expected / harness，勿自行發明未提供的領域規則。
- 若無補充片段，維持藍圖與憲法即可，不要臆測幾何或資產細節。
"""

_HARNESS_COT_BLOCK = """
【Harness 執行契約 — 本任務必須遵守】
1. Phase 1（感知）：修改前先以 MCP 讀取現場，確認是否已滿足目標。
2. Phase 2（行動）：僅在需要時寫入；已存在則回報「已存在，跳過」並結束。
3. Phase 3（驗證）：寫入後再次讀取，比對預期後再宣告完成。
"""


class _HarnessHintsOut(BaseModel):
    pre_read: str | None = None
    post_read: str | None = None


class _TaskTargetOut(BaseModel):
    game_object: str | None = None
    scene_path: str | None = None


class NormalizedTaskOut(BaseModel):
    id: str
    description: str
    prompt: str
    priority: int = 10
    title: str | None = None
    plan_source_id: str | None = None
    harness: _HarnessHintsOut | None = None
    target: _TaskTargetOut | None = None
    expected: dict[str, Any] = Field(default_factory=dict)


class PlanNormalizeResponse(BaseModel):
    normalized_tasks: list[NormalizedTaskOut]
    plan_changelog: str = ""


def _ensure_harness_cot(prompt: str) -> str:
    body = prompt.strip()
    if "Phase 1" in body and "Phase 3" in body:
        return body
    return body + "\n" + _HARNESS_COT_BLOCK


def _task_from_build(task: BuildTask, *, priority: int) -> NormalizedTask:
    description = task.objective.strip() or task.title
    return NormalizedTask(
        id=task.id,
        description=description,
        title=task.title,
        prompt=_ensure_harness_cot(task.prompt),
        priority=priority,
        plan_source_id=task.id,
    )


def normalize_plan_passthrough(plan: BuildPlan, *, plan_revision: int = 1) -> NormalizedPlan:
    """不呼叫 LLM：逐條轉換藍圖任務並補上 Harness CoT 句式。"""
    enabled = plan.enabled_tasks()
    tasks = [
        _task_from_build(t, priority=(i + 1) * 10)
        for i, t in enumerate(enabled)
    ]
    return NormalizedPlan(
        normalized_tasks=tasks,
        plan_changelog="passthrough：逐條對應 build_goals，已補 Harness CoT 句式",
        plan_revision=plan_revision,
        source_plan="build_goals.yaml",
    )


def _task_from_out(item: NormalizedTaskOut) -> NormalizedTask:
    harness = HarnessHints()
    if item.harness:
        harness = HarnessHints(
            pre_read=item.harness.pre_read,
            post_read=item.harness.post_read,
        )
    target = TaskTarget()
    if item.target:
        target = TaskTarget(
            game_object=item.target.game_object,
            scene_path=item.target.scene_path,
        )
    return NormalizedTask(
        id=item.id.strip(),
        description=item.description.strip(),
        prompt=_ensure_harness_cot(item.prompt),
        priority=int(item.priority),
        title=item.title,
        target=target,
        expected=dict(item.expected or {}),
        harness=harness,
        plan_source_id=item.plan_source_id or item.id,
    )


def parse_normalize_response(raw: str) -> NormalizedPlan:
    """解析 LLM 回傳的 JSON（允許外層 markdown fence）。"""
    text = raw.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fence:
        text = fence.group(1).strip()
    data = json.loads(text)
    if isinstance(data, dict) and "normalized_tasks" in data:
        payload = data
    elif isinstance(data, list):
        payload = {"normalized_tasks": data, "plan_changelog": ""}
    else:
        raise ValueError("normalize 回應須含 normalized_tasks 陣列")
    response = PlanNormalizeResponse.model_validate(payload)
    tasks = [_task_from_out(t) for t in response.normalized_tasks]
    if not tasks:
        raise ValueError("normalized_tasks 不可為空")
    return NormalizedPlan(
        normalized_tasks=tasks,
        plan_changelog=response.plan_changelog.strip(),
        plan_revision=1,
        source_plan="build_goals.yaml",
    )


def build_normalize_user_prompt(
    plan: BuildPlan,
    *,
    extra_context: str = "",
    supplement_context: str = "",
) -> str:
    """組裝送給規劃 LLM 的使用者訊息。"""
    tasks_payload = []
    for t in plan.enabled_tasks():
        tasks_payload.append(
            {
                "id": t.id,
                "title": t.title,
                "objective": t.objective,
                "prompt": t.prompt,
            }
        )
    sections = [
        f"【專案】{plan.project}",
        "",
        "【總體目標 goal】",
        plan.goal or "（未提供）",
        "",
        "【Definition of Done】",
        "\n".join(f"- {x}" for x in plan.definition_of_done) or "（未提供）",
        "",
        "【Agent 憲法 system_context】",
        plan.system_context or "（未提供）",
        "",
        "【藍圖任務 tasks（可能為粗粒度，請規範化/拆分）】",
        json.dumps(tasks_payload, ensure_ascii=False, indent=2),
        "",
        "請輸出 JSON，頂層含 normalized_tasks 與 plan_changelog。",
    ]
    if supplement_context.strip():
        sections.extend(["", supplement_context.strip()])
    from core.project_state.context import format_project_state_for_planning

    project_state_ctx = format_project_state_for_planning()
    if project_state_ctx.strip():
        sections.extend(["", "【Unity 專案狀態文件樹 project_state/】", project_state_ctx.strip()])
    if extra_context.strip():
        sections.extend(["", "【Unity 專案補充（唯讀 MCP）】", extra_context.strip()])
    return "\n".join(sections)


def normalize_plan(
    plan: BuildPlan,
    *,
    model: str | None = None,
    plan_revision: int = 1,
    plan_with_mcp: bool = False,
    plan_interactive: bool = False,
    supplements_path: str | Path | None = None,
    chat: Chat | None = None,
    specs: dict[str, dict[str, Any]] | None = None,
    unity_config_path: str | None = None,
) -> NormalizedPlan:
    """
    以 LLM 規範化藍圖任務；失敗時回退 passthrough。

    ``plan_with_mcp=True`` 時先做一次唯讀 MCP 查詢，將摘要併入規劃 prompt。
    規劃後會依 ``config/prompt_supplements.json`` 注入匹配片段；``plan_interactive=True`` 時對剩餘模糊項終端詢問。
    """
    from core.pipeline.prompt_supplements import (
        enrich_normalized_plan,
        load_prompt_supplements,
        match_supplements_for_task,
        format_supplements_for_normalize_prompt,
    )

    supplement_doc = load_prompt_supplements(supplements_path)
    pre_matched_by_id: dict[str, Any] = {}
    for task in plan.enabled_tasks():
        for sup in match_supplements_for_task(task, supplement_doc):
            pre_matched_by_id[sup.id] = sup
    supplement_context = format_supplements_for_normalize_prompt(list(pre_matched_by_id.values()))

    extra = ""
    if plan_with_mcp:
        from unity_common import ask_unity, register_unity_servers

        register_unity_servers(specs, config_path=unity_config_path)
        try:
            extra = ask_unity(
                "唯讀：列出 Assets 下與 Scenes 相關的資源路徑與目前場景名稱。"
                "不要修改任何東西，只回傳列表摘要。",
                mcp_servers=plan.mcp_servers,
                model=resolve_unity_llm_model(plan.model),
                max_tool_rounds=3,
                specs=specs,
                config_path=unity_config_path,
            )
        except Exception as exc:
            _logger.warning("plan-with-mcp 讀取失敗，繼續純文字規劃: %s", exc)
            extra = f"（MCP 讀取失敗: {exc}）"

    user_prompt = build_normalize_user_prompt(
        plan,
        extra_context=extra,
        supplement_context=supplement_context,
    )
    resolved_model = resolve_unity_llm_model(model or plan.model)
    session = chat or Chat.stateless(system=PLAN_NORMALIZE_SYSTEM, model=resolved_model)

    try:
        result = session.complete_structured(
            user_prompt,
            response_model=PlanNormalizeResponse,
            mode="json",
        )
        normalized = NormalizedPlan(
            normalized_tasks=[_task_from_out(t) for t in result.normalized_tasks],
            plan_changelog=result.plan_changelog.strip(),
            plan_revision=plan_revision,
            source_plan="build_goals.yaml",
        )
        if not normalized.normalized_tasks:
            raise ValueError("LLM 回傳空任務列表")
        return enrich_normalized_plan(
            plan,
            normalized,
            supplements_path=supplements_path,
            plan_interactive=plan_interactive,
        )
    except (
        ProviderError,
        ValueError,
        json.JSONDecodeError,
        StructuredNoPayloadError,
        StructuredValidationError,
    ) as exc:
        _logger.warning("Plan Normalize LLM 失敗，改用 passthrough: %s", exc)
        fallback = normalize_plan_passthrough(plan, plan_revision=plan_revision)
        fallback.plan_changelog = f"LLM 規劃失敗（{exc}），已 passthrough"
        return enrich_normalized_plan(
            plan,
            fallback,
            supplements_path=supplements_path,
            plan_interactive=plan_interactive,
        )


def normalize_plan_passthrough_enriched(
    plan: BuildPlan,
    *,
    plan_revision: int = 1,
    plan_interactive: bool = False,
    supplements_path: str | Path | None = None,
) -> NormalizedPlan:
    """Passthrough + 補充 prompt 注入（不呼叫 LLM）。"""
    from core.pipeline.prompt_supplements import enrich_normalized_plan

    base = normalize_plan_passthrough(plan, plan_revision=plan_revision)
    return enrich_normalized_plan(
        plan,
        base,
        supplements_path=supplements_path,
        plan_interactive=plan_interactive,
    )
