"""E2E: concurrent SDK flushes against log-only collector (stress receive path)."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed

import pytest

from ollie.client import Client
from scenarios.customer_flows import flush_many_traces

pytestmark = pytest.mark.e2e


def _worker(base_url: str, worker_id: int, traces_per_worker: int) -> int:
    client = Client(
        api_key=f"concurrent-key-{worker_id}",
        base_url=base_url,
        agent_id=f"agent_worker_{worker_id}",
    )
    flush_many_traces(client, count=traces_per_worker, prefix=f"w{worker_id}")
    return traces_per_worker


def test_concurrent_validate_requests(sdk_collector):
    workers = 8
    traces_each = 5
    sdk_collector.clear()

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [
            pool.submit(_worker, sdk_collector.base_url, wid, traces_each)
            for wid in range(workers)
        ]
        totals = [f.result() for f in as_completed(futures)]

    assert sum(totals) == workers * traces_each
    batch_count = sdk_collector.count_path("/v1/sdk/events/batch")
    assert batch_count == workers * traces_each

    conv_ids: set[str] = set()
    for r in sdk_collector.requests():
        if r.path != "/v1/sdk/events/batch" or not isinstance(r.body, dict):
            continue
        for ev in r.body.get("events") or []:
            if isinstance(ev, dict):
                payload = ev.get("payload") if isinstance(ev.get("payload"), dict) else {}
                conv_ids.add(str(payload.get("conversation_id")))
    conv_ids.discard(None)  # type: ignore[arg-type]
    assert len(conv_ids) == workers * traces_each
