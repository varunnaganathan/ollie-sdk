"""Live Anthropic + OTel instrumentor → Ollie generation interactions."""

from __future__ import annotations

import os

import pytest

from ollie.instruments import Instruments
from tracing_live_helpers import (
    assert_generation_tree,
    require_env,
    require_tracing_extra,
    run_workflow_with_llm,
)

pytestmark = [pytest.mark.anthropic, pytest.mark.tracing]


def _anthropic_call(prompt: str = "Reply with exactly: ok") -> str:
    import anthropic

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    model = os.getenv("OLLIE_SIM_ANTHROPIC_MODEL", "claude-3-5-haiku-latest")
    msg = client.messages.create(
        model=model,
        max_tokens=16,
        messages=[{"role": "user", "content": prompt}],
    )
    parts = []
    for block in msg.content:
        text = getattr(block, "text", None)
        if text:
            parts.append(text)
    return "".join(parts).strip() or str(msg.content)


def test_auto_anthropic_captures_generation_and_tools():
    require_tracing_extra()
    require_env("ANTHROPIC_API_KEY")
    try:
        import anthropic  # noqa: F401
    except ImportError:
        pytest.skip("anthropic not installed")
    try:
        from opentelemetry.instrumentation.anthropic import AnthropicInstrumentor  # noqa: F401
    except ImportError:
        pytest.skip("opentelemetry-instrumentation-anthropic not installed")

    wire = run_workflow_with_llm(
        instruments={Instruments.ANTHROPIC},
        llm_call=_anthropic_call,
        workflow_name="Auto Anthropic Demo",
    )
    gen = assert_generation_tree(wire, provider="anthropic")
    assert gen["parent_interaction_ref"] == "ix_0"
