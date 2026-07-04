from __future__ import annotations

from ollie.client import Client
from ollie.primitives import EXTERNAL_INTERACTION


def test_interaction_structured_events_on_tool():
    client = Client(api_key="k", base_url="http://example.com", agent_id="a1")
    with client.workflow(name="W") as wf:
        ix = wf.interaction.start(name="Search", primitive=EXTERNAL_INTERACTION, parent=wf._root)
        ix.output = "ok"
        wf.interaction.end(ix, output="ok")
        wf.output = "done"
    search = [i for i in wf.to_validate_payload()["interactions"] if i["name"] == "Search"][0]
    events = search["events"]
    assert isinstance(events, dict)
    assert events["spans"][0]["name"] == "Search"
    assert events["spans"][0]["type"] == "tool"
    assert events["spans"][0]["status"] == "success"
    assert "used_tool" in {s["name"] for s in events["context"]}
