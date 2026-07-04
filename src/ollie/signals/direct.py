"""Direct context signals from spans and interaction fields."""

from __future__ import annotations

import re
from typing import Any

from ollie.primitives import EXTERNAL_INTERACTION, GENERATION
from ollie.signals.spans import _attrs_map, interaction_status

SAFETY_FINISH = frozenset({"safety", "content_filter", "content_filtered", "blocklist"})
TRUNCATED_FINISH = frozenset({"length", "max_tokens", "max_output_tokens", "truncated"})

_IO_ERROR_RE = re.compile(
    r"(?i)(traceback|exception|rate\s*limit|quota|credit\s*balance|"
    r"resource_exhausted|permission\s*denied|\b401\b|\b403\b|\b429\b|"
    r"api\s*error|billing)",
)


def _dedupe(signals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for sig in signals:
        name = str(sig.get("name") or "")
        if not name or name in seen:
            continue
        seen.add(name)
        out.append(sig)
    return out


def direct_signals_for_interactions(
    interactions: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return (trigger, context) from interaction list (run-level)."""
    trigger: list[dict[str, Any]] = []
    context: list[dict[str, Any]] = []

    gens = [ix for ix in interactions if str(ix.get("primitive") or "") == GENERATION]
    tools = [ix for ix in interactions if str(ix.get("primitive") or "") == EXTERNAL_INTERACTION]

    for ix in gens:
        status = interaction_status(ix)
        name = str(ix.get("name") or "llm")
        attrs = _attrs_map(ix)
        if status == "failure":
            context.append({"name": "llm_error", "llm": name})
        else:
            if not str(ix.get("output") or "").strip():
                context.append({"name": "llm_empty_output", "llm": name})
        if not str(ix.get("input") or "").strip():
            context.append({"name": "llm_empty_input", "llm": name})
        fr = str(attrs.get("finish_reason") or "").strip().lower()
        if fr in TRUNCATED_FINISH:
            context.append({"name": "output_truncated", "llm": name})
        elif fr in SAFETY_FINISH:
            context.append({"name": "safety_stop", "llm": name})
        out_text = str(ix.get("output") or "")
        if out_text and _IO_ERROR_RE.search(out_text):
            context.append({"name": "io_error_in_output", "llm": name})

    failed_tools: list[dict[str, Any]] = []
    for ix in tools:
        status = interaction_status(ix)
        name = str(ix.get("name") or "tool")
        if status == "failure":
            failed_tools.append(ix)
            context.append({"name": "tool_error", "tool": name})

    if tools:
        context.append({"name": "used_tool"})
    if len(failed_tools) >= 2:
        trigger.append({"name": "repeated_tool_error"})

    return trigger, _dedupe(context)


def direct_signals_for_unit(ix: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Local signals for a single child interaction."""
    if not ix.get("parent_interaction_ref"):
        return [], []
    return direct_signals_for_interactions([ix])
