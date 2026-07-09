"""CLI tests for cngx check offline mode."""

from pathlib import Path

from typer.testing import CliRunner

from cngx.cli.main import app

runner = CliRunner()

ROOT = Path(__file__).resolve().parents[2]
SHALLOW_OUTPUT = (
    "Patch: use items[(page - 1) * size : page * size] for 1-based pages. " "Ready to merge."
)
CODING_POLICY = ROOT / "examples/contracts/coding_agent_fix.yaml"


class TestCheckOfflineCli:
    def test_output_file_blocks_shallow_patch(self, tmp_path):
        output_file = tmp_path / "agent.txt"
        output_file.write_text(SHALLOW_OUTPUT, encoding="utf-8")
        result = runner.invoke(
            app,
            [
                "check",
                "-c",
                str(CODING_POLICY),
                "-p",
                "Fix pagination bug",
                "--output-file",
                str(output_file),
            ],
        )
        assert result.exit_code == 1

    def test_stdin_blocks_shallow_patch(self):
        result = runner.invoke(
            app,
            [
                "check",
                "-c",
                str(CODING_POLICY),
                "-p",
                "Fix bug",
                "--stdin",
            ],
            input=SHALLOW_OUTPUT,
        )
        assert result.exit_code == 1

    def test_online_mode_still_works(self, tmp_path):
        policy = tmp_path / "basic.yaml"
        policy.write_text(
            (ROOT / "examples/contracts/basic_reasoning.yaml").read_text(),
            encoding="utf-8",
        )
        result = runner.invoke(
            app,
            [
                "check",
                "-c",
                str(policy),
                "Step 1: think. Step 2: answer 4. Verified.",
                "--adapter",
                "mock",
            ],
        )
        assert result.exit_code in (0, 2)

    def test_prompt_file_context(self, tmp_path):
        prompt_file = tmp_path / "task.txt"
        prompt_file.write_text("Fix pagination and run tests", encoding="utf-8")
        output_file = tmp_path / "agent.txt"
        output_file.write_text(SHALLOW_OUTPUT, encoding="utf-8")
        result = runner.invoke(
            app,
            [
                "check",
                "-c",
                str(CODING_POLICY),
                "--prompt-file",
                str(prompt_file),
                "--output-file",
                str(output_file),
            ],
        )
        assert result.exit_code == 1
