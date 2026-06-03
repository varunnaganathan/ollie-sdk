"""Realistic customer-style instrumentation scenarios for E2E tests."""

from scenarios.customer_flows import (
    instrument_multi_agent_handoff,
    instrument_support_resolution,
    register_typical_custom_defs,
)

__all__ = [
    "register_typical_custom_defs",
    "instrument_support_resolution",
    "instrument_multi_agent_handoff",
]
