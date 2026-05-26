"""將規範化任務寫回 ``build_goals.yaml``（僅規劃期欄位）。"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import yaml

from core.pipeline.schema import NormalizedPlan, NormalizedTask
from tasks import LOCAL_GOALS_FILE
from unity_common import project_root


def _task_to_goals_entry(task: NormalizedTask) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "id": task.id,
        "title": task.title or task.description,
        "objective": task.description,
        "prompt": task.prompt,
        "enabled": True,
    }
    harness = task.harness.to_dict()
    if harness:
        entry["harness"] = harness
    target = task.target.to_dict()
    if target:
        entry["target"] = target
    if task.expected:
        entry["expected"] = task.expected
    if task.plan_source_id and task.plan_source_id != task.id:
        entry["plan_source_id"] = task.plan_source_id
    return entry


def write_back_build_goals(
    normalized: NormalizedPlan,
    goals_path: Path | str | None = None,
    *,
    backup: bool = False,
) -> Path:
    """合併寫回藍圖 ``tasks``；不修改 goal / system_context 等頂層欄位。"""
    path = Path(goals_path) if goals_path is not None else project_root() / LOCAL_GOALS_FILE
    if not path.is_file():
        raise FileNotFoundError(f"找不到 build_goals: {path}")

    if backup:
        shutil.copy2(path, path.with_suffix(path.suffix + ".bak"))

    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"build_goals 須為 YAML 映射: {path}")

    ordered = sorted(normalized.normalized_tasks, key=lambda t: (t.priority, t.id))
    data["tasks"] = [_task_to_goals_entry(t) for t in ordered]
    if normalized.plan_changelog:
        data["plan_normalize_changelog"] = normalized.plan_changelog
    data["plan_revision"] = normalized.plan_revision

    path.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False, default_flow_style=False),
        encoding="utf-8",
    )
    return path
