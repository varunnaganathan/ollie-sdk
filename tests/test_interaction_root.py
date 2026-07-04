from __future__ import annotations

from ollie.client import Client


def test_auto_root_interaction():
    client = Client(api_key="k", base_url="http://example.com", agent_id="a1")
    with client.workflow(name="Research", input="goal") as wf:
        wf.output = "final"
    interactions = wf.to_validate_payload()["interactions"]
    root = interactions[0]
    assert root["interaction_ref"] == "ix_0"
    assert root["parent_interaction_ref"] is None
    assert root["name"] == "Research"
    assert root["input"] == "goal"
    assert root["output"] == "final"
