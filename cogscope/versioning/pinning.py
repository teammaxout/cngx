"""Pinning manager for behavior pinning."""

from typing import Optional

from cogscope.core.models import Baseline
from cogscope.storage.database import Database, get_database
from cogscope.versioning.baseline import BaselineManager


class PinningManager:
    """Manage pinned behaviors.

    Pinning allows users to mark a specific behavior as the
    expected/desired behavior for future comparisons.
    """

    def __init__(self, db: Optional[Database] = None):
        self.db = db or get_database()
        self.baseline_manager = BaselineManager(db)

    def pin(
        self,
        trace_id: str,
        name: str,
        description: Optional[str] = None,
    ) -> Baseline:
        """Pin a trace as the expected behavior.

        This is an alias for creating a baseline.
        """
        return self.baseline_manager.create(
            trace_id=trace_id,
            name=name,
            description=description,
        )

    def unpin(self, name: str) -> None:
        """Remove a pin (deactivate baseline)."""
        self.baseline_manager.deactivate(name)

    def get_pin(self, name: str) -> Baseline:
        """Get a pinned behavior."""
        return self.baseline_manager.get(name)

    def list_pins(self, task_id: Optional[str] = None) -> list[Baseline]:
        """List all pinned behaviors."""
        return self.baseline_manager.list(task_id)

    def check_against_pin(
        self,
        pin_name: str,
        current_trace_id: str,
    ) -> dict:
        """Check if current behavior matches pinned behavior."""
        result = self.baseline_manager.compare_to_current(pin_name, current_trace_id)

        # Add pass/fail based on drift
        result["passed"] = result["drift_score"] < 0.3
        result["status"] = "PASS" if result["passed"] else "FAIL"

        return result
