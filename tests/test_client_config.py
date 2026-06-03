import os

import pytest

from ollie.client import Client


def test_client_from_explicit_args():
    c = Client(api_key="k", base_url="http://localhost:8001", agent_id="a")
    assert c.api_key == "k"


def test_client_requires_api_key(monkeypatch):
    monkeypatch.delenv("OLLIE_API_KEY", raising=False)
    with pytest.raises(ValueError, match="OLLIE_API_KEY"):
        Client(agent_id="a", base_url="http://x")
