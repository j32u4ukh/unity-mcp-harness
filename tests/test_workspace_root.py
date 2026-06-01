"""workspace_root / resolve_goals_path：從 catalog 子目錄執行時應讀 cwd 藍圖。"""

from pathlib import Path

import pytest
import yaml

from tasks import LOCAL_GOALS_FILE, resolve_goals_path
from unity_common import ENV_PROJECT_HOME, workspace_root


def test_workspace_root_prefers_cwd_when_marked(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    catalog = tmp_path / "my-catalog"
    catalog.mkdir()
    (catalog / LOCAL_GOALS_FILE).write_text("project: C\ngoal: g\ntasks: []\n", encoding="utf-8")
    harness_pkg = tmp_path / "unity-mcp-harness"
    harness_pkg.mkdir()
    (harness_pkg / LOCAL_GOALS_FILE).write_text(
        "project: Harness\ngoal: demo\ntasks: []\n", encoding="utf-8"
    )

    monkeypatch.delenv(ENV_PROJECT_HOME, raising=False)
    monkeypatch.chdir(catalog)
    monkeypatch.setattr("unity_common.project_root", lambda: harness_pkg)

    assert workspace_root() == catalog.resolve()
    assert resolve_goals_path().resolve() == (catalog / LOCAL_GOALS_FILE).resolve()


def test_resolve_goals_path_env_over_cwd(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    home = tmp_path / "home-ws"
    home.mkdir()
    goals = home / LOCAL_GOALS_FILE
    goals.write_text(
        yaml.safe_dump(
            {"project": "H", "goal": "from home", "tasks": [{"id": "a", "title": "A", "prompt": "p"}]},
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    other = tmp_path / "other"
    other.mkdir()
    (other / LOCAL_GOALS_FILE).write_text(
        yaml.safe_dump(
            {"project": "O", "goal": "from cwd", "tasks": [{"id": "b", "title": "B", "prompt": "p"}]},
            allow_unicode=True,
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv(ENV_PROJECT_HOME, str(home))
    monkeypatch.chdir(other)
    assert resolve_goals_path().resolve() == goals.resolve()
