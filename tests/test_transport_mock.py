from __future__ import annotations

import gzip
import json

import httpx
import pytest

from ollie.client import Client
from ollie.delivery import DeliveryConfig
from ollie.event import EVENT_TYPE_TRACE_PROCESS, EVENT_TYPE_TRACE_VALIDATE


def _decode_batch_request(request: httpx.Request) -> dict:
    raw = request.content
    if request.headers.get("content-encoding") == "gzip":
        raw = gzip.decompress(raw)
    return json.loads(raw.decode("utf-8"))


@pytest.mark.httpx_mock(assert_all_requests_were_expected=False)
def test_define_feature_posts_registry(httpx_mock):
    httpx_mock.add_response(url="http://test/v1/sdk/registry/features", json={"id": "1", "kind": "feature", "name": "x", "description": "d", "config": {}})
    client = Client(api_key="key", base_url="http://test", agent_id="agent1")
    client.define_feature("x", description="d", type="bool")


@pytest.mark.httpx_mock(assert_all_requests_were_expected=False)
def test_flush_validate(httpx_mock):
    def _respond(request: httpx.Request) -> httpx.Response:
        batch = _decode_batch_request(request)
        eid = batch["events"][0]["event_id"]
        return httpx.Response(
            200,
            json={
                "batch_id": batch["batch_id"],
                "accepted_count": 1,
                "duplicate_count": 0,
                "rejected_count": 0,
                "results": [
                    {
                        "event_id": eid,
                        "status": "accepted",
                        "validate_result": {
                            "accepted": True,
                            "normalized": {"interactions": []},
                            "errors": [],
                            "warnings": [],
                        },
                    }
                ],
            },
        )

    httpx_mock.add_callback(_respond, url="http://test/v1/sdk/events/batch")
    client = Client(api_key="key", base_url="http://test", agent_id="agent1")
    with client.trace() as trace:
        with trace.interaction(source="u", target="a") as ix:
            ix.feature("retry_count", 1)
    req = httpx_mock.get_requests()[-1]
    batch = _decode_batch_request(req)
    assert batch["events"][0]["event_type"] == EVENT_TYPE_TRACE_VALIDATE
    assert "definitions" not in batch["events"][0]["payload"]


@pytest.mark.httpx_mock(assert_all_requests_were_expected=False)
def test_flush_process(httpx_mock):
    def _respond(request: httpx.Request) -> httpx.Response:
        batch = _decode_batch_request(request)
        eid = batch["events"][0]["event_id"]
        return httpx.Response(
            200,
            json={
                "batch_id": batch["batch_id"],
                "accepted_count": 1,
                "duplicate_count": 0,
                "rejected_count": 0,
                "results": [
                    {
                        "event_id": eid,
                        "status": "accepted",
                        "process_result": {
                            "accepted": True,
                            "trace_id": "c1",
                            "interactions": [{"interaction_index": 0, "adapter_key": "sdk.instrumentation.v1"}],
                            "sparse_previews": [],
                            "signal_registry": [],
                            "warnings": [],
                            "errors": [],
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
    out = trace.flush_process()
    assert out["accepted"] is True
    assert len(out["interactions"]) == 1
