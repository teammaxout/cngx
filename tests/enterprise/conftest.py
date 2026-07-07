"""
Enterprise Test Suite — Shared Configuration & Fixtures

Mock-based fixtures for integration tests. Live LLM API tests were removed
in the oss-launch hardening pass — unit tests cover adapter behavior with mock.
"""

import asyncio
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import pytest

from cogscope.capture.tracer import CogscopeTracer
from cogscope.contracts.schema import BehaviorContract
from cogscope.contracts.validator import ContractValidator
from cogscope.core.models import BehavioralFingerprint, ReasoningTrace, TokenUsage
from cogscope.diff.engine import DiffEngine
from cogscope.drift.detector import DriftDetector
from cogscope.fingerprint.extractor import FingerprintExtractor
from cogscope.storage.database import Database, reset_database


@pytest.fixture()
def tmp_db(tmp_path):
    """Per-test temporary DuckDB database."""
    db_path = tmp_path / "enterprise_test.duckdb"
    db = Database(db_path)
    yield db
    db.close()


@pytest.fixture(scope="session")
def session_db(tmp_path_factory):
    """Session-scoped database for cross-test data sharing."""
    db_path = tmp_path_factory.mktemp("enterprise") / "session.duckdb"
    db = Database(db_path)
    yield db
    db.close()


@pytest.fixture()
def extractor():
    return FingerprintExtractor()


@pytest.fixture()
def validator():
    return ContractValidator()


@pytest.fixture()
def diff_engine():
    return DiffEngine()


@pytest.fixture()
def mock_tracer():
    """Tracer using mock adapter — no API keys required."""
    return CogscopeTracer(adapter="mock", model="mock-model", auto_fingerprint=True)


MATH_CONTRACT_YAML = """
name: enterprise_math
version: "1.0.0"
description: "Mathematical correctness contract"
domain: math
intent: "Verify math reasoning"
depth:
  min: 1
  max: 50
  severity: fail
steps:
  min: 1
  max: 100
  severity: fail
uncertainty:
  max_hedging_ratio: 0.6
  severity: warn
output:
  min_length: 5
  max_length: 50000
  severity: fail
forbidden_patterns:
  - pattern: "I don't know"
    description: "Model must attempt an answer"
    severity: fail
"""

CODE_CONTRACT_YAML = """
name: enterprise_code
version: "1.0.0"
description: "Code correctness contract"
domain: code
intent: "Ensure code generation has structure and verification"
depth:
  min: 1
  max: 50
  severity: fail
steps:
  min: 1
  max: 100
  severity: fail
output:
  min_length: 20
  max_length: 100000
  severity: fail
forbidden_patterns:
  - pattern: "TODO|FIXME|HACK"
    description: "No placeholder code"
    severity: warn
"""

RESEARCH_CONTRACT_YAML = """
name: enterprise_research
version: "1.0.0"
description: "Research quality contract"
domain: research
intent: "Ensure thorough research reasoning"
depth:
  min: 1
  max: 60
  severity: fail
steps:
  min: 1
  max: 150
  severity: fail
output:
  min_length: 50
  max_length: 100000
  severity: fail
uncertainty:
  max_hedging_ratio: 0.5
  severity: warn
"""

SAFETY_CRITICAL_CONTRACT_YAML = """
name: enterprise_safety_critical
version: "1.0.0"
description: "Safety-critical reasoning contract"
domain: safety_critical
intent: "Maximum verification for high-stakes decisions"
depth:
  min: 1
  max: 100
  severity: fail
steps:
  min: 1
  max: 200
  severity: fail
uncertainty:
  max_hedging_ratio: 0.2
  max_uncertainty_markers: 3
  severity: fail
output:
  min_length: 20
  max_length: 100000
  severity: fail
forbidden_patterns:
  - pattern: "I guess"
    description: "No guessing in safety-critical outputs"
    severity: fail
block_on_violation: true
"""


def load_contract(yaml_str: str) -> BehaviorContract:
    """Parse a YAML string into a BehaviorContract."""
    import yaml

    data = yaml.safe_load(yaml_str)
    return BehaviorContract(**data)


def run_async(coro):
    """Run an async coroutine from sync test code."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor() as pool:
                return pool.submit(asyncio.run, coro).result(timeout=120)
    except RuntimeError:
        pass
    return asyncio.run(coro)


def repo_root() -> Path:
    """Repository root (parent of tests/)."""
    return Path(__file__).resolve().parents[2]
