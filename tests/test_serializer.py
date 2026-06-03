from __future__ import annotations

from ollie.client import Client
from ollie.trace import TraceSession


def test_validate_payload_shape():
    client = Client(api_key="k", base_url="http://example.com", agent_id="a1")
    trace = TraceSession(client, conversation_id="c1")
    with trace.interaction(source="user", target="agent") as ix:
        ix.feature("retry_count", 3)
        with ix.span("tool_call"):
            pass
    payload = trace.to_validate_payload()
    assert "definitions" not in payload
    assert "events" not in payload
    ix0 = payload["interactions"][0]
    assert "features" in ix0
    assert "spans" in ix0
    assert ix0["features"][0]["name"] == "retry_count"
