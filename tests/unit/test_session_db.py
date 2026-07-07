"""Database session tracking tests."""

from datetime import datetime

import pytest

from cogscope.core.models import BehavioralFingerprint, ReasoningTrace, TokenUsage
from cogscope.storage.database import Database


def _fp(
    trace_id: str, task_id: str, verification: int, correction: int = 1
) -> BehavioralFingerprint:
    return BehavioralFingerprint(
        trace_id=trace_id,
        task_id=task_id,
        timestamp=datetime.utcnow(),
        model="test",
        depth=5,
        verification_steps=verification,
        correction_count=correction,
        total_steps=5,
        output_length=100,
    )


def test_session_turn_allocation_and_query(tmp_path):
    db = Database(tmp_path / "test.db")
    session_id = "sess-abc"

    for i in range(3):
        turn = db.allocate_session_turn(session_id)
        trace = ReasoningTrace(
            id=f"t{i}",
            task_id="task1",
            timestamp=datetime.utcnow(),
            model="test",
            adapter_type="mock",
            prompt="hi",
            output="ok",
            token_usage=TokenUsage(),
        )
        db.save_trace(trace)
        fp = _fp(f"t{i}", "task1", verification=3 + i)
        db.save_fingerprint(fp, session_id=session_id, session_turn=turn)

    fps = db.get_fingerprints_by_session(session_id)
    assert len(fps) == 3
    assert [fp.metadata["session_turn"] for fp in fps] == [1, 2, 3]
    assert db.get_session_turn_count(session_id) == 3
