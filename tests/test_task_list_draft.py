"""task_list modify 修改草案與 /write 合併。"""

import yaml

from core.pipeline.schema import HarnessTask, PipelineRecords, TaskListDocument
from core.task_list_merge import extract_tasks_yaml_from_text, merge_task_list_from_dialogue
from core.tasks_dialogue import TasksModifyState, apply_draft_to_task_list


def test_extract_tasks_prefers_last_yaml_block() -> None:
    text = """
說明文字
```yaml
tasks:
- id: old
  description: x
  prompt: p
```
更多說明
```yaml
tasks:
- id: new
  description: y
  prompt: p2
  priority: 5
```
"""
    tasks = extract_tasks_yaml_from_text(text)
    assert tasks is not None
    assert len(tasks) == 1
    assert tasks[0]["id"] == "new"


def test_write_applies_draft_not_llm() -> None:
    doc = TaskListDocument(
        plan_revision=1,
        tasks=[
            HarnessTask(
                id="a",
                description="old",
                status="completed",
                prompt="p",
                pipeline_records=PipelineRecords(actual_before={"x": 1}),
                verification="verified",
            )
        ],
    )
    state = TasksModifyState(
        draft_tasks=[
            {
                "id": "a",
                "description": "from draft",
                "prompt": "new prompt",
                "priority": 10,
            },
            {"id": "b", "description": "added", "prompt": "np", "priority": 20},
        ]
    )
    path = __import__("pathlib").Path("task_list.yaml")
    apply_draft_to_task_list(doc, state, path=path)
    assert len(doc.tasks) == 2
    assert doc.tasks[0].description == "from draft"
    assert doc.tasks[0].status == "completed"
    assert doc.tasks[0].pipeline_records.actual_before == {"x": 1}
    assert doc.tasks[1].id == "b"


def test_note_draft_from_reply() -> None:
    state = TasksModifyState()
    reply = """好的，草案如下：
```yaml
tasks:
- id: t1
  description: d
  prompt: p
  priority: 1
```
"""
    assert state.note_draft_from_reply(reply)
    assert state.draft_tasks and state.draft_tasks[0]["id"] == "t1"


def test_apply_draft_requires_draft() -> None:
    import pytest

    doc = TaskListDocument(tasks=[])
    state = TasksModifyState()
    with pytest.raises(ValueError, match="尚無修改草案"):
        apply_draft_to_task_list(doc, state, path=__import__("pathlib").Path("x.yaml"))
