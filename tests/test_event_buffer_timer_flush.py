from __future__ import annotations

from ollie.delivery import DeliveryConfig, DeliveryPipeline


def test_timer_flush_drains_buffer():
    calls: list[int] = []

    class _Transport:
        def send_event_batch(self, body, *, compression=True):
            calls.append(len(body["events"]))
            return {
                "batch_id": body["batch_id"],
                "accepted_count": len(body["events"]),
                "duplicate_count": 0,
                "rejected_count": 0,
                "results": [],
            }

    clock = {"t": 0.0}

    def _clock() -> float:
        return clock["t"]

    slept: list[float] = []

    def _sleep(sec: float) -> None:
        slept.append(sec)
        clock["t"] += sec
        pipeline.flush_pending()

    cfg = DeliveryConfig(max_buffer_events=50, flush_interval_s=5.0, compression=False, max_retries=0)
    pipeline = DeliveryPipeline(
        _Transport(),
        config=cfg,
        sdk_meta=lambda: {"name": "t", "version": "0"},
        clock=_clock,
        sleeper=_sleep,
    )
    pipeline._start_timer = lambda: None  # disable real timer
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
    assert calls == []
    pipeline.flush_pending()
    assert calls == [1]
    pipeline.shutdown()
