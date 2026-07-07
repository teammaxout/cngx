"""Session id resolution for multi-turn proxy traffic."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping, Optional

_SESSION_HEADER_KEYS = (
    "x-cogscope-session-id",
    "x-session-id",
    "x-conversation-id",
    "x-openai-conversation-id",
    "anthropic-conversation-id",
)


def _normalize_messages(messages: list[dict[str, Any]]) -> str:
    """Stable prefix of message history for auto session detection."""
    parts: list[str] = []
    for msg in messages[:6]:
        role = str(msg.get("role", ""))
        content = msg.get("content", "")
        if isinstance(content, list):
            text = " ".join(str(p.get("text", "")) for p in content if isinstance(p, dict))
        else:
            text = str(content)
        parts.append(f"{role}:{text[:120]}")
    return "|".join(parts)


def resolve_session_id(
    *,
    explicit: Optional[str] = None,
    headers: Optional[Mapping[str, str]] = None,
    body: Optional[dict[str, Any]] = None,
) -> str:
    """Resolve session id: explicit flag > headers > body metadata > message hash."""
    if explicit and explicit.strip():
        return explicit.strip()

    if headers:
        lowered = {k.lower(): v for k, v in headers.items()}
        for key in _SESSION_HEADER_KEYS:
            value = lowered.get(key)
            if value and str(value).strip():
                return str(value).strip()

    if body:
        meta = body.get("metadata") or {}
        if isinstance(meta, dict):
            for key in ("session_id", "conversation_id", "thread_id"):
                value = meta.get(key)
                if value and str(value).strip():
                    return str(value).strip()
        for key in ("session_id", "conversation_id"):
            value = body.get(key)
            if value and str(value).strip():
                return str(value).strip()

        messages = body.get("messages")
        if isinstance(messages, list) and messages:
            digest = hashlib.sha256(_normalize_messages(messages).encode()).hexdigest()[:16]
            return f"auto_{digest}"

    return "default"
