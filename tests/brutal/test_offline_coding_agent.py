"""Brutal tests for offline coding-agent policy gate."""

from pathlib import Path

import pytest
from typer.testing import CliRunner

from cngx.capture.trace_builder import build_trace_from_text
from cngx.cli.main import app
from cngx.contracts import DeploymentGate
from cngx.fingerprint.extractor import FingerprintExtractor
from cngx.system_demo.scenarios import CodingAgentFixScenario

ROOT = Path(__file__).resolve().parents[2]
POLICY = ROOT / "examples" / "contracts" / "coding_agent_verification.yaml"
SHALLOW = ROOT / "tests" / "fixtures" / "agent_outputs" / "unverified_patch.txt"

runner = CliRunner()


@pytest.fixture
def scenario():
    return CodingAgentFixScenario.get_scenario()


class TestOfflineCodingAgentGate:
    def test_policy_file_exists(self):
        assert (
            POLICY.is_file()
        ), "examples/contracts/coding_agent_verification.yaml must be committed"

    def test_shallow_fixture_blocks_via_extractor(self, scenario):
        output = SHALLOW.read_text(encoding="utf-8")
        trace = build_trace_from_text(
            prompt=scenario.problem,
            output=output,
            task_id="coding_agent_fix",
        )
        fp = FingerprintExtractor().extract(trace)
        result = DeploymentGate().check(fp, scenario.contract, trace)
        assert result.blocked
        assert result.exit_code == 1
        assert fp.verification_steps == 0

    def test_cli_offline_blocks_shallow_fixture(self):
        result = runner.invoke(
            app,
            [
                "check",
                "-c",
                str(POLICY),
                "-p",
                "Fix the pagination bug and run tests before merge",
                "--output-file",
                str(SHALLOW),
            ],
        )
        assert result.exit_code == 1
        assert "BLOCKED" in result.stdout or "BLOCKED" in result.stderr

    def test_quickstart_runs_real_tests_and_gates(self, tmp_path):
        """Quickstart must block the false claim by running real tests, then pass a real fix."""
        from cngx.cli.quickstart_cmd import _MODULE_BUGGY, _MODULE_FIXED, _TESTS, _run

        (tmp_path / "cart.py").write_text(_MODULE_BUGGY, encoding="utf-8")
        (tmp_path / "test_cart.py").write_text(_TESTS, encoding="utf-8")
        verdict, _ = _run(tmp_path)
        assert verdict.blocked

        (tmp_path / "cart.py").write_text(_MODULE_FIXED, encoding="utf-8")
        verdict_fixed, _ = _run(tmp_path)
        assert verdict_fixed.verified
