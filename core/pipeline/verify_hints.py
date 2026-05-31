"""Harness 規劃期：為任務產生精簡、可執行的 MCP 驗證讀取計畫（verify_read）。"""

from __future__ import annotations

import re
from typing import Protocol

_SCENE_PATH_PATTERN = re.compile(r"(Assets/[^\s\)`\"']+\.unity)", re.IGNORECASE)
_GAME_OBJECT_NAME_PATTERNS = (
    re.compile(r'名為\s*["「\']([^"」\']+)["」\']'),
    re.compile(r'named\s*["\']([^"\']+)["\']', re.IGNORECASE),
    re.compile(r'GameObject\s*(?:named\s*)?["\']([^"\']+)["\']', re.IGNORECASE),
)


class _TaskLike(Protocol):
    id: str
    description: str
    prompt: str
    target: object
    expected: dict
    harness: object


def infer_scene_path(task: _TaskLike) -> str | None:
    target = getattr(task, "target", None)
    if target is not None and getattr(target, "scene_path", None):
        return str(target.scene_path).strip()
    match = _SCENE_PATH_PATTERN.search(task.prompt or "")
    return match.group(1) if match else None


def infer_game_object_name(task: _TaskLike) -> str | None:
    target = getattr(task, "target", None)
    if target is not None and getattr(target, "game_object", None):
        return str(target.game_object).strip()
    text = task.prompt or ""
    for pattern in _GAME_OBJECT_NAME_PATTERNS:
        match = pattern.search(text)
        if match:
            return match.group(1).strip()
    return None

# 寫入 task_list.harness.verify_read；驗證 prompt 會引用
VERIFY_READ_STANDARD = """【Harness 驗證 MCP 預算 — 必須遵守】
- 至多 **2 次** LLM tool 回合（每回合可 batch 多個唯讀 tool）；取得證據後**立即**輸出 JSON，勿再要 tool。
- 第 1 回合：優先 `gameobject-find`（`includeComponents: true`, `includeData: true`）確認目標與關鍵組件。
- 第 2 回合（僅在 find 不足以判斷屬性時）：至多 **1 次** `gameobject-component-get`；`componentRef` **必須**含 find 回傳的 `instanceID`，**禁止** `{}` 或 0。
- **禁止**對同一 `instanceID` 重複 `component-get` / `object-get-data`。"""

VERIFY_READ_IDEMPOTENT = """【Harness 冪等驗證 MCP 預算 — Agent 宣稱已存在，跳過】
- 至多 **1 次** LLM tool 回合。
- 僅 `gameobject-find`（目標名, `includeComponents: true`, `includeData: true`）確認物件存在且關鍵組件在場。
- **禁止**逐 component 深讀；取得存在證據後**立即**輸出 JSON。"""

AGENT_READ_BUDGET_LINE = (
    "Phase 1 讀取：優先單次 gameobject-find(includeComponents=true, includeData=true)；"
    "避免對同一 component 重複 component-get / object-get-data。"
)


def _get_harness(task: _TaskLike):
    return task.harness


def _expected_asset_hint(expected: dict) -> str | None:
    if not expected:
        return None
    parts: list[str] = []
    gen_dir = expected.get("generated_asset_dir")
    gen_name = expected.get("generated_asset_name")
    if gen_dir and gen_name:
        parts.append(f"{gen_dir}/{gen_name}".replace("//", "/"))
    props = expected.get("properties")
    if isinstance(props, dict):
        for key in ("sprite", "color", "gravityScale"):
            if key in props:
                parts.append(f"{key}={props[key]}")
    if expected.get("transform_local_scale_x_min") is not None:
        parts.append(f"scale.x>={expected['transform_local_scale_x_min']}")
    if expected.get("component_exists"):
        parts.append(f"component:{expected['component_exists']}")
    if expected.get("file_exists"):
        parts.append(f"file:{expected['file_exists']}")
    return "; ".join(parts) if parts else None


def build_default_verify_read(task: _TaskLike) -> str:
    """依 target / prompt / expected 產生預設 verify_read（供 Plan Normalize 補全）。"""
    scene = infer_scene_path(task)  # type: ignore[arg-type]
    go_name = infer_game_object_name(task)  # type: ignore[arg-type]
    harness = _get_harness(task)
    post = (getattr(harness, "post_read", None) or "").strip()

    lines = [VERIFY_READ_STANDARD.strip(), ""]
    if scene or go_name:
        scope = []
        if scene:
            scope.append(f"scene={scene}")
        if go_name:
            scope.append(f'GameObject="{go_name}"')
        lines.append(f"驗證範圍：{', '.join(scope)}。")

    asset_hint = _expected_asset_hint(getattr(task, "expected", None) or {})
    if asset_hint:
        lines.append(f"須在 checks.detail 引用工具回傳證據核對：{asset_hint}。")
    elif post:
        lines.append(f"重點：{post}")
    else:
        lines.append(f"重點：{task.description}")

    return "\n".join(lines)


def ensure_task_verify_hints(task: _TaskLike) -> bool:
    """若缺少 harness.verify_read，補上預設；回傳是否修改。"""
    harness = _get_harness(task)
    current = (getattr(harness, "verify_read", None) or "").strip()
    if current:
        return False
    harness.verify_read = build_default_verify_read(task)  # type: ignore[attr-defined]
    return True


def ensure_agent_read_hint_in_prompt(prompt: str) -> str:
    """在 task prompt 末尾補 Agent Phase 1 讀取預算（若尚未提及）。"""
    body = (prompt or "").strip()
    if "includeComponents" in body and "重複" in body:
        return body
    if AGENT_READ_BUDGET_LINE in body:
        return body
    return body + "\n\n" + AGENT_READ_BUDGET_LINE


def apply_verify_hints_to_normalized_tasks(tasks: list) -> int:
    """對規劃期任務補全 verify_read 與 Agent 讀取提示。回傳修改筆數。"""
    changed = 0
    for task in tasks:
        if ensure_task_verify_hints(task):
            changed += 1
        new_prompt = ensure_agent_read_hint_in_prompt(task.prompt)
        if new_prompt != task.prompt:
            task.prompt = new_prompt
            changed += 1
    return changed


def backfill_task_list_verify_hints(doc) -> bool:
    """載入既有 task_list 時補齊 verify_read（若有變更回傳 True）。"""
    from core.pipeline.schema import TaskListDocument

    if not isinstance(doc, TaskListDocument):
        return False
    changed = apply_verify_hints_to_normalized_tasks(doc.tasks)
    return changed > 0
