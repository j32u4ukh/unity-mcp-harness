"""Initialize an external harness workspace from bundled scaffold templates."""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

McpTransport = Literal["stdio", "http"]

# Never overwrite unless --init-force (secret is extra-sensitive).
PROTECTED_PATHS = frozenset({"config/secret.yaml"})


@dataclass
class InitReport:
    target: Path
    created: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def scaffold_source_dir() -> Path:
    """Return the directory containing scaffold templates (editable + wheel)."""
    return Path(__file__).resolve().parent / "templates"


def _norm_rel(path: Path) -> str:
    return path.as_posix()


def _copy_file(
    src: Path,
    dest: Path,
    *,
    force: bool,
    report: InitReport,
    rel: str,
) -> None:
    if dest.is_file():
        if not force:
            report.skipped.append(rel)
            return
        if rel in PROTECTED_PATHS and not force:
            report.skipped.append(rel)
            return
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        report.created.append(rel)
    except OSError as exc:
        report.errors.append(f"{rel}: {exc}")


def _copy_tree(
    src_dir: Path,
    dest_dir: Path,
    *,
    force: bool,
    report: InitReport,
    prefix: str,
) -> None:
    if not src_dir.is_dir():
        report.errors.append(f"{prefix}: scaffold scripts directory missing")
        return
    for src in sorted(src_dir.rglob("*")):
        if not src.is_file():
            continue
        rel = _norm_rel(Path(prefix) / src.relative_to(src_dir))
        dest = dest_dir / src.relative_to(src_dir)
        if dest.is_file() and not force:
            report.skipped.append(rel)
            continue
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
            if rel not in report.created:
                report.created.append(rel)
        except OSError as exc:
            report.errors.append(f"{rel}: {exc}")


def _file_mappings(mcp_transport: McpTransport) -> list[tuple[str, str]]:
    unity_src = (
        "unity_servers.stdio.example.json"
        if mcp_transport == "stdio"
        else "unity_servers.http.example.json"
    )
    return [
        ("build_goals.example.yaml", "build_goals.yaml"),
        (unity_src, "unity_servers.json"),
        ("config/secret.yaml.example", "config/secret.yaml"),
        ("config/aicentral.yaml.example", "config/aicentral.yaml"),
        ("config/prompt_supplements.json.example", "config/prompt_supplements.json"),
        ("config/unity_explore.yaml.example", "config/unity_explore.yaml"),
        ("config/project.yaml.example", "config/project.yaml"),
        ("config/local.env.ps1.example", "config/local.env.ps1"),
        ("config/rate_limit_store.example.json", "config/rate_limit_store.json"),
        (".gitignore.example", ".gitignore"),
        ("README.md", "README.md"),
    ]


def init_workspace(
    target: Path,
    *,
    force: bool = False,
    mcp_transport: McpTransport = "stdio",
) -> InitReport:
    """Copy scaffold templates into *target* (created if missing)."""
    report = InitReport(target=target.resolve())
    scaffold = scaffold_source_dir()
    if not scaffold.is_dir():
        report.errors.append(f"scaffold not found: {scaffold}")
        return report

    target.mkdir(parents=True, exist_ok=True)

    for src_rel, dest_rel in _file_mappings(mcp_transport):
        src = scaffold / src_rel
        dest = target / dest_rel
        if not src.is_file():
            report.errors.append(f"missing template: {src_rel}")
            continue
        if dest_rel in PROTECTED_PATHS and dest.is_file() and not force:
            report.skipped.append(dest_rel)
            continue
        _copy_file(src, dest, force=force, report=report, rel=dest_rel)

    _copy_tree(
        scaffold / "scripts",
        target / "scripts",
        force=force,
        report=report,
        prefix="scripts",
    )
    _copy_tree(
        scaffold / "project_state",
        target / "project_state",
        force=force,
        report=report,
        prefix="project_state",
    )
    return report


def format_init_report(report: InitReport) -> str:
    lines = [f"已初始化工作區: {report.target}"]
    if report.created:
        lines.append(f"  已建立: {', '.join(report.created)}")
    if report.skipped:
        lines.append(f"  已略過（已存在）: {', '.join(report.skipped)}")
    if report.errors:
        lines.append("  錯誤:")
        for err in report.errors:
            lines.append(f"    - {err}")
    lines.extend(
        [
            "下一步:",
            f"  1. 編輯 config\\secret.yaml（gemini.api_key）",
            f"  2. 編輯 config\\local.env.ps1（Unity 專案與 Editor 路徑）",
            f"  3. cd {report.target}",
            "  4. .\\scripts\\list-tools.ps1          # 驗證 MCP（scripts 會自動設定 UNITY_MCP_HOME）",
            "  5. 啟動 Unity 後：unity-mcp-harness --bootstrap-state  # 盤點既有專案 → project_state/",
            "  6. .\\scripts\\harness-dry-run.ps1     # 規劃 + dry-run",
            "  7. .\\scripts\\harness-run.ps1         # 執行建構",
            "（若直接跑 unity-mcp-harness CLI，請先 . .\\scripts\\_env.ps1 或設定 UNITY_MCP_HOME）",
        ]
    )
    return "\n".join(lines)
