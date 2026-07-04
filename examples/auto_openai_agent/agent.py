from __future__ import annotations

import os
from typing import Any

from auto_openai_agent.tools import math_add, string_reverse

import ollie
from ollie.tree import render_interaction_tree


def run_auto_agent(
    *,
    client: ollie.Client | None = None,
    local_only: bool = True,
    user_message: str = "What is 15+27? Reply with just the number.",
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Run workflow: OpenAI SDK call (auto) + manual tools. Returns (result, wire_payload)."""
    if client is None:
        client = ollie.init(
            tracing=True,
            providers=["openai"],
            api_key=os.getenv("OLLIE_API_KEY", "sdk-test-key-1"),
            agent_id=os.getenv("OLLIE_AGENT_ID", "agent_sdk_test_1"),
            base_url=os.getenv("OLLIE_BASE_URL", "http://127.0.0.1:8001"),
            ingest_base_url=os.getenv("OLLIE_INGEST_BASE_URL", "http://127.0.0.1:8002"),
        )

    from openai import OpenAI

    oai = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    with client.workflow(name="Auto OpenAI Demo", input=user_message) as wf:
        # No manual generation wrap — OTel OpenAI instrumentor → Ollie generation interaction
        resp = oai.chat.completions.create(
            model=os.getenv("OLLIE_SIM_OPENAI_MODEL", "gpt-4o-mini"),
            messages=[
                {"role": "system", "content": "You are a concise assistant."},
                {"role": "user", "content": user_message},
            ],
            max_tokens=32,
        )
        llm_text = (resp.choices[0].message.content or "").strip()

        with ollie.tool("math.add", input="15+27") as t:
            t.output = str(math_add(15, 27))

        with ollie.tool("string.reverse", input="ollie") as t:
            t.output = string_reverse("ollie")

        wf.output = llm_text

    wire = wf.to_validate_payload()
    if local_only:
        return {"accepted": True, "local_only": True}, wire

    result = wf.flush_process()
    return result, wire


def assert_auto_capture(wire: dict[str, Any]) -> None:
    interactions = wire.get("interactions") or []
    gens = [i for i in interactions if i.get("primitive") == "generation"]
    tools = [i for i in interactions if i.get("primitive") == "external_interaction"]
    if not gens:
        raise AssertionError(
            "expected at least one auto generation interaction from OpenAI; "
            f"got interactions={[(i.get('name'), i.get('primitive')) for i in interactions]}"
        )
    if len(tools) < 2:
        raise AssertionError(f"expected 2 tool interactions, got {len(tools)}")
    roots = [i for i in interactions if not i.get("parent_interaction_ref")]
    if len(roots) != 1:
        raise AssertionError(f"expected one root, got {len(roots)}")
    root_ref = roots[0]["interaction_ref"]
    for g in gens:
        if g.get("parent_interaction_ref") != root_ref:
            raise AssertionError(f"generation parent should be root {root_ref}, got {g}")
    attrs = {a["name"]: a["value"] for a in (gens[0].get("attributes") or [])}
    if "latency_ms" not in attrs and "model" not in attrs:
        raise AssertionError(f"generation missing model/latency attributes: {attrs}")


def print_tree(wire: dict[str, Any]) -> str:
    return render_interaction_tree(wire)
