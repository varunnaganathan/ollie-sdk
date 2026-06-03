from __future__ import annotations

import os
from typing import Any

from ollie.delivery import DeliveryConfig, DeliveryPipeline
from ollie.transport import Transport
from ollie.trace import TraceSession


class Client:
    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        ingest_base_url: str | None = None,
        agent_id: str | None = None,
        delivery_config: DeliveryConfig | None = None,
    ):
        self.api_key = (api_key or os.getenv("OLLIE_API_KEY") or "").strip()
        if base_url is not None:
            self.base_url = base_url.strip()
        else:
            self.base_url = (os.getenv("OLLIE_BASE_URL") or "http://127.0.0.1:8001").strip()
        if ingest_base_url is not None:
            self.ingest_base_url = ingest_base_url.strip()
        else:
            env_ingest = (os.getenv("OLLIE_INGEST_BASE_URL") or "").strip()
            if env_ingest:
                self.ingest_base_url = env_ingest
            elif base_url is not None:
                # Tests/collector: single host for registry + batch
                self.ingest_base_url = self.base_url
            else:
                self.ingest_base_url = "http://127.0.0.1:8002"
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

    @property
    def delivery(self) -> DeliveryPipeline:
        return self._delivery

    def flush_delivery(self) -> list:
        return self._delivery.flush_pending()

    def retry_failed_delivery(self) -> list:
        return self._delivery.retry_failed()

    def shutdown(self) -> None:
        self._delivery.shutdown()

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

    def trace(self, *, conversation_id: str | None = None) -> TraceSession:
        return TraceSession(self, conversation_id=conversation_id)
