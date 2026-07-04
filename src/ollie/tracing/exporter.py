"""OTel SpanExporter that records LLM spans as Ollie generation interactions."""

from __future__ import annotations

import logging
import threading
from typing import Any, Sequence

from ollie.context import get_active_parent, get_active_workflow
from ollie.instruments import Instruments
from ollie.tracing.adapter import adapt_llm_span, is_llm_span

logger = logging.getLogger("ollie.tracing")

_warned_no_workflow = False
_warn_lock = threading.Lock()

_PROVIDER_TO_INSTRUMENT = {
    "openai": Instruments.OPENAI,
    "anthropic": Instruments.ANTHROPIC,
    "gemini": Instruments.GEMINI,
}


class OllieSpanExporter:
    """SpanExporter compatible with opentelemetry.sdk.trace.export.SpanExporter."""

    def __init__(self, *, capture_content: bool = True) -> None:
        self.capture_content = capture_content
        self.enabled = True

    def export(self, spans: Sequence[Any]) -> Any:
        from opentelemetry.sdk.trace.export import SpanExportResult

        if not self.enabled:
            return SpanExportResult.SUCCESS
        for span in spans:
            self._handle_span(span)
        return SpanExportResult.SUCCESS

    def shutdown(self) -> None:
        return None

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return True

    def _handle_span(self, span: Any) -> None:
        global _warned_no_workflow
        if not is_llm_span(span):
            return
        from ollie.tracing import active_instruments

        allowed = active_instruments()
        if not allowed:
            return

        fields = adapt_llm_span(span, capture_content=self.capture_content)
        provider = "openai"
        for attr in fields.get("attributes") or []:
            if attr.get("name") == "provider":
                provider = str(attr.get("value") or "openai")
                break
        inst = _PROVIDER_TO_INSTRUMENT.get(provider)
        if inst is None or inst not in allowed:
            return

        wf = get_active_workflow()
        if wf is None:
            with _warn_lock:
                if not _warned_no_workflow:
                    logger.warning(
                        "Ollie auto-instrumentation: LLM span dropped (no active workflow). "
                        "Wrap LLM calls in `with client.workflow(...)`."
                    )
                    _warned_no_workflow = True
            return
        parent = get_active_parent()
        try:
            wf.record_completed_interaction(
                name=fields["name"],
                primitive=fields["primitive"],
                parent=parent,
                input=fields.get("input"),
                output=fields.get("output"),
                started_at=fields["started_at"],
                ended_at=fields["ended_at"],
                events=fields.get("events"),
                attributes=fields.get("attributes"),
            )
        except Exception:
            logger.exception("Ollie auto-instrumentation: failed to record LLM interaction")
