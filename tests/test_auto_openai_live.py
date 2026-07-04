"""Live OpenAI + OTel instrumentor → Ollie generation interactions."""

from __future__ import annotations

import os

import pytest

from ollie.instruments import Instruments
from tracing_live_helpers import (
    assert_generation_tree,
    count_generations,
    require_env,
    require_tracing_extra,
    run_workflow_with_llm,
)

pytestmark = [pytest.mark.openai, pytest.mark.tracing]


def _openai_call(prompt: str = "Reply with exactly: ok") -> str:
    from openai import OpenAI

    oai = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    resp = oai.chat.completions.create(
        model=os.getenv("OLLIE_SIM_OPENAI_MODEL", "gpt-4o-mini"),
        messages=[{"role": "user", "content": prompt}],
        max_tokens=8,
    )
    return (resp.choices[0].message.content or "").strip()


def test_auto_openai_captures_generation_and_tools():
    require_tracing_extra()
    require_env("OPENAI_API_KEY")
    wire = run_workflow_with_llm(
        instruments={Instruments.OPENAI},
        llm_call=_openai_call,
        workflow_name="Auto OpenAI Demo",
    )
    gen = assert_generation_tree(wire, provider="openai")
    assert gen["parent_interaction_ref"] == "ix_0"


def test_instruments_allowlist_openai_only():
    require_tracing_extra()
    require_env("OPENAI_API_KEY")
    wire = run_workflow_with_llm(
        instruments={Instruments.OPENAI},
        llm_call=_openai_call,
    )
    assert count_generations(wire) >= 1


def test_instruments_anthropic_only_does_not_capture_openai():
    require_tracing_extra()
    require_env("OPENAI_API_KEY")
    wire = run_workflow_with_llm(
        instruments={Instruments.ANTHROPIC},
        llm_call=_openai_call,
    )
    assert count_generations(wire) == 0
    tools = [i for i in wire["interactions"] if i.get("primitive") == "external_interaction"]
    assert len(tools) >= 1


def test_block_instruments_openai():
    require_tracing_extra()
    require_env("OPENAI_API_KEY")
    wire = run_workflow_with_llm(
        block_instruments={Instruments.OPENAI},
        llm_call=_openai_call,
    )
    assert count_generations(wire) == 0


def test_auto_instrument_false_no_generation():
    require_tracing_extra()
    require_env("OPENAI_API_KEY")
    wire = run_workflow_with_llm(
        auto_instrument=False,
        llm_call=_openai_call,
    )
    assert count_generations(wire) == 0
    tools = [i for i in wire["interactions"] if i.get("primitive") == "external_interaction"]
    assert len(tools) >= 1
