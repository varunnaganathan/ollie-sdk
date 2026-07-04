from __future__ import annotations

from types import SimpleNamespace

from ollie.tracing.adapter import adapt_llm_span, is_llm_span


def _span(
    *,
    name: str = "chat gpt-4o-mini",
    attrs: dict | None = None,
    start_ns: int = 1_700_000_000_000_000_000,
    end_ns: int = 1_700_000_001_500_000_000,
    status_name: str = "UNSET",
    scope_name: str = "opentelemetry.instrumentation.openai",
    span_id: int = 0xABCD,
):
    status_code = SimpleNamespace(name=status_name)
    status = SimpleNamespace(status_code=status_code, description=None)
    context = SimpleNamespace(span_id=span_id)
    scope = SimpleNamespace(name=scope_name)
    return SimpleNamespace(
        name=name,
        attributes=attrs or {},
        start_time=start_ns,
        end_time=end_ns,
        status=status,
        context=context,
        instrumentation_scope=scope,
    )


def test_is_llm_span_openai_scope():
    assert is_llm_span(_span())


def test_is_llm_span_rejects_plain_http():
    span = _span(name="HTTP GET", attrs={}, scope_name="opentelemetry.instrumentation.httpx")
    assert not is_llm_span(span)


def test_adapt_llm_span_extracts_core_fields():
    span = _span(
        attrs={
            "gen_ai.request.model": "gpt-4o-mini",
            "gen_ai.system": "openai",
            "gen_ai.usage.input_tokens": 12,
            "gen_ai.usage.output_tokens": 4,
            "gen_ai.response.finish_reasons": ["stop"],
            "gen_ai.prompt": "hello",
            "gen_ai.completion": "world",
        }
    )
    fields = adapt_llm_span(span, capture_content=True)
    assert fields["primitive"] == "generation"
    assert fields["name"] == "openai.chat"
    assert fields["input"] == "hello"
    assert fields["output"] == "world"
    by_name = {a["name"]: a["value"] for a in fields["attributes"]}
    assert by_name["model"] == "gpt-4o-mini"
    assert by_name["provider"] == "openai"
    assert by_name["input_tokens"] == 12
    assert by_name["output_tokens"] == 4
    assert by_name["finish_reason"] == "stop"
    assert by_name["latency_ms"] == 1500
    assert by_name["otel_span_id"] == "000000000000abcd"
    assert by_name["success"] is True
    assert "events" not in fields


def test_adapt_llm_span_error_status():
    span = _span(status_name="ERROR")
    span.status.description = "boom"
    fields = adapt_llm_span(span, capture_content=False)
    by_name = {a["name"]: a["value"] for a in fields["attributes"]}
    assert by_name["status"] == "error"
    assert by_name["success"] is False
    assert fields["input"] is None


def test_adapt_openinference_aliases():
    span = _span(
        attrs={
            "llm.model_name": "gpt-4o",
            "llm.token_count.prompt": 3,
            "llm.token_count.completion": 7,
        }
    )
    fields = adapt_llm_span(span)
    by_name = {a["name"]: a["value"] for a in fields["attributes"]}
    assert by_name["model"] == "gpt-4o"
    assert by_name["input_tokens"] == 3
    assert by_name["output_tokens"] == 7


def test_adapt_anthropic_span():
    span = _span(
        name="anthropic.messages",
        scope_name="opentelemetry.instrumentation.anthropic",
        attrs={
            "gen_ai.system": "anthropic",
            "gen_ai.request.model": "claude-3-5-haiku-latest",
            "gen_ai.usage.input_tokens": 10,
            "gen_ai.usage.output_tokens": 2,
        },
    )
    assert is_llm_span(span)
    fields = adapt_llm_span(span)
    assert fields["name"] == "anthropic.messages"
    by_name = {a["name"]: a["value"] for a in fields["attributes"]}
    assert by_name["provider"] == "anthropic"
    assert by_name["model"] == "claude-3-5-haiku-latest"


def test_adapt_gemini_span():
    span = _span(
        name="generate_content gemini-2.0-flash",
        scope_name="opentelemetry.instrumentation.google_genai",
        attrs={
            "gen_ai.system": "gemini",
            "gen_ai.request.model": "gemini-2.0-flash",
        },
    )
    assert is_llm_span(span)
    fields = adapt_llm_span(span)
    assert fields["name"] == "gemini.generate_content"
    by_name = {a["name"]: a["value"] for a in fields["attributes"]}
    assert by_name["provider"] == "gemini"
    assert by_name["model"] == "gemini-2.0-flash"
