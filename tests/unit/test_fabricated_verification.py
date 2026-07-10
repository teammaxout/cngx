"""Strict coding-agent policy must reject bare 'I ran tests' claims."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from cngx.cli.main import app

ROOT = Path(__file__).resolve().parents[2]
POLICY = ROOT / "examples" / "contracts" / "coding_agent_verification.yaml"
FIXTURES = ROOT / "tests" / "fixtures" / "agent_outputs"


def test_fabricated_claim_without_result_is_blocked(tmp_path: Path) -> None:
    fake = tmp_path / "fake.txt"
    fake.write_text(
        "1. Located the pagination bug in users.py.\n"
        "2. Applied a one-line slice fix.\n"
        "3. I ran pytest and verified everything looks good.\n"
        "4. Ready to merge.\n",
        encoding="utf-8",
    )
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "check",
            "-c",
            str(POLICY),
            "-p",
            "Fix the pagination bug and run tests",
            "--output-file",
            str(fake),
        ],
    )
    assert result.exit_code == 1, result.output


def test_result_shaped_fixture_still_passes() -> None:
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "check",
            "-c",
            str(POLICY),
            "-p",
            "Fix the pagination bug and run tests",
            "--output-file",
            str(FIXTURES / "verified_fix.txt"),
        ],
    )
    assert result.exit_code == 0, result.output
