from __future__ import annotations

from ollie.client import Client
from ollie.context import get_active_interaction, get_active_parent, get_active_workflow


def test_workflow_sets_active_context():
    client = Client(api_key="k", base_url="http://example.com", agent_id="a1")
    assert get_active_workflow() is None
    with client.workflow(name="W", input="in") as wf:
        assert get_active_workflow() is wf
        assert get_active_interaction() is wf._root
        assert get_active_parent() is wf._root
        with wf.interaction(name="Child", parent=wf._root) as child:
            assert get_active_interaction() is child
            assert get_active_parent() is child
        assert get_active_interaction() is wf._root
    assert get_active_workflow() is None
    assert get_active_interaction() is None


def test_record_completed_interaction_under_root():
    client = Client(api_key="k", base_url="http://example.com", agent_id="a1")
    with client.workflow(name="W") as wf:
        ref = wf.record_completed_interaction(
            name="openai.chat",
            primitive="generation",
            parent=wf._root,
            input="hi",
            output="yo",
            started_at="2026-06-02T10:00:00+00:00",
            ended_at="2026-06-02T10:00:01+00:00",
            attributes=[
                {"name": "model", "value": "gpt-4o-mini"},
                {"name": "success", "value": True},
            ],
        )
        assert ref.startswith("ix_")
        wf.output = "yo"
    payload = wf.to_validate_payload()
    gens = [i for i in payload["interactions"] if i.get("primitive") == "generation"]
    assert len(gens) == 1
    assert gens[0]["parent_interaction_ref"] == "ix_0"
    assert any(a.get("name") == "model" for a in gens[0]["attributes"])
    root = next(i for i in payload["interactions"] if not i.get("parent_interaction_ref"))
    assert isinstance(root["events"], dict)
    assert "spans" in root["events"]

