"""Live Gemini + OTel instrumentor → Ollie generation interactions."""

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

pytestmark = [pytest.mark.gemini, pytest.mark.tracing]


def _gemini_call(prompt: str = "Reply with exactly: ok") -> str:
    from google import genai

    api_key = require_env("GEMINI_API_KEY", "GOOGLE_API_KEY")
    client = genai.Client(api_key=api_key)
    model = os.getenv("OLLIE_SIM_GEMINI_MODEL", "gemini-2.0-flash")
    resp = client.models.generate_content(model=model, contents=prompt)
    text = getattr(resp, "text", None)
    if text:
        return str(text).strip()
    # Fallback for response shapes without .text
    try:
        return str(resp.candidates[0].content.parts[0].text).strip()
    except Exception:
        return str(resp)[:200]


def test_auto_gemini_captures_generation_and_tools():
    require_tracing_extra()
    require_env("GEMINI_API_KEY", "GOOGLE_API_KEY")
    try:
        import google.genai  # noqa: F401
    except ImportError:
        pytest.skip("google-genai not installed")
    try:
        from opentelemetry.instrumentation.google_genai import GoogleGenAiSdkInstrumentor  # noqa: F401
    except ImportError:
        pytest.skip("opentelemetry-instrumentation-google-genai not installed")

    wire = run_workflow_with_llm(
        instruments={Instruments.GEMINI},
        llm_call=_gemini_call,
        workflow_name="Auto Gemini Demo",
    )
    gen = assert_generation_tree(wire, provider="gemini")
    assert gen["parent_interaction_ref"] == "ix_0"
