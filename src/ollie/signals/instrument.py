"""Build warehouse events (_signal_hits; empty trigger/context) for AI SDK workflows."""

from __future__ import annotations

from typing import Any

from ollie.signals.baselines import baseline_signals
from ollie.signals.direct import _dedupe, direct_signals_for_interactions, direct_signals_for_unit
from ollie.signals.hits import hits_from_named_signals
from ollie.signals.spans import interaction_to_span, interactions_to_spans


def empty_events() -> dict[str, Any]:
    return {"trigger": [], "context": [], "spans": []}


def instrument_run(
    *,
    interactions: list[dict[str, Any]],
    root_output: str | None,
    workflow_success: bool,
    workflow_latency_ms: int = 0,
    interaction_ref: str = "ix_0",
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Run-level events + anchored hits for the root interaction."""
    spans = interactions_to_spans(interactions)
    trig_d, ctx_d = direct_signals_for_interactions(interactions)
    trig_b, ctx_b = baseline_signals(
        interactions=interactions,
        root_output=root_output,
        workflow_success=workflow_success,
        workflow_latency_ms=workflow_latency_ms,
    )
    trigger = _dedupe(trig_d + trig_b)
    context = _dedupe(ctx_d + ctx_b)
    hits = hits_from_named_signals(
        trigger=trigger,
        context=context,
        spans=spans,
        interaction_ref=interaction_ref,
    )
    return ({"trigger": [], "context": [], "spans": spans}, hits)


def instrument_unit(ix: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Per-child events: local signals + single self-span."""
    span = interaction_to_span(ix)
    spans = [span] if span else []
    ref = str(ix.get("interaction_ref") or "")
    if not ix.get("parent_interaction_ref"):
        return empty_events(), []
    trig, ctx = direct_signals_for_unit(ix)
    _, ctx_b = baseline_signals(
        interactions=[ix],
        root_output=str(ix.get("output") or ""),
        workflow_success=True,
        workflow_latency_ms=0,
    )
    skip = {"empty_final_response", "runtime_failure", "used_tool", "tool_loop"}
    ctx_b = [s for s in ctx_b if s.get("name") not in skip]
    trigger = _dedupe(trig)
    context = _dedupe(ctx + ctx_b)
    hits = hits_from_named_signals(
        trigger=trigger,
        context=context,
        spans=spans,
        interaction_ref=ref or "ix_0",
    )
    return ({"trigger": [], "context": [], "spans": spans}, hits)


def finalize_interactions(
    interactions: list[dict[str, Any]],
    *,
    workflow_success: bool,
    workflow_latency_ms: int = 0,
) -> list[dict[str, Any]]:
    """Attach events + _signal_hits to root and each child; return new list."""
    if not interactions:
        return []

    roots = [ix for ix in interactions if not ix.get("parent_interaction_ref")]
    root = roots[0] if roots else interactions[0]
    root_ref = str(root.get("interaction_ref") or "")

    run_events, run_hits = instrument_run(
        interactions=interactions,
        root_output=str(root.get("output") or ""),
        workflow_success=workflow_success,
        workflow_latency_ms=workflow_latency_ms,
        interaction_ref=root_ref or "ix_0",
    )

    out: list[dict[str, Any]] = []
    for ix in interactions:
        row = dict(ix)
        ref = str(ix.get("interaction_ref") or "")
        if ref == root_ref or not ix.get("parent_interaction_ref"):
            row["events"] = run_events
            row["_signal_hits"] = run_hits
        else:
            events, hits = instrument_unit(ix)
            row["events"] = events
            row["_signal_hits"] = hits
        out.append(row)
    return out
