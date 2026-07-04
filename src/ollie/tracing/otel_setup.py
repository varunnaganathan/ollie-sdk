"""Configure TracerProvider + OllieSpanExporter."""

from __future__ import annotations

from typing import Any

_provider: Any = None
_processor: Any = None
_exporter: Any = None


def setup_tracer_provider(*, capture_content: bool = True) -> Any:
    """Install a TracerProvider with SimpleSpanProcessor → OllieSpanExporter."""
    global _provider, _processor, _exporter
    from opentelemetry import trace
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor

    from ollie.tracing.exporter import OllieSpanExporter

    if _exporter is not None:
        _exporter.capture_content = capture_content
        _exporter.enabled = True
    else:
        _exporter = OllieSpanExporter(capture_content=capture_content)

    if _provider is not None:
        return _provider

    existing = trace.get_tracer_provider()
    if isinstance(existing, TracerProvider) and type(existing).__name__ == "TracerProvider":
        # Reuse process-global SDK provider (OTel disallows override).
        _processor = SimpleSpanProcessor(_exporter)
        existing.add_span_processor(_processor)
        _provider = existing
        return _provider

    resource = Resource.create({"service.name": "ollie-sdk"})
    provider = TracerProvider(resource=resource)
    _processor = SimpleSpanProcessor(_exporter)
    provider.add_span_processor(_processor)
    trace.set_tracer_provider(provider)
    _provider = provider
    return provider


def shutdown_tracer_provider() -> None:
    """Detach Ollie exporter; keep provider (OTel cannot replace it)."""
    global _processor, _exporter
    # Do not null _provider — OTel forbids replacing TracerProvider.
    # Exporter becomes a no-op when auto_instrument is off via instrumentor uninstall.
    if _exporter is not None:
        _exporter.enabled = False
    # Leave provider/processor in place; instrumentors control whether spans are created.
