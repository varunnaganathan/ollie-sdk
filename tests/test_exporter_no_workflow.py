from __future__ import annotations

import logging
from types import SimpleNamespace

from ollie.instruments import Instruments
from ollie.tracing.exporter import OllieSpanExporter


def test_llm_span_dropped_without_active_workflow(caplog, monkeypatch):
    import ollie.tracing as tracing_mod
    import ollie.tracing.exporter as exp

    monkeypatch.setattr(exp, "_warned_no_workflow", False)
    monkeypatch.setattr(tracing_mod, "_active_instruments", {Instruments.OPENAI})
    monkeypatch.setattr(tracing_mod, "_installed", True)

    span = SimpleNamespace(
        name="chat",
        attributes={"gen_ai.request.model": "gpt-4o-mini", "gen_ai.system": "openai"},
        start_time=1_700_000_000_000_000_000,
        end_time=1_700_000_001_000_000_000,
        status=SimpleNamespace(status_code=SimpleNamespace(name="UNSET"), description=None),
        context=SimpleNamespace(span_id=1),
        instrumentation_scope=SimpleNamespace(name="opentelemetry.instrumentation.openai"),
    )
    exporter = OllieSpanExporter()
    with caplog.at_level(logging.WARNING, logger="ollie.tracing"):
        exporter._handle_span(span)
    assert any("no active workflow" in r.message for r in caplog.records)
