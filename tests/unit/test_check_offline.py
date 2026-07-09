"""Unit tests for offline cngx check (no API keys, no adapter calls)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from cngx.capture.tracer import CngxTracer
from cngx.cli.check_cmd import run_offline_check, run_policy_check
from cngx.cli.main import app

ROOT = Path(__file__).resolve().parents[2]
BASIC_POLICY = ROOT / "examples/contracts/basic_reasoning.yaml"
CODING_POLICY = ROOT / "examples/contracts/coding_agent_fix.yaml"
GOOD_OUTPUT = ROOT / "tests/fixtures/offline_good_output.txt"
BAD_OUTPUT = ROOT / "tests/fixtures/shallow_agent_output.txt"

runner = CliRunner()


class TestIngestOutput:
    def test_ingest_builds_offline_trace(self):
        trace, fp = CngxTracer.ingest_output(
            "Step 1: run pytest. Step 2: all tests passed. Verified.",
            prompt="Fix the bug",
            task_id="ci_check",
        )
        assert trace.adapter_type == "offline"
        assert trace.model == "agent-output"
        assert fp.trace_id == trace.id
        assert fp.verification_steps >= 1

    def test_ingest_never_calls_capture(self):
        with patch.object(CngxTracer, "capture", side_effect=AssertionError("capture called")):
            trace, fp = CngxTracer.ingest_output("Short answer here for testing purposes.")
        assert trace.id
        assert fp.trace_id == trace.id


class TestRunOfflineCheck:
    def test_good_output_passes_lenient_policy(self):
        if not GOOD_OUTPUT.is_file():
            pytest.skip("fixture missing")
        output = GOOD_OUTPUT.read_text(encoding="utf-8")
        code = run_offline_check(
            prompt="What is 15 * 7? Show your reasoning.",
            output=output,
            policy=BASIC_POLICY,
        )
        assert code in (0, 2)

    def test_shallow_patch_blocked(self):
        if not BAD_OUTPUT.is_file() or not CODING_POLICY.is_file():
            pytest.skip("fixtures missing")
        output = BAD_OUTPUT.read_text(encoding="utf-8")
        code = run_offline_check(
            prompt="Fix pagination and run tests",
            output=output,
            policy=CODING_POLICY,
        )
        assert code == 1

    def test_offline_path_never_instantiates_live_adapters(self):
        with (
            patch("cngx.capture.tracer.OpenAIAdapter", create=True) as openai_cls,
            patch("cngx.capture.tracer._get_adapter_class") as get_adapter,
        ):
            get_adapter.side_effect = AssertionError("adapter resolved")
            openai_cls.side_effect = AssertionError("openai adapter imported")
            code = run_policy_check(
                policy=BASIC_POLICY,
                prompt="context",
                output_file=GOOD_OUTPUT,
            )
        assert code in (0, 2)


class TestCheckOfflineCli:
    def test_output_file_passes_lenient_policy(self):
        result = runner.invoke(
            app,
            [
                "check",
                "-c",
                str(BASIC_POLICY),
                "-p",
                "What is 15 * 7?",
                "--output-file",
                str(GOOD_OUTPUT),
            ],
        )
        assert result.exit_code in (0, 2)

    def test_output_file_blocks_unverified_agent(self):
        result = runner.invoke(
            app,
            [
                "check",
                "-c",
                str(CODING_POLICY),
                "-p",
                "Fix pagination and run tests",
                "--output-file",
                str(BAD_OUTPUT),
            ],
        )
        assert result.exit_code == 1

    def test_stdin_blocks_unverified_agent(self):
        bad = BAD_OUTPUT.read_text(encoding="utf-8")
        result = runner.invoke(
            app,
            [
                "check",
                "-c",
                str(CODING_POLICY),
                "-p",
                "Fix pagination",
                "--stdin",
            ],
            input=bad,
        )
        assert result.exit_code == 1

    def test_online_mock_capture_unchanged(self):
        with patch.object(CngxTracer, "capture") as capture_mock:
            capture_mock.return_value = MagicMock(id="t1")
            with patch.object(CngxTracer, "get_fingerprint", return_value=None):
                result = runner.invoke(
                    app,
                    [
                        "check",
                        "-c",
                        str(BASIC_POLICY),
                        "Step 1: think. Step 2: answer.",
                        "--adapter",
                        "mock",
                    ],
                )
            capture_mock.assert_called_once()
        assert result.exit_code == 2

    def test_output_file_and_stdin_mutually_exclusive(self):
        result = runner.invoke(
            app,
            [
                "check",
                "-c",
                str(BASIC_POLICY),
                "--output-file",
                str(GOOD_OUTPUT),
                "--stdin",
            ],
        )
        assert result.exit_code == 2

    def test_json_uses_ci_output_shape(self):
        result = runner.invoke(
            app,
            [
                "check",
                "-c",
                str(CODING_POLICY),
                "-p",
                "Fix",
                "--output-file",
                str(BAD_OUTPUT),
                "--json",
            ],
        )
        import json

        data = json.loads(result.stdout)
        assert "passed" in data
        assert "exit_code" in data
        assert "violations" in data
