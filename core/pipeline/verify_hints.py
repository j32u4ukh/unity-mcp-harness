"""Harness 規劃期：為任務產生精簡、可執行的 MCP 驗證讀取計畫（verify_read）。"""

from __future__ import annotations

import re
from typing import Literal, Protocol

_SCENE_PATH_PATTERN = re.compile(r"(Assets/[^\s\)`\"']+\.unity)", re.IGNORECASE)
_SCRIPT_PATH_PATTERN = re.compile(r"(Assets/[^\s\)`\"']+\.cs)", re.IGNORECASE)
_GAME_OBJECT_NAME_PATTERNS = (
    re.compile(r'名為\s*["「\']([^"」\']+)["」\']'),
    re.compile(r'named\s*["\']([^"\']+)["\']', re.IGNORECASE),
    re.compile(r'GameObject\s*(?:named\s*)?["\']([^"\']+)["\']', re.IGNORECASE),
)
_SCRIPT_FILE_TASK_ID = re.compile(
    r"ensure_scripts|script_file|player_controller_script|create.*script",
    re.I,
)
_SCRIPT_MOUNT_TASK_ID = re.compile(
    r"implement_.*logic|attach.*script|mount.*script|掛載|附加至",
    re.I,
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


def infer_script_asset_path(task: _TaskLike) -> str | None:
    expected = getattr(task, "expected", None) or {}
    if expected.get("file_exists"):
        return str(expected["file_exists"]).strip()
    match = _SCRIPT_PATH_PATTERN.search(task.prompt or "")
    if match:
        return match.group(1)
    match = _SCRIPT_PATH_PATTERN.search(task.description or "")
    return match.group(1) if match else None


def infer_script_class_name(task: _TaskLike) -> str:
    path = infer_script_asset_path(task)
    if path:
        base = path.rsplit("/", 1)[-1]
        if base.endswith(".cs"):
            return base[:-3]
    if re.search(r"PlayerController", f"{task.id} {task.description}", re.I):
        return "PlayerController"
    return "PlayerController"


def classify_script_task(task: _TaskLike) -> Literal["file", "mount"] | None:
    """腳本相關任務：僅驗證 .cs 資產，或驗證掛載+邏輯。"""
    blob = f"{task.id}\n{task.description}\n{task.prompt}"
    if _SCRIPT_FILE_TASK_ID.search(task.id) or re.search(
        r"確保.*腳本|建立.*腳本檔|資料夾.*PlayerController\.cs",
        blob,
        re.I,
    ):
        if not re.search(r"實作.*邏輯|FixedUpdate|MovePosition|附加至.*Player", blob, re.I):
            return "file"
    if _SCRIPT_MOUNT_TASK_ID.search(blob) or re.search(
        r"實作.*移動|寫入移動邏輯|附加此腳本",
        blob,
        re.I,
    ):
        return "mount"
    if re.search(r"Assets/Scripts|PlayerController", blob, re.I):
        if re.search(r"附加|掛載|attach|Component 清單", blob, re.I):
            return "mount"
        if re.search(r"PlayerController\.cs", blob, re.I):
            return "file"
    return None


ASSETS_FIND_RULE = """【assets-find 語法 — 必守】
- filter 使用 Unity Search 語法（例如 `t:Script PlayerController`、`t:Script`、`l:Assets/Scripts`）。
- **禁止**把 `Assets/Scripts/PlayerController.cs` 等完整路徑當唯一 filter（常回傳空結果不代表檔案不存在）。
- 通過時 checks.detail 須引用工具回傳的 asset path / guid。"""

# 寫入 task_list.harness.verify_read；驗證 prompt 會引用
VERIFY_READ_STANDARD = f"""【Harness 驗證 MCP 預算 — 必須遵守】
- 至多 **2 次** LLM tool 回合（每回合可 batch 多個唯讀 tool）；取得證據後**立即**輸出 JSON，勿再要 tool。
- 第 1 回合：優先 `gameobject-find`（`includeComponents: true`, `includeData: true`）確認目標與關鍵組件。
- 第 2 回合（僅在 find 不足以判斷屬性時）：至多 **1 次** `gameobject-component-get`；`componentRef` **必須**含 find 回傳的 `instanceID`，**禁止** `{{}}` 或 0。
- **禁止**對同一 `instanceID` 重複 `component-get` / `object-get-data`。

{ASSETS_FIND_RULE}"""

VERIFY_READ_IDEMPOTENT = """【Harness 冪等驗證 MCP 預算 — Agent 宣稱已存在，跳過】
- 至多 **1 次** LLM tool 回合。
- 僅 `gameobject-find`（目標名, `includeComponents: true`, `includeData: true`）確認物件存在且關鍵組件在場。
- **禁止**逐 component 深讀；取得存在證據後**立即**輸出 JSON。"""

VERIFY_READ_IDEMPOTENT_SCRIPT_FILE = """【Harness 冪等驗證 — 腳本檔已存在】
- 至多 **1 次** tool 回合。
- 僅 `assets-find`，filter=`t:Script {class_name}`（或 `l:Assets/Scripts` + class 名）。
- **禁止**檢查 GameObject 掛載；**禁止**用完整 .cs 路徑當 filter。
- detail 須含回傳的 asset path 含 `{asset_path}`。"""

VERIFY_READ_SCRIPT_FILE = """【腳本資產驗證 — 僅驗證 .cs 存在，不驗證 GameObject 掛載】
- 至多 **2 次** tool 回合；夠證據後立即輸出 JSON。
- 第 1 回合：`assets-find`，filter=`t:Script {class_name}`（必要時第 2 回合 `l:Assets/Scripts`）。
- **禁止**用 `Assets/Scripts/PlayerController.cs` 整段當 filter。
- **禁止**以「Player 未掛載腳本」作為本任務失敗理由。
- checks 至少一項：腳本資產 path 含 `{asset_path}`。

{assets_find_rule}"""

VERIFY_READ_SCRIPT_MOUNT = """【腳本掛載與邏輯驗證】
- 至多 **2 次** tool 回合。
- 第 1 回合：`assets-find` filter=`t:Script {class_name}`，確認腳本資產存在（detail 引用 path）。
- 第 2 回合：`gameobject-find` name=`{go_name}`，`includeComponents: true`，須含 **PlayerController** 與 **Rigidbody2D**。
- **禁止**用完整 .cs 路徑當 assets-find filter。

{assets_find_rule}"""

SCRIPT_AGENT_READ_BUDGET = (
    "Phase 1 讀取：腳本任務用 assets-find，filter=`t:Script <類別名>` 或 `l:Assets/Scripts`；"
    "勿把 Assets/.../*.cs 整段路徑當 filter。掛載驗證留待後續任務。"
)

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


def build_script_verify_read(
    task: _TaskLike,
    kind: Literal["file", "mount"],
) -> str:
    asset_path = infer_script_asset_path(task) or "Assets/Scripts/PlayerController.cs"
    class_name = infer_script_class_name(task)
    go_name = infer_game_object_name(task) or "Player"
    if kind == "file":
        return VERIFY_READ_SCRIPT_FILE.format(
            class_name=class_name,
            asset_path=asset_path,
            assets_find_rule=ASSETS_FIND_RULE,
        )
    return VERIFY_READ_SCRIPT_MOUNT.format(
        class_name=class_name,
        go_name=go_name,
        assets_find_rule=ASSETS_FIND_RULE,
    )


def verify_read_is_stale_for_script_task(task: _TaskLike, kind: Literal["file", "mount"]) -> bool:
    current = (getattr(_get_harness(task), "verify_read", None) or "").strip()
    if not current:
        return True
    if "t:Script" not in current and "assets-find" not in current.lower():
        if kind == "file" and "gameobject-find" in current and "PlayerController" in current:
            return True
    if kind == "file" and re.search(r"掛載|includeComponents.*PlayerController", current, re.I):
        return True
    if kind == "mount" and "t:Script" not in current:
        return True
    return False


def ensure_script_task_expected(task: _TaskLike, kind: Literal["file", "mount"]) -> bool:
    if kind != "file":
        return False
    expected = getattr(task, "expected", None)
    if not isinstance(expected, dict):
        return False
    path = infer_script_asset_path(task) or "Assets/Scripts/PlayerController.cs"
    if expected.get("file_exists") == path:
        return False
    expected["file_exists"] = path
    return True


def build_default_verify_read(task: _TaskLike) -> str:
    """依 target / prompt / expected 產生預設 verify_read（供 Plan Normalize 補全）。"""
    script_kind = classify_script_task(task)
    if script_kind:
        return build_script_verify_read(task, script_kind)

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


def build_idempotent_script_verify_read(task: _TaskLike) -> str | None:
    kind = classify_script_task(task)
    if kind != "file":
        return None
    asset_path = infer_script_asset_path(task) or "Assets/Scripts/PlayerController.cs"
    return VERIFY_READ_IDEMPOTENT_SCRIPT_FILE.format(
        class_name=infer_script_class_name(task),
        asset_path=asset_path,
    )


def ensure_task_verify_hints(task: _TaskLike) -> bool:
    """若缺少 harness.verify_read，補上預設；回傳是否修改。"""
    harness = _get_harness(task)
    current = (getattr(harness, "verify_read", None) or "").strip()
    if current:
        return False
    harness.verify_read = build_default_verify_read(task)  # type: ignore[attr-defined]
    changed = True
    kind = classify_script_task(task)
    if kind:
        changed = ensure_script_task_expected(task, kind) or changed
    return changed


def upgrade_script_task_verify_hints(task: _TaskLike) -> bool:
    """修正既有錯誤的腳本任務 verify_read（例如僅 gameobject-find）。"""
    kind = classify_script_task(task)
    if not kind:
        return False
    changed = False
    if verify_read_is_stale_for_script_task(task, kind):
        _get_harness(task).verify_read = build_script_verify_read(task, kind)  # type: ignore[attr-defined]
        changed = True
    if ensure_script_task_expected(task, kind):
        changed = True
    return changed


def ensure_agent_read_hint_in_prompt(prompt: str, *, script_task: bool = False) -> str:
    """在 task prompt 末尾補 Agent Phase 1 讀取預算（若尚未提及）。"""
    body = (prompt or "").strip()
    budget = SCRIPT_AGENT_READ_BUDGET if script_task else AGENT_READ_BUDGET_LINE
    if script_task and "t:Script" in body:
        return body
    if not script_task and "includeComponents" in body and "重複" in body:
        return body
    if budget in body:
        return body
    return body + "\n\n" + budget


def apply_verify_hints_to_normalized_tasks(tasks: list) -> int:
    """對規劃期任務補全 verify_read 與 Agent 讀取提示。回傳修改筆數。"""
    changed = 0
    for task in tasks:
        if ensure_task_verify_hints(task):
            changed += 1
        if upgrade_script_task_verify_hints(task):
            changed += 1
        script = classify_script_task(task) is not None
        new_prompt = ensure_agent_read_hint_in_prompt(task.prompt, script_task=script)
        if new_prompt != task.prompt:
            task.prompt = new_prompt
            changed += 1
    return changed


def backfill_task_list_verify_hints(doc) -> bool:
    """載入既有 task_list 時補齊/升級 verify_read（若有變更回傳 True）。"""
    from core.pipeline.schema import TaskListDocument

    if not isinstance(doc, TaskListDocument):
        return False
    changed = apply_verify_hints_to_normalized_tasks(doc.tasks)
    return changed > 0
