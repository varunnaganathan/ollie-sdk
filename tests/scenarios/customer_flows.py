"""Instrumentation patterns modeled after real customer agent loops."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ollie.client import Client
    from ollie.trace import TraceSession


def register_typical_custom_defs(client: Client) -> None:
    """Register-before-instrument, as customers should."""
    client.define_feature(
        "discount_denied",
        kind="behavioral",
        description="Agent refused a discount",
        type="bool",
    )
    client.define_feature(
        "user_tier",
        kind="attribution",
        description="Subscription tier",
        type="categorical",
        allowed_values=["free", "pro", "enterprise"],
    )
    client.define_feature(
        "escalated_to_human",
        kind="observable",
        description="Conversation escalated",
        type="bool",
    )
    client.define_span_type("checkout_validation", description="Checkout validation step")
    client.define_span_type("policy_lookup", description="Policy KB lookup")
    client.define_signal("User Frustration", description="User expresses dissatisfaction")


def instrument_support_resolution(client: Client, *, conversation_id: str) -> TraceSession:
    """Single interaction: user → agent with retrieval, tool, and custom features."""
    trace = client.trace(conversation_id=conversation_id)
    with trace.interaction(
        source="user",
        target="agent",
        input="I need a refund for order #4421",
        output="I can help review your refund eligibility.",
    ) as ix:
        ix.feature("user_tier", "pro")
        ix.feature("retry_count", 1)
        ix.feature("discount_denied", False)
        ix.feature("escalated_to_human", False)
        with ix.span("retrieval") as retrieval:
            retrieval.status = "ok"
            retrieval.payload["hits"] = 3
            with ix.span("policy_lookup") as lookup:
                lookup.status = "ok"
        with ix.span("tool_call", name="crm.lookup_order"):
            pass
        with ix.span("llm_call", name="draft_reply"):
            pass
    return trace


def instrument_multi_agent_handoff(client: Client, *, conversation_id: str) -> TraceSession:
    """Planner → specialist → browser style handoffs (multiple interactions)."""
    trace = client.trace(conversation_id=conversation_id)
    with trace.interaction(
        source="user",
        target="planner",
        input="Book a flight to SFO next Tuesday",
        output="Routing to travel specialist",
    ) as ix0:
        ix0.feature("retry_count", 0)
        with ix0.span("llm_call", name="intent_route"):
            pass

    with trace.interaction(
        source="planner",
        target="travel_specialist",
        input="Book SFO flight",
        output="Found 3 options",
    ) as ix1:
        ix1.feature("latency_ms", 840)
        with ix1.span("web_search"):
            pass
        with ix1.span("tool_call", name="flights.search"):
            pass

    with trace.interaction(
        source="travel_specialist",
        target="browser",
        input="Open checkout for option 2",
        output="Checkout page loaded",
    ) as ix2:
        ix2.feature("success", True)
        with ix2.span("browser_session"):
            with ix2.span("checkout_validation"):
                pass
    return trace


def flush_many_traces(client: Client, *, count: int, prefix: str = "conv") -> list[dict[str, Any]]:
    """Burst of independent traces; each returns the validate HTTP response body."""
    results: list[dict[str, Any]] = []
    for i in range(count):
        trace = client.trace(conversation_id=f"{prefix}-{i}")
        with trace.interaction(source="user", target="agent") as ix:
            ix.feature("retry_count", i % 5)
            with ix.span("tool_call"):
                pass
        results.append(trace.flush())
    return results
