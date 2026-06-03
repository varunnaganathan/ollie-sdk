from __future__ import annotations

import pytest

from ollie.delivery import DeliveryConfig, DeliveryPipeline
from ollie.errors import OllieDeliveryError


def test_retry_then_succeed():
    attempts = {"n": 0}

    class _Transport:
        def send_event_batch(self, body, *, compression=True):
            attempts["n"] += 1
            if attempts["n"] < 3:
                raise RuntimeError("503")
            return {
                "batch_id": body["batch_id"],
                "accepted_count": 1,
                "duplicate_count": 0,
                "rejected_count": 0,
                "results": [{"event_id": body["events"][0]["event_id"], "status": "accepted"}],
            }

    pipeline = DeliveryPipeline(
        _Transport(),
        config=DeliveryConfig(max_buffer_events=50, flush_interval_s=0, max_retries=5, retry_backoff_base_s=0.01, compression=False),
        sdk_meta=lambda: {"name": "t", "version": "0"},
        sleeper=lambda _: None,
    )
    pipeline._start_timer = lambda: None
    pipeline.submit(
        {
            "event_id": "e1",
            "agent_id": "a",
            "session_id": "s",
            "timestamp": "t",
            "event_type": "x",
            "payload": {"agent_id": "a"},
        }
    )
    result = pipeline.flush_pending()[0]
    assert result.ok
    assert attempts["n"] == 3
    pipeline.shutdown()


def test_exhausted_retries_keeps_failed_batch():
    class _Transport:
        def send_event_batch(self, body, *, compression=True):
            raise RuntimeError("network down")

    pipeline = DeliveryPipeline(
        _Transport(),
        config=DeliveryConfig(max_retries=2, flush_interval_s=0, retry_backoff_base_s=0.01, compression=False),
        sdk_meta=lambda: {"name": "t", "version": "0"},
        sleeper=lambda _: None,
    )
    pipeline._start_timer = lambda: None
    pipeline.submit(
        {
            "event_id": "e1",
            "agent_id": "a",
            "session_id": "s",
            "timestamp": "t",
            "event_type": "x",
            "payload": {"agent_id": "a"},
        }
    )
    with pytest.raises(OllieDeliveryError):
        pipeline.flush_pending()
    assert len(pipeline.failed_batches) == 1
    pipeline.shutdown()
