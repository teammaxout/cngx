"""Tests for coding agent policy YAML pack and offline fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from cngx.cli.check_cmd import run_offline_check
from cngx.cli.main import app
from cngx.contracts import BehaviorContract

ROOT = Path(__file__).resolve().parents[2]
STRICT_POLICY = ROOT / "examples/contracts/coding_agent_verification.yaml"
LENIENT_POLICY = ROOT / "examples/contracts/coding_agent_verification_lenient.yaml"
VERIFIED_OUTPUT = ROOT / "tests/fixtures/agent_outputs/verified_fix.txt"
UNVERIFIED_OUTPUT = ROOT / "tests/fixtures/agent_outputs/unverified_patch.txt"

runner = CliRunner()


class TestPolicyYamlLoads:
    @pytest.mark.parametrize(
        "path",
        [STRICT_POLICY, LENIENT_POLICY],
    )
    def test_policy_loads_from_yaml(self, path: Path):
        contract = BehaviorContract.from_yaml(path)
        assert contract.name
        assert contract.verification is not None
        assert contract.verification.required is True


class TestStrictCodingAgentPolicy:
    def test_unverified_patch_blocked(self):
        output = UNVERIFIED_OUTPUT.read_text(encoding="utf-8")
        code = run_offline_check(
            prompt="Fix the pagination bug and run tests before merge",
            output=output,
            policy=STRICT_POLICY,
        )
        assert code == 1

    def test_verified_fix_passes(self):
        output = VERIFIED_OUTPUT.read_text(encoding="utf-8")
        code = run_offline_check(
            prompt="Fix the pagination bug and run tests before merge",
            output=output,
            policy=STRICT_POLICY,
        )
        assert code == 0

    def test_cli_output_file_unverified_exits_blocked(self):
        result = runner.invoke(
            app,
            [
                "check",
                "-c",
                str(STRICT_POLICY),
                "-p",
                "Fix the pagination bug and run tests",
                "--output-file",
                str(UNVERIFIED_OUTPUT),
            ],
        )
        assert result.exit_code == 1

    def test_cli_output_file_verified_exits_pass(self):
        result = runner.invoke(
            app,
            [
                "check",
                "-c",
                str(STRICT_POLICY),
                "-p",
                "Fix the pagination bug and run tests",
                "--output-file",
                str(VERIFIED_OUTPUT),
            ],
        )
        assert result.exit_code == 0


class TestLenientCodingAgentPolicy:
    def test_unverified_patch_fails_soft(self):
        output = UNVERIFIED_OUTPUT.read_text(encoding="utf-8")
        code = run_offline_check(
            prompt="Fix the pagination bug",
            output=output,
            policy=LENIENT_POLICY,
        )
        assert code == 2

    def test_verified_fix_passes(self):
        output = VERIFIED_OUTPUT.read_text(encoding="utf-8")
        code = run_offline_check(
            prompt="Fix the pagination bug",
            output=output,
            policy=LENIENT_POLICY,
        )
        assert code == 0
