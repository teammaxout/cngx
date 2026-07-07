"""Privacy guarantees for cogscope submit payloads."""

import json
from datetime import datetime

import pytest

from cogscope.cli.submit_cmd import (
    ALLOWED_SUBMIT_KEYS,
    FORBIDDEN_SUBMIT_KEYS,
    build_submit_payload,
    validate_submit_payload,
)
from cogscope.core.models import BehavioralFingerprint


def _sample_fingerprint(**kwargs) -> BehavioralFingerprint:
    defaults = dict(
        trace_id="local-trace-should-never-appear",
        task_id="secret-customer-pipeline",
        timestamp=datetime(2026, 1, 10, 12, 0, 0),
        model="gpt-4o-mini",
        depth=4,
        branching_factor=0.2,
        total_steps=5,
        verification_steps=2,
        hedging_ratio=0.1,
        correction_count=1,
        uncertainty_markers=2,
        output_length=400,
        reasoning_length=900,
        metadata={"prompt": "this must not leak", "output": "secret answer text"},
    )
    defaults.update(kwargs)
    return BehavioralFingerprint(**defaults)


class TestSubmitPrivacy:
    def test_payload_contains_only_allowed_keys(self):
        fp = _sample_fingerprint()
        payload = build_submit_payload(fp, baseline_label="my-baseline", drift_score=0.22)
        assert set(payload.keys()) <= ALLOWED_SUBMIT_KEYS
        validate_submit_payload(payload)

    def test_payload_excludes_trace_and_task_ids(self):
        fp = _sample_fingerprint()
        payload = build_submit_payload(fp, baseline_label="baseline", drift_score=0.1)
        blob = json.dumps(payload)
        assert "local-trace" not in blob
        assert "secret-customer" not in blob
        assert "prompt" not in blob
        assert "secret answer" not in blob

    def test_fingerprint_metadata_not_included(self):
        fp = _sample_fingerprint(metadata={"prompt": "Solve 2+2", "output": "4"})
        payload = build_submit_payload(fp, baseline_label="b", drift_score=0.0)
        assert "metadata" not in payload
        validate_submit_payload(payload)

    def test_injected_free_text_rejected(self):
        fp = _sample_fingerprint()
        payload = build_submit_payload(fp, baseline_label="b", drift_score=0.1)
        payload["prompt"] = "user secret prompt"
        with pytest.raises(ValueError, match="Disallowed keys"):
            validate_submit_payload(payload)

    def test_injected_output_field_rejected(self):
        fp = _sample_fingerprint()
        payload = build_submit_payload(fp, baseline_label="b", drift_score=0.1)
        payload["output"] = "The answer is 42 with long reasoning..."
        with pytest.raises(ValueError, match="Disallowed keys"):
            validate_submit_payload(payload)

    def test_serialized_forbidden_key_rejected(self):
        payload = {
            "schema_version": 1,
            "record_id": "abc",
            "timestamp": "2026-01-01T00:00:00Z",
            "model": "m",
            "baseline_label": "b",
            "drift_score": 0.1,
            "depth": 1,
            "verification_steps": 0,
            "hedging_ratio": 0.0,
            "branching_factor": 0.0,
            "total_steps": 1,
            "correction_count": 0,
            "uncertainty_markers": 0,
            "output_length": 10,
            "reasoning_length": 10,
        }
        validate_submit_payload(payload)
        payload["reasoning"] = "hidden chain of thought"
        with pytest.raises(ValueError):
            validate_submit_payload(payload)

    def test_no_forbidden_keys_in_allowed_set(self):
        assert not (ALLOWED_SUBMIT_KEYS & FORBIDDEN_SUBMIT_KEYS)
