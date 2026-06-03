"""E2E: buffered delivery sends multiple events in few gzip batch requests."""

from __future__ import annotations

import pytest

from ollie.delivery import DeliveryConfig, DeliveryPipeline
from ollie.event import EVENT_TYPE_TRACE_INGEST, build_event
from ollie.transport import Transport

pytestmark = pytest.mark.e2e


def test_sixty_events_two_batches(sdk_collector):
    sdk_collector.clear()
    transport = Transport(base_url=sdk_collector.base_url, api_key="batch-key")
    cfg = DeliveryConfig(max_buffer_events=50, flush_interval_s=3600, compression=True)
    pipeline = DeliveryPipeline(transport, config=cfg, sdk_meta=transport.sdk_meta)
    pipeline._start_timer = lambda: None

    for i in range(60):
        payload = {
            "agent_id": "agent1",
            "conversation_id": f"conv-{i}",
            "interactions": [],
        }
        pipeline.submit(build_event(event_type=EVENT_TYPE_TRACE_INGEST, payload=payload))
    pipeline.flush_pending()
    pipeline.shutdown()

    batch_reqs = [r for r in sdk_collector.requests() if r.path == "/v1/sdk/events/batch"]
    assert len(batch_reqs) == 2
    sizes = [len((r.body or {}).get("events") or []) for r in batch_reqs if isinstance(r.body, dict)]
    assert sizes == [50, 10]
