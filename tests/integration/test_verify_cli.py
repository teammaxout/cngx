"""End-to-end verify: run a real process and gate on the true result."""

import os
import sys
from contextlib import contextmanager
from pathlib import Path

from cngx.cli.verify_cmd import run_verify

_BUGGY = "def paginate(items, page, size):\n    return items[page * size:(page + 1) * size]\n"
_FIXED = "def paginate(items, page, size):\n    return items[(page - 1) * size:page * size]\n"
_TESTS = (
    "import unittest\n"
    "from cart import paginate\n\n"
    "class T(unittest.TestCase):\n"
    "    def test_first(self):\n"
    "        self.assertEqual(paginate([1,2,3,4], 1, 2), [1, 2])\n"
    "    def test_second(self):\n"
    "        self.assertEqual(paginate([1,2,3,4], 2, 2), [3, 4])\n"
)
_LIE = "Fixed it, all tests pass, ready to merge."


def _setup(tmp_path: Path, module: str) -> Path:
    (tmp_path / "cart.py").write_text(module, encoding="utf-8")
    (tmp_path / "test_cart.py").write_text(_TESTS, encoding="utf-8")
    claim = tmp_path / "agent.md"
    claim.write_text(_LIE, encoding="utf-8")
    return claim


def test_verify_blocks_false_claim(tmp_path, capsys):
    claim = _setup(tmp_path, _BUGGY)
    cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        code = run_verify(
            command=[sys.executable, "-m", "unittest"],
            output_file=claim,
        )
    finally:
        os.chdir(cwd)
    assert code == 1


def test_verify_passes_true_claim(tmp_path):
    claim = _setup(tmp_path, _FIXED)
    cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        code = run_verify(
            command=[sys.executable, "-m", "unittest"],
            output_file=claim,
        )
    finally:
        os.chdir(cwd)
    assert code == 0


def test_verify_evidence_file_failure(tmp_path):
    log = tmp_path / "ci.log"
    log.write_text("2 failed, 1 passed in 0.4s", encoding="utf-8")
    code = run_verify(command=[], claim="all tests pass", evidence_file=log)
    assert code == 1


def test_verify_evidence_file_success(tmp_path):
    log = tmp_path / "ci.log"
    log.write_text("=== 5 passed in 0.4s ===", encoding="utf-8")
    code = run_verify(command=[], claim="all tests pass", evidence_file=log)
    assert code == 0


def test_verify_no_command_no_evidence_is_usage_error(tmp_path, monkeypatch):
    # No command, no evidence, and no autodetectable tests -> usage error (2).
    monkeypatch.chdir(tmp_path)
    code = run_verify(command=[], claim="done")
    assert code == 2


def _init_repo_with_commit(tmp_path: Path, message: str) -> None:
    import subprocess

    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
    (tmp_path / "f.txt").write_text("x", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", message], cwd=tmp_path, check=True)


def test_verify_from_commit_blocks_false_claim(tmp_path):
    # The commit message claims success; the real tests fail -> BLOCKED (1).
    _init_repo_with_commit(tmp_path, "all tests pass, ready to merge")
    (tmp_path / "cart.py").write_text(_BUGGY, encoding="utf-8")
    (tmp_path / "test_cart.py").write_text(_TESTS, encoding="utf-8")
    cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        code = run_verify(command=[sys.executable, "-m", "unittest"], from_commit="HEAD")
    finally:
        os.chdir(cwd)
    assert code == 1


def test_verify_from_commit_passes_true_claim(tmp_path):
    _init_repo_with_commit(tmp_path, "all tests pass")
    (tmp_path / "cart.py").write_text(_FIXED, encoding="utf-8")
    (tmp_path / "test_cart.py").write_text(_TESTS, encoding="utf-8")
    cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        code = run_verify(command=[sys.executable, "-m", "unittest"], from_commit="HEAD")
    finally:
        os.chdir(cwd)
    assert code == 0


def test_verify_from_commit_bad_ref_is_usage_error(tmp_path):
    _init_repo_with_commit(tmp_path, "anything")
    cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        code = run_verify(command=[sys.executable, "-m", "pytest", "-q"], from_commit="no-such-ref")
    finally:
        os.chdir(cwd)
    assert code == 2


def test_verify_from_pr_reads_event_payload(tmp_path, monkeypatch):
    import json as _json

    event = {"pull_request": {"body": "all tests pass, ready to merge"}}
    event_path = tmp_path / "event.json"
    event_path.write_text(_json.dumps(event), encoding="utf-8")
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event_path))

    (tmp_path / "cart.py").write_text(_BUGGY, encoding="utf-8")
    (tmp_path / "test_cart.py").write_text(_TESTS, encoding="utf-8")
    cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        code = run_verify(command=[sys.executable, "-m", "unittest"], from_pr=True)
    finally:
        os.chdir(cwd)
    assert code == 1  # PR body claims success, tests fail -> blocked


def test_verify_from_pr_outside_actions_is_usage_error(tmp_path, monkeypatch):
    monkeypatch.delenv("GITHUB_EVENT_PATH", raising=False)
    code = run_verify(command=[sys.executable, "-m", "pytest", "-q"], from_pr=True)
    assert code == 2


def test_verify_from_pr_no_pull_request_in_payload_is_usage_error(tmp_path, monkeypatch):
    import json as _json

    # A push event has no pull_request key.
    event_path = tmp_path / "event.json"
    event_path.write_text(_json.dumps({"ref": "refs/heads/main"}), encoding="utf-8")
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event_path))
    code = run_verify(command=[sys.executable, "-m", "pytest", "-q"], from_pr=True)
    assert code == 2


def test_verify_conflicting_claim_sources_is_usage_error(tmp_path):
    # Each conflicting pair must exit 2 rather than silently pick one.
    log = tmp_path / "ci.log"
    log.write_text("5 passed", encoding="utf-8")

    assert run_verify(command=[], claim="x", stdin=True, evidence_file=log) == 2
    assert run_verify(command=[], claim="x", output_file=tmp_path / "a.md", evidence_file=log) == 2
    assert run_verify(command=[], claim="x", from_commit="HEAD", evidence_file=log) == 2
    assert run_verify(command=[], claim="x", from_pr=True, evidence_file=log) == 2
    assert run_verify(command=[], from_commit="HEAD", from_pr=True, evidence_file=log) == 2


def test_cli_verify_exposes_new_claim_source_options():
    # The real CLI (main.py app) must expose the flags; a prior version wired them into the wrong
    # module, so cngx verify had no --from-commit / --from-pr. Inspect the command's parameters
    # directly rather than scraping --help text, which Rich colorizes and line-wraps (the rendered
    # output can split "--from-commit" across ANSI escape codes, so a substring check is fragile).
    import typer

    from cngx.cli.main import app

    verify_cmd = typer.main.get_command(app).commands["verify"]
    option_names = {opt for param in verify_cmd.params for opt in param.opts}
    assert "--from-commit" in option_names
    assert "--from-pr" in option_names


def test_cli_verify_from_commit_runs_through_real_app(tmp_path):
    # Exercise the actual CLI entrypoint end to end (not run_verify directly): --from-commit HEAD
    # must be parsed as an option, not treated as the shell command.
    import subprocess

    from typer.testing import CliRunner

    from cngx.cli.main import app

    _init_repo_with_commit(tmp_path, "all tests pass")
    (tmp_path / "test_ok.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        result = CliRunner().invoke(
            app, ["verify", "--from-commit", "HEAD", "--", sys.executable, "-m", "pytest", "-q"]
        )
    finally:
        os.chdir(cwd)
    # Claim (from HEAD) says pass, tests pass -> verified (0). Crucially not a "command not found".
    assert result.exit_code == 0
    assert "command" not in result.output.lower() or "not found" not in result.output.lower()


def test_cli_verify_conflicting_sources_through_real_app(tmp_path):
    from typer.testing import CliRunner

    from cngx.cli.main import app

    result = CliRunner().invoke(
        app, ["verify", "--claim", "x", "--from-pr", "--", sys.executable, "-m", "pytest", "-q"]
    )
    assert result.exit_code == 2
    assert "Conflicting claim sources" in result.output


def test_cli_verify_exposes_recording_options():
    # The real CLI (main.py app) must expose the recording flags. Inspect the command's parameters
    # directly rather than scraping --help text, which Rich colorizes and line-wraps (the rendered
    # output can split "--record" across ANSI escape codes, so a substring check is fragile).
    import typer

    from cngx.cli.main import app

    verify_cmd = typer.main.get_command(app).commands["verify"]
    option_names = {opt for param in verify_cmd.params for opt in param.opts}
    assert "--record" in option_names
    assert "--label" in option_names
    assert "--stats" in option_names


@contextmanager
def _cngx_root_at(tmp_path):
    """Run the CLI with the cngx project root, and therefore the DuckDB store, inside tmp_path.

    Both the config and the database are module-level singletons and the store path is derived from
    `config.project_root`, which defaults to the cwd at the moment the config is first built. Changing
    the directory alone is not enough: in a full test session an earlier test has usually already built
    a config rooted at the repo, so the store would land in the real .cngx directory. Reset both
    singletons after moving, and again on the way out so later tests are unaffected.
    """
    from cngx.core.config import reset_config
    from cngx.storage.database import reset_database

    cwd = os.getcwd()
    os.chdir(tmp_path)
    reset_config()
    reset_database()
    try:
        yield
    finally:
        os.chdir(cwd)
        reset_config()
        reset_database()


def test_cli_verify_without_record_writes_no_database(tmp_path):
    # Plain `cngx verify` must stay zero-setup: no database is created or opened.
    from typer.testing import CliRunner

    from cngx.cli.main import app

    (tmp_path / "test_ok.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    with _cngx_root_at(tmp_path):
        result = CliRunner().invoke(
            app,
            ["verify", "--claim", "all tests pass", "--", sys.executable, "-m", "pytest", "-q"],
        )

    assert result.exit_code == 0
    assert not (tmp_path / ".cngx" / "cngx.db").exists()


def test_cli_verify_record_then_stats_round_trip(tmp_path):
    # Record a run through the real CLI, then read it back with --stats. This locks the wiring:
    # the flags have to be plumbed through main.py, not just present on run_verify.
    from typer.testing import CliRunner

    from cngx.cli.main import app

    (tmp_path / "test_ok.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    with _cngx_root_at(tmp_path):
        recorded = CliRunner().invoke(
            app,
            [
                "verify",
                "--record",
                "--label",
                "test-model",
                "--claim",
                "all tests pass",
                "--",
                sys.executable,
                "-m",
                "pytest",
                "-q",
            ],
        )
        stats = CliRunner().invoke(app, ["verify", "--stats"])

    # Claim says pass and the tests pass, so the run itself is verified.
    assert recorded.exit_code == 0
    # Recording is opt-in, so this run should have created the store and landed one row.
    assert (tmp_path / ".cngx" / "cngx.db").exists()
    assert stats.exit_code == 0
    assert "test-model" in stats.output
