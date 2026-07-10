"""Tests for cngx.enforcement module."""

import json
from pathlib import Path

import pytest


class TestEnforcementGate:
    def test_all_pass(self):
        from cngx.enforcement import EnforcementConfig, EnforcementGate

        gate = EnforcementGate(EnforcementConfig())
        result = gate.run(
            contract_results=[{"passed": True}, {"passed": True}],
            drift_score=0.1,
            benchmark_accuracy=0.95,
            stability_score=0.85,
        )
        assert result.passed
        assert result.exit_code == 0

    def test_contract_violation_fails(self):
        from cngx.enforcement import EnforcementConfig, EnforcementGate

        gate = EnforcementGate(EnforcementConfig())
        result = gate.run(
            contract_results=[
                {"passed": True},
                {"passed": False, "violation": "depth_too_low"},
            ],
        )
        assert not result.passed
        assert result.exit_code == 1

    def test_drift_exceeds_threshold(self):
        from cngx.enforcement import EnforcementConfig, EnforcementGate

        config = EnforcementConfig(drift_threshold=0.3)
        gate = EnforcementGate(config)
        result = gate.run(drift_score=0.5)
        assert not result.passed
        assert result.exit_code == 1

    def test_accuracy_below_threshold(self):
        from cngx.enforcement import EnforcementConfig, EnforcementGate

        config = EnforcementConfig(accuracy_threshold=0.8)
        gate = EnforcementGate(config)
        result = gate.run(benchmark_accuracy=0.6)
        assert not result.passed
        assert result.exit_code == 1

    def test_stability_warning(self):
        from cngx.enforcement import EnforcementConfig, EnforcementGate

        config = EnforcementConfig(stability_threshold=0.7)
        gate = EnforcementGate(config)
        result = gate.run(stability_score=0.5)
        # Stability is warning severity, not error
        assert result.passed  # Doesn't block
        assert result.exit_code == 3  # WARN

    def test_advisory_mode_never_fails(self):
        from cngx.enforcement import EnforcementConfig, EnforcementGate

        config = EnforcementConfig(mode="advisory")
        gate = EnforcementGate(config)
        result = gate.run(
            contract_results=[{"passed": False}],
            drift_score=0.9,
            benchmark_accuracy=0.1,
        )
        assert result.passed  # Advisory never blocks
        assert result.exit_code in (0, 3)

    def test_no_data_warns(self):
        from cngx.enforcement import EnforcementConfig, EnforcementGate

        gate = EnforcementGate(EnforcementConfig())
        result = gate.run()
        assert result.passed
        assert result.exit_code == 3  # WARN - no checks

    def test_latency_check(self):
        from cngx.enforcement import EnforcementConfig, EnforcementGate

        config = EnforcementConfig(max_latency_ms=1000)
        gate = EnforcementGate(config)
        result = gate.run(latency_ms=2000)
        # Latency is warning severity
        assert result.exit_code == 3

    def test_format_text(self):
        from cngx.enforcement import EnforcementConfig, EnforcementGate

        gate = EnforcementGate(EnforcementConfig())
        result = gate.run(drift_score=0.1)
        text = result.format_text()
        assert "CNGX ENFORCEMENT GATE" in text
        assert "PASS" in text

    def test_to_json(self):
        from cngx.enforcement import EnforcementConfig, EnforcementGate

        gate = EnforcementGate(EnforcementConfig())
        result = gate.run(drift_score=0.1)
        j = result.to_json()
        parsed = json.loads(j)
        assert "exit_code" in parsed
        assert "passed" in parsed
        assert "checks" in parsed

    def test_multiple_failures(self):
        from cngx.enforcement import EnforcementConfig, EnforcementGate

        config = EnforcementConfig(
            drift_threshold=0.3,
            accuracy_threshold=0.8,
        )
        gate = EnforcementGate(config)
        result = gate.run(
            drift_score=0.5,
            benchmark_accuracy=0.3,
        )
        assert not result.passed
        assert result.exit_code == 1
        failed_checks = [c for c in result.checks if not c.passed]
        assert len(failed_checks) == 2

    def test_consensus_check(self):
        from cngx.enforcement import EnforcementConfig, EnforcementGate

        config = EnforcementConfig(require_consensus=True)
        gate = EnforcementGate(config)
        result = gate.run(consensus_score=0.3)
        # Consensus is warning severity
        assert result.exit_code == 3


class TestGitHubActionGenerator:
    def test_generate_yaml(self):
        from cngx.enforcement import GitHubActionGenerator

        yaml = GitHubActionGenerator.generate()
        assert "cngx agent gate" in yaml
        assert "actions/checkout@v4" in yaml
        assert "aadi-joshi/cngx@" in yaml
        assert "output-file:" in yaml

    def test_custom_config(self):
        from cngx.enforcement import GitHubActionGenerator

        yaml = GitHubActionGenerator.generate(
            python_version="3.12",
            policy_file="policies/strict.yaml",
            output_file="out.txt",
            evidence_file="pytest.log",
            cngx_version="0.1.7",
        )
        assert "3.12" in yaml
        assert "policies/strict.yaml" in yaml
        assert "out.txt" in yaml
        assert "pytest.log" in yaml
        assert "0.1.7" in yaml

    def test_save(self, tmp_path):
        from cngx.enforcement import GitHubActionGenerator

        path = GitHubActionGenerator.save(
            output_path=str(tmp_path / ".github" / "workflows" / "test.yml"),
        )
        assert Path(path).exists()

    def test_disable_benchmark(self):
        from cngx.enforcement import GitHubActionGenerator

        yaml = GitHubActionGenerator.generate(run_benchmark=False)
        assert "cngx benchmark" not in yaml
        assert "Consensus" not in yaml

    def test_enable_consensus_ignored(self):
        from cngx.enforcement import GitHubActionGenerator

        # Deferred SaaS commands must not appear even if requested.
        yaml = GitHubActionGenerator.generate(run_consensus=True)
        assert "cngx consensus" not in yaml
        assert "output-file:" in yaml
