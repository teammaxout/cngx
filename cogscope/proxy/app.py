"""ASGI reverse proxy for OpenAI-compatible APIs."""

from __future__ import annotations

import json
import logging
import os
import time
from typing import AsyncIterator, Optional

import httpx
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response, StreamingResponse
from starlette.routing import Route

from cogscope.drift.session import resolve_session_id
from cogscope.proxy.analysis import schedule_analysis
from cogscope.proxy.config import get_proxy_config

logger = logging.getLogger("cogscope.proxy")


def _upstream_for_path(path: str) -> tuple[str, str, dict[str, str]] | None:
    """Return (provider, url, auth_headers), keys read from env, never logged."""
    if path.endswith("/v1/chat/completions") or path == "/v1/chat/completions":
        key = os.getenv("OPENAI_API_KEY") or os.getenv("COGSCOPE_OPENAI_API_KEY")
        if not key:
            return None
        base = os.getenv("OPENAI_BASE_URL", "https://api.openai.com")
        return (
            "openai",
            f"{base.rstrip('/')}/v1/chat/completions",
            {"Authorization": f"Bearer {key}"},
        )
    if path.endswith("/v1/messages") or path == "/v1/messages":
        key = os.getenv("ANTHROPIC_API_KEY")
        if not key:
            return None
        return (
            "anthropic",
            "https://api.anthropic.com/v1/messages",
            {
                "x-api-key": key,
                "anthropic-version": "2023-06-01",
            },
        )
    return None


def _task_id_from_request(request: Request, body: dict) -> str:
    header = request.headers.get("x-cogscope-task-id") or request.headers.get("X-Cogscope-Task-Id")
    if header:
        return header
    meta = body.get("metadata") or {}
    if isinstance(meta, dict) and meta.get("task_id"):
        return str(meta["task_id"])
    return get_proxy_config().default_task_id


def _session_id_from_request(request: Request, body: dict) -> str:
    cfg = get_proxy_config()
    return resolve_session_id(
        explicit=cfg.default_session_id,
        headers=request.headers,
        body=body,
    )


async def health(_: Request) -> JSONResponse:
    return JSONResponse({"status": "ok", "service": "cogscope-proxy"})


async def proxy_handler(request: Request) -> Response:
    upstream = _upstream_for_path(request.url.path)
    if upstream is None:
        return JSONResponse(
            {"error": "No upstream API key configured for this route"},
            status_code=502,
        )

    provider, url, auth_headers = upstream
    body_bytes = await request.body()
    try:
        body = json.loads(body_bytes) if body_bytes else {}
    except json.JSONDecodeError:
        body = {}

    task_id = _task_id_from_request(request, body)
    session_id = _session_id_from_request(request, body)
    is_stream = bool(body.get("stream"))
    start = time.monotonic()

    forward_headers = {
        "Content-Type": request.headers.get("content-type", "application/json"),
        **auth_headers,
    }

    client = httpx.AsyncClient(timeout=httpx.Timeout(300.0, connect=30.0))

    if is_stream and provider == "openai":
        return await _stream_openai(
            client, url, forward_headers, body_bytes, body, task_id, session_id, provider, start
        )

    try:
        resp = await client.post(url, content=body_bytes, headers=forward_headers)
        latency_ms = (time.monotonic() - start) * 1000
        content = resp.content
        schedule_analysis(
            provider, body, content, task_id, latency_ms, was_stream=False, session_id=session_id
        )
        return Response(
            content=content,
            status_code=resp.status_code,
            media_type=resp.headers.get("content-type", "application/json"),
        )
    finally:
        await client.aclose()


async def _stream_openai(
    client: httpx.AsyncClient,
    url: str,
    headers: dict,
    body_bytes: bytes,
    body: dict,
    task_id: str,
    session_id: str,
    provider: str,
    start: float,
) -> StreamingResponse:
    collected: list[bytes] = []

    async def generate() -> AsyncIterator[bytes]:
        nonlocal collected
        try:
            async with client.stream("POST", url, content=body_bytes, headers=headers) as resp:
                if resp.status_code >= 400:
                    err = await resp.aread()
                    yield err
                    return
                async for chunk in resp.aiter_bytes():
                    collected.append(chunk)
                    yield chunk
        finally:
            await client.aclose()
            latency_ms = (time.monotonic() - start) * 1000
            merged = b"".join(collected)
            schedule_analysis(
                provider,
                body,
                merged,
                task_id,
                latency_ms,
                was_stream=True,
                session_id=session_id,
            )

    return StreamingResponse(generate(), media_type="text/event-stream")


def create_app() -> Starlette:
    return Starlette(
        routes=[
            Route("/health", health),
            Route("/v1/chat/completions", proxy_handler, methods=["POST"]),
            Route("/v1/messages", proxy_handler, methods=["POST"]),
        ],
    )


app = create_app()
