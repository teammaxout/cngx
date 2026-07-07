"""Tests for session trajectory collapse detection."""

from __future__ import annotations

import pytest

from cogscope.drift.trajectory import (
    DEFAULT_MIN_TURNS,
    TrajectoryCollapseConfig,
    detect_verification_collapse,
    evaluate_collapse_at_turn,
    verification_health_label,
)


def _healthy_verification_series(n: int) -> list[int]:
    pattern = [3, 4, 5, 3, 4, 5, 4, 3, 5, 4]
    return [pattern[i % len(pattern)] for i in range(n)]


def _collapsing_verification_series(
    healthy_turns: int = 12,
    collapsed_value: int = 0,
    total: int = 35,
) -> list[int]:
    healthy = _healthy_verification_series(healthy_turns)
    collapsed = [collapsed_value] * (total - healthy_turns)
    return healthy + collapsed


class TestTrajectoryCollapse:
    def test_healthy_session_no_warning(self):
        series = _healthy_verification_series(30)
        result = detect_verification_collapse(series)
        print(
            f"\nHealthy session: turns={result.turn_count}, "
            f"recent_var={result.recent_variance:.3f}, detected={result.collapse_detected}"
        )
        assert not result.collapse_detected
        assert verification_health_label(series) == "varied"

    def test_collapsing_session_detected_with_reasonable_delay(self):
        series = _collapsing_verification_series(healthy_turns=12, collapsed_value=0, total=35)
        collapse_start_turn = 13
        result = detect_verification_collapse(series)
        print(
            f"\nCollapsing session: first_warning_turn={result.first_warning_turn}, "
            f"recent_var={result.recent_variance:.3f}, "
            f"recent_mean={result.recent_mean_verification:.2f}"
        )
        assert result.collapse_detected
        assert result.first_warning_turn is not None
        assert result.first_warning_turn >= DEFAULT_MIN_TURNS
        delay = result.first_warning_turn - collapse_start_turn
        print(f"Detection delay after collapse start: {delay} turns")
        assert delay <= 12, "Should not require the entire rest of the session"

    def test_evaluate_collapse_rule_is_concrete(self):
        cfg = TrajectoryCollapseConfig()
        healthy_prefix = _healthy_verification_series(cfg.min_turns)
        assert not evaluate_collapse_at_turn(healthy_prefix, cfg.min_turns, cfg)

        collapsing = _collapsing_verification_series(12, 0, 30)
        assert evaluate_collapse_at_turn(collapsing, 22, cfg)
