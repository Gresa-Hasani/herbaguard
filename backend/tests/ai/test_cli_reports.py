"""Evaluation commands never overwrite an existing (historical) report unless asked."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from herbaguard.ai.cli import ai_app


def test_existing_report_is_refused_before_any_work(tmp_path: Path) -> None:
    report = tmp_path / "generation_baseline_v1_2026-11-06.json"
    report.write_text("{}", encoding="utf-8")
    for command in ("evaluate-generation", "evaluate-retrieval"):
        result = CliRunner().invoke(
            ai_app, [command, "--dataset", "missing.yaml", "--output", str(report)]
        )
        assert result.exit_code == 2, result.output
    assert report.read_text(encoding="utf-8") == "{}"
