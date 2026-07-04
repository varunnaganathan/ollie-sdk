"""Map OTel ReadableSpan → Ollie generation interaction fields."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

# GenAI semantic conventions + OpenInference / OpenLLMetry aliases
_MODEL_KEYS = (
    "gen_ai.request.model",
    "gen_ai.response.model",
    "llm.model_name",
    "llm.request.model",
)
_PROVIDER_KEYS = ("gen_ai.system", "llm.system", "llm.provider")
_INPUT_TOKENS_KEYS = (
    "gen_ai.usage.input_tokens",
    "gen_ai.usage.prompt_tokens",
    "llm.token_count.prompt",
    "llm.usage.prompt_tokens",
)
_OUTPUT_TOKENS_KEYS = (
    "gen_ai.usage.output_tokens",
    "gen_ai.usage.completion_tokens",
    "llm.token_count.completion",
    "llm.usage.completion_tokens",
)
_FINISH_REASON_KEYS = (
    "gen_ai.response.finish_reasons",
    "gen_ai.response.finish_reason",
    "llm.response.finish_reason",
)
_INPUT_TEXT_KEYS = (
    "gen_ai.prompt",
    "gen_ai.input.messages",
    "llm.input_messages",
    "llm.prompts",
)
_OUTPUT_TEXT_KEYS = (
    "gen_ai.completion",
    "gen_ai.output.messages",
    "llm.output_messages",
    "llm.completions",
)

_PROVIDER_DEFAULT_NAMES = {
    "openai": "openai.chat",
    "anthropic": "anthropic.messages",
    "gemini": "gemini.generate_content",
}


def _attrs(span: Any) -> dict[str, Any]:
    raw = getattr(span, "attributes", None) or {}
    if hasattr(raw, "items"):
        return dict(raw)
    return {}


def _first(attrs: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for k in keys:
        if k in attrs and attrs[k] is not None:
            return attrs[k]
    return None


def _ns_to_iso(ns: int | None) -> str:
    if ns is None:
        return datetime.now(timezone.utc).isoformat()
    seconds = ns / 1_000_000_000
    return datetime.fromtimestamp(seconds, tz=timezone.utc).isoformat()


def _latency_ms(start_ns: int | None, end_ns: int | None) -> int | None:
    if start_ns is None or end_ns is None:
        return None
    return max(0, int((end_ns - start_ns) / 1_000_000))


def _status_str(span: Any) -> str:
    status = getattr(span, "status", None)
    if status is None:
        return "ok"
    status_code = getattr(status, "status_code", None)
    name = getattr(status_code, "name", None) or str(status_code or "")
    if name.upper() in ("ERROR", "STATUS_CODE_ERROR"):
        return "error"
    return "ok"


def _stringify(value: Any, *, max_len: int = 2000) -> str | None:
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        try:
            import json

            text = json.dumps(value, default=str)
        except Exception:
            text = str(value)
    else:
        text = str(value)
    if len(text) > max_len:
        return text[: max_len - 3] + "..."
    return text


def _scope_name(span: Any) -> str:
    instrumentation = getattr(span, "instrumentation_scope", None) or getattr(
        span, "instrumentation_info", None
    )
    if instrumentation is None:
        return ""
    return str(getattr(instrumentation, "name", "") or "")


def _normalize_provider(raw: Any, *, scope: str, span_name: str) -> str:
    text = str(raw or "").strip().lower()
    blob = f"{text} {scope.lower()} {span_name.lower()}"
    if "anthropic" in blob or "claude" in blob:
        return "anthropic"
    if "gemini" in blob or "google_genai" in blob or "google.genai" in blob or "generativeai" in blob:
        return "gemini"
    if "openai" in blob or text in ("openai", "openai.com", "azure.ai.openai"):
        return "openai"
    if text:
        return text
    return "openai"


def _default_interaction_name(provider: str, span_name: str) -> str:
    default = _PROVIDER_DEFAULT_NAMES.get(provider, f"{provider}.llm")
    name = (span_name or "").strip()
    if not name:
        return default
    lower = name.lower()
    if provider == "openai" and ("chat" in lower or name.startswith("openai.")):
        return "openai.chat" if "chat" in lower or not name.startswith("openai.") else name
    if provider == "anthropic" and ("message" in lower or "anthropic" in lower):
        return "anthropic.messages"
    if provider == "gemini" and ("generate" in lower or "gemini" in lower or "content" in lower):
        return "gemini.generate_content"
    if name.startswith(("openai.", "anthropic.", "gemini.")):
        return name
    return default


def is_llm_span(span: Any) -> bool:
    """Heuristic: GenAI / provider instrumentor LLM spans only."""
    attrs = _attrs(span)
    name = str(getattr(span, "name", "") or "")
    scope_name = _scope_name(span).lower()

    for token in ("openai", "anthropic", "google_genai", "google.generativeai", "gemini", "genai"):
        if token in scope_name:
            return True
    if any(k.startswith("gen_ai.") for k in attrs):
        return True
    if any(k.startswith("llm.") for k in attrs):
        return True
    lower = name.lower()
    if any(t in lower for t in ("chat", "completion", "message", "generate_content", "openai", "anthropic", "gemini")):
        if "http" in lower and not any(k.startswith("gen_ai.") for k in attrs):
            return False
        return True
    return False


def adapt_llm_span(span: Any, *, capture_content: bool = True) -> dict[str, Any]:
    """Return fields for WorkflowSession.record_completed_interaction."""
    attrs = _attrs(span)
    start_ns = getattr(span, "start_time", None)
    end_ns = getattr(span, "end_time", None)
    status = _status_str(span)
    model = _first(attrs, _MODEL_KEYS)
    scope = _scope_name(span)
    span_name = str(getattr(span, "name", "") or "").strip()
    provider = _normalize_provider(_first(attrs, _PROVIDER_KEYS), scope=scope, span_name=span_name)
    name = _default_interaction_name(provider, span_name)

    attributes: list[dict[str, Any]] = [
        {"name": "provider", "value": str(provider)},
        {"name": "status", "value": status},
    ]
    if model is not None:
        attributes.append({"name": "model", "value": str(model)})
    latency = _latency_ms(start_ns, end_ns)
    if latency is not None:
        attributes.append({"name": "latency_ms", "value": latency})
    in_tok = _first(attrs, _INPUT_TOKENS_KEYS)
    if in_tok is not None:
        try:
            attributes.append({"name": "input_tokens", "value": int(in_tok)})
        except (TypeError, ValueError):
            pass
    out_tok = _first(attrs, _OUTPUT_TOKENS_KEYS)
    if out_tok is not None:
        try:
            attributes.append({"name": "output_tokens", "value": int(out_tok)})
        except (TypeError, ValueError):
            pass
    finish = _first(attrs, _FINISH_REASON_KEYS)
    if finish is not None:
        if isinstance(finish, (list, tuple)):
            finish = finish[0] if finish else None
        if finish is not None:
            attributes.append({"name": "finish_reason", "value": str(finish)})

    ctx = getattr(span, "context", None)
    span_id = getattr(ctx, "span_id", None)
    if span_id is not None:
        attributes.append({"name": "otel_span_id", "value": format(int(span_id), "016x")})

    if status == "error":
        attributes.append({"name": "success", "value": False})
    else:
        attributes.append({"name": "success", "value": True})

    input_text = None
    output_text = None
    if capture_content:
        input_text = _stringify(_first(attrs, _INPUT_TEXT_KEYS))
        output_text = _stringify(_first(attrs, _OUTPUT_TEXT_KEYS))

    return {
        "name": name,
        "primitive": "generation",
        "input": input_text,
        "output": output_text,
        "started_at": _ns_to_iso(start_ns),
        "ended_at": _ns_to_iso(end_ns),
        "attributes": attributes,
    }
