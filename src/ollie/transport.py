from __future__ import annotations

import gzip
import json
from typing import Any

import httpx

from ollie.errors import OllieHTTPError, OllieValidationError
from ollie.version import __version__


class Transport:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        ingest_base_url: str | None = None,
        timeout: float = 30.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.ingest_base_url = (ingest_base_url or base_url).rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    def _api_headers(self, *, content_encoding: str | None = None) -> dict[str, str]:
        headers = {"X-API-Key": self.api_key}
        if content_encoding:
            headers["Content-Encoding"] = content_encoding
            headers["Content-Type"] = "application/json"
        else:
            headers["Content-Type"] = "application/json"
        return headers

    def post_json(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        """Registry and other non-event endpoints."""
        url = f"{self.base_url}{path}"
        with httpx.Client(timeout=self.timeout) as client:
            r = client.post(url, json=body, headers=self._api_headers())
        return self._parse_response(r)

    def send_event_batch(
        self,
        body: dict[str, Any],
        *,
        compression: bool = True,
    ) -> dict[str, Any]:
        """Layer 1: single send path for trace validate/process/ingest via event batch."""
        url = f"{self.ingest_base_url}/v1/sdk/events/batch"
        data = json.dumps(body, separators=(",", ":")).encode("utf-8")
        headers = self._api_headers()
        if compression:
            data = gzip.compress(data)
            headers["Content-Encoding"] = "gzip"
        with httpx.Client(timeout=self.timeout) as client:
            r = client.post(url, content=data, headers=headers)
        return self._parse_response(r)

    def _parse_response(self, r: httpx.Response) -> dict[str, Any]:
        if r.status_code in (200, 201):
            return r.json()
        if r.status_code == 409:
            return {"_conflict": True, "detail": r.text}
        detail = r.text
        try:
            detail = r.json().get("detail", detail)
        except Exception:
            pass
        raise OllieHTTPError(r.status_code, str(detail))

    def _submit_trace_event(
        self,
        event_type: str,
        payload: dict[str, Any],
        delivery: Any,
    ) -> dict[str, Any]:
        from ollie.event import build_event

        event = build_event(event_type=event_type, payload=payload)
        delivery.submit(event)
        results = delivery.flush_pending()
        if not results:
            return {}
        result = results[-1]
        if not result.ok:
            errs = []
            if result.response:
                for item in result.response.get("results") or []:
                    if item.get("status") == "rejected":
                        errs.extend(item.get("errors") or [])
            raise OllieValidationError(errs or ["batch delivery failed"])
        return self._extract_trace_response(event_type, result.response, event["event_id"])

    def _extract_trace_response(
        self,
        event_type: str,
        batch_response: dict[str, Any] | None,
        event_id: str,
    ) -> dict[str, Any]:
        if not batch_response:
            return {}
        for item in batch_response.get("results") or []:
            if str(item.get("event_id")) != event_id:
                continue
            if item.get("status") == "duplicate":
                # Retry succeeded as duplicate; return minimal accepted shape
                if event_type == "sdk.trace.ingest":
                    return {"accepted": True, "trace_id": None, "duplicate": True}
                return {"accepted": True, "duplicate": True}
            if event_type == "sdk.trace.validate" and item.get("validate_result"):
                return dict(item["validate_result"])
            if event_type == "sdk.trace.process" and item.get("process_result"):
                return dict(item["process_result"])
            if event_type == "sdk.trace.ingest":
                if item.get("ingest"):
                    return dict(item["ingest"])
                if item.get("status") == "accepted":
                    return {
                        "accepted": True,
                        "queued": bool(item.get("queued")),
                        "trace_id": None,
                    }
        raise OllieValidationError([f"no result for event_id {event_id}"])

    def validate_trace(self, payload: dict[str, Any], delivery: Any) -> dict[str, Any]:
        from ollie.event import EVENT_TYPE_TRACE_VALIDATE

        body = self._submit_trace_event(EVENT_TYPE_TRACE_VALIDATE, payload, delivery)
        if not body.get("accepted") and not body.get("duplicate"):
            raise OllieValidationError(list(body.get("errors") or []))
        return body

    def process_trace(self, payload: dict[str, Any], delivery: Any) -> dict[str, Any]:
        from ollie.event import EVENT_TYPE_TRACE_PROCESS

        body = self._submit_trace_event(EVENT_TYPE_TRACE_PROCESS, payload, delivery)
        if not body.get("accepted") and not body.get("duplicate"):
            raise OllieValidationError(list(body.get("errors") or []))
        return body

    def ingest_trace(self, payload: dict[str, Any], delivery: Any) -> dict[str, Any]:
        from ollie.event import EVENT_TYPE_TRACE_INGEST

        body = self._submit_trace_event(EVENT_TYPE_TRACE_INGEST, payload, delivery)
        if not body.get("accepted") and not body.get("duplicate"):
            raise OllieValidationError(list(body.get("errors") or []))
        return body

    def sdk_meta(self) -> dict[str, str]:
        return {"name": "ollie-sdk", "version": __version__}
