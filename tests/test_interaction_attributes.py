from __future__ import annotations

from ollie.client import Client


def test_interaction_attributes_on_wire():
    client = Client(api_key="k", base_url="http://example.com", agent_id="a1")
    with client.workflow(name="W") as wf:
        ix = wf.interaction.start(name="Step", parent=wf._root)
        ix.attribute("latency_ms", 120)
        ix.attribute("success", True)
        wf.interaction.end(ix)
    step = [i for i in wf.to_validate_payload()["interactions"] if i["name"] == "Step"][0]
    attrs = {a["name"]: a["value"] for a in step["attributes"]}
    assert attrs["latency_ms"] == 120
    assert attrs["success"] is True
