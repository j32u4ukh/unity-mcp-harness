"""project_state 權威摘要：以 task_list / harness_verification 為準，非 Agent 樂觀回覆。"""

from __future__ import annotations

from typing import Any

import re

from core.pipeline.schema import HarnessTask, TaskListDocument

_TASK_ID_SCENE = re.compile(r"scene|hierarchy|inspect", re.I)
_TASK_ID_ASSET = re.compile(r"sprite|asset|texture|png|psd|import", re.I)
_TASK_ID_SYSTEM = re.compile(r"camera|light|render|urp|input|audio", re.I)


def summarize_text(text: str, *, max_len: int = 500) -> str:
    body = (text or "").strip().replace("\r\n", "\n")
    if len(body) <= max_len:
        return body
    return body[: max_len - 1] + "…"


def overview_keys_for_task(task: HarnessTask) -> list[str]:
    keys: list[str] = []
    tid = task.id or ""
    if task.target.scene_path or _TASK_ID_SCENE.search(tid):
        keys.append("scenes/overview")
    if _TASK_ID_ASSET.search(tid):
        keys.append("assets/overview")
    if _TASK_ID_SYSTEM.search(tid):
        keys.append("systems/overview")
    if not keys:
        keys.append("scenes/overview")
    return keys


def overview_rel_path(key: str) -> str:
    mapping = {
        "scenes/overview": "scenes/_overview.md",
        "assets/overview": "assets/_overview.md",
        "systems/overview": "systems/_overview.md",
    }
    return mapping.get(key, "scenes/_overview.md")


def task_record_rel_path(task_id: str) -> str:
    safe = re.sub(r"[^\w\-]+", "_", task_id).strip("_") or "task"
    return f"tasks/{safe}.md"
from core.project_state.index import StateIndexEntry, utc_now_iso
from tasks import TaskResult

CURRENT_SECTION = "## 當前狀態"
SNAPSHOT_SECTION = "## 當前快照"
TASK_FILE_DISCLAIMER = (
    "> 由 Harness 依 task_list.yaml 同步；**完成與否以 status / verification 為準**，"
    "非 Agent 文字。執行前仍須 Phase 1 MCP 讀取驗證現場。"
)

VERIFIED_DONE = frozenset({"verified", "skipped_by_idempotent"})


def task_is_done(task: HarnessTask) -> bool:
    return task.status == "completed" and task.verification in VERIFIED_DONE


def harness_verification_from_task(task: HarnessTask) -> dict[str, Any]:
    after = task.pipeline_records.actual_after or {}
    hv = after.get("harness_verification")
    return hv if isinstance(hv, dict) else {}


def _last_operation_summary(task: HarnessTask, *, max_len: int = 200) -> str:
    ops = task.pipeline_records.operations_executed
    if not ops:
        return ""
    last = ops[-1]
    parts = [last.action]
    if last.tool:
        parts.append(str(last.tool))
    if last.summary:
        parts.append(summarize_text(last.summary, max_len=max_len))
    return " — ".join(parts)


def build_task_ssot_one_line(
    task: HarnessTask,
    result: TaskResult | None = None,
) -> str:
    """索引用一行摘要（不含未採信的 Agent 樂觀宣稱）。"""
    hv = harness_verification_from_task(task)
    if task_is_done(task):
        hv_sum = str(hv.get("summary") or "").strip()
        if hv_sum:
            return summarize_text(f"{task.id}: {task.status}/{task.verification} — {hv_sum}", max_len=120)
        return f"{task.id}: {task.status}/{task.verification} — 已驗證完成"

    err = ""
    if result and result.error:
        err = summarize_text(result.error, max_len=80)
    elif hv.get("failure_reason"):
        err = summarize_text(str(hv["failure_reason"]), max_len=80)
    elif hv.get("summary"):
        err = summarize_text(str(hv["summary"]), max_len=80)

    base = f"{task.id}: {task.status}/{task.verification}"
    if err:
        return summarize_text(f"{base} — {err}", max_len=120)
    return summarize_text(base, max_len=120)


def build_task_current_section_body(
    task: HarnessTask,
    result: TaskResult | None = None,
) -> str:
    """`## 當前狀態` 區塊內文。"""
    hv = harness_verification_from_task(task)
    lines = [
        f"- **status**: `{task.status}`",
        f"- **verification**: `{task.verification}`",
        f"- **description**: {task.description}",
        f"- **synced_at**: {utc_now_iso()}",
    ]
    if task.target.scene_path:
        lines.append(f"- **scene_path**: `{task.target.scene_path}`")
    if task.target.game_object:
        lines.append(f"- **game_object**: `{task.target.game_object}`")

    if hv:
        lines.append("")
        lines.append("**Harness 驗證（MCP 現場）**:")
        if hv.get("verified") is not None:
            lines.append(f"- verified: `{hv.get('verified')}`")
        if hv.get("active_scene_path"):
            lines.append(f"- active_scene_path: `{hv['active_scene_path']}`")
        if hv.get("summary"):
            lines.append(f"- summary: {hv['summary']}")
        if hv.get("failure_reason"):
            lines.append(f"- failure_reason: {hv['failure_reason']}")

    op = _last_operation_summary(task)
    if op:
        lines.append("")
        lines.append(f"**最後操作**: {op}")

    if not task_is_done(task) and result and (result.reply or "").strip():
        lines.append("")
        lines.append("**Agent 宣稱（未採信為完成依據）**:")
        lines.append(summarize_text(result.reply, max_len=400))

    return "\n".join(lines) + "\n"


def format_task_markdown_file(
    task: HarnessTask,
    result: TaskResult | None = None,
) -> str:
    safe_title = task.id.replace("_", " ").title()
    body = build_task_current_section_body(task, result)
    return (
        f"# {safe_title}\n\n"
        f"{TASK_FILE_DISCLAIMER}\n\n"
        f"{CURRENT_SECTION}\n\n"
        f"{body}"
    )


def build_changelog_line(task: HarnessTask, result: TaskResult) -> str:
    one = build_task_ssot_one_line(task, result)
    return f"- {utc_now_iso()} | `{task.id}` | {task.status} | {one}\n"


def format_task_list_for_planning(doc: TaskListDocument) -> str:
    lines = [
        "【執行隊列 SSOT — task_list.yaml】",
        "（規劃時以此為準；project_state 僅輔助。僅 status=completed 且 verification 為 verified/skipped_by_idempotent 可視為藍圖子項已完成。）",
        "",
    ]
    for t in sorted(doc.tasks, key=lambda x: (x.priority, x.id)):
        done = "可省略" if task_is_done(t) else "須規劃/重試"
        lines.append(
            f"- `{t.id}`: status=`{t.status}`, verification=`{t.verification}` "
            f"— {summarize_text(t.description, max_len=80)} [{done}]"
        )
    return "\n".join(lines)


def _overview_snapshot_lines(doc: TaskListDocument) -> dict[str, list[str]]:
    """依 domain 彙整最新 verified 任務摘要。"""
    buckets: dict[str, list[tuple[int, str, str]]] = {
        "scenes/overview": [],
        "assets/overview": [],
        "systems/overview": [],
    }
    for task in doc.tasks:
        if not task_is_done(task):
            continue
        line = build_task_ssot_one_line(task)
        for key in overview_keys_for_task(task):
            if key in buckets:
                buckets[key].append((task.priority, task.id, line))

    out: dict[str, list[str]] = {}
    for key, items in buckets.items():
        items.sort(key=lambda x: (x[0], x[1]))
        if items:
            out[key] = [f"- **{tid}**: {text}" for _, tid, text in items]
        else:
            out[key] = ["- （尚無 verified 任務涵蓋此領域；須 MCP 驗證）"]
    return out


def format_overview_file(
    title: str,
    snapshot_lines: list[str],
    *,
    extra_disclaimer: str = "",
) -> str:
    parts = [
        f"# {title}",
        "",
        TASK_FILE_DISCLAIMER,
    ]
    if extra_disclaimer:
        parts.append(extra_disclaimer)
    parts.extend(["", SNAPSHOT_SECTION, "", *snapshot_lines, ""])
    return "\n".join(parts) + "\n"


def read_section_from_markdown(text: str, section_heading: str) -> str:
    """擷取文件中某 ## 區塊內容（至下一個 ## 或結尾）。"""
    if section_heading not in text:
        return ""
    start = text.index(section_heading) + len(section_heading)
    rest = text[start:].lstrip("\n")
    end = rest.find("\n## ")
    if end >= 0:
        return rest[:end].strip()
    return rest.strip()


def sync_project_state_from_task_list(
    doc: TaskListDocument,
    *,
    root=None,
) -> int:
    """
    依 task_list 重寫 project_state 任務檔與索引（修剪舊 ## 任務 章節）。

    回傳寫入的任務檔數量。
    """
    from pathlib import Path

    from core.project_state.index import StateIndex, load_index, save_index
    from core.project_state.paths import default_project_state_root

    base = Path(root) if root is not None else default_project_state_root()
    if not base.is_dir():
        return 0

    index = load_index(base) or StateIndex(
        version=1,
        description="Unity 專案狀態索引（與 task_list.yaml 搭配）",
        entries=[],
    )

    # 保留 bootstrap 等非 tasks/* 條目
    preserved = [e for e in index.entries if not e.key.startswith("tasks/")]

    task_entries: list[StateIndexEntry] = []
    written = 0
    for task in doc.tasks:
        rel = task_record_rel_path(task.id)
        content = format_task_markdown_file(task)
        path = base / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        written += 1
        one_line = build_task_ssot_one_line(task)
        task_entries.append(
            StateIndexEntry(
                key=f"tasks/{task.id}",
                path=rel,
                summary=one_line,
                tags=["task", task.id],
                last_updated=utc_now_iso(),
                last_task_id=task.id,
            )
        )

    snapshots = _overview_snapshot_lines(doc)
    overview_titles = {
        "scenes/overview": "Scenes Overview",
        "assets/overview": "Assets Overview",
        "systems/overview": "Systems Overview",
    }
    overview_entries: list[StateIndexEntry] = []
    for key, title in overview_titles.items():
        rel = overview_rel_path(key)
        lines = snapshots.get(key, [])
        content = format_overview_file(title, lines)
        (base / rel).parent.mkdir(parents=True, exist_ok=True)
        (base / rel).write_text(content, encoding="utf-8")
        summary = summarize_text(lines[0] if lines else "待確認", max_len=120)
        overview_entries.append(
            StateIndexEntry(
                key=key,
                path=rel,
                summary=summary,
                tags=key.split("/"),
                last_updated=utc_now_iso(),
                last_task_id="sync",
            )
        )

    index.entries = preserved + task_entries + overview_entries
    save_index(index, base)
    return written
