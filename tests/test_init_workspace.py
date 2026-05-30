"""Tests for unity-mcp-harness --init / init_workspace."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from core.scaffold.init_workspace import init_workspace, scaffold_source_dir


def test_scaffold_source_dir_exists() -> None:
    root = scaffold_source_dir()
    assert root.is_dir()
    assert (root / "build_goals.example.yaml").is_file()
    assert (root / "scripts" / "_env.ps1").is_file()
    assert (root / "project_state" / "_index.yaml").is_file()


def test_init_workspace_creates_files(tmp_path: Path) -> None:
    report = init_workspace(tmp_path)
    assert report.ok
    assert (tmp_path / "build_goals.yaml").is_file()
    assert (tmp_path / "unity_servers.json").is_file()
    assert (tmp_path / "config" / "secret.yaml").is_file()
    assert (tmp_path / "scripts" / "harness-run.ps1").is_file()
    assert (tmp_path / "project_state" / "changelog.md").is_file()
    assert not (tmp_path / "task_list.yaml").exists()
    assert "build_goals.yaml" in report.created


def test_init_skips_existing_files(tmp_path: Path) -> None:
    init_workspace(tmp_path)
    (tmp_path / "build_goals.yaml").write_text("custom: true\n", encoding="utf-8")
    report = init_workspace(tmp_path)
    assert "build_goals.yaml" in report.skipped
    assert (tmp_path / "build_goals.yaml").read_text(encoding="utf-8") == "custom: true\n"


def test_init_secret_never_overwritten_without_force(tmp_path: Path) -> None:
    init_workspace(tmp_path)
    secret = tmp_path / "config" / "secret.yaml"
    secret.write_text("gemini:\n  api_key: keep-me\n", encoding="utf-8")
    report = init_workspace(tmp_path)
    assert "config/secret.yaml" in report.skipped
    assert "keep-me" in secret.read_text(encoding="utf-8")


def test_init_force_overwrites_secret(tmp_path: Path) -> None:
    init_workspace(tmp_path)
    secret = tmp_path / "config" / "secret.yaml"
    secret.write_text("gemini:\n  api_key: old\n", encoding="utf-8")
    init_workspace(tmp_path, force=True)
    text = secret.read_text(encoding="utf-8")
    assert "old" not in text
    assert "api_key" in text


def test_init_http_transport(tmp_path: Path) -> None:
    report = init_workspace(tmp_path, mcp_transport="http")
    assert report.ok
    content = (tmp_path / "unity_servers.json").read_text(encoding="utf-8")
    assert "http" in content.lower() or "url" in content.lower()


def test_init_creates_missing_root(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "workspace"
    report = init_workspace(target)
    assert report.ok
    assert target.is_dir()


def test_format_init_report_mentions_scripts(tmp_path: Path) -> None:
    from core.scaffold.init_workspace import format_init_report, init_workspace

    report = init_workspace(tmp_path)
    text = format_init_report(report)
    assert "harness-dry-run.ps1" in text
    assert "list-tools.ps1" in text
    assert "_env.ps1" in text


def test_cli_init_cwd(tmp_path: Path) -> None:
    harness_root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, "-m", "run_build", "--init"],
        cwd=tmp_path,
        env={**dict(__import__("os").environ), "PYTHONPATH": str(harness_root)},
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert result.returncode == 0, result.stderr + result.stdout
    assert (tmp_path / "build_goals.yaml").is_file()
    assert "build_goals.yaml" in result.stdout
    assert "harness-dry-run.ps1" in result.stdout
    assert str(tmp_path) in result.stdout
