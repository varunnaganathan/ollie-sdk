"""Default instrumented signal names (AI SDK pack + ADK language overlap)."""

from __future__ import annotations

# Shared with ADK / agents integrations
LANGUAGE_CONTEXT = frozenset(
    {
        "llm_error",
        "tool_error",
        "used_tool",
        "high_latency",
        "output_truncated",
        "safety_stop",
        "tool_loop",
        "runtime_failure",
        "empty_final_response",
    }
)
LANGUAGE_TRIGGER = frozenset({"repeated_tool_error"})

# AI-SDK v1 additions
AISDK_CONTEXT = frozenset(
    {
        "llm_empty_output",
        "llm_empty_input",
        "llm_provider_error_rate",
        "llm_token_blowup",
        "io_error_in_output",
    }
)

ALL_CONTEXT = LANGUAGE_CONTEXT | AISDK_CONTEXT
ALL_TRIGGER = LANGUAGE_TRIGGER
ALL_SIGNALS = ALL_CONTEXT | ALL_TRIGGER
