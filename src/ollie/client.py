from __future__ import annotations

import os
from typing import Any, Iterable, Sequence

from ollie.delivery import DeliveryConfig, DeliveryPipeline
from ollie.instruments import Instruments
from ollie.session import SessionContext
from ollie.transport import Transport
from ollie.trace import TraceSession
from ollie.workflow import WorkflowSession


class Client:
    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        ingest_base_url: str | None = None,
        agent_id: str | None = None,
        delivery_config: DeliveryConfig | None = None,
        tracing: bool = False,
        instruments: Iterable[Instruments | str] | None = None,
        block_instruments: Iterable[Instruments | str] | None = None,
        auto_instrument: bool = True,
        providers: Sequence[str] | None = None,
        capture_content: bool = True,
    ):
        self.api_key = (api_key or os.getenv("OLLIE_API_KEY") or "").strip()
        if base_url is not None:
            self.base_url = base_url.strip()
        else:
            self.base_url = (os.getenv("OLLIE_BASE_URL") or "http://127.0.0.1:8001").strip()
        if ingest_base_url is not None:
            self.ingest_base_url = ingest_base_url.strip()
        elif base_url is not None:
            # Explicit base_url alone → same host for registry + batch (tests/collector)
            self.ingest_base_url = self.base_url
        else:
            env_ingest = (os.getenv("OLLIE_INGEST_BASE_URL") or "").strip()
            self.ingest_base_url = env_ingest or "http://127.0.0.1:8002"
        self.agent_id = (agent_id or os.getenv("OLLIE_AGENT_ID") or "").strip()
        if not self.api_key:
            raise ValueError("OLLIE_API_KEY or api_key is required")
        if not self.agent_id:
            raise ValueError("OLLIE_AGENT_ID or agent_id is required")
        self._transport = Transport(
            base_url=self.base_url,
            ingest_base_url=self.ingest_base_url,
            api_key=self.api_key,
        )
        self._delivery = DeliveryPipeline(
            self._transport,
            config=delivery_config,
            sdk_meta=self._transport.sdk_meta,
        )
        self._session_id: str | None = None
        self.tracing = bool(tracing)
        self.instruments = instruments
        self.block_instruments = block_instruments
        self.auto_instrument = bool(auto_instrument)
        self.providers = list(providers) if providers is not None else None
        self.capture_content = bool(capture_content)
        if self.tracing:
            from ollie.tracing import install

            install(
                instruments=self.instruments,
                block_instruments=self.block_instruments,
                auto_instrument=self.auto_instrument,
                providers=self.providers,
                capture_content=self.capture_content,
            )

    @property
    def delivery(self) -> DeliveryPipeline:
        return self._delivery

    def flush_delivery(self) -> list:
        return self._delivery.flush_pending()

    def retry_failed_delivery(self) -> list:
        return self._delivery.retry_failed()

    def shutdown(self) -> None:
        self._delivery.shutdown()
        if self.tracing:
            try:
                from ollie.tracing import uninstall

                uninstall()
            except Exception:
                pass

    def define_feature(
        self,
        name: str,
        *,
        kind: str = "observable",
        description: str,
        type: str = "categorical",
        allowed_values: list[str] | None = None,
    ) -> None:
        body: dict[str, Any] = {
            "name": name,
            "kind": kind,
            "description": description,
            "type": type,
        }
        if allowed_values is not None:
            body["allowed_values"] = allowed_values
        resp = self._transport.post_json("/v1/sdk/registry/features", body)
        if resp.get("_conflict"):
            return

    def define_span_type(self, name: str, *, description: str) -> None:
        body = {"name": name, "description": description}
        resp = self._transport.post_json("/v1/sdk/registry/span-types", body)
        if resp.get("_conflict"):
            return

    def define_signal(self, name: str, *, description: str, detector_type: str = "stub") -> None:
        body = {"name": name, "description": description, "detector_type": detector_type}
        resp = self._transport.post_json("/v1/sdk/registry/signals", body)
        if resp.get("_conflict"):
            return

    def session(self, session_id: str) -> SessionContext:
        return SessionContext(self, session_id)

    def workflow(
        self,
        *,
        name: str,
        input: str | None = None,
    ) -> WorkflowSession:
        return WorkflowSession(self, name=name, input=input)

    def trace(self, *, conversation_id: str | None = None) -> TraceSession:
        """Legacy v1 trace (dialogue turns + nested spans). Prefer workflow() for v2."""
        if conversation_id:
            self._session_id = conversation_id
        return TraceSession(self, conversation_id=conversation_id)
