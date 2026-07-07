"""FastAPI application for Cogscope web UI."""

import json
import logging
import os
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

from cogscope import __version__
from cogscope.core.config import get_config
from cogscope.storage.database import get_database

logger = logging.getLogger("cogscope.server")

# ---------------------------------------------------------------------------
# Configuration from environment
# ---------------------------------------------------------------------------

MAX_REQUEST_BODY_BYTES = int(os.getenv("COGSCOPE_MAX_REQUEST_BODY", str(2 * 1024 * 1024)))  # 2 MB
RATE_LIMIT_RPM = int(os.getenv("COGSCOPE_RATE_LIMIT_RPM", "120"))  # 120 req/min default


# ---------------------------------------------------------------------------
# Simple in-process sliding-window rate limiter
# ---------------------------------------------------------------------------


class _RateLimiter:
    """Per-IP sliding window rate limiter."""

    def __init__(self, max_requests: int = 120, window_seconds: int = 60):
        self._max = max_requests
        self._window = window_seconds
        self._buckets: dict[str, list[float]] = {}

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        bucket = self._buckets.setdefault(key, [])
        # Evict expired entries
        bucket[:] = [t for t in bucket if now - t < self._window]
        if len(bucket) >= self._max:
            return False
        bucket.append(now)
        return True


_rate_limiter = _RateLimiter(max_requests=RATE_LIMIT_RPM, window_seconds=60)


# ---------------------------------------------------------------------------
# Lifespan — graceful startup / shutdown
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage server lifecycle — initialise DB on startup, close on shutdown."""
    logger.info("Cogscope server starting (v%s)", __version__)
    db = get_database()
    logger.info("Database ready (%s traces)", db.get_stats().get("traces", 0))
    yield
    logger.info("Cogscope server shutting down — closing database")
    db.close()
    logger.info("Shutdown complete")


app = FastAPI(
    title="Cogscope — Behavioral Contract Enforcement",
    description="Git for model behavior, not prompts",
    version=__version__,
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------

_cors_origins = os.getenv("COGSCOPE_CORS_ORIGINS", "http://localhost:3000,http://localhost:8642").split(
    ","
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _cors_origins],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
)


@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    """Add security headers and request-id to every response."""
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4())[:8])
    start = time.monotonic()

    response: Response = await call_next(request)

    # Security headers
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Request-ID"] = request_id

    # Timing header
    elapsed_ms = (time.monotonic() - start) * 1000
    response.headers["X-Response-Time-Ms"] = f"{elapsed_ms:.1f}"

    return response


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    """Rate-limit requests per client IP."""
    if request.url.path in ("/health", "/"):
        return await call_next(request)  # exempt health checks

    client_ip = request.client.host if request.client else "unknown"
    if not _rate_limiter.allow(client_ip):
        return JSONResponse(
            status_code=429,
            content={"detail": "Rate limit exceeded. Try again later."},
            headers={"Retry-After": "60"},
        )
    return await call_next(request)


@app.middleware("http")
async def request_size_limit_middleware(request: Request, call_next):
    """Reject requests with bodies larger than the configured limit."""
    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > MAX_REQUEST_BODY_BYTES:
        return JSONResponse(
            status_code=413,
            content={"detail": f"Request body too large. Max {MAX_REQUEST_BODY_BYTES} bytes."},
        )
    return await call_next(request)


# ==================== Models ====================


class CaptureRequest(BaseModel):
    prompt: str = Field(..., max_length=100_000)
    task_id: str = Field(default="default", max_length=500)
    system_message: Optional[str] = Field(default=None, max_length=50_000)
    model: str = Field(default="gpt-4o-mini", max_length=100)
    adapter: str = Field(default="mock", max_length=50)


class DiffRequest(BaseModel):
    baseline_id: str
    current_id: str


class DriftRequest(BaseModel):
    task_id: str
    baseline_name: Optional[str] = None
    window_hours: int = 24


# ==================== Health ====================


@app.get("/")
async def root():
    """Root endpoint with basic info."""
    return {
        "name": "Cogscope",
        "version": __version__,
        "status": "running",
    }


@app.get("/health")
async def health():
    """Health check — verifies database connectivity."""
    try:
        db = get_database()
        stats = db.get_stats()
        return {
            "status": "healthy",
            "version": __version__,
            "db_traces": stats.get("traces", 0),
        }
    except Exception as e:
        return JSONResponse(
            status_code=503,
            content={"status": "unhealthy", "error": str(e)},
        )


# ==================== Stats ====================


@app.get("/api/stats")
async def get_stats():
    """Get database statistics."""
    db = get_database()
    stats = db.get_stats()
    return stats


# ==================== Traces ====================


@app.get("/api/traces")
async def list_traces(
    task_id: Optional[str] = None,
    limit: int = 50,
):
    """List recent traces."""
    db = get_database()

    if task_id:
        traces = db.get_traces_by_task(task_id, limit=limit)
    else:
        traces = db.get_recent_traces(limit=limit)

    return [
        {
            "id": t.id,
            "task_id": t.task_id,
            "model": t.model,
            "timestamp": t.timestamp.isoformat(),
            "latency_ms": t.latency_ms,
            "tokens": t.token_usage.total_tokens,
        }
        for t in traces
    ]


@app.get("/api/traces/{trace_id}")
async def get_trace(trace_id: str):
    """Get a specific trace."""
    db = get_database()

    try:
        trace = db.get_trace(trace_id)
        fp = db.get_fingerprint_by_trace(trace_id)

        return {
            "trace": trace.model_dump(mode="json"),
            "fingerprint": fp.model_dump(mode="json") if fp else None,
        }
    except Exception as e:
        logger.warning("Trace not found: %s — %s", trace_id, e)
        raise HTTPException(status_code=404, detail="Trace not found")


@app.post("/api/capture")
async def capture_trace(request: CaptureRequest):
    """Capture a new trace."""
    from cogscope.capture.tracer import CogscopeTracer

    tracer = CogscopeTracer(adapter=request.adapter, model=request.model)

    try:
        trace = tracer.capture(
            prompt=request.prompt,
            task_id=request.task_id,
            system_message=request.system_message,
        )
        fp = tracer.get_fingerprint(trace.id)

        return {
            "trace_id": trace.id,
            "fingerprint": fp.model_dump(mode="json") if fp else None,
        }
    except Exception as e:
        logger.error("Capture failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Capture failed. Check server logs.")


@app.get("/api/baselines")
async def list_baselines(task_id: Optional[str] = None):
    """List baselines."""
    from cogscope.versioning.baseline import BaselineManager

    manager = BaselineManager()
    baselines = manager.list(task_id)

    return [
        {
            "id": b.id,
            "name": b.name,
            "task_id": b.task_id,
            "trace_id": b.trace_id,
            "created_at": b.created_at.isoformat(),
        }
        for b in baselines
    ]


@app.get("/api/baselines/{name}")
async def get_baseline(name: str):
    """Get baseline details."""
    from cogscope.versioning.baseline import BaselineManager

    manager = BaselineManager()

    try:
        baseline = manager.get(name)
        fp = manager.get_fingerprint(name)

        return {
            "baseline": baseline.model_dump(mode="json"),
            "fingerprint": fp.model_dump(mode="json"),
        }
    except Exception as e:
        logger.warning("Baseline not found: %s", e)
        raise HTTPException(status_code=404, detail="Baseline not found")


@app.post("/api/baselines")
async def create_baseline(
    trace_id: str,
    name: str,
    description: Optional[str] = None,
):
    """Create a new baseline."""
    from cogscope.versioning.baseline import BaselineManager

    manager = BaselineManager()

    try:
        baseline = manager.create(trace_id, name, description)
        return {"id": baseline.id, "name": baseline.name}
    except Exception as e:
        logger.error("Baseline creation failed: %s", e)
        raise HTTPException(status_code=400, detail="Failed to create baseline")


# ==================== Diff ====================


@app.post("/api/diff")
async def compute_diff(request: DiffRequest):
    """Compute diff between two fingerprints."""
    from cogscope.diff.engine import DiffEngine
    from cogscope.diff.formatter import DiffFormatter

    db = get_database()
    engine = DiffEngine()
    formatter = DiffFormatter()

    try:
        baseline_fp = db.get_fingerprint_by_trace(request.baseline_id)
        current_fp = db.get_fingerprint_by_trace(request.current_id)

        if not baseline_fp or not current_fp:
            raise HTTPException(status_code=404, detail="Fingerprints not found")

        diff = engine.diff(baseline_fp, current_fp)
        return formatter.format_dict(diff)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Diff computation failed: %s", e)
        raise HTTPException(status_code=500, detail="Diff computation failed")


# ==================== Drift ====================


@app.post("/api/drift")
async def detect_drift(request: DriftRequest):
    """Detect drift for a task."""
    from cogscope.drift.detector import DriftDetector

    detector = DriftDetector()

    try:
        report = detector.detect_drift(
            task_id=request.task_id,
            baseline_name=request.baseline_name,
            window_hours=request.window_hours,
        )
        return report.model_dump(mode="json")
    except Exception as e:
        logger.error("Drift detection failed: %s", e)
        raise HTTPException(status_code=500, detail="Drift detection failed")


# ==================== UI ====================


@app.get("/ui", response_class=HTMLResponse)
async def ui():
    """Minimal web UI."""
    return """
<!DOCTYPE html>
<html>
<head>
    <title>Cogscope — Behavioral Contract Enforcement</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #0d1117;
            color: #c9d1d9;
            padding: 20px;
        }
        .container { max-width: 1200px; margin: 0 auto; }
        h1 { color: #58a6ff; margin-bottom: 20px; }
        h2 { color: #8b949e; margin: 20px 0 10px; font-size: 1.2em; }
        .card {
            background: #161b22;
            border: 1px solid #30363d;
            border-radius: 6px;
            padding: 16px;
            margin-bottom: 16px;
        }
        .stats { display: flex; gap: 20px; flex-wrap: wrap; }
        .stat {
            background: #21262d;
            padding: 16px 24px;
            border-radius: 6px;
            text-align: center;
        }
        .stat-value { font-size: 2em; color: #58a6ff; }
        .stat-label { color: #8b949e; font-size: 0.9em; }
        table { width: 100%; border-collapse: collapse; }
        th, td { padding: 10px; text-align: left; border-bottom: 1px solid #30363d; }
        th { color: #8b949e; font-weight: 500; }
        .badge {
            display: inline-block;
            padding: 2px 8px;
            border-radius: 3px;
            font-size: 0.85em;
        }
        .badge-green { background: #238636; }
        .badge-yellow { background: #9e6a03; }
        .badge-red { background: #da3633; }
        #loading { color: #8b949e; }
    </style>
</head>
<body>
    <div class="container">
        <h1>Cogscope — Behavioral Contract Enforcement</h1>

        <div class="card">
            <h2>Statistics</h2>
            <div id="stats" class="stats">
                <div id="loading">Loading...</div>
            </div>
        </div>

        <div class="card">
            <h2>Recent Traces</h2>
            <table id="traces">
                <thead>
                    <tr>
                        <th>ID</th>
                        <th>Task</th>
                        <th>Model</th>
                        <th>Timestamp</th>
                        <th>Latency</th>
                    </tr>
                </thead>
                <tbody id="traces-body"></tbody>
            </table>
        </div>

        <div class="card">
            <h2>Baselines</h2>
            <table id="baselines">
                <thead>
                    <tr>
                        <th>Name</th>
                        <th>Task</th>
                        <th>Created</th>
                    </tr>
                </thead>
                <tbody id="baselines-body"></tbody>
            </table>
        </div>
    </div>

    <script>
        async function loadStats() {
            try {
                const res = await fetch('/api/stats');
                const data = await res.json();
                document.getElementById('stats').innerHTML = `
                    <div class="stat"><div class="stat-value">${data.traces}</div><div class="stat-label">Traces</div></div>
                    <div class="stat"><div class="stat-value">${data.fingerprints}</div><div class="stat-label">Fingerprints</div></div>
                    <div class="stat"><div class="stat-value">${data.baselines}</div><div class="stat-label">Baselines</div></div>
                    <div class="stat"><div class="stat-value">${data.tasks}</div><div class="stat-label">Tasks</div></div>
                `;
            } catch (e) {
                document.getElementById('stats').innerHTML = '<div>Error loading stats</div>';
            }
        }

        async function loadTraces() {
            try {
                const res = await fetch('/api/traces?limit=10');
                const data = await res.json();
                document.getElementById('traces-body').innerHTML = data.map(t => `
                    <tr>
                        <td>${t.id.substring(0, 20)}...</td>
                        <td>${t.task_id}</td>
                        <td>${t.model}</td>
                        <td>${new Date(t.timestamp).toLocaleString()}</td>
                        <td>${Math.round(t.latency_ms)}ms</td>
                    </tr>
                `).join('');
            } catch (e) {
                document.getElementById('traces-body').innerHTML = '<tr><td colspan="5">Error loading traces</td></tr>';
            }
        }

        async function loadBaselines() {
            try {
                const res = await fetch('/api/baselines');
                const data = await res.json();
                if (data.length === 0) {
                    document.getElementById('baselines-body').innerHTML = '<tr><td colspan="3">No baselines yet</td></tr>';
                    return;
                }
                document.getElementById('baselines-body').innerHTML = data.map(b => `
                    <tr>
                        <td>${b.name}</td>
                        <td>${b.task_id}</td>
                        <td>${new Date(b.created_at).toLocaleString()}</td>
                    </tr>
                `).join('');
            } catch (e) {
                document.getElementById('baselines-body').innerHTML = '<tr><td colspan="3">Error loading baselines</td></tr>';
            }
        }

        loadStats();
        loadTraces();
        loadBaselines();
    </script>
</body>
</html>
"""
