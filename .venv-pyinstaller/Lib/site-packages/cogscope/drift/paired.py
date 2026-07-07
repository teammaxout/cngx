"""Paired significance testing for fixed-benchmark CI regression.

McNemar's exact test (McNemar, 1947) applies to paired binary pass/fail outcomes
on identical benchmark items. For continuous or graded paired scores (heuristic
ratios, rubric grades, multi-run averages), use the paired permutation test
implemented via the holdout library (sign-flip test; generalizes the Amazon
Science LLM-Accuracy-Stats recommendation for non-binary paired data).

Why here and not on live proxy traffic:
- Both tests require paired observations on identical items across conditions.
- Live open-ended proxy traffic has no ground-truth correctness oracle per call.
- CI regression suites with fixed tasks provide the paired structure these tests need.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np
from scipy import stats

try:
    from holdout import mcnemar_exact, paired_permutation_test
except ImportError:  # pragma: no cover - holdout is a declared dependency
    mcnemar_exact = None  # type: ignore[assignment]
    paired_permutation_test = None  # type: ignore[assignment]


@dataclass
class McNemarResult:
    """Result of McNemar's test on paired binary outcomes."""

    statistic: float
    p_value: float
    n_discordant: int
    b_baseline_wrong_current_right: int
    c_baseline_right_current_wrong: int
    shift_detected: bool
    alpha: float
    summary: str

    @property
    def degradation_detected(self) -> bool:
        """Backward-compatible alias."""
        return self.shift_detected


@dataclass
class PairedContinuousResult:
    """Result of paired permutation test on continuous paired scores."""

    mean_difference: float
    p_value: float
    shift_detected: bool
    alpha: float
    summary: str
    n_pairs: int


def mcnemar_test(
    baseline_correct: Sequence[bool],
    current_correct: Sequence[bool],
    alpha: float = 0.05,
    *,
    shift_direction: str = "current_worse",
) -> McNemarResult:
    """McNemar's exact test for paired binary correctness vectors."""
    if len(baseline_correct) != len(current_correct):
        raise ValueError("baseline_correct and current_correct must have same length")
    if len(baseline_correct) < 2:
        return McNemarResult(
            statistic=0.0,
            p_value=1.0,
            n_discordant=0,
            b_baseline_wrong_current_right=0,
            c_baseline_right_current_wrong=0,
            shift_detected=False,
            alpha=alpha,
            summary="Insufficient paired items for McNemar test (need >=2).",
        )

    b = 0
    c = 0
    for bl, cl in zip(baseline_correct, current_correct):
        if not bl and cl:
            b += 1
        elif bl and not cl:
            c += 1

    n_discordant = b + c
    if n_discordant == 0:
        return McNemarResult(
            statistic=0.0,
            p_value=1.0,
            n_discordant=0,
            b_baseline_wrong_current_right=b,
            c_baseline_right_current_wrong=c,
            shift_detected=False,
            alpha=alpha,
            summary="No discordant pairs; no paired shift signal.",
        )

    if mcnemar_exact is not None:
        p_value = float(mcnemar_exact(b, c))
        stat = float(abs(c - b))
    else:
        p_value = float(stats.binomtest(c, n=n_discordant, p=0.5).pvalue)
        stat = float(abs(c - b))

    if shift_direction == "current_worse":
        shift = c > b and p_value < alpha
    else:
        shift = p_value < alpha

    summary = f"McNemar: discordant b={b}, c={c}, p={p_value:.4f}" + (
        ", paired shift detected." if shift else "."
    )

    return McNemarResult(
        statistic=stat,
        p_value=p_value,
        n_discordant=n_discordant,
        b_baseline_wrong_current_right=b,
        c_baseline_right_current_wrong=c,
        shift_detected=shift,
        alpha=alpha,
        summary=summary,
    )


def paired_continuous_test(
    baseline_scores: Sequence[float],
    current_scores: Sequence[float],
    alpha: float = 0.05,
    *,
    n_resamples: int = 5000,
    alternative: str = "two-sided",
) -> PairedContinuousResult:
    """Paired permutation (sign-flip) test for continuous paired scores.

    Uses holdout.paired_permutation_test on per-item differences
    (current - baseline). Valid for graded or continuous outcomes without
    arbitrary pass/fail thresholding.
    """
    if len(baseline_scores) != len(current_scores):
        raise ValueError("baseline_scores and current_scores must have same length")
    if len(baseline_scores) < 2:
        return PairedContinuousResult(
            mean_difference=0.0,
            p_value=1.0,
            shift_detected=False,
            alpha=alpha,
            summary="Insufficient paired items for permutation test (need >=2).",
            n_pairs=len(baseline_scores),
        )

    diffs = [float(c) - float(b) for b, c in zip(baseline_scores, current_scores)]
    if paired_permutation_test is None:
        raise ImportError("holdout package is required for paired continuous testing")

    mean_diff, p_value = paired_permutation_test(
        diffs,
        n_resamples=n_resamples,
        alternative=alternative,
        seed=42,
    )
    shift = float(p_value) < alpha
    summary = f"Paired permutation: mean_diff={mean_diff:.4f}, p={float(p_value):.4f}" + (
        ", shift detected." if shift else "."
    )
    return PairedContinuousResult(
        mean_difference=float(mean_diff),
        p_value=float(p_value),
        shift_detected=shift,
        alpha=alpha,
        summary=summary,
        n_pairs=len(diffs),
    )


def evaluate_item_correctness(
    output: str,
    *,
    expected_substrings: Sequence[str] | None = None,
    forbidden_substrings: Sequence[str] | None = None,
    policy_passed: bool | None = None,
) -> bool:
    """Score one benchmark item as correct/incorrect for McNemar pairing.

    Priority: explicit policy_passed if given, else substring oracle hooks.
    """
    if policy_passed is not None:
        return bool(policy_passed)

    text = output or ""
    if expected_substrings:
        if not all(s in text for s in expected_substrings):
            return False
    if forbidden_substrings:
        if any(s in text for s in forbidden_substrings):
            return False
    return True if (expected_substrings or forbidden_substrings) else False
