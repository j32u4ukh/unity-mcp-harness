"""core.cli_plan 旗標解析測試。"""

import argparse

from core.cli_plan import add_plan_cli_arguments, resolve_plan_cli


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser()
    add_plan_cli_arguments(p)
    return p


def test_legacy_goals_to_task_list_maps_sync_only() -> None:
    flags = resolve_plan_cli(_parser().parse_args(["--goals-to-task-list"]))
    assert flags.sync_blueprint_only


def test_legacy_replan_and_run_maps_sync_only_not_run() -> None:
    flags = resolve_plan_cli(_parser().parse_args(["--replan-and-run"]))
    assert flags.sync_blueprint_only


def test_export_task_list_standalone() -> None:
    flags = resolve_plan_cli(_parser().parse_args(["--export-goals-from-task-list"]))
    assert flags.export_goals_from_task_list
    assert flags.standalone_export_from_task_list
    assert not flags.sync_blueprint_only


def test_export_task_list_with_legacy_sync() -> None:
    flags = resolve_plan_cli(
        _parser().parse_args(
            ["--goals-to-task-list", "--export-goals-from-task-list"]
        )
    )
    assert flags.export_goals_from_task_list
    assert flags.sync_blueprint_only
    assert not flags.standalone_export_from_task_list


def test_deprecated_sync_plan_maps_sync_only() -> None:
    flags = resolve_plan_cli(_parser().parse_args(["--sync-plan"]))
    assert flags.sync_blueprint_only


def test_deprecated_write_back_on_sync_maps_to_task_list_export() -> None:
    flags = resolve_plan_cli(
        _parser().parse_args(["--sync-plan", "--write-back-goals"])
    )
    assert flags.export_goals_from_task_list


def test_deprecated_write_back_on_replan_maps_to_normalize_export() -> None:
    flags = resolve_plan_cli(
        _parser().parse_args(["--replan", "--write-back-goals"])
    )
    assert flags.sync_blueprint_only
    assert flags.export_goals_from_normalize
