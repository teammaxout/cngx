"""DuckDB-based storage for Cogscope.

This module provides a robust local-first storage solution using DuckDB.
All reasoning traces, fingerprints, baselines, and diffs are stored here.

Thread safety: All database operations are serialized through a threading.Lock
since DuckDB connections are not thread-safe.
"""

import atexit
import functools
import json
import logging
import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import duckdb

from cogscope.core.exceptions import BaselineNotFoundError, StorageError, TraceNotFoundError
from cogscope.core.models import (
    Baseline,
    BehavioralFingerprint,
    BehaviorDiff,
    DriftReport,
    EvalResult,
    EvalSuite,
    ReasoningTrace,
)

logger = logging.getLogger("cogscope.storage")


def _json_serialize(obj):
    """JSON serializer that handles datetime objects."""
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")


def _json_dumps(data) -> str:
    """Dump data to JSON with datetime support."""
    return json.dumps(data, default=_json_serialize)


class Database:
    """DuckDB-based storage for Cogscope data.

    Thread-safe: All operations are serialized through a Lock.
    DuckDB connections are not safe for concurrent access from
    multiple threads, so we guard all queries.
    """

    def __init__(self, db_path: "str | Path"):
        self.db_path = Path(db_path) if not isinstance(db_path, Path) else db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._closed = False
        self.conn = duckdb.connect(str(db_path))

        # Set memory limit from env (default 512 MB)
        mem_limit = os.getenv("COGSCOPE_DB_MEMORY_LIMIT", "512MB")
        try:
            self.conn.execute(f"SET memory_limit = '{mem_limit}'")
        except Exception:
            pass  # Older DuckDB versions may not support this

        self._init_schema()
        self._migrate_schema()
        atexit.register(self._atexit_close)

    def _migrate_schema(self) -> None:
        """Add session columns to existing databases."""
        for ddl in (
            "ALTER TABLE fingerprints ADD COLUMN IF NOT EXISTS session_id VARCHAR",
            "ALTER TABLE fingerprints ADD COLUMN IF NOT EXISTS session_turn INTEGER",
            """
            CREATE TABLE IF NOT EXISTS session_counters (
                session_id VARCHAR PRIMARY KEY,
                next_turn INTEGER NOT NULL DEFAULT 1,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """,
        ):
            try:
                self.conn.execute(ddl)
            except Exception:
                pass
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_fingerprints_session ON fingerprints(session_id, session_turn)"
        )

    def _execute(self, query: str, params=None):
        """Thread-safe query execution. Returns the cursor result.

        IMPORTANT: For read queries, prefer _fetchone() or _fetchall()
        which materialize results inside the lock. This method is for
        write queries that don't need results.
        """
        with self._lock:
            if params is not None:
                return self.conn.execute(query, params)
            return self.conn.execute(query)

    def _fetchone(self, query: str, params=None):
        """Thread-safe query + fetchone. Returns (row, column_names)."""
        with self._lock:
            if params is not None:
                cur = self.conn.execute(query, params)
            else:
                cur = self.conn.execute(query)
            row = cur.fetchone()
            cols = [d[0] for d in cur.description] if cur.description else []
            return row, cols

    def _fetchall(self, query: str, params=None):
        """Thread-safe query + fetchall. Returns (rows, column_names)."""
        with self._lock:
            if params is not None:
                cur = self.conn.execute(query, params)
            else:
                cur = self.conn.execute(query)
            rows = cur.fetchall()
            cols = [d[0] for d in cur.description] if cur.description else []
            return rows, cols

    def _init_schema(self) -> None:
        """Initialize the database schema."""
        # Reasoning traces
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS traces (
                id VARCHAR PRIMARY KEY,
                task_id VARCHAR NOT NULL,
                task_description VARCHAR,
                model VARCHAR NOT NULL,
                model_config_params JSON,
                adapter_type VARCHAR,
                system_message VARCHAR,
                prompt TEXT NOT NULL,
                messages JSON,
                tool_calls JSON,
                reasoning_tokens JSON,
                reasoning_content TEXT,
                output TEXT NOT NULL,
                finish_reason VARCHAR,
                latency_ms DOUBLE,
                token_usage JSON,
                metadata JSON,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                content_hash VARCHAR
            )
        """)

        # Behavioral fingerprints
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS fingerprints (
                id VARCHAR PRIMARY KEY,
                trace_id VARCHAR NOT NULL,
                task_id VARCHAR NOT NULL,
                model VARCHAR,
                depth INTEGER,
                branching_factor DOUBLE,
                total_steps INTEGER,
                max_step_length INTEGER,
                tool_call_count INTEGER,
                tool_call_sequence JSON,
                tool_diversity DOUBLE,
                tool_success_rate DOUBLE,
                output_length INTEGER,
                reasoning_length INTEGER,
                compression_ratio DOUBLE,
                avg_sentence_length DOUBLE,
                correction_count INTEGER,
                backtrack_count INTEGER,
                revision_count INTEGER,
                uncertainty_markers INTEGER,
                confidence_markers INTEGER,
                hedging_ratio DOUBLE,
                verification_steps INTEGER,
                example_count INTEGER,
                structured_output BOOLEAN,
                tokens_per_step DOUBLE,
                reasoning_overhead DOUBLE,
                signature_hash VARCHAR,
                metadata JSON,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (trace_id) REFERENCES traces(id)
            )
        """)

        # Baselines
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS baselines (
                id VARCHAR PRIMARY KEY,
                name VARCHAR UNIQUE NOT NULL,
                description VARCHAR,
                task_id VARCHAR NOT NULL,
                fingerprint_id VARCHAR NOT NULL,
                trace_id VARCHAR NOT NULL,
                metadata JSON,
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (fingerprint_id) REFERENCES fingerprints(id),
                FOREIGN KEY (trace_id) REFERENCES traces(id)
            )
        """)

        # Behavior diffs
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS diffs (
                id VARCHAR PRIMARY KEY,
                baseline_id VARCHAR NOT NULL,
                current_id VARCHAR NOT NULL,
                baseline_task_id VARCHAR,
                current_task_id VARCHAR,
                changes JSON,
                drift_score DOUBLE,
                significance VARCHAR,
                total_changes INTEGER,
                breaking_changes INTEGER,
                summary TEXT,
                recommendations JSON,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Drift reports
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS drift_reports (
                id VARCHAR PRIMARY KEY,
                task_id VARCHAR NOT NULL,
                baseline_id VARCHAR,
                start_time TIMESTAMP,
                end_time TIMESTAMP,
                drift_score DOUBLE,
                drift_trend VARCHAR,
                significant_changes JSON,
                sample_count INTEGER,
                variance DOUBLE,
                std_deviation DOUBLE,
                z_scores JSON,
                summary TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Eval results
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS eval_results (
                id VARCHAR PRIMARY KEY,
                task_id VARCHAR NOT NULL,
                trace_id VARCHAR NOT NULL,
                fingerprint_id VARCHAR NOT NULL,
                passed BOOLEAN,
                score DOUBLE,
                expected_behavior JSON,
                actual_behavior JSON,
                baseline_id VARCHAR,
                drift_from_baseline DOUBLE,
                is_regression BOOLEAN,
                message TEXT,
                details JSON,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Eval suites
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS eval_suites (
                id VARCHAR PRIMARY KEY,
                name VARCHAR UNIQUE NOT NULL,
                description VARCHAR,
                task_ids JSON,
                baseline_ids JSON,
                thresholds JSON,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Create indexes
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_traces_task ON traces(task_id)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_traces_model ON traces(model)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_traces_timestamp ON traces(timestamp)")
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_fingerprints_task ON fingerprints(task_id)"
        )
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_fingerprints_trace ON fingerprints(trace_id)"
        )
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_baselines_task ON baselines(task_id)")

    def close(self) -> None:
        """Close the database connection."""
        if not self._closed:
            self._closed = True
            try:
                self.conn.close()
                logger.debug("Database connection closed: %s", self.db_path)
            except Exception:
                pass

    def _atexit_close(self) -> None:
        """Called by atexit to ensure clean shutdown."""
        self.close()

    # ==================== Traces ====================

    def save_trace(self, trace: ReasoningTrace) -> str:
        """Save a reasoning trace."""
        try:
            self._execute(
                """
                INSERT INTO traces 
                (id, task_id, task_description, model, model_config_params, adapter_type,
                 system_message, prompt, messages, tool_calls, reasoning_tokens,
                 reasoning_content, output, finish_reason, latency_ms, token_usage,
                 metadata, timestamp, content_hash)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (id) DO UPDATE SET
                    task_id = excluded.task_id,
                    task_description = excluded.task_description,
                    model = excluded.model,
                    model_config_params = excluded.model_config_params,
                    adapter_type = excluded.adapter_type,
                    system_message = excluded.system_message,
                    prompt = excluded.prompt,
                    messages = excluded.messages,
                    tool_calls = excluded.tool_calls,
                    reasoning_tokens = excluded.reasoning_tokens,
                    reasoning_content = excluded.reasoning_content,
                    output = excluded.output,
                    finish_reason = excluded.finish_reason,
                    latency_ms = excluded.latency_ms,
                    token_usage = excluded.token_usage,
                    metadata = excluded.metadata,
                    timestamp = excluded.timestamp,
                    content_hash = excluded.content_hash
            """,
                [
                    trace.id,
                    trace.task_id,
                    trace.task_description,
                    trace.model,
                    _json_dumps(trace.model_config_params.model_dump()),
                    trace.adapter_type,
                    trace.system_message,
                    trace.prompt,
                    _json_dumps(trace.messages),
                    _json_dumps([tc.model_dump() for tc in trace.tool_calls]),
                    _json_dumps(trace.reasoning_tokens),
                    trace.reasoning_content,
                    trace.output,
                    trace.finish_reason,
                    trace.latency_ms,
                    _json_dumps(trace.token_usage.model_dump()),
                    _json_dumps(trace.metadata),
                    trace.timestamp,
                    trace.content_hash,
                ],
            )
            return trace.id
        except Exception as e:
            raise StorageError(f"Failed to save trace: {e}")

    def save_traces_batch(self, traces: list[ReasoningTrace]) -> list[str]:
        """Save multiple traces in a single transaction for better performance.

        Uses executemany internally which is significantly faster than
        individual inserts for large batches.
        """
        if not traces:
            return []

        params_list = []
        for trace in traces:
            params_list.append(
                [
                    trace.id,
                    trace.task_id,
                    trace.task_description,
                    trace.model,
                    _json_dumps(trace.model_config_params.model_dump()),
                    trace.adapter_type,
                    trace.system_message,
                    trace.prompt,
                    _json_dumps(trace.messages),
                    _json_dumps([tc.model_dump() for tc in trace.tool_calls]),
                    _json_dumps(trace.reasoning_tokens),
                    trace.reasoning_content,
                    trace.output,
                    trace.finish_reason,
                    trace.latency_ms,
                    _json_dumps(trace.token_usage.model_dump()),
                    _json_dumps(trace.metadata),
                    trace.timestamp,
                    trace.content_hash,
                ]
            )

        try:
            with self._lock:
                self.conn.execute("BEGIN TRANSACTION")
                try:
                    for params in params_list:
                        self.conn.execute(
                            """
                            INSERT INTO traces
                            (id, task_id, task_description, model, model_config_params, adapter_type,
                             system_message, prompt, messages, tool_calls, reasoning_tokens,
                             reasoning_content, output, finish_reason, latency_ms, token_usage,
                             metadata, timestamp, content_hash)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            ON CONFLICT (id) DO NOTHING
                            """,
                            params,
                        )
                    self.conn.execute("COMMIT")
                except Exception:
                    self.conn.execute("ROLLBACK")
                    raise
            return [t.id for t in traces]
        except Exception as e:
            raise StorageError(f"Failed to save trace batch: {e}")

    def get_trace(self, trace_id: str) -> ReasoningTrace:
        """Get a trace by ID."""
        row, cols = self._fetchone("SELECT * FROM traces WHERE id = ?", [trace_id])
        if not row:
            raise TraceNotFoundError(trace_id)
        return self._row_to_trace(row, cols)

    def get_traces_by_task(
        self, task_id: str, limit: int = 100, offset: int = 0
    ) -> list[ReasoningTrace]:
        """Get all traces for a task."""
        rows, cols = self._fetchall(
            "SELECT * FROM traces WHERE task_id = ? ORDER BY timestamp DESC LIMIT ? OFFSET ?",
            [task_id, limit, offset],
        )
        return [self._row_to_trace(r, cols) for r in rows]

    def get_recent_traces(self, limit: int = 50) -> list[ReasoningTrace]:
        """Get most recent traces."""
        rows, cols = self._fetchall("SELECT * FROM traces ORDER BY timestamp DESC LIMIT ?", [limit])
        return [self._row_to_trace(r, cols) for r in rows]

    def _row_to_trace(self, row: tuple, columns: list[str]) -> ReasoningTrace:
        """Convert a database row to a ReasoningTrace."""
        data = dict(zip(columns, row))

        # Parse JSON fields
        for field in (
            "model_config_params",
            "messages",
            "tool_calls",
            "reasoning_tokens",
            "token_usage",
            "metadata",
        ):
            if isinstance(data.get(field), str):
                data[field] = json.loads(data[field])

        return ReasoningTrace(**data)

    # ==================== Fingerprints ====================

    def save_fingerprint(
        self,
        fp: BehavioralFingerprint,
        *,
        session_id: Optional[str] = None,
        session_turn: Optional[int] = None,
    ) -> str:
        """Save a behavioral fingerprint."""
        try:
            # Generate ID if not present
            fp_id = f"fp_{fp.trace_id}"
            sid = session_id or fp.metadata.get("session_id")
            turn = session_turn if session_turn is not None else fp.metadata.get("session_turn")

            self._execute(
                """
                INSERT INTO fingerprints
                (id, trace_id, task_id, model, depth, branching_factor, total_steps,
                 max_step_length, tool_call_count, tool_call_sequence, tool_diversity,
                 tool_success_rate, output_length, reasoning_length, compression_ratio,
                 avg_sentence_length, correction_count, backtrack_count, revision_count,
                 uncertainty_markers, confidence_markers, hedging_ratio, verification_steps,
                 example_count, structured_output, tokens_per_step, reasoning_overhead,
                 signature_hash, metadata, timestamp, session_id, session_turn)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (id) DO UPDATE SET
                    trace_id = excluded.trace_id,
                    task_id = excluded.task_id,
                    model = excluded.model,
                    depth = excluded.depth,
                    branching_factor = excluded.branching_factor,
                    total_steps = excluded.total_steps,
                    max_step_length = excluded.max_step_length,
                    tool_call_count = excluded.tool_call_count,
                    tool_call_sequence = excluded.tool_call_sequence,
                    tool_diversity = excluded.tool_diversity,
                    tool_success_rate = excluded.tool_success_rate,
                    output_length = excluded.output_length,
                    reasoning_length = excluded.reasoning_length,
                    compression_ratio = excluded.compression_ratio,
                    avg_sentence_length = excluded.avg_sentence_length,
                    correction_count = excluded.correction_count,
                    backtrack_count = excluded.backtrack_count,
                    revision_count = excluded.revision_count,
                    uncertainty_markers = excluded.uncertainty_markers,
                    confidence_markers = excluded.confidence_markers,
                    hedging_ratio = excluded.hedging_ratio,
                    verification_steps = excluded.verification_steps,
                    example_count = excluded.example_count,
                    structured_output = excluded.structured_output,
                    tokens_per_step = excluded.tokens_per_step,
                    reasoning_overhead = excluded.reasoning_overhead,
                    signature_hash = excluded.signature_hash,
                    metadata = excluded.metadata,
                    timestamp = excluded.timestamp,
                    session_id = excluded.session_id,
                    session_turn = excluded.session_turn
            """,
                [
                    fp_id,
                    fp.trace_id,
                    fp.task_id,
                    fp.model,
                    fp.depth,
                    fp.branching_factor,
                    fp.total_steps,
                    fp.max_step_length,
                    fp.tool_call_count,
                    _json_dumps(fp.tool_call_sequence),
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
                    _json_dumps(fp.metadata),
                    fp.timestamp,
                    sid,
                    turn,
                ],
            )
            return fp_id
        except Exception as e:
            raise StorageError(f"Failed to save fingerprint: {e}")

    def get_fingerprint(self, fingerprint_id: str) -> BehavioralFingerprint:
        """Get a fingerprint by ID."""
        row, cols = self._fetchone("SELECT * FROM fingerprints WHERE id = ?", [fingerprint_id])
        if not row:
            raise StorageError(f"Fingerprint not found: {fingerprint_id}")
        return self._row_to_fingerprint(row, cols)

    def get_fingerprint_by_trace(self, trace_id: str) -> Optional[BehavioralFingerprint]:
        """Get fingerprint for a trace."""
        row, cols = self._fetchone("SELECT * FROM fingerprints WHERE trace_id = ?", [trace_id])
        if not row:
            return None
        return self._row_to_fingerprint(row, cols)

    def get_fingerprints_by_task(
        self, task_id: str, limit: int = 100
    ) -> list[BehavioralFingerprint]:
        """Get all fingerprints for a task."""
        rows, cols = self._fetchall(
            "SELECT * FROM fingerprints WHERE task_id = ? ORDER BY timestamp DESC LIMIT ?",
            [task_id, limit],
        )
        return [self._row_to_fingerprint(r, cols) for r in rows]

    def allocate_session_turn(self, session_id: str) -> int:
        """Atomically allocate the next turn number for a session."""
        with self._lock:
            row = self.conn.execute(
                "SELECT next_turn FROM session_counters WHERE session_id = ?",
                [session_id],
            ).fetchone()
            if row is None:
                turn = 1
                self.conn.execute(
                    "INSERT INTO session_counters (session_id, next_turn) VALUES (?, ?)",
                    [session_id, 2],
                )
            else:
                turn = int(row[0])
                self.conn.execute(
                    "UPDATE session_counters SET next_turn = ?, updated_at = CURRENT_TIMESTAMP "
                    "WHERE session_id = ?",
                    [turn + 1, session_id],
                )
            return turn

    def get_fingerprints_by_session(
        self, session_id: str, limit: int = 500
    ) -> list[BehavioralFingerprint]:
        """Get fingerprints for a session ordered by turn number."""
        rows, cols = self._fetchall(
            """
            SELECT * FROM fingerprints
            WHERE session_id = ?
            ORDER BY session_turn ASC, timestamp ASC
            LIMIT ?
            """,
            [session_id, limit],
        )
        return [self._row_to_fingerprint(r, cols) for r in rows]

    def get_session_turn_count(self, session_id: str) -> int:
        row, _ = self._fetchone(
            "SELECT COUNT(*) FROM fingerprints WHERE session_id = ?",
            [session_id],
        )
        return int(row[0]) if row else 0

    def _row_to_fingerprint(self, row: tuple, columns: list[str]) -> BehavioralFingerprint:
        """Convert a database row to a BehavioralFingerprint."""
        data = dict(zip(columns, row))

        # Parse JSON fields
        for field in ("tool_call_sequence", "metadata"):
            if isinstance(data.get(field), str):
                data[field] = json.loads(data[field])

        session_id = data.pop("session_id", None)
        session_turn = data.pop("session_turn", None)

        # Remove 'id' as it's not in the model
        del data["id"]

        fp = BehavioralFingerprint(**data)
        if session_id:
            fp.metadata["session_id"] = session_id
        if session_turn is not None:
            fp.metadata["session_turn"] = int(session_turn)
        return fp

    # ==================== Baselines ====================

    def save_baseline(self, baseline: Baseline) -> str:
        """Save a baseline."""
        try:
            self._execute(
                """
                INSERT INTO baselines
                (id, name, description, task_id, fingerprint_id, trace_id,
                 metadata, is_active, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (id) DO UPDATE SET
                    name = excluded.name,
                    description = excluded.description,
                    task_id = excluded.task_id,
                    fingerprint_id = excluded.fingerprint_id,
                    trace_id = excluded.trace_id,
                    metadata = excluded.metadata,
                    is_active = excluded.is_active,
                    created_at = excluded.created_at
            """,
                [
                    baseline.id,
                    baseline.name,
                    baseline.description,
                    baseline.task_id,
                    baseline.fingerprint_id,
                    baseline.trace_id,
                    _json_dumps(baseline.metadata),
                    baseline.is_active,
                    baseline.created_at,
                ],
            )
            return baseline.id
        except Exception as e:
            raise StorageError(f"Failed to save baseline: {e}")

    def get_baseline(self, name: str) -> Baseline:
        """Get a baseline by name."""
        row, cols = self._fetchone("SELECT * FROM baselines WHERE name = ?", [name])
        if not row:
            raise BaselineNotFoundError(name)
        return self._row_to_baseline(row, cols)

    def get_baseline_by_id(self, baseline_id: str) -> Baseline:
        """Get a baseline by ID."""
        row, cols = self._fetchone("SELECT * FROM baselines WHERE id = ?", [baseline_id])
        if not row:
            raise BaselineNotFoundError(baseline_id)
        return self._row_to_baseline(row, cols)

    def get_baselines_for_task(self, task_id: str) -> list[Baseline]:
        """Get all baselines for a task."""
        rows, cols = self._fetchall(
            "SELECT * FROM baselines WHERE task_id = ? AND is_active = TRUE ORDER BY created_at DESC",
            [task_id],
        )
        return [self._row_to_baseline(r, cols) for r in rows]

    def list_baselines(self, active_only: bool = True) -> list[Baseline]:
        """List all baselines."""
        if active_only:
            rows, cols = self._fetchall(
                "SELECT * FROM baselines WHERE is_active = TRUE ORDER BY created_at DESC"
            )
        else:
            rows, cols = self._fetchall("SELECT * FROM baselines ORDER BY created_at DESC")
        return [self._row_to_baseline(r, cols) for r in rows]

    def _row_to_baseline(self, row: tuple, columns: list[str]) -> Baseline:
        """Convert a database row to a Baseline."""
        data = dict(zip(columns, row))
        if isinstance(data.get("metadata"), str):
            data["metadata"] = json.loads(data["metadata"])
        return Baseline(**data)

    # ==================== Diffs ====================

    def save_diff(self, diff: BehaviorDiff) -> str:
        """Save a behavior diff."""
        try:
            diff_id = f"diff_{diff.baseline_id}_{diff.current_id}"
            self._execute(
                """
                INSERT INTO diffs
                (id, baseline_id, current_id, baseline_task_id, current_task_id,
                 changes, drift_score, significance, total_changes, breaking_changes,
                 summary, recommendations, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (id) DO UPDATE SET
                    baseline_id = excluded.baseline_id,
                    current_id = excluded.current_id,
                    baseline_task_id = excluded.baseline_task_id,
                    current_task_id = excluded.current_task_id,
                    changes = excluded.changes,
                    drift_score = excluded.drift_score,
                    significance = excluded.significance,
                    total_changes = excluded.total_changes,
                    breaking_changes = excluded.breaking_changes,
                    summary = excluded.summary,
                    recommendations = excluded.recommendations,
                    timestamp = excluded.timestamp
            """,
                [
                    diff_id,
                    diff.baseline_id,
                    diff.current_id,
                    diff.baseline_task_id,
                    diff.current_task_id,
                    _json_dumps([c.model_dump() for c in diff.changes]),
                    diff.drift_score,
                    (
                        diff.significance.value
                        if hasattr(diff.significance, "value")
                        else diff.significance
                    ),
                    diff.total_changes,
                    diff.breaking_changes,
                    diff.summary,
                    _json_dumps(diff.recommendations),
                    diff.timestamp,
                ],
            )
            return diff_id
        except Exception as e:
            raise StorageError(f"Failed to save diff: {e}")

    def get_recent_diffs(self, limit: int = 50) -> list[BehaviorDiff]:
        """Get most recent diffs."""
        rows, cols = self._fetchall("SELECT * FROM diffs ORDER BY timestamp DESC LIMIT ?", [limit])
        return [self._row_to_diff(r, cols) for r in rows]

    def _row_to_diff(self, row: tuple, columns: list[str]) -> BehaviorDiff:
        """Convert a database row to a BehaviorDiff."""
        data = dict(zip(columns, row))

        # Parse JSON fields
        if isinstance(data["changes"], str):
            data["changes"] = json.loads(data["changes"])
        if isinstance(data["recommendations"], str):
            data["recommendations"] = json.loads(data["recommendations"])

        # Remove the generated ID
        del data["id"]

        return BehaviorDiff(**data)

    # ==================== Drift Reports ====================

    def save_drift_report(self, report: DriftReport) -> str:
        """Save a drift report."""
        try:
            self._execute(
                """
                INSERT INTO drift_reports
                (id, task_id, baseline_id, start_time, end_time, drift_score,
                 drift_trend, significant_changes, sample_count, variance,
                 std_deviation, z_scores, summary)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (id) DO UPDATE SET
                    task_id = excluded.task_id,
                    baseline_id = excluded.baseline_id,
                    start_time = excluded.start_time,
                    end_time = excluded.end_time,
                    drift_score = excluded.drift_score,
                    drift_trend = excluded.drift_trend,
                    significant_changes = excluded.significant_changes,
                    sample_count = excluded.sample_count,
                    variance = excluded.variance,
                    std_deviation = excluded.std_deviation,
                    z_scores = excluded.z_scores,
                    summary = excluded.summary
            """,
                [
                    report.id,
                    report.task_id,
                    report.baseline_id,
                    report.start_time,
                    report.end_time,
                    report.drift_score,
                    report.drift_trend,
                    _json_dumps([c.model_dump() for c in report.significant_changes]),
                    report.sample_count,
                    report.variance,
                    report.std_deviation,
                    _json_dumps(report.z_scores),
                    report.summary,
                ],
            )
            return report.id
        except Exception as e:
            raise StorageError(f"Failed to save drift report: {e}")

    # ==================== Stats ====================

    def get_stats(self) -> dict[str, Any]:
        """Get database statistics."""
        trace_count = self._fetchone("SELECT COUNT(*) FROM traces")[0][0]
        fp_count = self._fetchone("SELECT COUNT(*) FROM fingerprints")[0][0]
        baseline_count = self._fetchone("SELECT COUNT(*) FROM baselines WHERE is_active = TRUE")[0][
            0
        ]
        diff_count = self._fetchone("SELECT COUNT(*) FROM diffs")[0][0]
        task_count = self._fetchone("SELECT COUNT(DISTINCT task_id) FROM traces")[0][0]

        return {
            "traces": trace_count,
            "fingerprints": fp_count,
            "baselines": baseline_count,
            "diffs": diff_count,
            "tasks": task_count,
        }


# Global database instance (thread-safe singleton)
_db: Optional[Database] = None
_db_lock = threading.Lock()


def get_database(db_path: Optional[Path] = None) -> Database:
    """Get or create the global database instance."""
    global _db
    if _db is None:
        with _db_lock:
            if _db is None:  # double-checked locking
                if db_path is None:
                    from cogscope.core.config import get_config

                    config = get_config()
                    db_path = config.get_db_path()
                _db = Database(db_path)
    return _db


def reset_database() -> None:
    """Reset the global database (useful for testing)."""
    global _db
    with _db_lock:
        if _db is not None:
            _db.close()
            _db = None
