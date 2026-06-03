"""Ollie instrumentation SDK."""

from ollie.client import Client
from ollie.version import __version__

__all__ = ["Client", "__version__"]

_default_client: Client | None = None


def _get_default_client() -> Client:
    global _default_client
    if _default_client is None:
        _default_client = Client()
    return _default_client


def define_feature(*args, **kwargs):
    return _get_default_client().define_feature(*args, **kwargs)


def define_span_type(*args, **kwargs):
    return _get_default_client().define_span_type(*args, **kwargs)


def define_signal(*args, **kwargs):
    return _get_default_client().define_signal(*args, **kwargs)
