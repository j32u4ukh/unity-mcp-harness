"""build_workflow 單元測試（mock Chat）。"""

from unittest.mock import MagicMock, patch

from build_workflow import run_build_plan
from core.pipeline.schema import HarnessTask, PipelineRecords, TaskListDocument
from tasks import BuildPlan, BuildTask


@patch("build_workflow.create_unity_mcp_runner")
@patch("build_workflow.register_unity_servers")
def test_run_build_plan_sequential(mock_reg: MagicMock, mock_runner_factory: MagicMock) -> None:
    mock_runner = MagicMock()
    mock_runner.ask.side_effect = ["reply-1", "reply-2"]
    mock_runner_factory.return_value = mock_runner

    plan = BuildPlan(
        project="Test",
        mcp_servers=["unity"],
        tasks=[
            BuildTask(id="a", title="A", prompt="first"),
            BuildTask(id="b", title="B", prompt="second"),
        ],
    )
    results = run_build_plan(plan, specs={"unity": {"transport": "http", "url": "http://x/mcp"}})
    assert len(results) == 2
    assert results[0].success and results[0].reply == "reply-1"
    assert results[1].success and results[1].reply == "reply-2"
    assert mock_runner.ask.call_count == 2


@patch("build_workflow.create_unity_mcp_runner")
@patch("build_workflow.register_unity_servers")
def test_run_build_plan_stops_on_error(mock_reg: MagicMock, mock_runner_factory: MagicMock) -> None:
    from aicentral.mcp import MCPError

    mock_runner = MagicMock()
    mock_runner.ask.side_effect = [MCPError("fail"), "should-not-run"]
    mock_runner_factory.return_value = mock_runner

    plan = BuildPlan(
        tasks=[
            BuildTask(id="a", title="A", prompt="x"),
            BuildTask(id="b", title="B", prompt="y"),
        ],
    )
    results = run_build_plan(plan, stop_on_error=True)
    assert len(results) == 1
    assert not results[0].success


@patch("build_workflow.create_unity_mcp_runner")
@patch("build_workflow.register_unity_servers")
def test_run_build_plan_marks_refusal_as_failure(
    mock_reg: MagicMock, mock_runner_factory: MagicMock
) -> None:
    mock_runner = MagicMock()
    mock_runner.ask.return_value = (
        "抱歉，我沒有足夠的工具來操作 Editor，無法完成建立場景，"
        "無法直接執行您要求的任務。"
    )
    mock_runner_factory.return_value = mock_runner

    plan = BuildPlan(
        tasks=[BuildTask(id="a", title="A", prompt="建立場景")],
    )
    results = run_build_plan(plan)
    assert len(results) == 1
    assert not results[0].success
    assert results[0].error


@patch("build_workflow.create_unity_mcp_runner")
@patch("build_workflow.register_unity_servers")
def test_run_build_plan_injects_harness_context(
    mock_reg: MagicMock, mock_runner_factory: MagicMock
) -> None:
    mock_runner = MagicMock()
    mock_runner.ask.return_value = "ok"
    mock_runner_factory.return_value = mock_runner

    blueprint = BuildPlan(
        project="P",
        mcp_servers=["unity"],
        tasks=[BuildTask(id="a", title="A", prompt="blueprint-only")],
    )
    task_list = TaskListDocument(
        tasks=[
            HarnessTask(
                id="a",
                description="desc",
                prompt="from-task-list prompt",
                status="pending",
                pipeline_records=PipelineRecords(actual_before={"x": 1}),
            )
        ]
    )
    from core.pipeline.execution import build_plan_for_execution

    exec_plan = build_plan_for_execution(blueprint, task_list)
    run_build_plan(exec_plan, task_list=task_list, resume=True)

    prompt_sent = mock_runner.ask.call_args[0][0]
    assert "from-task-list prompt" in prompt_sent
    assert "blueprint-only" not in prompt_sent
    assert "Harness 執行期狀態" in prompt_sent
    assert "重啟提醒" in prompt_sent
