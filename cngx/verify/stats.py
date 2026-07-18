"""Aggregate recorded verify outcomes into per-label fabricated-claim stats (issue #43).

Definitions are fixed by the issue and must not drift:

    fabricated = claimed_success AND status == "blocked" AND NOT timed_out

A run only counts toward the fabricated-claim *rate* if the agent actually made a success claim, so:

    rate(label) = fabricated / runs_with_success_claim

Timeouts, usage errors, and `--require-claim` blocks with no success claim are never counted as
fabricated. This module is pure (no I/O): it takes the list of outcome dicts from the store and returns
plain data, so it is trivial to test against the exact definition above.
"""

from __future__ import annotations

from dataclasses import dataclass, field

BLOCKED = "blocked"


def is_fabricated(outcome: dict) -> bool:
    """A fabricated claim: the agent claimed success, but verification blocked (and did not time out)."""
    return (
        bool(outcome.get("claimed_success"))
        and outcome.get("status") == BLOCKED
        and not bool(outcome.get("timed_out"))
    )


@dataclass
class LabelStats:
    """Fabricated-claim stats for a single model/agent label."""

    label: str
    runs: int = 0
    success_claims: int = 0
    fabricated: int = 0
    # For the trend: fabricated-claim rate over the most recent N vs the prior N runs (success-claim
    # runs only), so the number moves for the same reason the headline rate does.
    recent_rate: float | None = None
    prior_rate: float | None = None

    @property
    def fabricated_rate(self) -> float | None:
        """fabricated / success_claims, or None when there are no success claims to divide by."""
        if self.success_claims == 0:
            return None
        return self.fabricated / self.success_claims

    def to_dict(self) -> dict:
        return {
            "label": self.label,
            "runs": self.runs,
            "success_claims": self.success_claims,
            "fabricated": self.fabricated,
            "fabricated_rate": self.fabricated_rate,
            "recent_rate": self.recent_rate,
            "prior_rate": self.prior_rate,
        }


@dataclass
class VerifyStats:
    """All per-label stats plus a small overall summary."""

    labels: list[LabelStats] = field(default_factory=list)
    total_runs: int = 0

    def to_dict(self) -> dict:
        return {
            "total_runs": self.total_runs,
            "labels": [ls.to_dict() for ls in self.labels],
        }


def _rate(outcomes: list[dict]) -> float | None:
    """fabricated / success_claims over the given outcomes, or None if no success claims."""
    success = [o for o in outcomes if bool(o.get("claimed_success"))]
    if not success:
        return None
    fab = sum(1 for o in success if is_fabricated(o))
    return fab / len(success)


def compute_stats(outcomes: list[dict], *, trend_window: int = 10) -> VerifyStats:
    """Aggregate outcome rows (oldest first) into per-label stats.

    `trend_window` is the N for the last-N vs prior-N fabricated-rate comparison, computed over
    success-claim runs only so the trend and the headline rate share a denominator.
    """
    by_label: dict[str, list[dict]] = {}
    for o in outcomes:
        label = (o.get("label") or "").strip()
        by_label.setdefault(label, []).append(o)

    label_stats: list[LabelStats] = []
    for label, rows in by_label.items():
        success_rows = [o for o in rows if bool(o.get("claimed_success"))]
        ls = LabelStats(
            label=label,
            runs=len(rows),
            success_claims=len(success_rows),
            fabricated=sum(1 for o in rows if is_fabricated(o)),
        )

        # Trend over success-claim runs only (rows are oldest-first, so the tail is most recent).
        if len(success_rows) >= 2 * trend_window:
            ls.recent_rate = _rate(success_rows[-trend_window:])
            ls.prior_rate = _rate(success_rows[-2 * trend_window : -trend_window])

        label_stats.append(ls)

    # Stable, useful ordering: unlabeled bucket last, otherwise most runs first then label name.
    label_stats.sort(key=lambda s: (s.label == "", -s.runs, s.label))

    return VerifyStats(labels=label_stats, total_runs=len(outcomes))
