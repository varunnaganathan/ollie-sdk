"""Event Production: buffer, batch, retry, send (Layer 1)."""

from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable
from uuid import uuid4

from ollie.errors import OllieDeliveryError


@dataclass
class DeliveryConfig:
    max_buffer_events: int = 50
    flush_interval_s: float = 5.0
    compression: bool = True
    max_retries: int = 5
    retry_backoff_base_s: float = 0.5

    @classmethod
    def from_env(cls) -> DeliveryConfig:
        def _int(name: str, default: int) -> int:
            try:
                return int(os.getenv(name, str(default)))
            except ValueError:
                return default

        def _float(name: str, default: float) -> float:
            try:
                return float(os.getenv(name, str(default)))
            except ValueError:
                return default

        comp = os.getenv("OLLIE_COMPRESSION", "1").strip().lower() not in ("0", "false", "no")
        return cls(
            max_buffer_events=_int("OLLIE_BUFFER_MAX_EVENTS", 50),
            flush_interval_s=_float("OLLIE_BUFFER_FLUSH_INTERVAL_S", 5.0),
            compression=comp,
            max_retries=_int("OLLIE_RETRY_MAX", 5),
            retry_backoff_base_s=_float("OLLIE_RETRY_BACKOFF_BASE", 0.5),
        )


@dataclass
class DeliveryBatch:
    batch_id: str
    events: list[dict[str, Any]]
    attempt: int = 0


@dataclass
class DeliveryResult:
    batch_id: str
    attempt: int
    event_count: int
    accepted_count: int = 0
    duplicate_count: int = 0
    rejected_count: int = 0
    response: dict[str, Any] | None = None
    retried: bool = False

    @property
    def ok(self) -> bool:
        if self.response is None:
            return False
        return self.rejected_count == 0 and (
            self.accepted_count + self.duplicate_count >= self.event_count
        )


class DeliveryPipeline:
    """In-process event buffer + batch sender with whole-batch retry."""

    def __init__(
        self,
        transport: Any,
        *,
        config: DeliveryConfig | None = None,
        sdk_meta: Callable[[], dict[str, str]] | None = None,
        clock: Callable[[], float] | None = None,
        sleeper: Callable[[float], None] | None = None,
    ):
        self._transport = transport
        self._config = config or DeliveryConfig.from_env()
        self._sdk_meta = sdk_meta or (lambda: {"name": "ollie-sdk", "version": "0.0.0"})
        self._clock = clock or time.monotonic
        self._sleep = sleeper or time.sleep
        self._lock = threading.Lock()
        self._buffer: list[dict[str, Any]] = []
        self._failed_batches: list[DeliveryBatch] = []
        self._timer: threading.Timer | None = None
        self._closed = False
        self._start_timer()

    @property
    def failed_batches(self) -> list[DeliveryBatch]:
        with self._lock:
            return list(self._failed_batches)

    def _start_timer(self) -> None:
        if self._closed or self._config.flush_interval_s <= 0:
            return

        def _tick() -> None:
            if not self._closed:
                try:
                    self.flush_pending()
                except Exception:
                    pass
                self._start_timer()

        self._timer = threading.Timer(self._config.flush_interval_s, _tick)
        self._timer.daemon = True
        self._timer.start()

    def submit(self, event: dict[str, Any]) -> None:
        to_send: list[dict[str, Any]] | None = None
        with self._lock:
            self._buffer.append(event)
            if len(self._buffer) >= self._config.max_buffer_events:
                to_send = self._buffer
                self._buffer = []
        if to_send is not None:
            self._send_batch(to_send)

    def flush_pending(self) -> list[DeliveryResult]:
        with self._lock:
            if not self._buffer:
                pending: list[dict[str, Any]] = []
            else:
                pending = self._buffer
                self._buffer = []
        results: list[DeliveryResult] = []
        if pending:
            results.append(self._send_batch(pending))
        return results

    def retry_failed(self) -> list[DeliveryResult]:
        with self._lock:
            batches = list(self._failed_batches)
            self._failed_batches = []
        out: list[DeliveryResult] = []
        for batch in batches:
            out.append(self._send_batch(batch.events, batch_id=batch.batch_id, attempt=batch.attempt))
        return out

    def shutdown(self) -> None:
        self._closed = True
        if self._timer:
            self._timer.cancel()
            self._timer = None
        self.flush_pending()

    def _send_batch(
        self,
        events: list[dict[str, Any]],
        *,
        batch_id: str | None = None,
        attempt: int = 0,
    ) -> DeliveryResult:
        if not events:
            return DeliveryResult(batch_id="", attempt=0, event_count=0, response={})

        bid = batch_id or str(uuid4())
        body = {
            "sdk": self._sdk_meta(),
            "batch_id": bid,
            "events": events,
        }
        last_error: Exception | None = None
        response: dict[str, Any] | None = None
        retried = False

        for i in range(self._config.max_retries + 1):
            try_attempt = attempt + i
            if i > 0:
                retried = True
                delay = self._config.retry_backoff_base_s * (2 ** (i - 1))
                self._sleep(delay)
            try:
                response = self._transport.send_event_batch(
                    body,
                    compression=self._config.compression,
                )
                rejected = int(response.get("rejected_count") or 0)
                accepted = int(response.get("accepted_count") or 0)
                duplicate = int(response.get("duplicate_count") or 0)
                result = DeliveryResult(
                    batch_id=bid,
                    attempt=try_attempt,
                    event_count=len(events),
                    accepted_count=accepted,
                    duplicate_count=duplicate,
                    rejected_count=rejected,
                    response=response,
                    retried=retried,
                )
                if result.ok:
                    return result
                last_error = OllieDeliveryError(
                    bid,
                    try_attempt,
                    f"batch rejected_count={rejected}",
                )
            except Exception as exc:
                last_error = exc

        failed = DeliveryBatch(batch_id=bid, events=events, attempt=attempt + self._config.max_retries)
        with self._lock:
            self._failed_batches.append(failed)
        raise OllieDeliveryError(
            bid,
            failed.attempt,
            str(last_error) if last_error else "batch delivery failed",
        )
