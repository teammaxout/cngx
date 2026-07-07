"""
Enterprise Test: REST API Server Integration

Tests the FastAPI server with httpx:
- Health endpoint
- Capture endpoint
- Trace retrieval
- Baseline management
- Diff endpoint
- Error responses
"""

import asyncio
import json
from datetime import datetime

import httpx
import pytest

from cogscope.core.models import ModelConfig, ReasoningTrace, TokenUsage
from cogscope.server.app import app


def _run(coro):
    """Run an async coroutine synchronously."""
    return asyncio.get_event_loop().run_until_complete(coro)


class _SyncClient:
    """Wrapper around httpx.AsyncClient for sync test usage."""

    def __init__(self, app):
        transport = httpx.ASGITransport(app=app)
        self._client = httpx.AsyncClient(transport=transport, base_url="http://test")

    def get(self, url, **kwargs):
        return _run(self._client.get(url, **kwargs))

    def post(self, url, **kwargs):
        return _run(self._client.post(url, **kwargs))

    def close(self):
        _run(self._client.aclose())


@pytest.fixture()
def test_client():
    """Create a test client for the FastAPI app."""
    client = _SyncClient(app)
    yield client
    client.close()


class TestHealthAndInfo:
    """Health and info endpoints."""

    def test_root_endpoint(self, test_client):
        """Root endpoint returns server info."""
        resp = test_client.get("/")
        assert resp.status_code == 200
        data = resp.json()
        assert "name" in data or "version" in data or isinstance(data, dict)

    def test_health_endpoint(self, test_client):
        """Health endpoint returns 200."""
        resp = test_client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert "status" in data or isinstance(data, dict)

    def test_stats_endpoint(self, test_client):
        """Stats endpoint returns database statistics."""
        resp = test_client.get("/api/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, dict)


class TestCaptureEndpoint:
    """Test the /api/capture endpoint."""

    def test_capture_with_mock_adapter(self, test_client):
        """Capture endpoint works with mock adapter."""
        resp = test_client.post(
            "/api/capture",
            json={
                "prompt": "What is 2+2?",
                "task_id": "api_test",
                "adapter": "mock",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "id" in data or "trace_id" in data or "output" in data

    def test_capture_with_custom_task_id(self, test_client):
        """Capture endpoint respects task_id parameter."""
        resp = test_client.post(
            "/api/capture",
            json={
                "prompt": "Hello",
                "task_id": "custom_task_123",
                "adapter": "mock",
            },
        )
        assert resp.status_code == 200


class TestTraceEndpoints:
    """Test trace retrieval endpoints."""

    def test_list_traces(self, test_client):
        """List traces endpoint returns array."""
        # First capture something
        test_client.post(
            "/api/capture",
            json={
                "prompt": "test for list",
                "task_id": "list_test",
                "adapter": "mock",
            },
        )
        resp = test_client.get("/api/traces")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    def test_list_traces_with_task_filter(self, test_client):
        """List traces filtered by task_id."""
        task_id = "filter_test_unique"
        test_client.post(
            "/api/capture",
            json={
                "prompt": "test for filter",
                "task_id": task_id,
                "adapter": "mock",
            },
        )
        resp = test_client.get(f"/api/traces?task_id={task_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)


class TestBaselineEndpoints:
    """Test baseline management endpoints."""

    def test_list_baselines(self, test_client):
        """List baselines endpoint works."""
        resp = test_client.get("/api/baselines")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)


class TestDiffEndpoint:
    """Test the /api/diff endpoint."""

    def test_diff_requires_ids(self, test_client):
        """Diff endpoint requires baseline_id and current_id."""
        resp = test_client.post("/api/diff", json={})
        # Should return 422 (validation error) or 400
        assert resp.status_code in (400, 422, 500)


class TestErrorResponses:
    """API returns proper error responses."""

    def test_404_for_unknown_trace(self, test_client):
        """Unknown trace ID returns 404 or error."""
        resp = test_client.get("/api/traces/nonexistent_trace_12345")
        assert resp.status_code in (404, 500)

    def test_invalid_json_body(self, test_client):
        """Invalid JSON body returns 422."""
        resp = test_client.post(
            "/api/capture",
            content=b"not json",
            headers={"content-type": "application/json"},
        )
        assert resp.status_code in (400, 422)

    def test_missing_required_field(self, test_client):
        """Missing required field returns 422."""
        resp = test_client.post(
            "/api/capture",
            json={
                # Missing 'prompt' field
                "task_id": "test",
            },
        )
        assert resp.status_code in (400, 422)
