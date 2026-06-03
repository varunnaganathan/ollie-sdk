from __future__ import annotations

import httpx
import pytest

from ollie.delivery import DeliveryConfig, DeliveryPipeline


@pytest.mark.httpx_mock(assert_all_requests_were_expected=False)
def test_buffer_flushes_at_max_events(httpx_mock):
    calls: list[int] = []

    class _Transport:
        def send_event_batch(self, body, *, compression=True):
            calls.append(len(body["events"]))
            return {
                "batch_id": body["batch_id"],
                "accepted_count": len(body["events"]),
                "duplicate_count": 0,
                "rejected_count": 0,
                "results": [{"event_id": e["event_id"], "status": "accepted"} for e in body["events"]],
            }

        def sdk_meta(self):
            return {"name": "t", "version": "0"}

    cfg = DeliveryConfig(max_buffer_events=3, flush_interval_s=3600, compression=False)
    pipeline = DeliveryPipeline(_Transport(), config=cfg, sdk_meta=_Transport().sdk_meta)
    for i in range(7):
        pipeline.submit(
            {
                "event_id": f"e{i}",
                "agent_id": "a",
                "session_id": "s",
                "timestamp": "t",
                "event_type": "sdk.trace.ingest",
                "payload": {"agent_id": "a", "interactions": []},
            }
        )
    pipeline.flush_pending()
    assert calls == [3, 3, 1]
    pipeline.shutdown()
