"""Unit tests for offline policy check (no LLM adapter)."""

from pathlib import Path

import pytest

from cngx.capture.trace_builder import build_trace_from_text
from cngx.cli.check_cmd import run_offline_check
from cngx.contracts import DeploymentGate
from cngx.fingerprint.extractor import FingerprintExtractor
from cngx.system_demo.scenarios import CodingAgentFixScenario

POLICY_PATH = Path(__file__).resolve().parents[2] / "examples/contracts/basic_reasoning.yaml"

SHALLOW_AGENT_OUTPUT = (
    "Patch: use items[(page - 1) * size : page * size] for 1-based pages. " "Ready to merge."
)

VERIFIED_AGENT_OUTPUT = (
    "1. Reproduced the failing test for page 1 pagination.\n"
    "2. Updated slice logic to items[(page - 1) * size : page * size].\n"
    "3. Ran pytest on tests/test_users.py and all 12 tests passed.\n"
    "4. Summary: fix verified, safe to merge."
)


class TestBuildTraceFromText:
    def test_builds_trace_without_adapter(self):
        trace = build_trace_from_text(
            prompt="Fix the bug",
            output="Done.",
            task_id="coding_fix",
            model="agent-output",
        )
        assert trace.output == "Done."
        assert trace.prompt == "Fix the bug"
        assert trace.adapter_type == "offline"
        assert trace.model == "agent-output"
        assert trace.task_id == "coding_fix"
        assert trace.id

    def test_reasoning_content_preserved(self):
        trace = build_trace_from_text(
            prompt="Fix",
            output="Patch applied.",
            reasoning_content="First I read the test failure.",
        )
        assert trace.reasoning_content == "First I read the test failure."


class TestOfflineFingerprintAndGate:
    def setup_method(self):
        self.scenario = CodingAgentFixScenario.get_scenario()
        self.extractor = FingerprintExtractor()
        self.gate = DeploymentGate()

    def _check_output(self, output: str, prompt: str | None = None):
        trace = build_trace_from_text(
            prompt=prompt or self.scenario.problem,
            output=output,
            task_id="coding_agent_fix",
        )
        fp = self.extractor.extract(trace)
        return self.gate.check(fp, self.scenario.contract, trace)

    def test_shallow_patch_blocked(self):
        result = self._check_output(SHALLOW_AGENT_OUTPUT)
        assert result.blocked
        assert result.exit_code == 1

    def test_verified_patch_passes_or_soft_fails(self):
        result = self._check_output(VERIFIED_AGENT_OUTPUT)
        assert not result.blocked
        assert result.exit_code != 1

    def test_zero_verification_steps_on_shallow(self):
        trace = build_trace_from_text(
            prompt=self.scenario.problem,
            output=SHALLOW_AGENT_OUTPUT,
        )
        fp = self.extractor.extract(trace)
        assert fp.verification_steps == 0


class TestRunOfflineCheck:
    def test_shallow_agent_exit_code_blocked(self, tmp_path):
        contract = CodingAgentFixScenario.get_scenario().contract
        policy = tmp_path / "policy.yaml"
        policy.write_text(contract.to_yaml(), encoding="utf-8")

        code = run_offline_check(
            prompt="Fix pagination",
            output=SHALLOW_AGENT_OUTPUT,
            policy=policy,
        )
        assert code == 1

    def test_run_offline_check_with_yaml_policy(self):
        if not POLICY_PATH.exists():
            pytest.skip("basic_reasoning.yaml not found")
        code = run_offline_check(
            prompt="What is 15 * 7? Show your reasoning step by step.",
            output=(
                "Step 1: 15 * 7 means fifteen groups of seven.\n"
                "Step 2: 10 * 7 = 70 and 5 * 7 = 35.\n"
                "Step 3: 70 + 35 = 105.\n"
                "Let me verify: 105 / 15 = 7. Confirmed."
            ),
            policy=POLICY_PATH,
        )
        assert code in (0, 2)

    def test_json_output_uses_ci_shape(self, tmp_path, capsys):
        contract = CodingAgentFixScenario.get_scenario().contract
        policy = tmp_path / "policy.yaml"
        policy.write_text(contract.to_yaml(), encoding="utf-8")

        run_offline_check(
            prompt="Fix",
            output=SHALLOW_AGENT_OUTPUT,
            policy=policy,
            json_output=True,
        )
        captured = capsys.readouterr()
        import json

        data = json.loads(captured.out)
        assert "exit_code" in data
        assert "passed" in data
        assert data["exit_code"] == 1
