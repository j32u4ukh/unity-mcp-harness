"""project_state/ 路徑解析（位於 UNITY_MCP_HOME 工作區根）。"""

from __future__ import annotations

from pathlib import Path

PROJECT_STATE_DIR = "project_state"
INDEX_FILENAME = "_index.yaml"
CHANGELOG_FILENAME = "changelog.md"


def project_state_dir_name() -> str:
    return PROJECT_STATE_DIR


def default_project_state_root() -> Path:
    from unity_common import project_root

    return project_root() / PROJECT_STATE_DIR


def index_path(root: Path | None = None) -> Path:
    base = root if root is not None else default_project_state_root()
    return base / INDEX_FILENAME


def changelog_path(root: Path | None = None) -> Path:
    base = root if root is not None else default_project_state_root()
    return base / CHANGELOG_FILENAME
