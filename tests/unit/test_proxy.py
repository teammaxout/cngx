"""Proxy health and routing smoke tests."""

import os

from starlette.testclient import TestClient

from cngx.proxy.app import create_app


def test_proxy_health():
    client = TestClient(create_app())
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["service"] == "cngx-proxy"


def test_proxy_missing_key_returns_502(monkeypatch):
    """Without a provider key the proxy must fail closed, not forward."""
    for key in (
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "GOOGLE_API_KEY",
        "GEMINI_API_KEY",
    ):
        monkeypatch.delenv(key, raising=False)

    client = TestClient(create_app())
    resp = client.post(
        "/v1/chat/completions",
        json={"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "hi"}]},
    )
    assert resp.status_code == 502
    body = resp.json()
    assert "error" in body or "detail" in body or "message" in str(body).lower()
