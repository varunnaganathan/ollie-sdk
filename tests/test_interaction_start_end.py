from __future__ import annotations

from ollie.client import Client


def test_interaction_start_end_output():
    client = Client(api_key="k", base_url="http://example.com", agent_id="a1")
    with client.workflow(name="W") as wf:
        child = wf.interaction.start(name="Child", input="hello")
        wf.interaction.end(child, output="done")
    ix1 = [ix for ix in wf.to_validate_payload()["interactions"] if ix["name"] == "Child"][0]
    assert ix1["input"] == "hello"
    assert ix1["output"] == "done"
    assert ix1["started_at"]
    assert ix1["ended_at"]
