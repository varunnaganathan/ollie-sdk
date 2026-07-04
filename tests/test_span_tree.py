from __future__ import annotations

import json
from pathlib import Path

from ollie.client import Client
from ollie.tree import render_interaction_tree


def test_render_interaction_tree_golden():
    fixture = Path(__file__).resolve().parent / "fixtures" / "valid_workflow_v2.json"
    payload = json.loads(fixture.read_text())
    tree = render_interaction_tree(payload)
    assert "Workflow: Research Competitors [completed]" in tree
    assert "Search Sources [external_interaction]" in tree
    assert "Google [external_interaction]" in tree
    assert tree.index("Search Sources") < tree.index("Google")


def test_render_interaction_tree_from_sdk():
    client = Client(api_key="k", base_url="http://example.com", agent_id="a1")
    with client.workflow(name="Research Competitors", input="goal") as wf:
        search = wf.interaction.start(
            name="Search Sources",
            primitive="external_interaction",
            parent=wf._root,
            input="Find SEC filings",
        )
        wf.interaction.end(search, output="6 docs")
        wf.output = "6 docs"
    payload = wf.to_validate_payload()
    tree = render_interaction_tree(payload)
    assert "Research Competitors" in tree
    assert "Search Sources" in tree
