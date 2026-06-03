"""Built-in names (must match server sdk_ingest.builtins)."""

BUILTIN_SPAN_TYPES = frozenset(
    {"llm_call", "retrieval", "tool_call", "web_search", "db_query", "browser_session"}
)
BUILTIN_FEATURE_NAMES = frozenset(
    {
        "retry_count",
        "latency_ms",
        "latency_bucket",
        "token_count",
        "cost_usd",
        "model_family",
        "success",
        "failure",
    }
)
