"""Ollie instrumentation SDK."""

from __future__ import annotations

from typing import Any, Iterable, Sequence

from ollie.client import Client
from ollie.instruments import Instruments
from ollie.primitives import BUILTIN_PRIMITIVES
from ollie.tool import tool
from ollie.tree import render_interaction_tree
from ollie.version import __version__
from ollie.workflow import WorkflowSession

__all__ = [
    "BUILTIN_PRIMITIVES",
    "Client",
    "Instruments",
    "WorkflowSession",
    "__version__",
    "init",
    "render_interaction_tree",
    "tool",
]

_default_client: Client | None = None


def _get_default_client() -> Client:
    global _default_client
    if _default_client is None:
        _default_client = Client()
    return _default_client


def init(
    *,
    tracing: bool = False,
    instruments: Iterable[Instruments | str] | None = None,
    block_instruments: Iterable[Instruments | str] | None = None,
    auto_instrument: bool = True,
    providers: Sequence[str] | None = None,
    capture_content: bool = True,
    api_key: str | None = None,
    base_url: str | None = None,
    ingest_base_url: str | None = None,
    agent_id: str | None = None,
    **kwargs: Any,
) -> Client:
    """Configure the default client and optionally enable auto-instrumentation."""
    global _default_client
    _default_client = Client(
        api_key=api_key,
        base_url=base_url,
        ingest_base_url=ingest_base_url,
        agent_id=agent_id,
        tracing=tracing,
        instruments=instruments,
        block_instruments=block_instruments,
        auto_instrument=auto_instrument,
        providers=providers,
        capture_content=capture_content,
        **kwargs,
    )
    return _default_client


def define_feature(*args, **kwargs):
    return _get_default_client().define_feature(*args, **kwargs)


def define_span_type(*args, **kwargs):
    return _get_default_client().define_span_type(*args, **kwargs)


def define_signal(*args, **kwargs):
    return _get_default_client().define_signal(*args, **kwargs)
