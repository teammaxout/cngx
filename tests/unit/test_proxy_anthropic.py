"""Anthropic proxy fingerprinting (stream + non-stream)."""

from __future__ import annotations

import inspect
import json

import pytest

from cngx.core.config import get_config, reset_config
from cngx.proxy import analysis
from cngx.proxy.app import create_app, proxy_handler
from cngx.storage.database import reset_database


@pytest.fixture(autouse=True)
def _reset(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    reset_config()
    reset_database()
    get_config(project_root=tmp_path).ensure_cngx_dir()
    yield
    reset_config()
    reset_database()


def test_proxy_streams_anthropic_like_openai():
    """Anthropic streaming must use the same passthrough+fingerprint path."""
    src = inspect.getsource(proxy_handler)
    assert 'provider in ("openai", "anthropic")' in src
    assert "_stream_and_fingerprint" in src


def test_parse_anthropic_non_stream():
    body = {
        "id": "msg_test",
        "type": "message",
        "role": "assistant",
        "model": "claude-sonnet-4-20250514",
        "content": [{"type": "text", "text": "Let me verify the tests passed."}],
        "usage": {"input_tokens": 12, "output_tokens": 8},
    }
    parsed = analysis._parse_anthropic_response(json.dumps(body).encode(), was_stream=False)
    assert parsed is not None
    assert analysis._anthropic_text_from_content(parsed.get("content")).startswith("Let me verify")


def test_parse_anthropic_stream_sse():
    sse = (
        "event: message_start\n"
        'data: {"type":"message_start","message":{"model":"claude-sonnet-4-20250514",'
        '"usage":{"input_tokens":5}}}\n\n'
        "event: content_block_delta\n"
        'data: {"type":"content_block_delta","delta":{"type":"text_delta",'
        '"text":"Step 1: plan. "}}\n\n'
        "event: content_block_delta\n"
        'data: {"type":"content_block_delta","delta":{"type":"text_delta",'
        '"text":"Tests passed."}}\n\n'
        "event: message_delta\n"
        'data: {"type":"message_delta","usage":{"output_tokens":4}}\n\n'
        "event: message_stop\n"
        'data: {"type":"message_stop"}\n\n'
    )
    parsed = analysis._parse_anthropic_response(sse.encode(), was_stream=True)
    assert parsed is not None
    text = analysis._anthropic_text_from_content(parsed.get("content"))
    assert "Step 1: plan." in text
    assert "Tests passed." in text
    assert parsed.get("model") == "claude-sonnet-4-20250514"
    assert parsed.get("usage", {}).get("input_tokens") == 5
    assert parsed.get("usage", {}).get("output_tokens") == 4


@pytest.mark.asyncio
async def test_analyze_anthropic_non_stream_persists_fingerprint():
    request = {
        "model": "claude-sonnet-4-20250514",
        "max_tokens": 256,
        "messages": [{"role": "user", "content": "Fix the bug and run tests"}],
    }
    response = {
        "id": "msg_test",
        "type": "message",
        "role": "assistant",
        "model": "claude-sonnet-4-20250514",
        "content": [
            {
                "type": "text",
                "text": (
                    "Step 1: inspect the failing test.\n"
                    "I ran pytest and saw 12 passed.\n"
                    "Step 2: apply the fix."
                ),
            }
        ],
        "usage": {"input_tokens": 20, "output_tokens": 40},
    }
    await analysis.analyze_completed_call(
        "anthropic",
        request,
        json.dumps(response).encode(),
        task_id="anthropic-fp-test",
        latency_ms=12.0,
        was_stream=False,
        session_id="sess-anthropic",
    )
    from cngx.storage.database import get_database

    db = get_database()
    stats = db.get_stats()
    assert stats["traces"] >= 1
    assert stats["fingerprints"] >= 1
    fps = db.get_fingerprints_by_session("sess-anthropic")
    assert len(fps) >= 1
    assert fps[0].output_length > 0


@pytest.mark.asyncio
async def test_analyze_anthropic_stream_persists_fingerprint():
    request = {
        "model": "claude-sonnet-4-20250514",
        "max_tokens": 256,
        "stream": True,
        "messages": [{"role": "user", "content": "hi"}],
    }
    sse = (
        'data: {"type":"message_start","message":{"model":"claude-sonnet-4-20250514",'
        '"usage":{"input_tokens":3}}}\n\n'
        'data: {"type":"content_block_delta","delta":{"type":"text_delta",'
        '"text":"Verified with pytest: 3 passed."}}\n\n'
        'data: {"type":"message_stop"}\n\n'
    )
    await analysis.analyze_completed_call(
        "anthropic",
        request,
        sse.encode(),
        task_id="anthropic-stream-fp",
        latency_ms=8.0,
        was_stream=True,
        session_id="sess-anthropic-stream",
    )
    from cngx.storage.database import get_database

    db = get_database()
    fps = db.get_fingerprints_by_session("sess-anthropic-stream")
    assert len(fps) >= 1


def test_proxy_app_still_healthy():
    from starlette.testclient import TestClient

    client = TestClient(create_app())
    assert client.get("/health").json()["service"] == "cngx-proxy"
