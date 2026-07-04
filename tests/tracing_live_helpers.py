"""Shared helpers for live auto-instrumentation tests."""

from __future__ import annotations

import os
from typing import Any, Callable

import pytest

from ollie.instruments import Instruments


def require_tracing_extra() -> None:
    try:
        import opentelemetry  # noqa: F401
        from opentelemetry.sdk.trace import TracerProvider  # noqa: F401
    except ImportError:
        pytest.skip("ollie-sdk[tracing] not installed")


def require_env(*names: str) -> str:
    for name in names:
        val = (os.getenv(name) or "").strip().strip('"').strip("'")
        if val:
            return val
    pytest.skip(f"one of {names} required")


def assert_generation_tree(
    wire: dict[str, Any],
    *,
    provider: str,
    min_tools: int = 1,
) -> dict[str, Any]:
    interactions = wire.get("interactions") or []
    gens = [i for i in interactions if i.get("primitive") == "generation"]
    tools = [i for i in interactions if i.get("primitive") == "external_interaction"]
    if not gens:
        raise AssertionError(
            f"expected generation interaction for {provider}; "
            f"got {[(i.get('name'), i.get('primitive')) for i in interactions]}"
        )
    roots = [i for i in interactions if not i.get("parent_interaction_ref")]
    if len(roots) != 1:
        raise AssertionError(f"expected one root, got {len(roots)}")
    root_ref = roots[0]["interaction_ref"]
    for g in gens:
        if g.get("parent_interaction_ref") != root_ref:
            raise AssertionError(f"generation parent should be {root_ref}, got {g}")
    attrs = {a["name"]: a["value"] for a in (gens[0].get("attributes") or [])}
    if attrs.get("provider") != provider:
        raise AssertionError(f"expected provider={provider!r}, got {attrs.get('provider')!r} attrs={attrs}")
    if "model" not in attrs and "latency_ms" not in attrs:
        raise AssertionError(f"missing model/latency on generation: {attrs}")
    if len(tools) < min_tools:
        raise AssertionError(f"expected >= {min_tools} tools, got {len(tools)}")

    root = roots[0]
    events = root.get("events")
    if not isinstance(events, dict) or "spans" not in events or "context" not in events:
        raise AssertionError(f"root missing structured events: {events!r}")
    for s in events["spans"]:
        for req in ("type", "name", "status", "span_ref"):
            if not s.get(req):
                raise AssertionError(f"span missing {req}: {s}")
    ctx = {str(s.get("name")) for s in events.get("context") or []}
    if min_tools >= 1 and "used_tool" not in ctx:
        raise AssertionError(f"expected used_tool signal, got {ctx}")
    return gens[0]


def run_workflow_with_llm(
    *,
    instruments: set[Instruments] | None = None,
    block_instruments: set[Instruments] | None = None,
    auto_instrument: bool = True,
    providers: list[str] | None = None,
    llm_call: Callable[[], str],
    tool_name: str = "math.add",
    tool_input: str = "1+1",
    tool_output: str = "2",
    workflow_name: str = "Live Auto Demo",
    user_message: str = "Say hi in one word.",
) -> dict[str, Any]:
    import ollie
    from ollie.tracing import uninstall

    uninstall()
    client = ollie.Client(
        api_key="k",
        base_url="http://example.com",
        agent_id="agent_auto_multi",
        tracing=True,
        instruments=instruments,
        block_instruments=block_instruments,
        auto_instrument=auto_instrument,
        providers=providers,
    )
    try:
        with client.workflow(name=workflow_name, input=user_message) as wf:
            try:
                text = llm_call()
            except Exception as exc:
                msg = str(exc).lower()
                if any(
                    token in msg
                    for token in (
                        "429",
                        "resource_exhausted",
                        "quota",
                        "rate limit",
                        "credit balance",
                        "too low",
                        "billing",
                    )
                ):
                    pytest.skip(f"provider quota/billing unavailable: {exc}")
                raise
            with ollie.tool(tool_name, input=tool_input) as t:
                t.output = tool_output
            wf.output = text
        return wf.to_validate_payload()
    finally:
        client.shutdown()


def count_generations(wire: dict[str, Any]) -> int:
    return sum(1 for i in (wire.get("interactions") or []) if i.get("primitive") == "generation")
