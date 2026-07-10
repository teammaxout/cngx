"""Abstract storage backend interface.

Provides a uniform interface over DuckDB with optional compression.
"""

from __future__ import annotations

import abc
import json
import logging
import zlib
from dataclasses import dataclass
from typing import Any, Optional

from cngx.core.models import (
    Baseline,
    BehavioralFingerprint,
    BehaviorDiff,
    DriftReport,
    EvalResult,
    EvalSuite,
    ReasoningTrace,
)

logger = logging.getLogger("cngx.storage.backend")


@dataclass
class StorageConfig:
    """Configuration for storage backend."""

    backend: str = "duckdb"
    db_path: str = "~/.cngx/cngx.db"
    enable_compression: bool = False
    compression_level: int = 6  # zlib 1-9
    max_connections: int = 5


class StorageBackend(abc.ABC):
    """Abstract storage backend interface.

    All storage operations go through this interface,
    allowing transparent switching between backends.
    """

    @abc.abstractmethod
    def save_trace(self, trace: ReasoningTrace) -> str: ...

    @abc.abstractmethod
    def get_trace(self, trace_id: str) -> ReasoningTrace: ...

    @abc.abstractmethod
    def get_traces_by_task(
        self, task_id: str, limit: int = 100, offset: int = 0
    ) -> list[ReasoningTrace]: ...

    @abc.abstractmethod
    def get_recent_traces(self, limit: int = 50) -> list[ReasoningTrace]: ...

    @abc.abstractmethod
    def save_fingerprint(self, fp: BehavioralFingerprint) -> str: ...

    @abc.abstractmethod
    def get_fingerprint(self, fingerprint_id: str) -> BehavioralFingerprint: ...

    @abc.abstractmethod
    def get_fingerprint_by_trace(self, trace_id: str) -> Optional[BehavioralFingerprint]: ...

    @abc.abstractmethod
    def get_fingerprints_by_task(
        self, task_id: str, limit: int = 100
    ) -> list[BehavioralFingerprint]: ...

    @abc.abstractmethod
    def save_baseline(self, baseline: Baseline) -> str: ...

    @abc.abstractmethod
    def get_baseline(self, name: str) -> Baseline: ...

    @abc.abstractmethod
    def get_baseline_by_id(self, baseline_id: str) -> Baseline: ...

    @abc.abstractmethod
    def save_diff(self, diff: BehaviorDiff) -> str: ...

    @abc.abstractmethod
    def save_drift_report(self, report: DriftReport) -> str: ...

    @abc.abstractmethod
    def save_eval_result(self, result: EvalResult) -> str: ...

    @abc.abstractmethod
    def close(self) -> None: ...

    @abc.abstractmethod
    def count_traces(self, task_id: Optional[str] = None) -> int: ...

    @abc.abstractmethod
    def delete_traces(self, older_than_days: int) -> int: ...


class DuckDBAdapter(StorageBackend):
    """Adapter wrapping the existing DuckDB Database class.

    Delegates all operations to the existing Database implementation,
    providing the StorageBackend interface.
    """

    def __init__(self, config: StorageConfig | None = None):
        from pathlib import Path

        from cngx.storage.database import Database

        cfg = config or StorageConfig()
        db_path = Path(cfg.db_path).expanduser()
        self._db = Database(db_path)
        self._compression = cfg.enable_compression
        self._compression_level = cfg.compression_level

    def save_trace(self, trace: ReasoningTrace) -> str:
        return self._db.save_trace(trace)

    def get_trace(self, trace_id: str) -> ReasoningTrace:
        return self._db.get_trace(trace_id)

    def get_traces_by_task(
        self, task_id: str, limit: int = 100, offset: int = 0
    ) -> list[ReasoningTrace]:
        return self._db.get_traces_by_task(task_id, limit, offset)

    def get_recent_traces(self, limit: int = 50) -> list[ReasoningTrace]:
        return self._db.get_recent_traces(limit)

    def save_fingerprint(self, fp: BehavioralFingerprint) -> str:
        return self._db.save_fingerprint(fp)

    def get_fingerprint(self, fingerprint_id: str) -> BehavioralFingerprint:
        return self._db.get_fingerprint(fingerprint_id)

    def get_fingerprint_by_trace(self, trace_id: str) -> Optional[BehavioralFingerprint]:
        return self._db.get_fingerprint_by_trace(trace_id)

    def get_fingerprints_by_task(
        self, task_id: str, limit: int = 100
    ) -> list[BehavioralFingerprint]:
        return self._db.get_fingerprints_by_task(task_id, limit)

    def save_baseline(self, baseline: Baseline) -> str:
        return self._db.save_baseline(baseline)

    def get_baseline(self, name: str) -> Baseline:
        return self._db.get_baseline(name)

    def get_baseline_by_id(self, baseline_id: str) -> Baseline:
        return self._db.get_baseline_by_id(baseline_id)

    def save_diff(self, diff: BehaviorDiff) -> str:
        return self._db.save_diff(diff)

    def save_drift_report(self, report: DriftReport) -> str:
        return self._db.save_drift_report(report)

    def save_eval_result(self, result: EvalResult) -> str:
        return self._db.save_eval_result(result)

    def close(self) -> None:
        self._db.close()

    def count_traces(self, task_id: Optional[str] = None) -> int:
        if task_id:
            row, _ = self._db._fetchone("SELECT COUNT(*) FROM traces WHERE task_id = ?", [task_id])
        else:
            row, _ = self._db._fetchone("SELECT COUNT(*) FROM traces")
        return row[0] if row else 0

    def delete_traces(self, older_than_days: int) -> int:
        row, _ = self._db._fetchone(
            "SELECT COUNT(*) FROM traces WHERE timestamp < CURRENT_TIMESTAMP - INTERVAL ? DAY",
            [older_than_days],
        )
        count = row[0] if row else 0
        self._db._execute(
            "DELETE FROM traces WHERE timestamp < CURRENT_TIMESTAMP - INTERVAL ? DAY",
            [older_than_days],
        )
        return count


class TraceCompressor:
    """Compress/decompress trace data for storage efficiency."""

    def __init__(self, level: int = 6):
        self.level = level

    def compress(self, data: str) -> bytes:
        return zlib.compress(data.encode("utf-8"), self.level)

    def decompress(self, data: bytes) -> str:
        return zlib.decompress(data).decode("utf-8")

    def compress_json(self, obj: Any) -> bytes:
        return self.compress(json.dumps(obj))

    def decompress_json(self, data: bytes) -> Any:
        return json.loads(self.decompress(data))

    def compression_ratio(self, data: str) -> float:
        """Return compression ratio (compressed/original)."""
        original = len(data.encode("utf-8"))
        compressed = len(self.compress(data))
        return compressed / original if original > 0 else 1.0


def create_backend(config: StorageConfig | None = None) -> StorageBackend:
    """Factory: create the DuckDB storage backend."""
    return DuckDBAdapter(config)
