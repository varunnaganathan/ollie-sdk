"""Enable OpenTelemetry Gemini / Google GenAI instrumentors when available."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("ollie.tracing")

_instrumentor: Any = None
_instrumented = False


def instrument_gemini() -> bool:
    """Return True if a Gemini instrumentor was enabled."""
    global _instrumentor, _instrumented
    if _instrumented:
        return True

    has_client = False
    for mod in ("google.genai", "google.generativeai"):
        try:
            __import__(mod)
            has_client = True
            break
        except ImportError:
            continue
    if not has_client:
        logger.debug("google.genai / google.generativeai not installed; skipping Gemini instrumentor")
        return False

    instrumentor = _get_instrumentor()
    if instrumentor is None:
        logger.warning(
            "Gemini OTel instrumentor not found. "
            "Install with: pip install 'ollie-sdk[tracing]'"
        )
        return False
    if getattr(instrumentor, "is_instrumented_by_opentelemetry", False):
        _instrumented = True
        return True
    instrumentor.instrument()
    _instrumented = True
    logger.info("Ollie: Gemini auto-instrumentation enabled")
    return True


def uninstrument_gemini() -> None:
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
        ("opentelemetry.instrumentation.google_genai", "GoogleGenAiSdkInstrumentor"),
        ("opentelemetry.instrumentation.google_generativeai", "GoogleGenerativeAiInstrumentor"),
        ("openinference.instrumentation.google_genai", "GoogleGenAIInstrumentor"),
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
