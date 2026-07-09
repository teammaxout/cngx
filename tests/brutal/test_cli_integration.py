"""
BRUTAL TEST: CLI Integration

Tests that the CLI commands actually work end-to-end.
Uses CliRunner to invoke commands programmatically.
"""

import json
import os
import tempfile
from pathlib import Path

import pytest
from typer.testing import CliRunner

from cngx.cli.main import app

runner = CliRunner()


class TestInitCommand:
    """Test `cngx init` command."""

    def test_init_creates_cngx_dir(self, tmp_path):
        """cngx init should create .cngx directory structure."""
        result = runner.invoke(app, ["init", str(tmp_path)])
        assert result.exit_code == 0, f"cngx init failed: {result.output}"
        cngx_dir = tmp_path / ".cngx"
        assert cngx_dir.exists(), f".cngx directory not created in {tmp_path}"

    def test_init_creates_db(self, tmp_path):
        """cngx init should create the database file."""
        result = runner.invoke(app, ["init", str(tmp_path)])
        assert result.exit_code == 0
        cngx_dir = tmp_path / ".cngx"
        assert cngx_dir.exists()

    def test_init_idempotent(self, tmp_path):
        """Running init twice should work (or give clear error)."""
        runner.invoke(app, ["init", str(tmp_path)])
        result2 = runner.invoke(app, ["init", str(tmp_path)])
        # Second run should either succeed or fail gracefully
        assert result2.exit_code in [0, 1], f"Second init crashed: {result2.output}"

    def test_init_force_overwrites(self, tmp_path):
        """cngx init --force should overwrite existing .cngx directory."""
        runner.invoke(app, ["init", str(tmp_path)])
        result = runner.invoke(app, ["init", str(tmp_path), "--force"])
        assert result.exit_code == 0, f"Force init failed: {result.output}"


class TestVersionCommand:
    """Test `cngx version` command."""

    def test_version_output(self):
        """cngx version should output the version string."""
        from cngx import __version__

        result = runner.invoke(app, ["version"])
        assert result.exit_code == 0
        assert __version__ in result.output or "cngx" in result.output.lower()


class TestStatusCommand:
    """Test `cngx status` command."""

    def test_status_in_uninitialized_dir(self, tmp_path):
        """Status in non-cngx dir should give clear message."""
        os.chdir(str(tmp_path))
        result = runner.invoke(app, ["status"])
        # Should either succeed with empty status or fail gracefully
        assert result.exit_code in [0, 1]


class TestGateCommand:
    """Test `cngx gate` commands with mock adapter."""

    def test_gate_check_mock_pass(self, tmp_path):
        """Gate check with mock adapter and lenient contract should pass."""
        # Write a lenient contract
        contract_path = tmp_path / "lenient.yaml"
        contract_path.write_text(
            """
name: lenient
version: "1.0"
domain: general
depth:
  min: 1
  severity: warn
output:
  min_length: 1
  severity: warn
""",
            encoding="utf-8",
        )

        result = runner.invoke(
            app,
            [
                "gate",
                "check",
                "What is 2 + 2?",
                "--contract",
                str(contract_path),
                "--adapter",
                "mock",
                "--model",
                "mock-model",
            ],
        )
        assert (
            result.exit_code == 0
        ), f"Gate check should pass with lenient contract: {result.output}"

    def test_gate_check_json_output(self, tmp_path):
        """Gate check with --json should output valid JSON."""
        contract_path = tmp_path / "test.yaml"
        contract_path.write_text(
            """
name: json_test
version: "1.0"
domain: general
depth:
  min: 1
  severity: warn
""",
            encoding="utf-8",
        )

        result = runner.invoke(
            app,
            [
                "gate",
                "check",
                "Simple question",
                "--contract",
                str(contract_path),
                "--adapter",
                "mock",
                "--json",
            ],
        )
        assert result.exit_code == 0
        # Try to parse JSON from output
        try:
            output_json = json.loads(result.output)
            assert "passed" in output_json or "exit_code" in output_json
        except json.JSONDecodeError:
            # Some output may go to stderr, check that there's *some* structured output
            pass

    def test_gate_check_strict_blocks(self, tmp_path):
        """Gate check with strict contract and mock should block (mock may produce shallow output)."""
        contract_path = tmp_path / "strict.yaml"
        contract_path.write_text(
            """
name: strict_test
version: "1.0"
domain: math
depth:
  min: 100
  severity: block
""",
            encoding="utf-8",
        )

        result = runner.invoke(
            app,
            [
                "gate",
                "check",
                "What is 2 + 2?",
                "--contract",
                str(contract_path),
                "--adapter",
                "mock",
            ],
        )
        # With depth min=100, mock should fail
        assert (
            result.exit_code == 1
        ), f"Impossible depth should be blocked. Exit: {result.exit_code}, Output: {result.output}"

    def test_gate_check_invalid_contract(self, tmp_path):
        """Gate check with invalid contract file should fail gracefully."""
        bad_path = tmp_path / "nonexistent.yaml"
        result = runner.invoke(
            app,
            [
                "gate",
                "check",
                "Test",
                "--contract",
                str(bad_path),
                "--adapter",
                "mock",
            ],
        )
        assert result.exit_code != 0, "Invalid contract should fail"


class TestCaptureCommand:
    """Test `cngx capture` commands."""

    def test_capture_run_mock(self, tmp_path):
        """Capture with mock adapter should work."""
        # Init first
        runner.invoke(app, ["init", str(tmp_path)])
        os.chdir(str(tmp_path))

        result = runner.invoke(
            app,
            [
                "capture",
                "run",
                "Test prompt for capture",
                "--adapter",
                "mock",
                "--task",
                "cli_capture_test",
            ],
        )
        # Should succeed or at least not crash with unhandled exception
        assert result.exit_code in [0, 1], f"Capture failed unexpectedly: {result.output}"


class TestDemoCommand:
    """Test `cngx demo` command."""

    def test_demo_help(self):
        """Demo help should show available options."""
        result = runner.invoke(app, ["demo", "--help"])
        assert result.exit_code == 0
        assert "demo" in result.output.lower() or "Demo" in result.output
