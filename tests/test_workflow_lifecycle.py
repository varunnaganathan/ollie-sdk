from __future__ import annotations

from ollie.client import Client


def test_workflow_lifecycle_timestamps_and_status():
    client = Client(api_key="k", base_url="http://example.com", agent_id="a1")
    with client.workflow(name="Task A", input="in") as wf:
        wf.output = "out"
    payload = wf.to_validate_payload()
    wf_meta = payload["workflow"]
    assert wf_meta["name"] == "Task A"
    assert wf_meta["status"] == "completed"
    assert wf_meta["started_at"]
    assert wf_meta["ended_at"]


def test_workflow_failed_status_on_exception():
    client = Client(api_key="k", base_url="http://example.com", agent_id="a1")
    try:
        with client.workflow(name="Task B") as wf:
            raise RuntimeError("boom")
    except RuntimeError:
        pass
    assert wf.to_validate_payload()["workflow"]["status"] == "failed"
