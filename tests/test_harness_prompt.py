"""執行期 prompt（task_list + Harness 上下文）測試。"""

from core.pipeline.execution import build_plan_for_execution, get_next_runnable_task
from core.pipeline.schema import HarnessHints, HarnessTask, PipelineRecords, TaskListDocument
from tasks import BuildPlan, BuildTask, format_task_prompt


def test_format_task_prompt_uses_task_list_prompt_not_blueprint() -> None:
    blueprint = BuildPlan(
        project="P",
        system_context="2D 憲法",
        tasks=[BuildTask(id="t1", title="藍圖", prompt="藍圖粗 prompt")],
    )
    harness = HarnessTask(
        id="t1",
        description="執行描述",
        title="執行標題",
        prompt="task_list 規範化 prompt：先讀再寫",
        harness=HarnessHints(pre_read="Unity_ListResources"),
        pipeline_records=PipelineRecords(actual_before={"ready": False}),
    )
    task = BuildTask(id="t1", title="x", prompt=harness.prompt, objective=harness.description)
    text = format_task_prompt(
        task,
        plan=blueprint,
        prior_results=[],
        harness_task=harness,
    )
    assert "task_list 規範化 prompt" in text
    assert "藍圖粗 prompt" not in text
    assert "2D 憲法" in text
    assert "Unity_ListResources" in text
    assert "actual_before" in text


def test_build_plan_for_execution_skips_completed() -> None:
    blueprint = BuildPlan(project="P", tasks=[])
    doc = TaskListDocument(
        project_name="P",
        tasks=[
            HarnessTask(id="done", description="d", prompt="p", status="completed"),
            HarnessTask(id="next", description="n", prompt="run me", status="pending", priority=20),
            HarnessTask(id="first", description="f", prompt="first", status="pending", priority=10),
        ],
    )
    exec_plan = build_plan_for_execution(blueprint, doc)
    ids = [t.id for t in exec_plan.enabled_tasks()]
    assert ids == ["first", "next"]
    assert exec_plan.enabled_tasks()[0].prompt == "first"


def test_build_plan_for_execution_skips_failed_by_default() -> None:
    blueprint = BuildPlan(project="P", tasks=[])
    doc = TaskListDocument(
        tasks=[
            HarnessTask(id="failed", description="f", prompt="retry me", status="failed", priority=1),
            HarnessTask(id="pending", description="p", prompt="run me", status="pending", priority=10),
        ]
    )
    exec_plan = build_plan_for_execution(blueprint, doc)
    ids = [t.id for t in exec_plan.enabled_tasks()]
    assert ids == ["pending"]


def test_build_plan_for_execution_includes_failed_with_retry_flag() -> None:
    blueprint = BuildPlan(project="P", tasks=[])
    doc = TaskListDocument(
        tasks=[
            HarnessTask(id="failed", description="f", prompt="retry me", status="failed", priority=1),
            HarnessTask(id="pending", description="p", prompt="run me", status="pending", priority=10),
        ]
    )
    exec_plan = build_plan_for_execution(blueprint, doc, retry_failed=True)
    ids = [t.id for t in exec_plan.enabled_tasks()]
    assert ids == ["failed", "pending"]


def test_get_next_runnable_task_skips_completed() -> None:
    doc = TaskListDocument(
        tasks=[
            HarnessTask(id="done", description="d", prompt="p", status="completed"),
            HarnessTask(id="next", description="n", prompt="p", status="pending", priority=5),
        ]
    )
    nxt = get_next_runnable_task(doc)
    assert nxt is not None
    assert nxt.id == "next"


def test_get_next_runnable_task_skips_failed_by_default() -> None:
    doc = TaskListDocument(
        tasks=[
            HarnessTask(id="failed", description="f", prompt="p", status="failed", priority=1),
            HarnessTask(id="next", description="n", prompt="p", status="pending", priority=5),
        ]
    )
    nxt = get_next_runnable_task(doc)
    assert nxt is not None
    assert nxt.id == "next"


def test_get_next_runnable_task_can_retry_failed() -> None:
    doc = TaskListDocument(
        tasks=[
            HarnessTask(id="failed", description="f", prompt="p", status="failed", priority=1),
            HarnessTask(id="next", description="n", prompt="p", status="pending", priority=5),
        ]
    )
    nxt = get_next_runnable_task(doc, retry_failed=True)
    assert nxt is not None
    assert nxt.id == "failed"
