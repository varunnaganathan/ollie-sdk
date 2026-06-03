from __future__ import annotations

import re

from ollie.event import build_event, new_event_id


def test_new_event_id_is_uuid():
    eid = new_event_id()
    assert re.match(
        r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
        eid,
    )


def test_build_event_required_fields():
    ev = build_event(
        event_type="sdk.trace.ingest",
        payload={"agent_id": "a1", "conversation_id": "c1", "interactions": []},
    )
    assert ev["agent_id"] == "a1"
    assert ev["session_id"] == "c1"
    assert ev["event_type"] == "sdk.trace.ingest"
    assert ev["payload"]["agent_id"] == "a1"
