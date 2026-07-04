from __future__ import annotations

import os
from typing import Any

import ollie
from ollie.instruments import Instruments
from ollie.tree import render_interaction_tree

_PROVIDER_INSTRUMENT = {
    "openai": Instruments.OPENAI,
    "anthropic": Instruments.ANTHROPIC,
    "gemini": Instruments.GEMINI,
}


def _call_openai(prompt: str) -> str:
    from openai import OpenAI

    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    resp = client.chat.completions.create(
        model=os.getenv("OLLIE_SIM_OPENAI_MODEL", "gpt-4o-mini"),
        messages=[{"role": "user", "content": prompt}],
        max_tokens=32,
    )
    return (resp.choices[0].message.content or "").strip()


def _call_anthropic(prompt: str) -> str:
    import anthropic

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    msg = client.messages.create(
        model=os.getenv("OLLIE_SIM_ANTHROPIC_MODEL", "claude-3-5-haiku-latest"),
        max_tokens=32,
        messages=[{"role": "user", "content": prompt}],
    )
    parts = [getattr(b, "text", "") or "" for b in msg.content]
    return "".join(parts).strip()


def _call_gemini(prompt: str) -> str:
    from google import genai

    api_key = (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or "").strip().strip('"')
    client = genai.Client(api_key=api_key)
    model = os.getenv("OLLIE_SIM_GEMINI_MODEL", "gemini-2.0-flash")
    resp = client.models.generate_content(model=model, contents=prompt)
    text = getattr(resp, "text", None)
    if text:
        return str(text).strip()
    return str(resp)[:200]


_CALLERS = {
    "openai": _call_openai,
    "anthropic": _call_anthropic,
    "gemini": _call_gemini,
}


def run_auto_agent(
    *,
    provider: str = "openai",
    client: ollie.Client | None = None,
    local_only: bool = True,
    user_message: str = "What is 15+27? Reply with just the number.",
) -> tuple[dict[str, Any], dict[str, Any]]:
    provider = provider.strip().lower()
    if provider not in _PROVIDER_INSTRUMENT:
        raise ValueError(f"unknown provider {provider!r}; choose openai|anthropic|gemini")

    instrument = _PROVIDER_INSTRUMENT[provider]
    if client is None:
        client = ollie.init(
            tracing=True,
            instruments={instrument},
            api_key=os.getenv("OLLIE_API_KEY", "sdk-test-key-1"),
            agent_id=os.getenv("OLLIE_AGENT_ID", "agent_sdk_test_1"),
            base_url=os.getenv("OLLIE_BASE_URL", "http://127.0.0.1:8001"),
            ingest_base_url=os.getenv("OLLIE_INGEST_BASE_URL", "http://127.0.0.1:8002"),
        )

    caller = _CALLERS[provider]
    with client.workflow(name=f"Auto {provider.title()} Demo", input=user_message) as wf:
        llm_text = caller(user_message)
        with ollie.tool("math.add", input="15+27") as t:
            t.output = "42"
        wf.output = llm_text

    wire = wf.to_validate_payload()
    if local_only:
        return {"accepted": True, "local_only": True}, wire
    return wf.flush_process(), wire


def assert_auto_capture(wire: dict[str, Any], *, provider: str) -> None:
    interactions = wire.get("interactions") or []
    gens = [i for i in interactions if i.get("primitive") == "generation"]
    tools = [i for i in interactions if i.get("primitive") == "external_interaction"]
    if not gens:
        raise AssertionError(f"expected auto generation for {provider}")
    if not tools:
        raise AssertionError("expected tool interaction")
    attrs = {a["name"]: a["value"] for a in (gens[0].get("attributes") or [])}
    if attrs.get("provider") != provider:
        raise AssertionError(f"expected provider={provider}, got {attrs.get('provider')}")

    roots = [i for i in interactions if not i.get("parent_interaction_ref")]
    if len(roots) != 1:
        raise AssertionError(f"expected one root, got {len(roots)}")
    events = roots[0].get("events")
    if not isinstance(events, dict):
        raise AssertionError(f"root events must be dict, got {type(events)}")
    for key in ("trigger", "context", "spans"):
        if key not in events:
            raise AssertionError(f"root events missing {key}")
    spans = events["spans"]
    if not spans:
        raise AssertionError("root events.spans empty")
    for s in spans:
        for req in ("type", "name", "status", "span_ref"):
            if not s.get(req):
                raise AssertionError(f"span missing {req}: {s}")
        extra = set(s.keys()) - {"type", "name", "status", "span_ref", "parent_span_ref"}
        if extra:
            raise AssertionError(f"span has unexpected fields {extra}: {s}")
    ctx_names = {str(s.get("name")) for s in events.get("context") or []}
    if "used_tool" not in ctx_names:
        raise AssertionError(f"expected used_tool in context signals, got {ctx_names}")
    # Success path should not mark llm_error
    gen_failed = any(
        (a.get("name") == "success" and a.get("value") is False)
        for a in (gens[0].get("attributes") or [])
    )
    if not gen_failed and "llm_error" in ctx_names:
        raise AssertionError("unexpected llm_error on success path")


def print_tree(wire: dict[str, Any]) -> str:
    return render_interaction_tree(wire)
