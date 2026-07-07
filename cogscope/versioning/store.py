"""Version store for managing trace and fingerprint versions."""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from cogscope.core.models import BehavioralFingerprint, ReasoningTrace
from cogscope.storage.database import Database, get_database


class VersionStore:
    """Manage versions of reasoning traces and fingerprints.

    Provides methods for:
    - Listing versions
    - Comparing versions
    - Exporting/importing versions
    """

    def __init__(self, db: Optional[Database] = None):
        self.db = db or get_database()

    def list_versions(
        self,
        task_id: str,
        limit: int = 50,
    ) -> list[dict]:
        """List all versions for a task.

        Returns a simplified list of version info.
        """
        traces = self.db.get_traces_by_task(task_id, limit=limit)

        versions = []
        for trace in traces:
            fp = self.db.get_fingerprint_by_trace(trace.id)

            versions.append(
                {
                    "trace_id": trace.id,
                    "timestamp": trace.timestamp.isoformat(),
                    "model": trace.model,
                    "fingerprint_hash": fp.signature_hash if fp else None,
                    "depth": fp.depth if fp else None,
                    "tool_count": fp.tool_call_count if fp else None,
                }
            )

        return versions

    def get_version(self, trace_id: str) -> dict:
        """Get full version info for a trace."""
        trace = self.db.get_trace(trace_id)
        fp = self.db.get_fingerprint_by_trace(trace_id)

        return {
            "trace": trace.model_dump(),
            "fingerprint": fp.model_dump() if fp else None,
        }

    def export_version(self, trace_id: str, output_path: Path) -> None:
        """Export a version to a JSON file."""
        data = self.get_version(trace_id)

        # Convert datetime objects
        def serialize(obj):
            if isinstance(obj, datetime):
                return obj.isoformat()
            raise TypeError(f"Object of type {type(obj)} is not JSON serializable")

        with open(output_path, "w") as f:
            json.dump(data, f, indent=2, default=serialize)

    def import_version(self, input_path: Path) -> str:
        """Import a version from a JSON file."""
        with open(input_path) as f:
            data = json.load(f)

        # Parse and save trace
        trace_data = data["trace"]
        trace_data["timestamp"] = datetime.fromisoformat(trace_data["timestamp"])
        trace = ReasoningTrace(**trace_data)
        self.db.save_trace(trace)

        # Parse and save fingerprint if present
        if data.get("fingerprint"):
            fp_data = data["fingerprint"]
            fp_data["timestamp"] = datetime.fromisoformat(fp_data["timestamp"])
            fp = BehavioralFingerprint(**fp_data)
            self.db.save_fingerprint(fp)

        return trace.id

    def compare_versions(
        self,
        trace_id_1: str,
        trace_id_2: str,
    ) -> dict:
        """Compare two versions."""
        from cogscope.diff.engine import DiffEngine

        fp1 = self.db.get_fingerprint_by_trace(trace_id_1)
        fp2 = self.db.get_fingerprint_by_trace(trace_id_2)

        if not fp1 or not fp2:
            raise ValueError("Fingerprints not found for one or both traces")

        engine = DiffEngine()
        diff = engine.diff(fp1, fp2)

        return {
            "diff": diff.model_dump(),
            "drift_score": diff.drift_score,
            "significance": diff.significance.value,
        }
