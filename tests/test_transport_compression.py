from __future__ import annotations

import gzip
import json

import httpx
import pytest

from ollie.transport import Transport


@pytest.mark.httpx_mock(assert_all_requests_were_expected=False)
def test_send_event_batch_gzip(httpx_mock):
    captured: dict = {}

    def _respond(request: httpx.Request) -> httpx.Response:
        assert request.headers.get("content-encoding") == "gzip"
        captured["body"] = json.loads(gzip.decompress(request.content).decode("utf-8"))
        return httpx.Response(200, json={"batch_id": "b", "accepted_count": 0, "duplicate_count": 0, "rejected_count": 0, "results": []})

    httpx_mock.add_callback(_respond, url="http://test/v1/sdk/events/batch")
    t = Transport(base_url="http://test", api_key="k")
    body = {"sdk": {"name": "ollie-sdk", "version": "0.1.0"}, "batch_id": "b1", "events": []}
    t.send_event_batch(body, compression=True)
    assert captured["body"]["batch_id"] == "b1"
