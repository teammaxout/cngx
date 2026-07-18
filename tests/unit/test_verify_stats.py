"""Tests for verify-outcome recording and fabricated-claim stats (issue #43)."""

import tempfile
from pathlib import Path

from cngx.storage.database import Database
from cngx.verify.stats import compute_stats, is_fabricated


def _outcome(claimed_success, status, timed_out):
    return {"claimed_success": claimed_success, "status": status, "timed_out": timed_out}


class TestIsFabricated:
    """fabricated = claimed_success AND status == 'blocked' AND NOT timed_out."""

    def test_claimed_success_and_blocked_is_fabricated(self):
        assert is_fabricated(_outcome(True, "blocked", False)) is True

    def test_timeout_is_not_fabricated(self):
        assert is_fabricated(_outcome(True, "blocked", True)) is False

    def test_verified_is_not_fabricated(self):
        assert is_fabricated(_outcome(True, "verified", False)) is False

    def test_no_success_claim_is_not_fabricated(self):
        # e.g. a --require-claim block where the agent never claimed success
        assert is_fabricated(_outcome(False, "blocked", False)) is False


class TestComputeStats:
    def test_rate_denominator_is_success_claims_not_total_runs(self):
        outcomes = [
            _outcome(True, "blocked", False),  # fabricated, counts in denominator
            _outcome(True, "verified", False),  # success claim, not fabricated
            _outcome(False, "blocked", False),  # no claim -> excluded from denominator
        ]
        for o in outcomes:
            o["label"] = "m"
        stats = compute_stats(outcomes)
        m = stats.labels[0]
        assert m.runs == 3
        assert m.success_claims == 2  # excludes the no-claim run
        assert m.fabricated == 1
        assert m.fabricated_rate == 0.5  # 1 / 2, not 1 / 3

    def test_no_success_claims_gives_none_rate(self):
        outcomes = [{"label": "m", **_outcome(False, "blocked", False)}]
        m = compute_stats(outcomes).labels[0]
        assert m.success_claims == 0
        assert m.fabricated_rate is None

    def test_unlabeled_bucket_sorts_last(self):
        outcomes = [
            {"label": "", **_outcome(True, "blocked", False)},
            {"label": "claude", **_outcome(True, "blocked", False)},
        ]
        labels = [ls.label for ls in compute_stats(outcomes).labels]
        assert labels[-1] == ""

    def test_trend_last_n_vs_prior_n(self):
        # 25 success-claim runs: first 12 fabricated, rest clean -> improving trend.
        outcomes = []
        for i in range(25):
            fab = i < 12
            outcomes.append(
                {"label": "m", **_outcome(True, "blocked" if fab else "verified", False)}
            )
        m = compute_stats(outcomes, trend_window=10).labels[0]
        assert m.recent_rate is not None and m.prior_rate is not None
        assert m.prior_rate > m.recent_rate  # got better over time

    def test_empty_outcomes(self):
        stats = compute_stats([])
        assert stats.total_runs == 0
        assert stats.labels == []


class TestRecordAndRead:
    def _db(self):
        return Database(Path(tempfile.mkdtemp()) / "test.db")

    def test_record_then_read_round_trip(self):
        db = self._db()
        db.record_verify_outcome(
            label="gpt-4o",
            claimed_success=True,
            real_ok=False,
            status="blocked",
            timed_out=False,
            claimed_passed=12,
            real_passed=9,
            real_failed=3,
            framework="pytest",
        )
        outcomes = db.get_verify_outcomes()
        assert len(outcomes) == 1
        o = outcomes[0]
        assert o["label"] == "gpt-4o"
        assert o["claimed_success"] is True
        assert o["real_ok"] is False
        assert o["status"] == "blocked"
        assert o["timed_out"] is False
        assert o["claimed_passed"] == 12
        assert o["real_passed"] == 9
        assert o["real_failed"] == 3
        assert o["framework"] == "pytest"
        db.close()

    def test_stored_columns_contain_no_claim_text_or_command(self):
        db = self._db()
        db.record_verify_outcome(
            label="m",
            claimed_success=True,
            real_ok=True,
            status="verified",
            timed_out=False,
        )
        cols = set(db.get_verify_outcomes()[0].keys())
        # None of the privacy-sensitive fields should ever be persisted.
        for forbidden in ("claim", "command", "stdout", "output", "path", "reasons", "receipt"):
            assert forbidden not in cols
        db.close()

    def test_empty_label_stored_as_empty_string(self):
        db = self._db()
        db.record_verify_outcome(
            label="",
            claimed_success=True,
            real_ok=False,
            status="blocked",
            timed_out=False,
        )
        assert db.get_verify_outcomes()[0]["label"] == ""
        db.close()

    def test_outcomes_returned_oldest_first(self):
        db = self._db()
        for i in range(3):
            db.record_verify_outcome(
                label=f"m{i}",
                claimed_success=True,
                real_ok=True,
                status="verified",
                timed_out=False,
            )
        labels = [o["label"] for o in db.get_verify_outcomes()]
        assert labels == ["m0", "m1", "m2"]
        db.close()
