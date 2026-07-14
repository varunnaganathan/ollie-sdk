"""Map interactions to minimal cold-path span records."""

from __future__ import annotations

from typing import Any

from ollie.primitives import EXTERNAL_INTERACTION, GENERATION


def _attrs_map(ix: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for a in ix.get("attributes") or []:
        if isinstance(a, dict) and a.get("name") is not None:
            out[str(a["name"])] = a.get("value")
    return out


def interaction_status(ix: dict[str, Any]) -> str:
    attrs = _attrs_map(ix)
    if attrs.get("success") is False:
        return "failure"
    status = str(attrs.get("status") or "").strip().lower()
    if status in ("error", "failure", "failed"):
        return "failure"
    return "success"


def interaction_to_span(ix: dict[str, Any]) -> dict[str, Any] | None:
    """Return minimal span for a non-root interaction, or None for root/unknown."""
    if not ix.get("parent_interaction_ref"):
        return None
    prim = str(ix.get("primitive") or "").strip()
    if prim == GENERATION:
        span_type = "llm"
    elif prim == EXTERNAL_INTERACTION:
        span_type = "tool"
    else:
        return None
    name = str(ix.get("name") or span_type)
    status = interaction_status(ix)
    attrs = _attrs_map(ix)
    props: dict[str, Any] = {"kind": span_type, "name": name, "status": status}
    for key in ("latency_ms", "token_count", "finish_reason", "error_type", "model", "provider"):
        # map latency_ms -> duration_ms for warehouse
        if key == "latency_ms" and attrs.get(key) is not None:
            props["duration_ms"] = attrs[key]
        elif attrs.get(key) is not None:
            props[key] = attrs[key]
    inp = str(ix.get("input") or "").strip()
    out = str(ix.get("output") or "").strip()
    span: dict[str, Any] = {
        "type": span_type,
        "name": name,
        "status": status,
        "span_ref": str(ix.get("interaction_ref") or ""),
        "input": {"text": inp} if inp else {},
        "output": {"text": out} if out else {},
        "properties": props,
    }
    if "duration_ms" in props:
        span["duration_ms"] = props["duration_ms"]
    if "token_count" in props:
        span["token_count"] = props["token_count"]
    if "finish_reason" in props:
        span["finish_reason"] = props["finish_reason"]
    parent = ix.get("parent_interaction_ref")
    if parent:
        span["parent_span_ref"] = str(parent)
    return span


def interactions_to_spans(interactions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    spans: list[dict[str, Any]] = []
    for ix in interactions:
        span = interaction_to_span(ix)
        if span and span.get("span_ref"):
            spans.append(span)
    return spans
