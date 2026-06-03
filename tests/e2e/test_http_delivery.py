"""E2E: SDK sends real HTTP to a log-only collector (no Postgres)."""

from __future__ import annotations

import pytest

from ollie.client import Client
from scenarios.customer_flows import (
    instrument_multi_agent_handoff,
    instrument_support_resolution,
    register_typical_custom_defs,
)

pytestmark = pytest.mark.e2e


def _last_batch_payload(sdk_collector) -> dict:
    batch_reqs = [r for r in sdk_collector.requests() if r.path == "/v1/sdk/events/batch"]
    assert batch_reqs
    body = batch_reqs[-1].body
    assert isinstance(body, dict)
    events = body.get("events") or []
    assert events
    payload = events[-1].get("payload") if isinstance(events[-1], dict) else {}
    assert isinstance(payload, dict)
    return payload


def test_define_and_validate_hit_collector(sdk_collector):
    client = Client(
        api_key="e2e-test-key",
        base_url=sdk_collector.base_url,
        agent_id="agent_e2e_1",
    )
    register_typical_custom_defs(client)
    trace = instrument_support_resolution(client, conversation_id="e2e-support-1")
    trace.flush()

    paths = [r.path for r in sdk_collector.requests()]
    assert "/v1/sdk/registry/features" in paths
    assert "/v1/sdk/registry/span-types" in paths
    assert "/v1/sdk/registry/signals" in paths
    assert sdk_collector.count_path("/v1/sdk/events/batch") >= 1

    body = _last_batch_payload(sdk_collector)
    assert body.get("agent_id") == "agent_e2e_1"
    assert len(body.get("interactions") or []) == 1
    ix = body["interactions"][0]
    assert ix["source"] == "user"
    assert any(f["name"] == "retry_count" for f in ix.get("features") or [])
    assert any(s["kind"] == "retrieval" for s in ix.get("spans") or [])


def test_multi_interaction_handoff_payload(sdk_collector):
    client = Client(
        api_key="e2e-key",
        base_url=sdk_collector.base_url,
        agent_id="agent_e2e_2",
    )
    register_typical_custom_defs(client)
    trace = instrument_multi_agent_handoff(client, conversation_id="e2e-handoff-1")
    trace.flush()

    body = _last_batch_payload(sdk_collector)
    assert len(body["interactions"]) == 3
    roles = {(ix["source"], ix["target"]) for ix in body["interactions"]}
    assert ("user", "planner") in roles
    assert ("planner", "travel_specialist") in roles
    assert ("travel_specialist", "browser") in roles


def test_trace_context_manager_auto_flush(sdk_collector):
    client = Client(api_key="k", base_url=sdk_collector.base_url, agent_id="a1")
    before = sdk_collector.count_path("/v1/sdk/events/batch")
    with client.trace(conversation_id="auto-flush") as trace:
        with trace.interaction(source="user", target="agent") as ix:
            ix.feature("retry_count", 1)
    after = sdk_collector.count_path("/v1/sdk/events/batch")
    assert after == before + 1
