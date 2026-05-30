"""啟動前：Plan Normalize + bootstrap task_list。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.pipeline.bootstrap import ensure_task_list
from core.pipeline.goals_writeback import write_back_build_goals
from core.pipeline.plan_normalize import normalize_plan, normalize_plan_passthrough_enriched
from core.pipeline.schema import NormalizedPlan, NormalizedTask, TaskListDocument
from core.pipeline.store import default_task_list_path
from tasks import BuildPlan, resolve_build_plan


def _normalized_from_task_list(doc: TaskListDocument) -> NormalizedPlan:
    """由既有 task_list 重建規劃摘要（供 dry-run / 沿用 SSOT 時顯示）。"""
    tasks = [
        NormalizedTask(
            id=t.id,
            description=t.description,
            prompt=t.prompt,
            priority=t.priority,
            title=t.title,
            target=t.target,
            expected=t.expected,
            harness=t.harness,
            plan_source_id=t.plan_source_id or t.id,
        )
        for t in doc.tasks
    ]
    return NormalizedPlan(
        normalized_tasks=tasks,
        plan_changelog="（沿用既有 task_list.yaml）",
        plan_revision=doc.plan_revision,
        source_plan=doc.source_plan,
    )


@dataclass
class HarnessPrepareResult:
    build_plan: BuildPlan
    normalized: NormalizedPlan
    task_list: TaskListDocument
    task_list_path: Path
    created_task_list: bool


def prepare_harness_queue(
    *,
    goals_path: Path | str | None = None,
    skip_plan_normalize: bool = False,
    replan: bool = False,
    init_tasks: bool = False,
    write_back_goals: bool = False,
    backup_goals: bool = False,
    plan_with_mcp: bool = False,
    plan_interactive: bool = False,
    supplements_path: Path | str | None = None,
    unity_config_path: str | None = None,
    specs: dict[str, dict[str, Any]] | None = None,
) -> HarnessPrepareResult:
    """
    載入藍圖 →（可選）LLM 規範化 →（可選）寫回藍圖 → bootstrap/載入 task_list。

    - 無 ``task_list.yaml``、``--replan`` 或 ``--init-tasks`` 時會 bootstrap 並落盤。
    - 否則沿用既有 ``task_list``（不重新 normalize）。
    """
    build_plan = resolve_build_plan(plan_path=goals_path)
    task_path = default_task_list_path()
    had_task_list = task_path.is_file()
    need_bootstrap = (not had_task_list) or replan or init_tasks

    if need_bootstrap:
        if skip_plan_normalize:
            normalized = normalize_plan_passthrough_enriched(
                build_plan,
                plan_interactive=plan_interactive,
                supplements_path=supplements_path,
            )
        else:
            existing_revision = 1
            if had_task_list and replan:
                from core.pipeline.store import load_task_list

                existing_revision = load_task_list(task_path).plan_revision + 1
            normalized = normalize_plan(
                build_plan,
                plan_revision=existing_revision,
                plan_with_mcp=plan_with_mcp,
                plan_interactive=plan_interactive,
                supplements_path=supplements_path,
                specs=specs,
                unity_config_path=unity_config_path,
            )
        if write_back_goals:
            write_back_build_goals(normalized, goals_path, backup=backup_goals)
        task_list = ensure_task_list(
            normalized,
            project_name=build_plan.project,
            path=task_path,
            replan=replan or init_tasks or not had_task_list,
            preserve_completed=True,
        )
        created = True
    else:
        from core.pipeline.store import load_task_list

        task_list = load_task_list(task_path)
        normalized = _normalized_from_task_list(task_list)
        created = False

    return HarnessPrepareResult(
        build_plan=build_plan,
        normalized=normalized,
        task_list=task_list,
        task_list_path=task_path,
        created_task_list=created,
    )
