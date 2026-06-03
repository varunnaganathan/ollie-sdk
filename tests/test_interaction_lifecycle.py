from __future__ import annotations

from ollie.client import Client
from ollie.trace import TraceSession


def test_nested_span_parent_ref():
    client = Client(api_key="k", base_url="http://example.com", agent_id="a1")
    trace = TraceSession(client)
    with trace.interaction(source="a", target="b") as ix:
        with ix.span("retrieval") as outer:
            outer.status = "ok"
            with ix.span("db_query") as inner:
                inner.status = "ok"
    data = trace._interactions[0]
    assert len(data["spans"]) == 2
    by_kind = {s["kind"]: s for s in data["spans"]}
    assert by_kind["db_query"]["parent_span_ref"] == by_kind["retrieval"]["span_ref"]
