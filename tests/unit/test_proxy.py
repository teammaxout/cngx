"""Proxy health and routing smoke tests."""

from starlette.testclient import TestClient

from cogscope.proxy.app import create_app


def test_proxy_health():
    client = TestClient(create_app())
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["service"] == "cogscope-proxy"


def test_proxy_missing_key_returns_502():
    client = TestClient(create_app())
    resp = client.post(
        "/v1/chat/completions",
        json={"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "hi"}]},
    )
    assert resp.status_code == 502
