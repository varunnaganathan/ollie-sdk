from __future__ import annotations

import builtins

import pytest

from ollie.errors import OllieError
from ollie.instruments import Instruments


def test_install_raises_clear_error_when_otel_missing(monkeypatch):
    import ollie.tracing as tracing_mod

    monkeypatch.setattr(tracing_mod, "_installed", False)
    monkeypatch.setattr(tracing_mod, "_active_instruments", set())
    real_import = builtins.__import__

    def blocked(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "opentelemetry" or (isinstance(name, str) and name.startswith("opentelemetry.")):
            raise ImportError("blocked for test")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", blocked)
    with pytest.raises(OllieError, match=r"ollie-sdk\[tracing\]"):
        tracing_mod.install(instruments={Instruments.OPENAI})
    monkeypatch.setattr(tracing_mod, "_installed", False)


def test_client_tracing_true_installs_when_extra_present():
    from ollie.client import Client
    from ollie.tracing import active_instruments, is_installed, uninstall

    uninstall()
    client = Client(
        api_key="k",
        base_url="http://example.com",
        agent_id="a1",
        tracing=True,
        instruments={Instruments.OPENAI},
    )
    assert client.tracing is True
    assert is_installed() is True
    assert Instruments.OPENAI in active_instruments()
    assert Instruments.ANTHROPIC not in active_instruments()
    client.shutdown()


def test_auto_instrument_false_installs_no_providers():
    from ollie.client import Client
    from ollie.tracing import active_instruments, is_installed, uninstall

    uninstall()
    client = Client(
        api_key="k",
        base_url="http://example.com",
        agent_id="a1",
        tracing=True,
        auto_instrument=False,
    )
    assert is_installed() is True
    assert active_instruments() == set()
    client.shutdown()


def test_block_openai_does_not_enable_openai():
    from ollie.client import Client
    from ollie.tracing import active_instruments, uninstall

    uninstall()
    client = Client(
        api_key="k",
        base_url="http://example.com",
        agent_id="a1",
        tracing=True,
        block_instruments={Instruments.OPENAI},
    )
    active = active_instruments()
    assert Instruments.OPENAI not in active
    # anthropic/gemini only if client libs + instrumentors present
    client.shutdown()
