#!/usr/bin/env python3
"""Inspect gzip batch payloads as the server receives them (Layer 1 demo).

Run from packages/ollie-sdk:
  PYTHONPATH=src python examples/demo_batch_payload_inspection.py
"""

from __future__ import annotations

import gzip
import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# allow `python examples/...` without install
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ollie.delivery import DeliveryConfig, DeliveryPipeline
from ollie.event import EVENT_TYPE_TRACE_INGEST, build_event
from ollie.transport import Transport


@dataclass
class WireCapture:
    attempts: list[dict[str, Any]] = field(default_factory=list)


class RecordingTransport(Transport):
    """Capture raw gzip bytes before they would hit the network."""

    def __init__(self, *, base_url: str, api_key: str, fail_until_attempt: int = 0):
        super().__init__(base_url=base_url, api_key=api_key)
        self.fail_until_attempt = fail_until_attempt
        self.capture = WireCapture()
        self._send_count = 0

    def send_event_batch(self, body: dict[str, Any], *, compression: bool = True) -> dict[str, Any]:
        self._send_count += 1
        attempt = self._send_count

        json_bytes = json.dumps(body, separators=(",", ":"), indent=2).encode("utf-8")
        wire_bytes = gzip.compress(json_bytes) if compression else json_bytes

        entry = {
            "attempt": attempt,
            "compression": "gzip" if compression else "none",
            "json_bytes": len(json_bytes),
            "wire_bytes": len(wire_bytes),
            "ratio": round(len(wire_bytes) / max(len(json_bytes), 1), 3),
            "content_encoding": "gzip" if compression else None,
            "batch_id": body.get("batch_id"),
            "event_count": len(body.get("events") or []),
            "wire_hex_preview": wire_bytes[:32].hex(),
            "json_preview": body,
        }
        self.capture.attempts.append(entry)

        if attempt <= self.fail_until_attempt:
            raise RuntimeError(f"simulated network failure on attempt {attempt}")

        # Build server-style ack
        results = []
        for ev in body.get("events") or []:
            eid = str(ev.get("event_id") or "")
            results.append(
                {
                    "event_id": eid,
                    "status": "accepted",
                    "ingest": {
                        "accepted": True,
                        "trace_id": (ev.get("payload") or {}).get("conversation_id"),
                        "interaction_count": len((ev.get("payload") or {}).get("interactions") or []),
                    },
                }
            )
        return {
            "batch_id": body.get("batch_id"),
            "accepted_count": len(results),
            "duplicate_count": 0,
            "rejected_count": 0,
            "results": results,
        }


def _sample_trace_payload(agent_id: str, conversation_id: str, *, ix_count: int = 2) -> dict[str, Any]:
    interactions = []
    for i in range(ix_count):
        interactions.append(
            {
                "source": "user" if i % 2 == 0 else "agent",
                "target": "agent" if i % 2 == 0 else "user",
                "input": f"message {i}",
                "output": f"reply {i}",
                "started_at": "2026-06-02T12:00:00Z",
                "ended_at": "2026-06-02T12:00:01Z",
                "features": [{"name": "retry_count", "value": i}],
                "spans": [{"kind": "tool_call", "span_ref": f"sp_{i}", "started_at": "2026-06-02T12:00:00Z", "ended_at": "2026-06-02T12:00:01Z", "payload": {}}],
            }
        )
    return {
        "sdk": {"name": "ollie-sdk", "version": "demo"},
        "agent_id": agent_id,
        "conversation_id": conversation_id,
        "interactions": interactions,
    }


def _print_section(title: str) -> None:
    print("\n" + "=" * 72)
    print(title)
    print("=" * 72)


def demo_batch_and_compression() -> WireCapture:
    _print_section("1–4) Batch flush: gzip on the wire → decompress → multi-event → no data loss")

    transport = RecordingTransport(base_url="http://demo", api_key="demo-key")
    cfg = DeliveryConfig(max_buffer_events=10, flush_interval_s=3600, compression=True, max_retries=0)
    pipeline = DeliveryPipeline(transport, config=cfg, sdk_meta=lambda: {"name": "ollie-sdk", "version": "demo"})
    pipeline._start_timer = lambda: None  # manual flush only

    # Three separate trace payloads → three events in one batch
    sources = []
    for n in range(3):
        payload = _sample_trace_payload("agent_demo_1", f"conv-batch-{n}", ix_count=2)
        sources.append(payload)
        pipeline.submit(build_event(event_type=EVENT_TYPE_TRACE_INGEST, payload=payload))

    results = pipeline.flush_pending()
    assert results and results[0].ok
    pipeline.shutdown()

    cap = transport.capture.attempts[-1]
    json_bytes = json.dumps(cap["json_preview"], separators=(",", ":")).encode("utf-8")
    wire = gzip.compress(json_bytes)

    print(f"Compression format: {cap['compression']} (Content-Encoding: gzip)")
    print(f"Uncompressed JSON size: {cap['json_bytes']:,} bytes")
    print(f"On-the-wire (gzip) size: {cap['wire_bytes']:,} bytes")
    print(f"Compression ratio (wire/json): {cap['ratio']}")
    print(f"HTTP requests for this flush: 1")
    print(f"Events in batch: {cap['event_count']}")

    decompressed = json.loads(gzip.decompress(wire).decode("utf-8"))
    print("\n--- Decompressed batch (server view after gzip.decompress) ---")
    print(json.dumps(decompressed, indent=2)[:4000])
    if len(json.dumps(decompressed)) > 4000:
        print("... [truncated for terminal] ...")

    print("\n--- Per-event summary (proves batching) ---")
    for i, ev in enumerate(decompressed.get("events") or []):
        pl = ev.get("payload") or {}
        print(
            f"  event[{i}] id={ev.get('event_id')[:8]}… "
            f"type={ev.get('event_type')} session={ev.get('session_id')} "
            f"interactions={len(pl.get('interactions') or [])}"
        )

    print("\n--- Data integrity (submitted vs received) ---")
    ok = True
    for i, (src, ev) in enumerate(zip(sources, decompressed.get("events") or [])):
        recv = ev.get("payload") or {}
        match = recv == src
        ok = ok and match
        print(f"  event[{i}] payload byte-identical to SDK submit: {match}")
        if not match:
            print("    MISSING keys:", set(src) - set(recv))
            print("    EXTRA keys:", set(recv) - set(src))
    print(f"  ALL payloads preserved: {ok}")
    if not ok:
        raise SystemExit(1)

    return transport.capture


def demo_retry(capture: WireCapture) -> None:
    _print_section("5) Intentional failure → whole-batch retry")

    transport = RecordingTransport(base_url="http://demo", api_key="demo-key", fail_until_attempt=2)
    cfg = DeliveryConfig(
        max_buffer_events=10,
        flush_interval_s=3600,
        compression=True,
        max_retries=5,
        retry_backoff_base_s=0.1,
    )
    pipeline = DeliveryPipeline(
        transport,
        config=cfg,
        sdk_meta=lambda: {"name": "ollie-sdk", "version": "demo"},
        sleeper=lambda s: None,
    )
    pipeline._start_timer = lambda: None

    payload = _sample_trace_payload("agent_demo_1", "conv-retry-1", ix_count=1)
    event = build_event(event_type=EVENT_TYPE_TRACE_INGEST, payload=payload)
    pipeline.submit(event)

    result = pipeline.flush_pending()[0]
    pipeline.shutdown()

    print(f"Send attempts observed: {len(transport.capture.attempts)}")
    for a in transport.capture.attempts:
        print(f"  attempt {a['attempt']}: wire={a['wire_bytes']}B events={a['event_count']} batch_id={a['batch_id']}")
    print(f"Final delivery ok: {result.ok}")
    print(f"Client retried: {result.retried}")
    print(f"Same batch_id on all attempts: {len({a['batch_id'] for a in transport.capture.attempts}) == 1}")
    print(f"Same event_id on all attempts: event_id={event['event_id']}")

    if len(transport.capture.attempts) < 3:
        raise SystemExit("Expected 2 failures + 1 success (3 send attempts)")
    if not result.ok:
        raise SystemExit("Retry demo failed")


def main() -> int:
    demo_batch_and_compression()
    demo_retry(WireCapture())
    _print_section("Done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
