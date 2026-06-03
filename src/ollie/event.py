"""Stable SDK event envelope (Layer 1)."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from ollie.trace import utc_now_iso

EVENT_TYPE_TRACE_VALIDATE = "sdk.trace.validate"
EVENT_TYPE_TRACE_PROCESS = "sdk.trace.process"
EVENT_TYPE_TRACE_INGEST = "sdk.trace.ingest"


def new_event_id() -> str:
    return str(uuid4())


def session_id_from_payload(payload: dict[str, Any]) -> str:
    cid = str(payload.get("conversation_id") or "").strip()
    if cid:
        return cid
    aid = str(payload.get("agent_id") or "").strip()
    return aid or "session-unknown"


def build_event(
    *,
    event_type: str,
    payload: dict[str, Any],
    event_id: str | None = None,
) -> dict[str, Any]:
    agent_id = str(payload.get("agent_id") or "").strip()
    if not agent_id:
        raise ValueError("payload.agent_id is required")
    return {
        "event_id": event_id or new_event_id(),
        "agent_id": agent_id,
        "session_id": session_id_from_payload(payload),
        "timestamp": utc_now_iso(),
        "event_type": event_type,
        "payload": payload,
    }
