"""Evidence-file cross-check for offline agent gating."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from cngx.cli.main import app
from cngx.enforcement.evidence import check_evidence_text, first_result_snippet

ROOT = Path(__file__).resolve().parents[2]
POLICY = ROOT / "examples" / "contracts" / "coding_agent_verification.yaml"
VERIFIED = ROOT / "tests" / "fixtures" / "agent_outputs" / "verified_fix.txt"

# Solid writeup that references pytest but omits a concrete result line.
REASONED_WITHOUT_RESULT = """\
1. Reproduced the failing pagination test for page 1 in tests/test_users.py.
2. Updated slice logic to items[(page - 1) * size : page * size] for 1-based pages.
3. Ran pytest on tests/test_users.py to verify the fix and check for regressions.
4. Verified the change against the original bug report. Summary: safe to merge after checks.
"""


def test_evidence_requires_result_line() -> None:
    bad = check_evidence_text("I ran pytest and everything looks fine.")
    assert not bad.ok
    good = check_evidence_text("===== 12 passed in 0.42s =====")
    assert good.ok


def test_first_result_snippet_picks_matching_line() -> None:
    log = "collecting ...\ntests/test_users.py ........\n===== 12 passed in 0.41s =====\n"
    assert first_result_snippet(log) == "===== 12 passed in 0.41s ====="
    assert first_result_snippet("no results here") is None


def test_cli_blocks_when_evidence_lacks_results(tmp_path: Path) -> None:
    evidence = tmp_path / "pytest.log"
    evidence.write_text("starting tests...\nI think they passed\n", encoding="utf-8")
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "check",
            "-c",
            str(POLICY),
            "-p",
            "Fix the bug and run tests",
            "--output-file",
            str(VERIFIED),
            "--evidence-file",
            str(evidence),
        ],
    )
    assert result.exit_code == 1, result.output
    assert "evidence" in result.output.lower() or "BLOCKED" in result.output


def test_cli_passes_with_real_pytest_log(tmp_path: Path) -> None:
    evidence = tmp_path / "pytest.log"
    evidence.write_text(
        "tests/test_users.py ........\n" "===== 12 passed in 0.41s =====\n",
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
            "Fix the bug and run tests",
            "--output-file",
            str(VERIFIED),
            "--evidence-file",
            str(evidence),
        ],
    )
    assert result.exit_code == 0, result.output


def test_cli_injects_evidence_snippet_into_output_missing_result(
    tmp_path: Path,
) -> None:
    """CI log supplies the result line the agent writeup omitted."""
    output = tmp_path / "agent_output.txt"
    output.write_text(REASONED_WITHOUT_RESULT, encoding="utf-8")
    evidence = tmp_path / "pytest.log"
    evidence.write_text(
        "tests/test_users.py ........\n===== 12 passed in 0.41s =====\n",
        encoding="utf-8",
    )

    runner = CliRunner()
    without_evidence = runner.invoke(
        app,
        [
            "check",
            "-c",
            str(POLICY),
            "-p",
            "Fix the bug and run tests",
            "--output-file",
            str(output),
        ],
    )
    assert without_evidence.exit_code == 1, without_evidence.output

    with_evidence = runner.invoke(
        app,
        [
            "check",
            "-c",
            str(POLICY),
            "-p",
            "Fix the bug and run tests",
            "--output-file",
            str(output),
            "--evidence-file",
            str(evidence),
            "--json",
        ],
    )
    assert with_evidence.exit_code == 0, with_evidence.output
    assert "12 passed" in with_evidence.output
    assert '"snippet"' in with_evidence.output
