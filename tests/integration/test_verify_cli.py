"""End-to-end verify: run a real process and gate on the true result."""

import os
import sys
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
