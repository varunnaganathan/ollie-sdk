from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal

from ollie import context as ollie_context
from ollie.interaction_v2 import InteractionHandle, WorkflowInteractionController
from ollie.trace import utc_now_iso

if TYPE_CHECKING:
    from ollie.client import Client

WorkflowStatus = Literal["completed", "failed", "cancelled", "abandoned"]


class WorkflowSession:
    """Customer-declared workflow boundary (maps to a trace / task)."""

    def __init__(
        self,
        client: Client,
        *,
        name: str,
        input: str | None = None,
    ) -> None:
        self._client = client
        self.name = str(name).strip()
        self.input = input
        self.output: str | None = None
        self._session_id = client._session_id
        self._started_at: str | None = None
        self._ended_at: str | None = None
        self._status: WorkflowStatus = "completed"
        self._interactions: list[dict[str, Any]] = []
        self._open: dict[str, InteractionHandle] = {}
        self._stack: list[str] = []
        self._seq = 0
        self._root: InteractionHandle | None = None
        self.interaction = WorkflowInteractionController(self)
        self._workflow_token: Any = None
        self._interaction_token: Any = None

    def _next_ref(self) -> str:
        ref = f"ix_{self._seq}"
        self._seq += 1
        return ref

    def _start_interaction(
        self,
        *,
        name: str,
        primitive: str | None,
        parent: InteractionHandle | None,
        input: str | None,
        started_at: str | None = None,
    ) -> InteractionHandle:
        parent_ref = parent.interaction_ref if parent is not None else (self._stack[-1] if self._stack else None)
        ref = self._next_ref()
        handle = InteractionHandle(
            self,
            interaction_ref=ref,
            parent_interaction_ref=parent_ref,
            name=name,
            primitive=primitive,
            input=input,
            started_at=started_at or utc_now_iso(),
        )
        self._open[ref] = handle
        self._stack.append(ref)
        ollie_context.set_active_interaction(handle)
        return handle

    def _end_interaction(self, handle: InteractionHandle, *, output: str | None = None) -> None:
        wire = handle._close(output=output)
        self._interactions.append(wire)
        self._open.pop(handle.interaction_ref, None)
        if self._stack and self._stack[-1] == handle.interaction_ref:
            self._stack.pop()
        elif handle.interaction_ref in self._stack:
            self._stack = [r for r in self._stack if r != handle.interaction_ref]
        parent_ref = handle.parent_interaction_ref
        if parent_ref and parent_ref in self._open:
            ollie_context.set_active_interaction(self._open[parent_ref])
        elif (
            self._root is not None
            and not self._root._closed
            and handle is not self._root
        ):
            ollie_context.set_active_interaction(self._root)
        else:
            ollie_context.set_active_interaction(None)


    def record_completed_interaction(
        self,
        *,
        name: str,
        primitive: str | None,
        parent: InteractionHandle | None,
        input: str | None = None,
        output: str | None = None,
        started_at: str,
        ended_at: str,
        events: dict[str, Any] | list[dict[str, Any]] | None = None,
        attributes: list[dict[str, Any]] | None = None,
    ) -> str:
        """Append a fully completed interaction (used by auto-instrumentation)."""
        parent_ref = None
        if parent is not None:
            parent_ref = parent.interaction_ref
        elif self._root is not None:
            parent_ref = self._root.interaction_ref
        ref = self._next_ref()
        wire = {
            "interaction_ref": ref,
            "parent_interaction_ref": parent_ref,
            "name": name,
            "primitive": primitive,
            "input": input,
            "output": output,
            "events": events
            if isinstance(events, dict)
            else {"trigger": [], "context": [], "spans": []},
            "attributes": list(attributes or []),
            "started_at": started_at,
            "ended_at": ended_at,
        }
        self._interactions.append(wire)
        return ref

    def _workflow_latency_ms(self) -> int:
        started = self._started_at
        ended = self._ended_at or utc_now_iso()
        if not started:
            return 0
        try:
            from datetime import datetime

            def _parse(s: str) -> datetime:
                return datetime.fromisoformat(str(s).replace("Z", "+00:00"))

            a = _parse(started)
            b = _parse(ended)
            return max(0, int((b - a).total_seconds() * 1000))
        except Exception:
            return 0

    def to_validate_payload(self) -> dict[str, Any]:
        from ollie.signals import finalize_interactions

        session_id = self._session_id
        interactions = finalize_interactions(
            list(self._interactions),
            workflow_success=self._status == "completed",
            workflow_latency_ms=self._workflow_latency_ms(),
        )
        payload: dict[str, Any] = {
            "schema_version": 2,
            "sdk": self._client._transport.sdk_meta(),
            "agent_id": self._client.agent_id,
            "workflow": {
                "name": self.name,
                "status": self._status,
                "started_at": self._started_at or utc_now_iso(),
                "ended_at": self._ended_at or utc_now_iso(),
            },
            "interactions": interactions,
        }
        if session_id:
            payload["session_id"] = session_id
        return payload

    def flush(self) -> dict[str, Any]:
        payload = self.to_validate_payload()
        return self._client._transport.validate_trace(payload, self._client._delivery)

    def flush_process(self) -> dict[str, Any]:
        payload = self.to_validate_payload()
        return self._client._transport.process_trace(payload, self._client._delivery)

    def flush_ingest(self) -> dict[str, Any]:
        payload = self.to_validate_payload()
        return self._client._transport.ingest_trace(payload, self._client._delivery)

    def __enter__(self) -> WorkflowSession:
        self._started_at = utc_now_iso()
        self._workflow_token = ollie_context.set_active_workflow(self)
        self._root = self._start_interaction(
            name=self.name,
            primitive=None,
            parent=None,
            input=self.input,
        )
        return self

    def __exit__(self, exc_type: type[BaseException] | None, exc: BaseException | None, *_: Any) -> None:
        if exc_type is not None:
            self._status = "failed"
        self._ended_at = utc_now_iso()
        if self._root is not None and not self._root._closed:
            self._end_interaction(self._root, output=self.output)
        for ref in list(reversed(self._stack)):
            handle = self._open.get(ref)
            if handle is not None and not handle._closed:
                self._end_interaction(handle, output=handle.output)
        if self._workflow_token is not None:
            ollie_context.reset_active_workflow(self._workflow_token)
            self._workflow_token = None
