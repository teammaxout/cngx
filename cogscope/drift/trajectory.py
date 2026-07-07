"""Session-level trajectory analysis for multi-turn agent sessions.

Detects verification-behavior *collapse* across a session: when rolling variance
of verification_steps falls toward zero while the session previously showed
varied verification. This is distinct from single-turn structural drift alerts.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

# Documented, testable collapse rule parameters
DEFAULT_MIN_TURNS = 20
DEFAULT_BASELINE_WINDOW = 10
DEFAULT_RECENT_WINDOW = 10
DEFAULT_BASELINE_MIN_VARIANCE = 0.5
DEFAULT_BASELINE_MIN_MEAN = 2.0
DEFAULT_COLLAPSE_MAX_VARIANCE = 0.15
DEFAULT_COLLAPSE_MAX_MEAN = 1.0
DEFAULT_COLLAPSE_MAX_UNIQUE = 2


@dataclass(frozen=True)
class TrajectoryCollapseConfig:
    """Concrete thresholds for session verification collapse detection."""

    min_turns: int = DEFAULT_MIN_TURNS
    baseline_window: int = DEFAULT_BASELINE_WINDOW
    recent_window: int = DEFAULT_RECENT_WINDOW
    baseline_min_variance: float = DEFAULT_BASELINE_MIN_VARIANCE
    baseline_min_mean: float = DEFAULT_BASELINE_MIN_MEAN
    collapse_max_variance: float = DEFAULT_COLLAPSE_MAX_VARIANCE
    collapse_max_mean: float = DEFAULT_COLLAPSE_MAX_MEAN
    collapse_max_unique: int = DEFAULT_COLLAPSE_MAX_UNIQUE


@dataclass
class TrajectoryCollapseResult:
    """Outcome of session trajectory collapse check."""

    collapse_detected: bool
    turn_count: int
    first_warning_turn: int | None = None
    baseline_variance: float = 0.0
    recent_variance: float = 0.0
    baseline_mean_verification: float = 0.0
    recent_mean_verification: float = 0.0
    recent_unique_values: int = 0
    summary: str = ""
    verification_series: list[int] = field(default_factory=list)
    correction_series: list[int] = field(default_factory=list)


def _window_stats(values: list[float]) -> tuple[float, float, int]:
    if not values:
        return 0.0, 0.0, 0
    arr = np.asarray(values, dtype=float)
    var = float(np.var(arr, ddof=1)) if len(arr) > 1 else 0.0
    mean = float(np.mean(arr))
    unique = len(set(int(round(v)) for v in values))
    return var, mean, unique


def evaluate_collapse_at_turn(
    verification_steps: list[int],
    turn_index: int,
    config: TrajectoryCollapseConfig,
) -> bool:
    """Return True if collapse rule fires at 1-based turn_index (inclusive prefix)."""
    if turn_index < config.min_turns:
        return False
    prefix = verification_steps[:turn_index]
    if len(prefix) < config.min_turns:
        return False

    baseline = [float(v) for v in prefix[: config.baseline_window]]
    recent = [float(v) for v in prefix[-config.recent_window :]]

    var_b, mean_b, _ = _window_stats(baseline)
    var_r, mean_r, uniq_r = _window_stats(recent)

    return (
        var_b >= config.baseline_min_variance
        and mean_b >= config.baseline_min_mean
        and var_r <= config.collapse_max_variance
        and mean_r <= config.collapse_max_mean
        and uniq_r <= config.collapse_max_unique
    )


def detect_verification_collapse(
    verification_steps: list[int],
    correction_counts: list[int] | None = None,
    config: TrajectoryCollapseConfig | None = None,
) -> TrajectoryCollapseResult:
    """Detect session-level verification collapse on a turn-ordered series.

    Rule (at turn T >= min_turns):
    - Baseline window = first ``baseline_window`` turns (typically 1-10).
    - Recent window = last ``recent_window`` turns ending at T.
    - Fire when baseline showed varied, meaningful verification but the recent
      window has collapsed to a flat, low pattern.
    """
    cfg = config or TrajectoryCollapseConfig()
    series = [int(v) for v in verification_steps]
    corrections = [int(v) for v in (correction_counts or [])]
    n = len(series)

    if n < cfg.min_turns:
        return TrajectoryCollapseResult(
            collapse_detected=False,
            turn_count=n,
            summary=(
                f"Session has {n} turn(s); need at least {cfg.min_turns} "
                "for trajectory collapse analysis."
            ),
            verification_series=series,
            correction_series=corrections,
        )

    first_warning: int | None = None
    for turn in range(cfg.min_turns, n + 1):
        if evaluate_collapse_at_turn(series, turn, cfg):
            first_warning = turn
            break

    baseline = [float(v) for v in series[: cfg.baseline_window]]
    recent = [float(v) for v in series[-cfg.recent_window :]]
    var_b, mean_b, _ = _window_stats(baseline)
    var_r, mean_r, uniq_r = _window_stats(recent)

    detected = first_warning is not None
    if detected:
        summary = (
            f"Session stability warning at turn {first_warning}: verification_steps "
            f"variance collapsed from {var_b:.2f} (baseline mean {mean_b:.1f}) "
            f"to {var_r:.2f} (recent mean {mean_r:.1f}, {uniq_r} unique values). "
            "This is a heuristic pattern check, not proof the agent failed."
        )
    else:
        summary = (
            f"Session verification trajectory healthy over {n} turns "
            f"(recent variance {var_r:.2f}, mean {mean_r:.1f})."
        )

    return TrajectoryCollapseResult(
        collapse_detected=detected,
        turn_count=n,
        first_warning_turn=first_warning,
        baseline_variance=var_b,
        recent_variance=var_r,
        baseline_mean_verification=mean_b,
        recent_mean_verification=mean_r,
        recent_unique_values=uniq_r,
        summary=summary,
        verification_series=series,
        correction_series=corrections,
    )


def verification_health_label(
    verification_steps: list[int],
    config: TrajectoryCollapseConfig | None = None,
) -> str:
    """Short label for TUI: varied, flattening, or collapsed."""
    result = detect_verification_collapse(verification_steps, config=config)
    if result.collapse_detected:
        return "collapsed"
    if result.turn_count < (config or TrajectoryCollapseConfig()).min_turns:
        return "warming up"
    if result.recent_variance <= (config or TrajectoryCollapseConfig()).collapse_max_variance * 2:
        return "flattening"
    return "varied"
