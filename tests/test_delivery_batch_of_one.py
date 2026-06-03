from __future__ import annotations

import gzip
import json

import httpx
import pytest

from ollie.client import Client
from ollie.event import EVENT_TYPE_TRACE_INGEST


@pytest.mark.httpx_mock(assert_all_requests_were_expected=False)
def test_flush_ingest_batch_of_one(httpx_mock):
    captured: dict = {}

    def _respond(request: httpx.Request) -> httpx.Response:
        raw = request.content
        if request.headers.get("content-encoding") == "gzip":
            raw = gzip.decompress(raw)
        captured["batch"] = json.loads(raw.decode("utf-8"))
        eid = captured["batch"]["events"][0]["event_id"]
        return httpx.Response(
            200,
            json={
                "batch_id": captured["batch"]["batch_id"],
                "accepted_count": 1,
                "duplicate_count": 0,
                "rejected_count": 0,
                "results": [
                    {
                        "event_id": eid,
                        "status": "accepted",
                        "ingest": {
                            "accepted": True,
                            "trace_id": "c1",
                            "interaction_count": 1,
                            "errors": [],
                            "warnings": [],
                        },
                    }
                ],
            },
        )

    httpx_mock.add_callback(_respond, url="http://test/v1/sdk/events/batch")
    client = Client(api_key="key", base_url="http://test", agent_id="agent1")
    trace = client.trace(conversation_id="c1")
    with trace.interaction(source="u", target="a") as ix:
        ix.feature("retry_count", 1)
    expected_payload = trace.to_validate_payload()
    out = trace.flush_ingest()
    assert out["accepted"] is True
    assert len(httpx_mock.get_requests()) == 1
    batch = captured["batch"]
    assert len(batch["events"]) == 1
    ev = batch["events"][0]
    assert ev["event_type"] == EVENT_TYPE_TRACE_INGEST
    assert ev["payload"] == expected_payload
