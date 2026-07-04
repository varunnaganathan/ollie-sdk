from __future__ import annotations

from ollie.client import Client


def test_interaction_tree_refs():
    client = Client(api_key="k", base_url="http://example.com", agent_id="a1")
    with client.workflow(name="Root") as wf:
        outer = wf.interaction.start(name="Outer", parent=wf._root)
        inner = wf.interaction.start(name="Inner", parent=outer)
        wf.interaction.end(inner, output="i")
        wf.interaction.end(outer, output="o")
    interactions = wf.to_validate_payload()["interactions"]
    by_name = {ix["name"]: ix for ix in interactions}
    assert by_name["Root"]["interaction_ref"] == "ix_0"
    assert by_name["Root"]["parent_interaction_ref"] is None
    assert by_name["Outer"]["parent_interaction_ref"] == "ix_0"
    assert by_name["Inner"]["parent_interaction_ref"] == by_name["Outer"]["interaction_ref"]
