"""Live OpenAI + simulated agent for event-batch SDK delivery (/v1/sdk/events/batch)."""

from __future__ import annotations

import gzip
import json
import os
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import func
from sqlalchemy.exc import ProgrammingError

from artifacts_util import ARTIFACTS_DIR, manifest_to_dict, write_sim_artifact

pytestmark = [pytest.mark.e2e, pytest.mark.integration, pytest.mark.openai]


def _require_openai() -> None:
    if not (os.getenv("OPENAI_API_KEY") or "").strip():
        pytest.skip("OPENAI_API_KEY required for simulated agent live tests")


class _TestClientTransport:
    """Route registry calls to intelligence API; event batch to sdk_ingest app."""

    def __init__(
        self,
        ingest_client: Any,
        *,
        api_client: Any | None = None,
        api_key: str,
    ) -> None:
        self._ingest_client = ingest_client
        self._api_client = api_client or ingest_client
        self.api_key = api_key
        self.base_url = "http://testserver"
        self.ingest_base_url = "http://testserver"
        self.timeout = 30.0
        self.batch_calls: list[dict[str, Any]] = []
        self.last_compression: bool = False

    def _headers(self, *, gzip_body: bool = False) -> dict[str, str]:
        h = {"X-API-Key": self.api_key, "Content-Type": "application/json"}
        if gzip_body:
            h["Content-Encoding"] = "gzip"
        return h

    def post_json(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        r = self._api_client.post(path, json=body, headers=self._headers())
        return self._parse(r)

    def send_event_batch(self, body: dict[str, Any], *, compression: bool = True) -> dict[str, Any]:
        self.batch_calls.append(body)
        self.last_compression = compression
        data = json.dumps(body, separators=(",", ":")).encode("utf-8")
        if compression:
            data = gzip.compress(data)
        r = self._ingest_client.post(
            "/v1/sdk/events/batch",
            content=data,
            headers=self._headers(gzip_body=compression),
        )
        return self._parse(r)

    def _parse(self, r: Any) -> dict[str, Any]:
        if r.status_code in (200, 201):
            return r.json()
        if r.status_code == 409:
            return {"_conflict": True, "detail": r.text}
        detail = r.text
        try:
            detail = r.json().get("detail", detail)
        except Exception:
            pass
        from ollie.errors import OllieHTTPError

        raise OllieHTTPError(r.status_code, str(detail))

    def _submit_trace_event(
        self,
        event_type: str,
        payload: dict[str, Any],
        delivery: Any,
    ) -> dict[str, Any]:
        from ollie.transport import Transport

        return Transport._submit_trace_event(self, event_type, payload, delivery)  # type: ignore[arg-type]

    def _extract_trace_response(
        self,
        event_type: str,
        batch_response: dict[str, Any] | None,
        event_id: str,
    ) -> dict[str, Any]:
        from ollie.transport import Transport

        return Transport._extract_trace_response(self, event_type, batch_response, event_id)  # type: ignore[arg-type]

    def validate_trace(self, payload: dict[str, Any], delivery: Any) -> dict[str, Any]:
        from ollie.transport import Transport

        return Transport.validate_trace(self, payload, delivery)  # type: ignore[arg-type]

    def process_trace(self, payload: dict[str, Any], delivery: Any) -> dict[str, Any]:
        from ollie.transport import Transport

        return Transport.process_trace(self, payload, delivery)  # type: ignore[arg-type]

    def ingest_trace(self, payload: dict[str, Any], delivery: Any) -> dict[str, Any]:
        from ollie.transport import Transport

        return Transport.ingest_trace(self, payload, delivery)  # type: ignore[arg-type]

    def sdk_meta(self) -> dict[str, str]:
        from ollie.version import __version__

        return {"name": "ollie-sdk", "version": __version__}


def _drain_ingest_process_jobs(session: Any, bundle: dict) -> None:
    """Phase B: run process worker for pending sdk.trace.ingest raw events (no Redis required)."""
    from sdk_ingest.models import PROCESSING_STATUS_DONE, PROCESSING_STATUS_PENDING, SdkRawEvent
    from sdk_ingest.process_event import handle_sdk_event_process_job

    rows = (
        session.query(SdkRawEvent)
        .filter(
            SdkRawEvent.customer_id == bundle["customer_id"],
            SdkRawEvent.event_type == "sdk.trace.ingest",
        )
        .order_by(SdkRawEvent.received_at.asc())
        .all()
    )
    for row in rows:
        if row.processing_status == PROCESSING_STATUS_DONE:
            continue
        handle_sdk_event_process_job(
            session,
            {
                "job_type": "sdk_event_process",
                "event_id": row.event_id,
                "customer_id": bundle["customer_id"],
                "raw_row_id": row.id,
            },
        )


def _wire_transport(
    client: Any,
    ingest_client: Any,
    api_key: str,
    *,
    api_client: Any | None = None,
) -> _TestClientTransport:
    from ollie.delivery import DeliveryPipeline

    transport = _TestClientTransport(
        ingest_client,
        api_client=api_client,
        api_key=api_key,
    )
    client._transport = transport
    client._delivery = DeliveryPipeline(
        transport,
        sdk_meta=transport.sdk_meta,
    )
    return transport


@pytest.fixture
def sim_sdk_client(integration_session):
    from auth import get_db_and_customer
    from fastapi.testclient import TestClient
    from main import app as intelligence_app
    from sdk_ingest.app import app as ingest_app
    from tests.integration.db_helpers import cleanup_customer, seed_sdk_test_customer

    import ollie
    from simulated_agent.agent import run_simulation
    from simulated_agent.cases import get_case
    from simulated_agent.registry import ensure_registry

    bundle = seed_sdk_test_customer(integration_session)

    def fake_auth():
        yield integration_session, bundle["customer_id"]

    intelligence_app.dependency_overrides[get_db_and_customer] = fake_auth
    ingest_app.dependency_overrides[get_db_and_customer] = fake_auth
    with TestClient(intelligence_app) as api_client, TestClient(ingest_app) as ingest_client:
        client = ollie.Client(
            api_key=bundle["api_key"],
            base_url="http://testserver",
            ingest_base_url="http://testserver",
            agent_id=bundle["agent_id"],
        )
        transport = _wire_transport(
            client,
            ingest_client,
            bundle["api_key"],
            api_client=api_client,
        )
        ensure_registry(client)

        def run(case_id: str, *, seed: int | None = None):
            case = get_case(case_id)
            result, manifest = run_simulation(client, case=case, seed=seed)
            wire = manifest.wire_payload or {}
            return result, manifest, wire

        yield run, bundle, integration_session, ingest_client, transport
    intelligence_app.dependency_overrides.clear()
    ingest_app.dependency_overrides.clear()
    cleanup_customer(integration_session, bundle["customer_id"])


@pytest.fixture
def sim_sdk_ingest_client(integration_session):
    from auth import get_db_and_customer
    from fastapi.testclient import TestClient
    from main import app as intelligence_app
    from sdk_ingest.app import app as ingest_app
    from tests.integration.db_helpers import cleanup_customer, seed_dummy_sdk_customer

    import ollie
    from simulated_agent.agent import run_simulation
    from simulated_agent.cases import get_case
    from simulated_agent.registry import ensure_registry

    bundle = seed_dummy_sdk_customer(integration_session)

    def fake_auth():
        yield integration_session, bundle["customer_id"]

    intelligence_app.dependency_overrides[get_db_and_customer] = fake_auth
    ingest_app.dependency_overrides[get_db_and_customer] = fake_auth
    with TestClient(intelligence_app) as api_client, TestClient(ingest_app) as ingest_client:
        client = ollie.Client(
            api_key=bundle["api_key"],
            base_url="http://testserver",
            ingest_base_url="http://testserver",
            agent_id=bundle["agent_id"],
        )
        transport = _wire_transport(
            client,
            ingest_client,
            bundle["api_key"],
            api_client=api_client,
        )
        ensure_registry(client)

        def run(case_id: str, *, seed: int | None = None, flush_mode: str = "ingest"):
            case = get_case(case_id)
            result, manifest = run_simulation(client, case=case, seed=seed, flush_mode=flush_mode)
            return result, manifest

        yield run, bundle, integration_session, ingest_client, transport
    intelligence_app.dependency_overrides.clear()
    ingest_app.dependency_overrides.clear()
    cleanup_customer(integration_session, bundle["customer_id"])


def test_process_random_single_ix(sim_sdk_client):
    _require_openai()
    run, _bundle, _session, _http, _transport = sim_sdk_client
    result, manifest, wire = run("random_single_ix", seed=42)
    assert result.get("accepted") is True
    assert len(result.get("interactions") or []) >= 1
    write_sim_artifact(
        ARTIFACTS_DIR / "sim_process_random_single_ix.json",
        result=result,
        manifest=manifest,
        wire=wire,
    )


def test_ingest_persists_trace_interactions_spans(sim_sdk_ingest_client):
    _require_openai()
    run, bundle, session, _http, _transport = sim_sdk_ingest_client
    from models import SdkAgentSpan, SdkInstrumentationRevision, Trace, TraceInteractionEvent

    try:
        t0 = session.query(func.count(Trace.id)).scalar()
        e0 = session.query(func.count(TraceInteractionEvent.id)).scalar()
        s0 = session.query(func.count(SdkAgentSpan.id)).scalar()
        r0 = session.query(func.count(SdkInstrumentationRevision.id)).scalar()
    except ProgrammingError as e:
        pytest.skip(f"missing sdk phase2b tables (run alembic upgrade): {e}")

    result, _manifest = run("random_single_ix", seed=99, flush_mode="ingest")
    assert result.get("accepted") is True
    # Phase B: accept queues async; drain process worker before DB assertions
    if result.get("queued"):
        _drain_ingest_process_jobs(session, bundle)
    assert result.get("trace_id") or result.get("queued")

    t1 = session.query(func.count(Trace.id)).scalar()
    e1 = session.query(func.count(TraceInteractionEvent.id)).scalar()
    s1 = session.query(func.count(SdkAgentSpan.id)).scalar()
    r1 = session.query(func.count(SdkInstrumentationRevision.id)).scalar()
    assert t1 > t0
    assert e1 > e0
    assert s1 > s0
    assert r1 >= r0


def test_delivery_requirements_simulated_agent(sim_sdk_ingest_client):
    """Layer 1 gate: batch-of-1, gzip, payload shape, raw events, idempotent retry."""
    _require_openai()
    run, bundle, session, http_client, transport = sim_sdk_ingest_client
    from ollie.event import EVENT_TYPE_TRACE_INGEST
    from sdk_ingest.models import SdkRawEvent

    try:
        session.query(SdkRawEvent).limit(1).all()
    except ProgrammingError as e:
        pytest.skip(f"missing sdk_raw_events (run alembic upgrade): {e}")

    transport.batch_calls.clear()
    result, _manifest = run("random_single_ix", seed=7, flush_mode="ingest")
    assert result.get("accepted") is True
    if result.get("queued"):
        _drain_ingest_process_jobs(session, bundle)
    assert len(transport.batch_calls) >= 1
    last_batch = transport.batch_calls[-1]
    assert len(last_batch["events"]) == 1
    assert last_batch["events"][0]["event_type"] == EVENT_TYPE_TRACE_INGEST
    assert transport.last_compression is True

    from models import TraceInteractionEvent

    e_count_after = session.query(func.count(TraceInteractionEvent.id)).scalar()
    assert e_count_after > 0

    # Build duplicate batch from DB raw events for this customer
    raw_rows = (
        session.query(SdkRawEvent)
        .filter(SdkRawEvent.customer_id == bundle["customer_id"])
        .order_by(SdkRawEvent.received_at.desc())
        .limit(5)
        .all()
    )
    assert len(raw_rows) >= 1
    events = [
        {
            "event_id": row.event_id,
            "agent_id": row.agent_id,
            "session_id": row.session_id,
            "timestamp": row.timestamp,
            "event_type": row.event_type,
            "payload": row.payload,
        }
        for row in raw_rows
    ]
    body = {
        "sdk": {"name": "ollie-sdk", "version": "0.1.0"},
        "batch_id": str(uuid4()),
        "events": events,
    }
    data = gzip.compress(json.dumps(body).encode("utf-8"))
    r2 = http_client.post(
        "/v1/sdk/events/batch",
        content=data,
        headers={
            "X-API-Key": bundle["api_key"],
            "Content-Type": "application/json",
            "Content-Encoding": "gzip",
        },
    )
    assert r2.status_code == 200
    dup_body = r2.json()
    assert dup_body["duplicate_count"] >= 1
    e_count_dup = session.query(func.count(TraceInteractionEvent.id)).scalar()
    assert e_count_dup == e_count_after

    ev = events[0]
    assert ev["event_type"] == "sdk.trace.ingest"
    assert ev["payload"].get("agent_id") == bundle["agent_id"]
    assert isinstance(ev["payload"].get("interactions"), list)
