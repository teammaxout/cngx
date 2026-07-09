"""
Lambda handler for opt-in tracker submissions.

Schema and validation rules must stay in sync with cngx/cli/submit_cmd.py.
Never log or persist client IP, headers, or any identity fields.
"""

from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime
from typing import Any

import boto3

# --- schema (mirror submit_cmd.py) ---
SCHEMA_VERSION = 1
MAX_BODY_BYTES = 8_192
MAX_STRING_LEN = 128

ALLOWED_KEYS = frozenset(
    {
        "schema_version",
        "record_id",
        "timestamp",
        "model",
        "baseline_label",
        "drift_score",
        "depth",
        "verification_steps",
        "hedging_ratio",
        "branching_factor",
        "total_steps",
        "correction_count",
        "uncertainty_markers",
        "output_length",
        "reasoning_length",
    }
)

FORBIDDEN_KEYS = frozenset(
    {
        "prompt",
        "output",
        "reasoning",
        "reasoning_content",
        "trace_id",
        "task_id",
        "messages",
        "content",
        "text",
        "description",
        "system_message",
        "user_message",
        "adapter_type",
        "metadata",
        "tool_call_sequence",
        "signature_hash",
    }
)

INT_MAX = 10_000
LENGTH_MAX = 10_000_000
UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    re.I,
)

s3 = boto3.client("s3")
BUCKET = os.environ["BUCKET_NAME"]
PREFIX = os.environ.get("OBJECT_PREFIX", "community")


def _response(status: int, body: dict[str, Any]) -> dict[str, Any]:
    return {
        "statusCode": status,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
        },
        "body": json.dumps(body),
    }


def _parse_body(raw: str | None, is_base64: bool) -> dict[str, Any]:
    if not raw:
        raise ValueError("empty body")
    if is_base64:
        import base64

        data = base64.b64decode(raw)
    else:
        data = raw.encode("utf-8")
    if len(data) > MAX_BODY_BYTES:
        raise ValueError("body too large")
    parsed = json.loads(data.decode("utf-8"))
    if not isinstance(parsed, dict):
        raise ValueError("body must be a JSON object")
    return parsed


def _validate_timestamp(value: str) -> None:
    if len(value) > MAX_STRING_LEN:
        raise ValueError("timestamp too long")
    text = value.rstrip("Z")
    try:
        datetime.fromisoformat(text)
    except ValueError as exc:
        raise ValueError("invalid timestamp") from exc


def _validate_payload(payload: dict[str, Any]) -> dict[str, Any]:
    keys = set(payload.keys())
    if keys != ALLOWED_KEYS:
        extra = keys - ALLOWED_KEYS
        missing = ALLOWED_KEYS - keys
        if extra:
            raise ValueError(f"disallowed keys: {sorted(extra)}")
        if missing:
            raise ValueError(f"missing keys: {sorted(missing)}")

    forbidden = keys & FORBIDDEN_KEYS
    if forbidden:
        raise ValueError(f"forbidden keys: {sorted(forbidden)}")

    if payload["schema_version"] != SCHEMA_VERSION:
        raise ValueError("unsupported schema_version")

    record_id = payload["record_id"]
    if not isinstance(record_id, str) or not UUID_RE.match(record_id):
        raise ValueError("invalid record_id")

    for field in ("model", "baseline_label"):
        val = payload[field]
        if not isinstance(val, str) or not val.strip() or len(val) > MAX_STRING_LEN:
            raise ValueError(f"invalid {field}")

    _validate_timestamp(payload["timestamp"])

    drift = payload["drift_score"]
    if not isinstance(drift, (int, float)) or drift < 0 or drift > 1:
        raise ValueError("drift_score out of range")

    hedging = payload["hedging_ratio"]
    if not isinstance(hedging, (int, float)) or hedging < 0 or hedging > 1:
        raise ValueError("hedging_ratio out of range")

    branching = payload["branching_factor"]
    if not isinstance(branching, (int, float)) or branching < 0 or branching > 100:
        raise ValueError("branching_factor out of range")

    for field in (
        "depth",
        "verification_steps",
        "total_steps",
        "correction_count",
        "uncertainty_markers",
    ):
        val = payload[field]
        if not isinstance(val, int) or isinstance(val, bool) or val < 0 or val > INT_MAX:
            raise ValueError(f"{field} out of range")

    for field in ("output_length", "reasoning_length"):
        val = payload[field]
        if not isinstance(val, int) or isinstance(val, bool) or val < 0 or val > LENGTH_MAX:
            raise ValueError(f"{field} out of range")

    serialized = json.dumps(payload).lower()
    for forbidden in FORBIDDEN_KEYS:
        if f'"{forbidden}"' in serialized:
            raise ValueError(f"forbidden key in serialized payload: {forbidden}")

    # Normalize numeric types for stable storage
    clean = {
        "schema_version": SCHEMA_VERSION,
        "record_id": record_id,
        "timestamp": payload["timestamp"],
        "model": payload["model"].strip(),
        "baseline_label": payload["baseline_label"].strip(),
        "drift_score": round(float(drift), 4),
        "depth": int(payload["depth"]),
        "verification_steps": int(payload["verification_steps"]),
        "hedging_ratio": round(float(hedging), 4),
        "branching_factor": round(float(branching), 4),
        "total_steps": int(payload["total_steps"]),
        "correction_count": int(payload["correction_count"]),
        "uncertainty_markers": int(payload["uncertainty_markers"]),
        "output_length": int(payload["output_length"]),
        "reasoning_length": int(payload["reasoning_length"]),
    }
    return clean


def _load_index() -> dict[str, Any]:
    key = f"{PREFIX}/index.json"
    try:
        obj = s3.get_object(Bucket=BUCKET, Key=key)
        return json.loads(obj["Body"].read().decode("utf-8"))
    except s3.exceptions.NoSuchKey:
        return {
            "schema_version": 1,
            "updated_at": datetime.utcnow().isoformat() + "Z",
            "by_model": {},
            "record_count": 0,
        }
    except Exception:
        return {
            "schema_version": 1,
            "updated_at": datetime.utcnow().isoformat() + "Z",
            "by_model": {},
            "record_count": 0,
        }


def _save_index(index: dict[str, Any]) -> None:
    index["updated_at"] = datetime.utcnow().isoformat() + "Z"
    body = json.dumps(index, indent=2) + "\n"
    s3.put_object(
        Bucket=BUCKET,
        Key=f"{PREFIX}/index.json",
        Body=body.encode("utf-8"),
        ContentType="application/json",
        CacheControl="public, max-age=120",
    )


def _append_to_index(record: dict[str, Any]) -> None:
    index = _load_index()
    by_model: dict[str, list] = index.setdefault("by_model", {})
    model = record["model"]
    records = by_model.setdefault(model, [])
    records = [r for r in records if r.get("record_id") != record["record_id"]]
    records.append(record)
    records.sort(key=lambda r: r.get("timestamp", ""))
    by_model[model] = records
    index["record_count"] = sum(len(v) for v in by_model.values())
    _save_index(index)


def handler(event: dict[str, Any], _context: Any) -> dict[str, Any]:
    method = (event.get("requestContext", {}).get("http", {}) or {}).get("method", "")
    if method == "OPTIONS":
        return _response(204, {})

    if method != "POST":
        return _response(405, {"error": "method not allowed"})

    try:
        body = event.get("body")
        is_b64 = bool(event.get("isBase64Encoded"))
        payload = _parse_body(body, is_b64)
        record = _validate_payload(payload)
    except (ValueError, json.JSONDecodeError) as exc:
        return _response(400, {"error": str(exc)})

    record_key = f"{PREFIX}/{record['record_id']}.json"
    record_body = json.dumps(record, indent=2) + "\n"

    try:
        s3.put_object(
            Bucket=BUCKET,
            Key=record_key,
            Body=record_body.encode("utf-8"),
            ContentType="application/json",
            CacheControl="public, max-age=300",
        )
        _append_to_index(record)
    except Exception:
        return _response(500, {"error": "storage failed"})

    return _response(
        201,
        {
            "ok": True,
            "record_id": record["record_id"],
        },
    )
