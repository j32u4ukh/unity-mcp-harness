"""``task_list.yaml`` 與 Plan Normalize 輸出的資料模型。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class TaskTarget:
    game_object: str | None = None
    scene_path: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> TaskTarget:
        if not data:
            return cls()
        return cls(
            game_object=data.get("game_object"),
            scene_path=data.get("scene_path"),
        )

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        if self.game_object is not None:
            out["game_object"] = self.game_object
        if self.scene_path is not None:
            out["scene_path"] = self.scene_path
        return out


@dataclass
class HarnessHints:
    pre_read: str | None = None
    post_read: str | None = None
    verify_read: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> HarnessHints:
        if not data:
            return cls()
        return cls(
            pre_read=data.get("pre_read"),
            post_read=data.get("post_read"),
            verify_read=data.get("verify_read"),
        )

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        if self.pre_read is not None:
            out["pre_read"] = self.pre_read
        if self.post_read is not None:
            out["post_read"] = self.post_read
        if self.verify_read is not None:
            out["verify_read"] = self.verify_read
        return out


@dataclass
class OperationRecord:
    timestamp: str
    action: str
    tool: str | None = None
    summary: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> OperationRecord:
        return cls(
            timestamp=str(data["timestamp"]),
            action=str(data["action"]),
            tool=data.get("tool"),
            summary=data.get("summary"),
        )

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "timestamp": self.timestamp,
            "action": self.action,
        }
        if self.tool is not None:
            out["tool"] = self.tool
        if self.summary is not None:
            out["summary"] = self.summary
        return out


@dataclass
class PipelineRecords:
    actual_before: dict[str, Any] = field(default_factory=dict)
    operations_executed: list[OperationRecord] = field(default_factory=list)
    actual_after: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> PipelineRecords:
        if not data:
            return cls()
        ops = [
            OperationRecord.from_dict(item)
            for item in data.get("operations_executed") or []
            if isinstance(item, dict)
        ]
        return cls(
            actual_before=dict(data.get("actual_before") or {}),
            operations_executed=ops,
            actual_after=dict(data.get("actual_after") or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "actual_before": self.actual_before,
            "operations_executed": [op.to_dict() for op in self.operations_executed],
            "actual_after": self.actual_after,
        }


@dataclass
class NormalizedTask:
    """規劃期任務（Plan Normalize 輸出；bootstrap 前）。"""

    id: str
    description: str
    prompt: str
    priority: int = 10
    title: str | None = None
    target: TaskTarget = field(default_factory=TaskTarget)
    expected: dict[str, Any] = field(default_factory=dict)
    harness: HarnessHints = field(default_factory=HarnessHints)
    plan_source_id: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> NormalizedTask:
        return cls(
            id=str(data["id"]),
            description=str(data.get("description") or data.get("title") or data["id"]),
            prompt=str(data.get("prompt") or ""),
            priority=int(data.get("priority", 10)),
            title=data.get("title"),
            target=TaskTarget.from_dict(data.get("target")),
            expected=dict(data.get("expected") or {}),
            harness=HarnessHints.from_dict(data.get("harness")),
            plan_source_id=data.get("plan_source_id"),
        )

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "id": self.id,
            "description": self.description,
            "prompt": self.prompt,
            "priority": self.priority,
        }
        if self.title is not None:
            out["title"] = self.title
        target = self.target.to_dict()
        if target:
            out["target"] = target
        if self.expected:
            out["expected"] = self.expected
        harness = self.harness.to_dict()
        if harness:
            out["harness"] = harness
        if self.plan_source_id is not None:
            out["plan_source_id"] = self.plan_source_id
        return out


@dataclass
class NormalizedPlan:
    """Plan Normalize 完整輸出。"""

    normalized_tasks: list[NormalizedTask]
    plan_changelog: str = ""
    plan_revision: int = 1
    source_plan: str = "build_goals.yaml"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> NormalizedPlan:
        tasks = [
            NormalizedTask.from_dict(item)
            for item in data.get("normalized_tasks") or []
            if isinstance(item, dict)
        ]
        return cls(
            normalized_tasks=tasks,
            plan_changelog=str(data.get("plan_changelog") or ""),
            plan_revision=int(data.get("plan_revision", 1)),
            source_plan=str(data.get("source_plan") or "build_goals.yaml"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "normalized_tasks": [t.to_dict() for t in self.normalized_tasks],
            "plan_changelog": self.plan_changelog,
            "plan_revision": self.plan_revision,
            "source_plan": self.source_plan,
        }


@dataclass
class HarnessTask:
    """執行期任務（``task_list.yaml`` 單筆）。"""

    id: str
    description: str
    status: str = "pending"
    priority: int = 10
    prompt: str = ""
    title: str | None = None
    target: TaskTarget = field(default_factory=TaskTarget)
    expected: dict[str, Any] = field(default_factory=dict)
    harness: HarnessHints = field(default_factory=HarnessHints)
    pipeline_records: PipelineRecords = field(default_factory=PipelineRecords)
    verification: str = "pending"
    injected_by: str | None = None
    plan_source_id: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> HarnessTask:
        return cls(
            id=str(data["id"]),
            description=str(data.get("description") or data.get("title") or data["id"]),
            status=str(data.get("status", "pending")),
            priority=int(data.get("priority", 10)),
            prompt=str(data.get("prompt") or ""),
            title=data.get("title"),
            target=TaskTarget.from_dict(data.get("target")),
            expected=dict(data.get("expected") or {}),
            harness=HarnessHints.from_dict(data.get("harness")),
            pipeline_records=PipelineRecords.from_dict(data.get("pipeline_records")),
            verification=str(data.get("verification", "pending")),
            injected_by=data.get("injected_by"),
            plan_source_id=data.get("plan_source_id"),
        )

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "id": self.id,
            "description": self.description,
            "status": self.status,
            "priority": self.priority,
            "prompt": self.prompt,
            "pipeline_records": self.pipeline_records.to_dict(),
            "verification": self.verification,
        }
        if self.title is not None:
            out["title"] = self.title
        target = self.target.to_dict()
        if target:
            out["target"] = target
        if self.expected:
            out["expected"] = self.expected
        harness = self.harness.to_dict()
        if harness:
            out["harness"] = harness
        if self.injected_by is not None:
            out["injected_by"] = self.injected_by
        if self.plan_source_id is not None:
            out["plan_source_id"] = self.plan_source_id
        return out

    @classmethod
    def from_normalized(cls, task: NormalizedTask, *, status: str = "pending") -> HarnessTask:
        return cls(
            id=task.id,
            description=task.description,
            status=status,
            priority=task.priority,
            prompt=task.prompt,
            title=task.title,
            target=task.target,
            expected=task.expected,
            harness=task.harness,
            plan_source_id=task.plan_source_id,
        )


@dataclass
class TaskListDocument:
    """``task_list.yaml`` 根文件。"""

    tasks: list[HarnessTask]
    project_name: str = ""
    harness_version: int = 1
    last_updated: str | None = None
    current_lifecycle_phase: str | None = None
    source_plan: str = "build_goals.yaml"
    plan_revision: int = 1
    plan_normalized_at: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TaskListDocument:
        tasks = [
            HarnessTask.from_dict(item)
            for item in data.get("tasks") or []
            if isinstance(item, dict)
        ]
        return cls(
            tasks=tasks,
            project_name=str(data.get("project_name") or ""),
            harness_version=int(data.get("harness_version", 1)),
            last_updated=data.get("last_updated"),
            current_lifecycle_phase=data.get("current_lifecycle_phase"),
            source_plan=str(data.get("source_plan") or "build_goals.yaml"),
            plan_revision=int(data.get("plan_revision", 1)),
            plan_normalized_at=data.get("plan_normalized_at"),
        )

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "project_name": self.project_name,
            "harness_version": self.harness_version,
            "source_plan": self.source_plan,
            "plan_revision": self.plan_revision,
            "tasks": [t.to_dict() for t in self.tasks],
        }
        if self.last_updated is not None:
            out["last_updated"] = self.last_updated
        if self.current_lifecycle_phase is not None:
            out["current_lifecycle_phase"] = self.current_lifecycle_phase
        if self.plan_normalized_at is not None:
            out["plan_normalized_at"] = self.plan_normalized_at
        return out
