from __future__ import annotations

from ollie.delivery import DeliveryConfig, DeliveryPipeline


def test_duplicate_status_is_batch_success():
    posts = {"n": 0}

    class _Transport:
        def send_event_batch(self, body, *, compression=True):
            posts["n"] += 1
            return {
                "batch_id": body["batch_id"],
                "accepted_count": 0,
                "duplicate_count": 1,
                "rejected_count": 0,
                "results": [{"event_id": body["events"][0]["event_id"], "status": "duplicate"}],
            }

    pipeline = DeliveryPipeline(
        _Transport(),
        config=DeliveryConfig(flush_interval_s=0, compression=False),
        sdk_meta=lambda: {"name": "t", "version": "0"},
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
    assert posts["n"] == 1
    pipeline.shutdown()
