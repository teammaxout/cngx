"""Abstract storage backend interface.

Provides a uniform interface over different storage engines
(DuckDB, PostgreSQL, etc.) with optional compression.
"""

from __future__ import annotations

import abc
import json
import logging
import zlib
from dataclasses import dataclass, field
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

    backend: str = "duckdb"  # duckdb | postgres
    db_path: str = "~/.cngx/cngx.db"  # for DuckDB
    postgres_dsn: Optional[str] = None  # for PostgreSQL
    enable_compression: bool = False
    compression_level: int = 6  # zlib 1-9
    max_connections: int = 5  # for connection pooling


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


class PostgresBackend(StorageBackend):
    """PostgreSQL storage backend.

    Requires psycopg2: pip install psycopg2-binary sqlalchemy
    """

    def __init__(self, config: StorageConfig):
        try:
            import psycopg2
            import psycopg2.extras
        except ImportError:
            raise ImportError(
                "PostgreSQL backend requires psycopg2. "
                "Install with: pip install psycopg2-binary sqlalchemy"
            )

        if not config.postgres_dsn:
            raise ValueError("postgres_dsn is required for PostgreSQL backend")

        self._dsn = config.postgres_dsn
        self._conn = psycopg2.connect(self._dsn)
        self._conn.autocommit = True
        self._init_schema()
        self._compression = config.enable_compression
        self._compression_level = config.compression_level

    def _init_schema(self) -> None:
        import psycopg2

        with self._conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS traces (
                    id VARCHAR PRIMARY KEY,
                    task_id VARCHAR NOT NULL,
                    task_description VARCHAR,
                    model VARCHAR NOT NULL,
                    model_config_params JSONB,
                    adapter_type VARCHAR,
                    system_message VARCHAR,
                    prompt TEXT NOT NULL,
                    messages JSONB,
                    tool_calls JSONB,
                    reasoning_tokens JSONB,
                    reasoning_content TEXT,
                    output TEXT NOT NULL,
                    finish_reason VARCHAR,
                    latency_ms DOUBLE PRECISION,
                    token_usage JSONB,
                    metadata JSONB,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    content_hash VARCHAR
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS fingerprints (
                    id VARCHAR PRIMARY KEY,
                    trace_id VARCHAR NOT NULL REFERENCES traces(id),
                    task_id VARCHAR NOT NULL,
                    model VARCHAR,
                    depth INTEGER,
                    branching_factor DOUBLE PRECISION,
                    total_steps INTEGER,
                    max_step_length INTEGER,
                    tool_call_count INTEGER,
                    tool_call_sequence JSONB,
                    tool_diversity DOUBLE PRECISION,
                    tool_success_rate DOUBLE PRECISION,
                    output_length INTEGER,
                    reasoning_length INTEGER,
                    compression_ratio DOUBLE PRECISION,
                    avg_sentence_length DOUBLE PRECISION,
                    correction_count INTEGER,
                    backtrack_count INTEGER,
                    revision_count INTEGER,
                    uncertainty_markers INTEGER,
                    confidence_markers INTEGER,
                    hedging_ratio DOUBLE PRECISION,
                    verification_steps INTEGER,
                    example_count INTEGER,
                    structured_output BOOLEAN,
                    tokens_per_step DOUBLE PRECISION,
                    reasoning_overhead DOUBLE PRECISION,
                    signature_hash VARCHAR,
                    metadata JSONB,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS baselines (
                    id VARCHAR PRIMARY KEY,
                    name VARCHAR UNIQUE NOT NULL,
                    description VARCHAR,
                    task_id VARCHAR NOT NULL,
                    fingerprint_id VARCHAR NOT NULL REFERENCES fingerprints(id),
                    trace_id VARCHAR NOT NULL REFERENCES traces(id),
                    metadata JSONB,
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS diffs (
                    id VARCHAR PRIMARY KEY,
                    baseline_id VARCHAR NOT NULL,
                    current_id VARCHAR NOT NULL,
                    baseline_task_id VARCHAR,
                    current_task_id VARCHAR,
                    changes JSONB,
                    drift_score DOUBLE PRECISION,
                    significance VARCHAR,
                    total_changes INTEGER,
                    breaking_changes INTEGER,
                    summary TEXT,
                    recommendations JSONB,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS drift_reports (
                    id VARCHAR PRIMARY KEY,
                    task_id VARCHAR NOT NULL,
                    baseline_id VARCHAR,
                    start_time TIMESTAMP,
                    end_time TIMESTAMP,
                    drift_score DOUBLE PRECISION,
                    drift_trend VARCHAR,
                    significant_changes JSONB,
                    sample_count INTEGER,
                    variance DOUBLE PRECISION,
                    std_deviation DOUBLE PRECISION,
                    z_scores JSONB,
                    summary TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS eval_results (
                    id VARCHAR PRIMARY KEY,
                    task_id VARCHAR NOT NULL,
                    trace_id VARCHAR NOT NULL,
                    fingerprint_id VARCHAR NOT NULL,
                    passed BOOLEAN,
                    score DOUBLE PRECISION,
                    expected_behavior JSONB,
                    actual_behavior JSONB,
                    baseline_id VARCHAR,
                    drift_from_baseline DOUBLE PRECISION,
                    is_regression BOOLEAN,
                    message TEXT,
                    details JSONB,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            # Indexes
            cur.execute("CREATE INDEX IF NOT EXISTS idx_pg_traces_task ON traces(task_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_pg_traces_model ON traces(model)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_pg_traces_ts ON traces(timestamp)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_pg_fp_task ON fingerprints(task_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_pg_fp_trace ON fingerprints(trace_id)")

    def _json_dumps(self, data: Any) -> str:
        from datetime import datetime as dt

        def serializer(obj):
            if isinstance(obj, dt):
                return obj.isoformat()
            raise TypeError(f"Not serializable: {type(obj)}")

        return json.dumps(data, default=serializer)

    def save_trace(self, trace: ReasoningTrace) -> str:
        import psycopg2.extras

        with self._conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO traces
                (id, task_id, task_description, model, model_config_params, adapter_type,
                 system_message, prompt, messages, tool_calls, reasoning_tokens,
                 reasoning_content, output, finish_reason, latency_ms, token_usage,
                 metadata, timestamp, content_hash)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (id) DO UPDATE SET
                    output = EXCLUDED.output, timestamp = EXCLUDED.timestamp
            """,
                (
                    trace.id,
                    trace.task_id,
                    trace.task_description,
                    trace.model,
                    self._json_dumps(trace.model_config_params.model_dump()),
                    trace.adapter_type,
                    trace.system_message,
                    trace.prompt,
                    self._json_dumps(trace.messages),
                    self._json_dumps([tc.model_dump() for tc in trace.tool_calls]),
                    self._json_dumps(trace.reasoning_tokens),
                    trace.reasoning_content,
                    trace.output,
                    trace.finish_reason,
                    trace.latency_ms,
                    self._json_dumps(trace.token_usage.model_dump()),
                    self._json_dumps(trace.metadata),
                    trace.timestamp,
                    trace.content_hash,
                ),
            )
        return trace.id

    def get_trace(self, trace_id: str) -> ReasoningTrace:
        from cngx.core.exceptions import TraceNotFoundError

        with self._conn.cursor() as cur:
            cur.execute("SELECT * FROM traces WHERE id = %s", (trace_id,))
            row = cur.fetchone()
            if not row:
                raise TraceNotFoundError(trace_id)
            cols = [d[0] for d in cur.description]
        return self._row_to_trace(row, cols)

    def get_traces_by_task(
        self, task_id: str, limit: int = 100, offset: int = 0
    ) -> list[ReasoningTrace]:
        with self._conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM traces WHERE task_id = %s ORDER BY timestamp DESC LIMIT %s OFFSET %s",
                (task_id, limit, offset),
            )
            rows = cur.fetchall()
            cols = [d[0] for d in cur.description] if cur.description else []
        return [self._row_to_trace(r, cols) for r in rows]

    def get_recent_traces(self, limit: int = 50) -> list[ReasoningTrace]:
        with self._conn.cursor() as cur:
            cur.execute("SELECT * FROM traces ORDER BY timestamp DESC LIMIT %s", (limit,))
            rows = cur.fetchall()
            cols = [d[0] for d in cur.description] if cur.description else []
        return [self._row_to_trace(r, cols) for r in rows]

    def _row_to_trace(self, row: tuple, columns: list[str]) -> ReasoningTrace:
        data = dict(zip(columns, row))
        for f in (
            "model_config_params",
            "messages",
            "tool_calls",
            "reasoning_tokens",
            "token_usage",
            "metadata",
        ):
            if isinstance(data.get(f), str):
                data[f] = json.loads(data[f])
        return ReasoningTrace(**data)

    def save_fingerprint(self, fp: BehavioralFingerprint) -> str:
        fp_id = f"fp_{fp.trace_id}"
        with self._conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO fingerprints
                (id, trace_id, task_id, model, depth, branching_factor, total_steps,
                 max_step_length, tool_call_count, tool_call_sequence, tool_diversity,
                 tool_success_rate, output_length, reasoning_length, compression_ratio,
                 avg_sentence_length, correction_count, backtrack_count, revision_count,
                 uncertainty_markers, confidence_markers, hedging_ratio, verification_steps,
                 example_count, structured_output, tokens_per_step, reasoning_overhead,
                 signature_hash, metadata, timestamp)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (id) DO UPDATE SET depth = EXCLUDED.depth
            """,
                (
                    fp_id,
                    fp.trace_id,
                    fp.task_id,
                    fp.model,
                    fp.depth,
                    fp.branching_factor,
                    fp.total_steps,
                    fp.max_step_length,
                    fp.tool_call_count,
                    self._json_dumps(fp.tool_call_sequence),
                    fp.tool_diversity,
                    fp.tool_success_rate,
                    fp.output_length,
                    fp.reasoning_length,
                    fp.compression_ratio,
                    fp.avg_sentence_length,
                    fp.correction_count,
                    fp.backtrack_count,
                    fp.revision_count,
                    fp.uncertainty_markers,
                    fp.confidence_markers,
                    fp.hedging_ratio,
                    fp.verification_steps,
                    fp.example_count,
                    fp.structured_output,
                    fp.tokens_per_step,
                    fp.reasoning_overhead,
                    fp.signature_hash,
                    self._json_dumps(fp.metadata),
                    fp.timestamp,
                ),
            )
        return fp_id

    def get_fingerprint(self, fingerprint_id: str) -> BehavioralFingerprint:
        from cngx.core.exceptions import StorageError

        with self._conn.cursor() as cur:
            cur.execute("SELECT * FROM fingerprints WHERE id = %s", (fingerprint_id,))
            row = cur.fetchone()
            if not row:
                raise StorageError(f"Fingerprint not found: {fingerprint_id}")
            cols = [d[0] for d in cur.description]
        return self._row_to_fingerprint(row, cols)

    def get_fingerprint_by_trace(self, trace_id: str) -> Optional[BehavioralFingerprint]:
        with self._conn.cursor() as cur:
            cur.execute("SELECT * FROM fingerprints WHERE trace_id = %s", (trace_id,))
            row = cur.fetchone()
            if not row:
                return None
            cols = [d[0] for d in cur.description]
        return self._row_to_fingerprint(row, cols)

    def get_fingerprints_by_task(
        self, task_id: str, limit: int = 100
    ) -> list[BehavioralFingerprint]:
        with self._conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM fingerprints WHERE task_id = %s ORDER BY timestamp DESC LIMIT %s",
                (task_id, limit),
            )
            rows = cur.fetchall()
            cols = [d[0] for d in cur.description] if cur.description else []
        return [self._row_to_fingerprint(r, cols) for r in rows]

    def _row_to_fingerprint(self, row: tuple, columns: list[str]) -> BehavioralFingerprint:
        data = dict(zip(columns, row))
        for f in ("tool_call_sequence", "metadata"):
            if isinstance(data.get(f), str):
                data[f] = json.loads(data[f])
        del data["id"]
        return BehavioralFingerprint(**data)

    def save_baseline(self, baseline: Baseline) -> str:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO baselines
                (id, name, description, task_id, fingerprint_id, trace_id,
                 metadata, is_active, created_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (id) DO UPDATE SET
                    name = EXCLUDED.name, is_active = EXCLUDED.is_active
            """,
                (
                    baseline.id,
                    baseline.name,
                    baseline.description,
                    baseline.task_id,
                    baseline.fingerprint_id,
                    baseline.trace_id,
                    self._json_dumps(baseline.metadata),
                    baseline.is_active,
                    baseline.created_at,
                ),
            )
        return baseline.id

    def get_baseline(self, name: str) -> Baseline:
        from cngx.core.exceptions import BaselineNotFoundError

        with self._conn.cursor() as cur:
            cur.execute("SELECT * FROM baselines WHERE name = %s", (name,))
            row = cur.fetchone()
            if not row:
                raise BaselineNotFoundError(name)
            cols = [d[0] for d in cur.description]
        data = dict(zip(cols, row))
        if isinstance(data.get("metadata"), str):
            data["metadata"] = json.loads(data["metadata"])
        return Baseline(**data)

    def get_baseline_by_id(self, baseline_id: str) -> Baseline:
        from cngx.core.exceptions import BaselineNotFoundError

        with self._conn.cursor() as cur:
            cur.execute("SELECT * FROM baselines WHERE id = %s", (baseline_id,))
            row = cur.fetchone()
            if not row:
                raise BaselineNotFoundError(baseline_id)
            cols = [d[0] for d in cur.description]
        data = dict(zip(cols, row))
        if isinstance(data.get("metadata"), str):
            data["metadata"] = json.loads(data["metadata"])
        return Baseline(**data)

    def save_diff(self, diff: BehaviorDiff) -> str:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO diffs
                (id, baseline_id, current_id, baseline_task_id, current_task_id,
                 changes, drift_score, significance, total_changes, breaking_changes,
                 summary, recommendations, timestamp)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (id) DO NOTHING
            """,
                (
                    diff.id,
                    diff.baseline_id,
                    diff.current_id,
                    diff.baseline_task_id,
                    diff.current_task_id,
                    self._json_dumps([c.model_dump() for c in diff.changes]),
                    diff.drift_score,
                    diff.significance,
                    diff.total_changes,
                    diff.breaking_changes,
                    diff.summary,
                    self._json_dumps(diff.recommendations) if diff.recommendations else None,
                    diff.timestamp,
                ),
            )
        return diff.id

    def save_drift_report(self, report: DriftReport) -> str:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO drift_reports
                (id, task_id, baseline_id, start_time, end_time, drift_score,
                 drift_trend, significant_changes, sample_count, variance,
                 std_deviation, z_scores, summary, timestamp)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (id) DO NOTHING
            """,
                (
                    report.id,
                    report.task_id,
                    report.baseline_id,
                    report.start_time,
                    report.end_time,
                    report.drift_score,
                    report.drift_trend,
                    self._json_dumps(report.significant_changes),
                    report.sample_count,
                    report.variance,
                    report.std_deviation,
                    self._json_dumps(report.z_scores),
                    report.summary,
                    report.timestamp,
                ),
            )
        return report.id

    def save_eval_result(self, result: EvalResult) -> str:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO eval_results
                (id, task_id, trace_id, fingerprint_id, passed, score,
                 expected_behavior, actual_behavior, baseline_id,
                 drift_from_baseline, is_regression, message, details, timestamp)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (id) DO NOTHING
            """,
                (
                    result.id,
                    result.task_id,
                    result.trace_id,
                    result.fingerprint_id,
                    result.passed,
                    result.score,
                    self._json_dumps(result.expected_behavior),
                    self._json_dumps(result.actual_behavior),
                    result.baseline_id,
                    result.drift_from_baseline,
                    result.is_regression,
                    result.message,
                    self._json_dumps(result.details),
                    result.timestamp,
                ),
            )
        return result.id

    def close(self) -> None:
        self._conn.close()

    def count_traces(self, task_id: Optional[str] = None) -> int:
        with self._conn.cursor() as cur:
            if task_id:
                cur.execute("SELECT COUNT(*) FROM traces WHERE task_id = %s", (task_id,))
            else:
                cur.execute("SELECT COUNT(*) FROM traces")
            row = cur.fetchone()
        return row[0] if row else 0

    def delete_traces(self, older_than_days: int) -> int:
        with self._conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM traces WHERE timestamp < NOW() - INTERVAL '%s days'",
                (older_than_days,),
            )
            count = (cur.fetchone() or (0,))[0]
            cur.execute(
                "DELETE FROM traces WHERE timestamp < NOW() - INTERVAL '%s days'",
                (older_than_days,),
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
    """Factory: create the appropriate storage backend.

    Local-first default is DuckDB. Postgres remains available for advanced
    self-hosting but is no longer advertised as a PyPI extra.
    """
    cfg = config or StorageConfig()
    if cfg.backend == "postgres":
        return PostgresBackend(cfg)
    return DuckDBAdapter(cfg)
