from __future__ import annotations

from contextlib import contextmanager
from typing import TYPE_CHECKING, Any, Iterator

from ollie.trace import utc_now_iso

if TYPE_CHECKING:
    from ollie.trace import TraceSession


class Interaction:
    def __init__(
        self,
        trace: TraceSession,
        *,
        source: str,
        target: str,
        input: str | None = None,
        output: str | None = None,
    ):
        self._trace = trace
        self.source = source
        self.target = target
        self.input = input
        self.output = output
        self._started_at = utc_now_iso()
        self._ended_at: str | None = None
        self._features: list[dict[str, Any]] = []
        self._spans: list[dict[str, Any]] = []
        self._span_stack: list[str] = []
        self._span_id_seq = 0

    def feature(self, name: str, value: bool | int | float | str) -> None:
        self._features.append({"name": name, "value": value})

    @contextmanager
    def span(
        self,
        kind: str,
        *,
        name: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> Iterator[SpanContext]:
        parent_ref = self._span_stack[-1] if self._span_stack else None
        span_ref = f"sp_{self._span_id_seq}"
        self._span_id_seq += 1
        started = utc_now_iso()
        ctx = SpanContext()
        self._span_stack.append(span_ref)
        try:
            yield ctx
        finally:
            self._span_stack.pop()
            self._spans.append(
                {
                    "kind": kind,
                    "name": name,
                    "span_ref": span_ref,
                    "parent_span_ref": parent_ref,
                    "started_at": started,
                    "ended_at": utc_now_iso(),
                    "status": ctx.status,
                    "payload": payload or ctx.payload,
                }
            )

    def end(self) -> None:
        self._ended_at = utc_now_iso()
        self._trace._append_interaction(self._to_dict())

    def _to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "target": self.target,
            "input": self.input,
            "output": self.output,
            "started_at": self._started_at,
            "ended_at": self._ended_at or utc_now_iso(),
            "features": list(self._features),
            "spans": list(self._spans),
        }

    def __enter__(self) -> Interaction:
        return self

    def __exit__(self, *args: Any) -> None:
        if self._ended_at is None:
            self.end()


class SpanContext:
    def __init__(self) -> None:
        self.status: str | None = None
        self.payload: dict[str, Any] = {}
