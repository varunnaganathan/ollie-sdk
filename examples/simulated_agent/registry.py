from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ollie.client import Client


def ensure_registry(client: Client) -> None:
    """Register all simulation custom features, span type, and signal (idempotent)."""
    client.define_feature(
        "user_language",
        kind="attribution",
        description="User language attribution",
        type="categorical",
        allowed_values=["en", "es", "fr"],
    )
    client.define_feature(
        "agent_confidence_band",
        kind="observable",
        description="LLM confidence band",
        type="categorical",
        allowed_values=["high", "medium", "low"],
    )
    for name in (
        "response_char_count",
        "llm_response_char_count",
        "tools_invoked_count",
        "last_tool_result_size",
    ):
        client.define_feature(
            name,
            kind="behavioral",
            description=f"Simulation metric {name}",
            type="int",
        )
    client.define_span_type("tool_dispatch", description="Wrapper span for randomized tools")
    client.define_signal(
        "simulation_anomaly",
        description="Synthetic testing agent detected an anomalous tool/LLM pattern",
        detector_type="stub",
    )
