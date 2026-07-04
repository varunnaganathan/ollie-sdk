"""Build ADK-shaped events (trigger / context / spans) for AI SDK workflows."""

from __future__ import annotations

from typing import Any

from ollie.signals.baselines import baseline_signals
from ollie.signals.direct import _dedupe, direct_signals_for_interactions, direct_signals_for_unit
from ollie.signals.spans import interaction_to_span, interactions_to_spans


def empty_events() -> dict[str, Any]:
    return {"trigger": [], "context": [], "spans": []}


def instrument_run(
    *,
    interactions: list[dict[str, Any]],
    root_output: str | None,
    workflow_success: bool,
    workflow_latency_ms: int = 0,
) -> dict[str, Any]:
    """Run-level events for the root interaction."""
    spans = interactions_to_spans(interactions)
    trig_d, ctx_d = direct_signals_for_interactions(interactions)
    trig_b, ctx_b = baseline_signals(
        interactions=interactions,
        root_output=root_output,
        workflow_success=workflow_success,
        workflow_latency_ms=workflow_latency_ms,
    )
    return {
        "trigger": _dedupe(trig_d + trig_b),
        "context": _dedupe(ctx_d + ctx_b),
        "spans": spans,
    }


def instrument_unit(ix: dict[str, Any]) -> dict[str, Any]:
    """Per-child events: local signals + single self-span."""
    span = interaction_to_span(ix)
    spans = [span] if span else []
    if not ix.get("parent_interaction_ref"):
        return empty_events()
    trig, ctx = direct_signals_for_unit(ix)
    # Unit-level baselines that apply to a single generation
    from ollie.signals.baselines import baseline_signals

    _, ctx_b = baseline_signals(
        interactions=[ix],
        root_output=str(ix.get("output") or ""),
        workflow_success=True,
        workflow_latency_ms=0,
    )
    # Avoid run-only signals on units
    skip = {"empty_final_response", "runtime_failure", "used_tool", "tool_loop"}
    ctx_b = [s for s in ctx_b if s.get("name") not in skip]
    return {
        "trigger": _dedupe(trig),
        "context": _dedupe(ctx + ctx_b),
        "spans": spans,
    }


def finalize_interactions(
    interactions: list[dict[str, Any]],
    *,
    workflow_success: bool,
    workflow_latency_ms: int = 0,
) -> list[dict[str, Any]]:
    """Attach structured events to root and each child; return new list."""
    if not interactions:
        return []

    roots = [ix for ix in interactions if not ix.get("parent_interaction_ref")]
    root = roots[0] if roots else interactions[0]
    root_ref = str(root.get("interaction_ref") or "")

    run_events = instrument_run(
        interactions=interactions,
        root_output=str(root.get("output") or ""),
        workflow_success=workflow_success,
        workflow_latency_ms=workflow_latency_ms,
    )

    out: list[dict[str, Any]] = []
    for ix in interactions:
        row = dict(ix)
        ref = str(ix.get("interaction_ref") or "")
        if ref == root_ref or not ix.get("parent_interaction_ref"):
            row["events"] = run_events
        else:
            row["events"] = instrument_unit(ix)
        out.append(row)
    return out
