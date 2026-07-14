"""Anchored signal hit helpers (warehouse shape)."""

from __future__ import annotations

from typing import Any, Literal

AnchorKind = Literal["span", "interaction"]

_SPAN_ANCHORED = frozenset(
    {
        "tool_error",
        "llm_error",
        "output_truncated",
        "safety_stop",
        "llm_empty_output",
        "llm_empty_input",
        "io_error_in_output",
        "llm_token_blowup",
    }
)


def make_signal_hit(
    *,
    signal: str,
    kind: str,
    anchor_kind: AnchorKind,
    anchor_id: str,
) -> dict[str, Any]:
    return {
        "signal": str(signal).strip(),
        "kind": str(kind).strip(),
        "anchor_kind": anchor_kind,
        "anchor_id": str(anchor_id).strip(),
    }


def hits_from_named_signals(
    *,
    trigger: list[dict[str, Any]],
    context: list[dict[str, Any]],
    spans: list[dict[str, Any]],
    interaction_ref: str,
) -> list[dict[str, Any]]:
    spans_by_name: dict[str, list[dict[str, Any]]] = {}
    for sp in spans:
        if not isinstance(sp, dict):
            continue
        n = str(sp.get("name") or "").strip()
        if n:
            spans_by_name.setdefault(n, []).append(sp)

    pending: list[dict[str, Any]] = []
    seen: set[str] = set()

    def _append(sig: dict[str, Any], kind: str) -> None:
        name = str(sig.get("name") or "").strip()
        if not name or name in seen:
            return
        seen.add(name)
        if name in _SPAN_ANCHORED:
            anchor_kind: AnchorKind = "span"
            anchor_id = ""
            tool_or_llm = str(sig.get("tool") or sig.get("llm") or "").strip()
            if tool_or_llm:
                for sp in spans_by_name.get(tool_or_llm, []):
                    anchor_id = str(sp.get("span_ref") or "")
                    if anchor_id:
                        break
            if not anchor_id and name == "tool_error":
                for sp in spans:
                    if sp.get("type") == "tool" and sp.get("status") == "failure":
                        anchor_id = str(sp.get("span_ref") or "")
                        break
            if not anchor_id and name in ("llm_error", "output_truncated", "safety_stop", "llm_empty_output", "llm_empty_input", "io_error_in_output", "llm_token_blowup"):
                for sp in spans:
                    if sp.get("type") == "llm":
                        if name == "llm_error" and sp.get("status") != "failure":
                            continue
                        anchor_id = str(sp.get("span_ref") or "")
                        if anchor_id:
                            break
            if not anchor_id:
                anchor_kind = "interaction"
                anchor_id = interaction_ref
        else:
            anchor_kind = "interaction"
            anchor_id = interaction_ref
        pending.append(
            make_signal_hit(signal=name, kind=kind, anchor_kind=anchor_kind, anchor_id=anchor_id)
        )

    for sig in trigger:
        if isinstance(sig, dict):
            _append(sig, "trigger")
    for sig in context:
        if isinstance(sig, dict):
            _append(sig, "context")
    return pending
