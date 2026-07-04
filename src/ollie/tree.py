from __future__ import annotations

from typing import Any


def _interactions(payload: dict[str, Any]) -> list[dict[str, Any]]:
    raw = payload.get("interactions") or []
    return [ix for ix in raw if isinstance(ix, dict)]


def _children_map(interactions: list[dict[str, Any]]) -> dict[str | None, list[dict[str, Any]]]:
    by_ref = {str(ix.get("interaction_ref")): ix for ix in interactions if ix.get("interaction_ref")}
    children: dict[str | None, list[dict[str, Any]]] = {}
    for ix in interactions:
        parent = ix.get("parent_interaction_ref")
        parent_key = str(parent) if parent else None
        if parent_key and parent_key not in by_ref:
            parent_key = None
        children.setdefault(parent_key, []).append(ix)
    for items in children.values():
        items.sort(key=lambda x: str(x.get("started_at") or ""))
    return children


def _format_ix(ix: dict[str, Any]) -> str:
    name = str(ix.get("name") or ix.get("interaction_ref") or "?")
    primitive = ix.get("primitive")
    prim = f" [{primitive}]" if primitive else ""
    events = ix.get("events")
    attrs = ix.get("attributes") or []
    suffix_parts: list[str] = []
    if isinstance(events, dict):
        n_sig = len(events.get("trigger") or []) + len(events.get("context") or [])
        n_spans = len(events.get("spans") or [])
        if n_sig:
            suffix_parts.append(f"signals={n_sig}")
        if n_spans:
            suffix_parts.append(f"spans={n_spans}")
    elif events:
        suffix_parts.append(f"events={len(events)}")
    if attrs:
        suffix_parts.append(f"attrs={len(attrs)}")
    suffix = f" {' '.join(suffix_parts)}" if suffix_parts else ""
    return f"{name}{prim}{suffix}"


def _render_node(ix: dict[str, Any], children_map: dict[str | None, list[dict[str, Any]]], *, prefix: str, is_last: bool) -> list[str]:
    ref = str(ix.get("interaction_ref") or "")
    branch = "└── " if is_last else "├── "
    lines = [f"{prefix}{branch}{_format_ix(ix)}"]
    child_prefix = prefix + ("    " if is_last else "│   ")
    kids = children_map.get(ref) or []
    for i, child in enumerate(kids):
        lines.extend(_render_node(child, children_map, prefix=child_prefix, is_last=i == len(kids) - 1))
    return lines


def render_interaction_tree(payload: dict[str, Any]) -> str:
    """Render ASCII tree from v2 workflow payload interactions[]."""
    workflow = payload.get("workflow") if isinstance(payload.get("workflow"), dict) else {}
    name = str(workflow.get("name") or "workflow")
    status = str(workflow.get("status") or "unknown")
    started = workflow.get("started_at") or "?"
    ended = workflow.get("ended_at") or "?"
    header = f"Workflow: {name} [{status}] {started} → {ended}"

    interactions = _interactions(payload)
    if not interactions:
        return header + "\n(no interactions)"

    children_map = _children_map(interactions)
    roots = children_map.get(None) or []
    if not roots:
        refs_with_parent = {str(ix.get("parent_interaction_ref")) for ix in interactions if ix.get("parent_interaction_ref")}
        roots = [ix for ix in interactions if str(ix.get("interaction_ref")) not in refs_with_parent]

    lines = [header]
    for i, root in enumerate(roots):
        lines.extend(_render_node(root, children_map, prefix="", is_last=i == len(roots) - 1))
    return "\n".join(lines)
