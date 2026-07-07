"""Tests for session id resolution."""

from cogscope.drift.session import resolve_session_id


def test_explicit_session_id_wins():
    sid = resolve_session_id(
        explicit="my-session",
        headers={"x-session-id": "header-session"},
        body={"metadata": {"session_id": "body-session"}},
    )
    assert sid == "my-session"


def test_header_session_id():
    sid = resolve_session_id(headers={"X-Session-Id": "conv-123"})
    assert sid == "conv-123"


def test_auto_detect_from_messages():
    body = {
        "messages": [
            {"role": "system", "content": "You are helpful"},
            {"role": "user", "content": "Hello"},
        ]
    }
    sid = resolve_session_id(body=body)
    assert sid.startswith("auto_")


def test_same_messages_same_auto_session():
    body = {"messages": [{"role": "user", "content": "ping"}]}
    assert resolve_session_id(body=body) == resolve_session_id(body=body)
