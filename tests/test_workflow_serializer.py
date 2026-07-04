from __future__ import annotations

from ollie.client import Client


def test_workflow_v2_serializer_shape():
    client = Client(api_key="k", base_url="http://example.com", agent_id="a1")
    with client.session("sess-1"):
        with client.workflow(name="W", input="in") as wf:
            with wf.interaction(name="Child", primitive="generation", parent=wf._root) as ix:
                ix.input = "in"
                ix.attribute("latency_ms", 1)
                ix.output = "out"
            wf.output = "done"
    payload = wf.to_validate_payload()
    assert payload["schema_version"] == 2
    assert payload["session_id"] == "sess-1"
    assert "definitions" not in payload
    assert "events" not in payload
    assert payload["workflow"]["name"] == "W"
    assert len(payload["interactions"]) == 2
    child = [i for i in payload["interactions"] if i["name"] == "Child"][0]
    assert child["primitive"] == "generation"
    assert isinstance(child["events"], dict)
    assert child["events"]["spans"][0]["span_ref"]
    assert child["attributes"]
    root = next(i for i in payload["interactions"] if not i.get("parent_interaction_ref"))
    assert "spans" in root["events"]
