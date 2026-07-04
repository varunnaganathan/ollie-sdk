"""Derived run-level signals (thresholds + rates)."""

from __future__ import annotations

import os
from typing import Any

from ollie.primitives import EXTERNAL_INTERACTION, GENERATION
from ollie.signals.spans import _attrs_map, interaction_status


def _tool_loop_threshold() -> int:
    try:
        return max(2, int(os.getenv("OLLIE_TOOL_LOOP_THRESHOLD", "5")))
    except ValueError:
        return 5


def _high_latency_ms() -> int:
    try:
        return max(1, int(os.getenv("OLLIE_HIGH_LATENCY_MS", "30000")))
    except ValueError:
        return 30000


def _token_blowup() -> int:
    try:
        return max(1, int(os.getenv("OLLIE_TOKEN_BLOWUP", "8000")))
    except ValueError:
        return 8000


def _llm_error_rate() -> float:
    try:
        return min(1.0, max(0.0, float(os.getenv("OLLIE_LLM_ERROR_RATE", "0.5"))))
    except ValueError:
        return 0.5


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


def baseline_signals(
    *,
    interactions: list[dict[str, Any]],
    root_output: str | None,
    workflow_success: bool,
    workflow_latency_ms: int = 0,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    trigger: list[dict[str, Any]] = []
    context: list[dict[str, Any]] = []

    gens = [ix for ix in interactions if str(ix.get("primitive") or "") == GENERATION]
    tools = [ix for ix in interactions if str(ix.get("primitive") or "") == EXTERNAL_INTERACTION]

    any_failure = any(interaction_status(ix) == "failure" for ix in gens + tools)
    if not workflow_success or any_failure:
        context.append({"name": "runtime_failure"})

    if not str(root_output or "").strip():
        context.append({"name": "empty_final_response"})

    if len(tools) >= _tool_loop_threshold():
        context.append({"name": "tool_loop"})

    latency_hit = workflow_latency_ms >= _high_latency_ms()
    for ix in gens:
        attrs = _attrs_map(ix)
        try:
            lat = int(attrs.get("latency_ms") or 0)
        except (TypeError, ValueError):
            lat = 0
        if lat >= _high_latency_ms():
            latency_hit = True
        try:
            in_tok = int(attrs.get("input_tokens") or 0)
            out_tok = int(attrs.get("output_tokens") or 0)
        except (TypeError, ValueError):
            in_tok, out_tok = 0, 0
        total = in_tok + out_tok
        if total >= _token_blowup() or (in_tok > 0 and out_tok >= max(10, in_tok * 10)):
            context.append({"name": "llm_token_blowup", "llm": ix.get("name")})

    if latency_hit:
        context.append({"name": "high_latency"})

    if gens:
        failed = sum(1 for ix in gens if interaction_status(ix) == "failure")
        rate = failed / len(gens)
        if rate >= _llm_error_rate():
            context.append(
                {
                    "name": "llm_provider_error_rate",
                    "failed": failed,
                    "total": len(gens),
                    "rate": rate,
                }
            )

    return trigger, _dedupe(context)
