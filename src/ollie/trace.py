from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ollie.client import Client
    from ollie.interaction import Interaction


class TraceSession:
    def __init__(self, client: Client, *, conversation_id: str | None = None):
        self._client = client
        self.conversation_id = conversation_id
        self._interactions: list[dict[str, Any]] = []
        self._current: Interaction | None = None

    def interaction(
        self,
        *,
        source: str,
        target: str,
        input: str | None = None,
        output: str | None = None,
    ) -> Interaction:
        from ollie.interaction import Interaction

        ix = Interaction(self, source=source, target=target, input=input, output=output)
        self._current = ix
        return ix

    def _append_interaction(self, ix_data: dict[str, Any]) -> None:
        self._interactions.append(ix_data)

    def to_validate_payload(self) -> dict[str, Any]:
        return {
            "sdk": self._client._transport.sdk_meta(),
            "agent_id": self._client.agent_id,
            "conversation_id": self.conversation_id,
            "interactions": self._interactions,
        }

    def flush(self) -> dict[str, Any]:
        payload = self.to_validate_payload()
        return self._client._transport.validate_trace(payload, self._client._delivery)

    def flush_process(self) -> dict[str, Any]:
        """Send trace via event batch (sdk.trace.process)."""
        payload = self.to_validate_payload()
        return self._client._transport.process_trace(payload, self._client._delivery)

    def flush_ingest(self) -> dict[str, Any]:
        """Send trace via event batch (sdk.trace.ingest)."""
        payload = self.to_validate_payload()
        return self._client._transport.ingest_trace(payload, self._client._delivery)

    def __enter__(self) -> TraceSession:
        return self

    def __exit__(self, *args: Any) -> None:
        if self._interactions:
            self.flush()


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
