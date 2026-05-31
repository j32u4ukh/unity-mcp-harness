"""Phase 3：任務結束後以獨立 MCP 唯讀回合驗證 Editor 現場（非信任 Agent 文字）。"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from core.pipeline.schema import HarnessTask
from core.pipeline.verify_hints import (
    VERIFY_READ_IDEMPOTENT,
    VERIFY_READ_STANDARD,
    infer_game_object_name,
    infer_scene_path,
)
from tasks import is_validate_task
from unity_common import ask_unity, task_reply_indicates_failure

_VERIFICATION_JSON_BLOCK = re.compile(
    r"```(?:json)?\s*(\{.*?\})\s*```",
    re.DOTALL | re.IGNORECASE,
)

_VERIFIER_SYSTEM = f"""\
你是 Unity Harness 驗證器。你只能使用 Unity MCP **唯讀**工具查詢 Editor 現場。
禁止建立、修改、刪除任何場景物件或資產。

{VERIFY_READ_STANDARD}

完成查詢後，你**必須**只輸出一個 JSON 物件（不要加說明文字、不要 markdown 程式碼區塊），格式：
{{
  "verified": true 或 false,
  "active_scene_path": "目前作用中場景資產路徑或空字串",
  "checks": [
    {{"name": "檢查項名稱", "passed": true 或 false, "detail": "從工具得到的具體證據"}}
  ],
  "failure_reason": "僅在 verified 為 false 時填寫"
}}

若 MCP 連線失敗、工具遭拒絕、或無法取得證據，設 verified 為 false 並在 failure_reason 說明。
禁止憑 Agent 宣稱或臆測填 verified=true；每一項 passed=true 必須有工具回傳依據寫在 detail。
gameobject-component-get 的 componentRef 必須含有效 instanceID（來自 find 結果），禁止空物件 {{}}。
"""


@dataclass
class VerificationResult:
    """Harness 事後驗證結果。"""

    passed: bool
    summary: str
    checks: list[dict[str, Any]] = field(default_factory=list)
    active_scene_path: str = ""
    failure_reason: str = ""
    raw_reply: str = ""
    parse_error: str | None = None

    def to_actual_after(self) -> dict[str, Any]:
        return {
            "harness_verification": {
                "verified": self.passed,
                "active_scene_path": self.active_scene_path,
                "checks": self.checks,
                "failure_reason": self.failure_reason,
                "parse_error": self.parse_error,
                "summary": self.summary,
            }
        }


def should_skip_verification(task: HarnessTask, *, skip_verification: bool = False) -> bool:
    if skip_verification:
        return True
    if task.expected.get("skip_harness_verification"):
        return True
    return False


def parse_verification_json(text: str) -> dict[str, Any] | None:
    """從驗證器回覆擷取 JSON 物件。"""
    raw = (text or "").strip()
    if not raw:
        return None

    for candidate in (raw,):
        try:
            data = json.loads(candidate)
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            pass

    block = _VERIFICATION_JSON_BLOCK.search(raw)
    if block:
        try:
            data = json.loads(block.group(1))
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            pass

    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        try:
            data = json.loads(raw[start : end + 1])
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            pass
    return None


def evaluate_verification_payload(data: dict[str, Any]) -> VerificationResult:
    verified = bool(data.get("verified"))
    checks = data.get("checks")
    if not isinstance(checks, list):
        checks = []
    normalized_checks: list[dict[str, Any]] = []
    for item in checks:
        if isinstance(item, dict):
            normalized_checks.append(item)

    active_scene = str(data.get("active_scene_path") or "").strip()
    failure_reason = str(data.get("failure_reason") or "").strip()

    if verified and normalized_checks:
        failed_checks = [c for c in normalized_checks if c.get("passed") is False]
        if failed_checks:
            verified = False
            names = ", ".join(str(c.get("name", "?")) for c in failed_checks[:5])
            failure_reason = failure_reason or f"checks 未通過: {names}"

    if verified:
        summary = "Harness MCP 驗證通過"
        if active_scene:
            summary += f"（場景: {active_scene}）"
    else:
        summary = failure_reason or "Harness MCP 驗證未通過"

    return VerificationResult(
        passed=verified,
        summary=summary,
        checks=normalized_checks,
        active_scene_path=active_scene,
        failure_reason=failure_reason if not verified else "",
    )


def _resolve_verify_read(task: HarnessTask, *, idempotent_skip: bool) -> str:
    custom = (task.harness.verify_read or "").strip()
    if idempotent_skip:
        base = VERIFY_READ_IDEMPOTENT
        if custom:
            return f"{base}\n\n【任務專用 verify_read】\n{custom}"
        return base
    if custom:
        return custom
    from core.pipeline.verify_hints import build_default_verify_read

    return build_default_verify_read(task)


def build_verification_prompt(
    task: HarnessTask,
    *,
    agent_reply_excerpt: str,
    definition_of_done: list[str] | None = None,
    idempotent_skip: bool = False,
) -> str:
    scene = infer_scene_path(task)
    go_name = infer_game_object_name(task)
    verify_plan = _resolve_verify_read(task, idempotent_skip=idempotent_skip)

    lines = [
        f"【驗證任務】{task.id} — {task.description}",
        "",
        verify_plan,
        "",
        "Agent 執行後宣稱摘要（僅供對照，不可作為通過依據）：",
        agent_reply_excerpt[:800] if agent_reply_excerpt else "（無）",
        "",
        "請依上方 MCP 預算用唯讀工具核對，並輸出規定格式的 JSON。checks 建議 2–4 項，每項 detail 須引用工具回傳。",
    ]

    check_items: list[str] = []
    if idempotent_skip:
        check_items.append(
            "Agent 宣稱「已存在，跳過」：以 gameobject-find 確認目標在 Hierarchy 存在；"
            "若不存在則 verified=false。"
        )
    else:
        check_items.append("確認 Agent 是否真正完成任務（非僅文字聲明）。")

    if scene:
        check_items.append(
            f"作用中場景須為 `{scene}`（或已載入）；在 JSON 填 active_scene_path。"
        )
    if go_name:
        check_items.append(
            f"Hierarchy 須存在 `{go_name}`；在 checks 中列出 find 得到的關鍵組件證據。"
        )

    expected = task.expected or {}
    props = expected.get("properties")
    if isinstance(props, dict) and props:
        check_items.append(
            f"核對 expected.properties：{json.dumps(props, ensure_ascii=False)}"
        )
    if expected.get("forbid_approximate_asset_match"):
        check_items.append("Sprite/材質須符合任務資產路徑，禁止近似貼圖充數。")

    gen_dir = expected.get("generated_asset_dir")
    gen_name = expected.get("generated_asset_name")
    if gen_dir and gen_name:
        check_items.append(
            f"Sprite 資產路徑應含 `{gen_dir}/{gen_name}`（以工具回傳為準）。"
        )
    if expected.get("transform_local_scale_x_min") is not None:
        check_items.append(
            f"Transform.localScale.x 應 >= {expected['transform_local_scale_x_min']}。"
        )
    if expected.get("component_exists"):
        check_items.append(f"須存在組件 `{expected['component_exists']}`。")
    if expected.get("file_exists"):
        check_items.append(f"須存在檔案 `{expected['file_exists']}`。")

    post_hint = (task.harness.post_read or "").strip()
    if post_hint and not (gen_dir and gen_name):
        check_items.append(f"額外：{post_hint}")

    lines.append("")
    lines.append("【須涵蓋的檢查項（寫入 checks）】")
    for i, item in enumerate(check_items, 1):
        lines.append(f"{i}. {item}")

    if is_validate_task(task.id) and definition_of_done:
        lines.extend(["", "【Definition of Done 逐項核對】"])
        for item in definition_of_done:
            lines.append(f"- {item}")

    return "\n".join(lines)


def run_task_verification(
    task: HarnessTask,
    *,
    agent_reply: str,
    model: str | None,
    mcp_servers: list[str],
    max_tool_rounds: int = 10,
    specs: dict[str, Any] | None = None,
    config_path: str | None = None,
    definition_of_done: list[str] | None = None,
    idempotent_skip: bool = False,
) -> VerificationResult:
    """執行獨立 MCP 驗證回合（新 Chat，不共用 Agent 歷史）。"""
    prompt = build_verification_prompt(
        task,
        agent_reply_excerpt=agent_reply,
        definition_of_done=definition_of_done,
        idempotent_skip=idempotent_skip,
    )
    try:
        reply = ask_unity(
            prompt,
            mcp_servers=mcp_servers,
            model=model,
            system=_VERIFIER_SYSTEM,
            max_tool_rounds=max_tool_rounds,
            specs=specs,
            config_path=config_path,
        )
    except Exception as exc:
        return VerificationResult(
            passed=False,
            summary=f"Harness 驗證 MCP 呼叫失敗: {exc}",
            failure_reason=str(exc),
            raw_reply="",
        )

    if task_reply_indicates_failure(reply):
        return VerificationResult(
            passed=False,
            summary="Harness 驗證回合回報失敗（連線/核准/工具）",
            failure_reason=reply[:500],
            raw_reply=reply,
        )

    data = parse_verification_json(reply)
    if data is None:
        return VerificationResult(
            passed=False,
            summary="Harness 驗證器未回傳可解析 JSON",
            failure_reason="驗證器必須輸出含 verified 欄位的 JSON",
            raw_reply=reply,
            parse_error="invalid_json",
        )

    result = evaluate_verification_payload(data)
    result.raw_reply = reply
    return result
