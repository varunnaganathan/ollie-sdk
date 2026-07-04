"""Enable OpenTelemetry Anthropic instrumentor when anthropic is installed."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("ollie.tracing")

_instrumentor: Any = None
_instrumented = False


def instrument_anthropic() -> bool:
    """Return True if Anthropic instrumentor was enabled."""
    global _instrumentor, _instrumented
    if _instrumented:
        return True
    try:
        import anthropic  # noqa: F401
    except ImportError:
        logger.debug("anthropic not installed; skipping Anthropic instrumentor")
        return False

    instrumentor = _get_instrumentor()
    if instrumentor is None:
        logger.warning(
            "Anthropic OTel instrumentor not found. "
            "Install with: pip install 'ollie-sdk[tracing]'"
        )
        return False
    if getattr(instrumentor, "is_instrumented_by_opentelemetry", False):
        _instrumented = True
        return True
    instrumentor.instrument()
    _instrumented = True
    logger.info("Ollie: Anthropic auto-instrumentation enabled")
    return True


def uninstrument_anthropic() -> None:
    global _instrumented
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
        ("opentelemetry.instrumentation.anthropic", "AnthropicInstrumentor"),
        ("openinference.instrumentation.anthropic", "AnthropicInstrumentor"),
    )
    for mod_name, cls_name in candidates:
        try:
            mod = __import__(mod_name, fromlist=[cls_name])
            cls = getattr(mod, cls_name, None)
            if cls is not None:
                _instrumentor = cls()
                return _instrumentor
        except ImportError:
            continue
    return None
