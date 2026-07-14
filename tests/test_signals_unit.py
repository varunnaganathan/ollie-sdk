from __future__ import annotations

from ollie.client import Client
from ollie.primitives import EXTERNAL_INTERACTION, GENERATION
from ollie.signals.instrument import finalize_interactions, instrument_run
from ollie.signals.spans import interaction_to_span


def _ix(
    *,
    ref: str,
    parent: str | None,
    name: str,
    primitive: str | None,
    input: str | None = "",
    output: str | None = "",
    success: bool = True,
    latency_ms: int | None = None,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    finish_reason: str | None = None,
) -> dict:
    attrs: list[dict] = [{"name": "success", "value": success}]
    if not success:
        attrs.append({"name": "status", "value": "error"})
    if latency_ms is not None:
        attrs.append({"name": "latency_ms", "value": latency_ms})
    if input_tokens is not None:
        attrs.append({"name": "input_tokens", "value": input_tokens})
    if output_tokens is not None:
        attrs.append({"name": "output_tokens", "value": output_tokens})
    if finish_reason is not None:
        attrs.append({"name": "finish_reason", "value": finish_reason})
    return {
        "interaction_ref": ref,
        "parent_interaction_ref": parent,
        "name": name,
        "primitive": primitive,
        "input": input,
        "output": output,
        "attributes": attrs,
        "started_at": "2026-06-02T10:00:00+00:00",
        "ended_at": "2026-06-02T10:00:01+00:00",
    }


def _hit_names(hits: list[dict]) -> set[str]:
    return {str(h.get("signal")) for h in hits}


def test_interaction_to_span_warehouse_fields():
    ix = _ix(ref="ix_1", parent="ix_0", name="openai.chat", primitive=GENERATION, success=False, input="q", output="")
    span = interaction_to_span(ix)
    assert span is not None
    assert span["type"] == "llm"
    assert span["name"] == "openai.chat"
    assert span["status"] == "failure"
    assert span["span_ref"] == "ix_1"
    assert span["parent_span_ref"] == "ix_0"
    assert isinstance(span.get("input"), dict)
    assert isinstance(span.get("output"), dict)
    assert isinstance(span.get("properties"), dict)
    assert span["properties"]["kind"] == "llm"


def test_llm_empty_input_output_and_error():
    interactions = [
        _ix(ref="ix_0", parent=None, name="Run", primitive=None, output="final"),
        _ix(ref="ix_1", parent="ix_0", name="openai.chat", primitive=GENERATION, input="", output="", success=True),
        _ix(ref="ix_2", parent="ix_0", name="openai.chat", primitive=GENERATION, input="hi", output="", success=False),
    ]
    events, hits = instrument_run(
        interactions=interactions,
        root_output="final",
        workflow_success=True,
    )
    assert events["trigger"] == []
    assert events["context"] == []
    names = _hit_names(hits)
    assert "llm_empty_input" in names
    assert "llm_empty_output" in names
    assert "llm_error" in names
    assert "runtime_failure" in names
    assert "llm_provider_error_rate" in names


def test_tool_error_and_repeated_tool_error():
    interactions = [
        _ix(ref="ix_0", parent=None, name="Run", primitive=None, output="ok"),
        _ix(ref="ix_1", parent="ix_0", name="search", primitive=EXTERNAL_INTERACTION, success=False),
        _ix(ref="ix_2", parent="ix_0", name="search", primitive=EXTERNAL_INTERACTION, success=False),
    ]
    events, hits = instrument_run(interactions=interactions, root_output="ok", workflow_success=True)
    assert events["trigger"] == []
    names = _hit_names(hits)
    assert "tool_error" in names
    assert "used_tool" in names
    assert "repeated_tool_error" in names


def test_tool_loop_and_token_blowup_and_high_latency():
    tools = [
        _ix(ref=f"ix_{i}", parent="ix_0", name=f"t{i}", primitive=EXTERNAL_INTERACTION)
        for i in range(1, 7)
    ]
    interactions = [
        _ix(ref="ix_0", parent=None, name="Run", primitive=None, output="ok"),
        _ix(
            ref="ix_10",
            parent="ix_0",
            name="openai.chat",
            primitive=GENERATION,
            input="q",
            output="a",
            latency_ms=50_000,
            input_tokens=100,
            output_tokens=9000,
        ),
        *tools,
    ]
    _, hits = instrument_run(interactions=interactions, root_output="ok", workflow_success=True)
    names = _hit_names(hits)
    assert "tool_loop" in names
    assert "high_latency" in names
    assert "llm_token_blowup" in names


def test_output_truncated_safety_and_io_error():
    interactions = [
        _ix(ref="ix_0", parent=None, name="Run", primitive=None, output="x"),
        _ix(
            ref="ix_1",
            parent="ix_0",
            name="openai.chat",
            primitive=GENERATION,
            input="q",
            output="partial",
            finish_reason="length",
        ),
        _ix(
            ref="ix_2",
            parent="ix_0",
            name="anthropic.messages",
            primitive=GENERATION,
            input="q",
            output="blocked",
            finish_reason="content_filter",
        ),
        _ix(
            ref="ix_3",
            parent="ix_0",
            name="gemini.generate_content",
            primitive=GENERATION,
            input="q",
            output="RESOURCE_EXHAUSTED quota exceeded",
        ),
    ]
    _, hits = instrument_run(interactions=interactions, root_output="x", workflow_success=True)
    names = _hit_names(hits)
    assert "output_truncated" in names
    assert "safety_stop" in names
    assert "io_error_in_output" in names


def test_empty_final_response():
    interactions = [
        _ix(ref="ix_0", parent=None, name="Run", primitive=None, output=""),
        _ix(ref="ix_1", parent="ix_0", name="openai.chat", primitive=GENERATION, input="q", output="a"),
    ]
    _, hits = instrument_run(interactions=interactions, root_output="", workflow_success=True)
    assert "empty_final_response" in _hit_names(hits)


def test_finalize_attaches_events_to_root_and_children():
    interactions = [
        _ix(ref="ix_0", parent=None, name="Run", primitive=None, output="done"),
        _ix(ref="ix_1", parent="ix_0", name="openai.chat", primitive=GENERATION, input="q", output="a"),
        _ix(ref="ix_2", parent="ix_0", name="math.add", primitive=EXTERNAL_INTERACTION, output="2"),
    ]
    out = finalize_interactions(interactions, workflow_success=True)
    root = next(i for i in out if i["interaction_ref"] == "ix_0")
    child = next(i for i in out if i["interaction_ref"] == "ix_1")
    assert isinstance(root["events"], dict)
    assert root["events"]["trigger"] == []
    assert root["events"]["context"] == []
    assert set(root["events"]) == {"trigger", "context", "spans"}
    assert len(root["events"]["spans"]) == 2
    assert "used_tool" in _hit_names(root.get("_signal_hits") or [])
    assert len(child["events"]["spans"]) == 1
    assert child["events"]["spans"][0]["span_ref"] == "ix_1"
    assert isinstance(child["events"]["spans"][0].get("properties"), dict)


def test_workflow_payload_includes_signals():
    client = Client(api_key="k", base_url="http://example.com", agent_id="a1")
    with client.workflow(name="Demo", input="goal") as wf:
        with wf.interaction(name="openai.chat", primitive=GENERATION, parent=wf._root) as ix:
            ix.input = "hello"
            ix.output = "world"
            ix.attribute("latency_ms", 10)
        with wf.interaction(name="math.add", primitive=EXTERNAL_INTERACTION, parent=wf._root) as t:
            t.output = "2"
        wf.output = "world"
    payload = wf.to_validate_payload()
    root = next(i for i in payload["interactions"] if not i.get("parent_interaction_ref"))
    assert root["events"]["trigger"] == []
    assert root["events"]["context"] == []
    assert "used_tool" in _hit_names(root.get("_signal_hits") or [])
    spans = root["events"]["spans"]
    assert {s["type"] for s in spans} == {"llm", "tool"}
    for s in spans:
        assert s["status"] == "success"
        assert isinstance(s.get("properties"), dict)
        assert isinstance(s.get("input"), dict)
        assert isinstance(s.get("output"), dict)
