"""合併對話 /write 輸出至既有 task_list（保留執行期欄位）。"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

import yaml

from core.pipeline.schema import HarnessTask, TaskListDocument


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


_PLANNING_KEYS = frozenset(
    {
        "id",
        "description",
        "prompt",
        "priority",
        "title",
        "target",
        "expected",
        "harness",
        "plan_source_id",
    }
)


def _apply_planning_fields(task: HarnessTask, item: dict[str, Any]) -> None:
    if "description" in item:
        task.description = str(item["description"])
    if "prompt" in item:
        task.prompt = str(item["prompt"])
    if "priority" in item:
        task.priority = int(item["priority"])
    if "title" in item:
        task.title = item["title"]
    if "target" in item and isinstance(item["target"], dict):
        from core.pipeline.schema import TaskTarget

        task.target = TaskTarget.from_dict(item["target"])
    if "expected" in item and isinstance(item["expected"], dict):
        task.expected = dict(item["expected"])
    if "harness" in item and isinstance(item["harness"], dict):
        from core.pipeline.schema import HarnessHints

        task.harness = HarnessHints.from_dict(item["harness"])
    if "plan_source_id" in item:
        task.plan_source_id = item["plan_source_id"]


def extract_tasks_yaml_from_text(text: str) -> list[dict[str, Any]] | None:
    """
    從助理回覆擷取 tasks 陣列；若有多個 ```yaml``` 區塊，取**最後一個**含 tasks 者。
    """
    raw = text.strip()
    blocks = re.findall(r"```(?:yaml)?\s*([\s\S]*?)```", raw, re.I)
    if not blocks:
        try:
            data = yaml.safe_load(raw)
            return _tasks_list_from_parsed(data)
        except yaml.YAMLError:
            return None

    for block in reversed(blocks):
        try:
            data = yaml.safe_load(block.strip())
        except yaml.YAMLError:
            continue
        tasks = _tasks_list_from_parsed(data)
        if tasks:
            return tasks
    return None


def _tasks_list_from_parsed(data: Any) -> list[dict[str, Any]] | None:
    if isinstance(data, list) and data:
        if all(isinstance(x, dict) and x.get("id") for x in data):
            return data
        return None
    if isinstance(data, dict) and isinstance(data.get("tasks"), list):
        tasks = data["tasks"]
        if tasks and all(isinstance(x, dict) and x.get("id") for x in tasks):
            return tasks
    return None


def merge_task_list_from_dialogue(
    doc: TaskListDocument,
    parsed: dict[str, Any] | list,
) -> TaskListDocument:
    """
    依 /write 的 tasks 陣列合併：更新規劃欄位、保留 status/verification/pipeline_records。

    未出現在新列表中的任務會移除；新 id 以 pending 加入。
    """
    if isinstance(parsed, list):
        updates = parsed
    elif isinstance(parsed, dict) and "tasks" in parsed:
        updates = parsed["tasks"]
    else:
        raise ValueError("回應須含 tasks 陣列")

    if not isinstance(updates, list) or not updates:
        raise ValueError("tasks 須為非空列表")

    by_id = {t.id: t for t in doc.tasks}
    merged: list[HarnessTask] = []

    for raw in updates:
        if not isinstance(raw, dict) or not raw.get("id"):
            raise ValueError("每筆 task 須為含 id 的映射")
        tid = str(raw["id"])
        if tid in by_id:
            existing = by_id[tid]
            _apply_planning_fields(existing, raw)
            merged.append(existing)
        else:
            item = {k: raw[k] for k in raw if k in _PLANNING_KEYS or k == "status"}
            if "status" not in item:
                item["status"] = "pending"
            if "verification" not in raw:
                item.setdefault("verification", "pending")
            merged.append(HarnessTask.from_dict(item))

    doc.tasks = merged
    doc.plan_revision = int(doc.plan_revision) + 1
    doc.last_updated = _utc_now_iso()
    return doc
