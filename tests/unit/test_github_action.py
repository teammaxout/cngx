"""Tests for the reusable GitHub Action (action.yml)."""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
ACTION_YML = ROOT / "action.yml"


def test_action_yml_exists_and_has_required_inputs():
    assert ACTION_YML.is_file(), "action.yml must exist at repository root"
    data = yaml.safe_load(ACTION_YML.read_text(encoding="utf-8"))
    assert data["runs"]["using"] == "composite"
    inputs = data["inputs"]
    assert "policy" in inputs and inputs["policy"]["required"] is True
    assert "prompt" in inputs
    assert "prompt-file" in inputs
    assert "output-file" in inputs
    assert data["inputs"]["install-mode"]["default"] == "pypi"


def test_github_action_local_smoke():
    """Run scripts/test_github_action_local.py (same logic as action.yml)."""
    import subprocess
    import sys

    script = ROOT / "scripts" / "test_github_action_local.py"
    result = subprocess.run(
        [sys.executable, str(script)],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
