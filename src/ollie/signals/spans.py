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
    span: dict[str, Any] = {
        "type": span_type,
        "name": str(ix.get("name") or span_type),
        "status": interaction_status(ix),
        "span_ref": str(ix.get("interaction_ref") or ""),
    }
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
