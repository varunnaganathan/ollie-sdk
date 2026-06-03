"""Built-in name sets (no HTTP / Postgres)."""

from __future__ import annotations

from ollie.builtins import BUILTIN_FEATURE_NAMES, BUILTIN_SPAN_TYPES


def test_builtin_features_include_retry_count():
    assert "retry_count" in BUILTIN_FEATURE_NAMES


def test_builtin_span_types_include_tool_call():
    assert "tool_call" in BUILTIN_SPAN_TYPES
