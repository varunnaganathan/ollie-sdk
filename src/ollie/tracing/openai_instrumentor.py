"""Enable OpenTelemetry OpenAI instrumentor when openai is installed."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("ollie.tracing")

_instrumentor: Any = None
_instrumented = False


def instrument_openai() -> bool:
    """Return True if OpenAI instrumentor was enabled."""
    global _instrumentor, _instrumented
    if _instrumented:
        return True
    try:
        import openai  # noqa: F401
    except ImportError:
        logger.debug("openai not installed; skipping OpenAI instrumentor")
        return False

    instrumentor = _get_instrumentor()
    if instrumentor is None:
        raise ImportError(
            "OpenAI OTel instrumentor not found. Install with: pip install 'ollie-sdk[tracing]'"
        )
    if getattr(instrumentor, "is_instrumented_by_opentelemetry", False):
        _instrumented = True
        return True
    instrumentor.instrument()
    _instrumented = True
    logger.info("Ollie: OpenAI auto-instrumentation enabled")
    return True


def uninstrument_openai() -> None:
    global _instrumentor, _instrumented
    if _instrumentor is not None and getattr(_instrumentor, "is_instrumented_by_opentelemetry", False):
        try:
            _instrumentor.uninstrument()
        except Exception:
            pass
    _instrumented = False


def _get_instrumentor() -> Any:
    global _instrumentor
    if _instrumentor is not None:
        return _instrumentor
    candidates = (
        "opentelemetry.instrumentation.openai",
        "opentelemetry.instrumentation.openai.v1",
        "openinference.instrumentation.openai",
    )
    for mod_name in candidates:
        try:
            mod = __import__(mod_name, fromlist=["OpenAIInstrumentor"])
            cls = getattr(mod, "OpenAIInstrumentor", None)
            if cls is not None:
                _instrumentor = cls()
                return _instrumentor
        except ImportError:
            continue
    return None
