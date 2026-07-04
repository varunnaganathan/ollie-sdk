from __future__ import annotations

from typing import Any

from simulated_agent.expectations import RunManifest

REQUIRED_PRIMITIVES = frozenset({"generation", "delegation", "external_interaction"})


def assert_triple_run_variance(manifests: list[RunManifest]) -> None:
    if len(manifests) != 3:
        raise AssertionError(f"expected 3 manifests, got {len(manifests)}")

    def signature(m: RunManifest) -> tuple[Any, ...]:
        return (
            frozenset(m.tools_picked),
            len(m.tools_picked),
            m.user_language,
            tuple(sorted(m.span_names)),
        )

    sigs = [signature(m) for m in manifests]
    diffs = sum(1 for i in range(3) for j in range(i + 1, 3) if sigs[i] != sigs[j])
    if diffs < 2:
        raise AssertionError(f"expected at least 2/3 run pairs to differ; signatures={sigs}")


def _is_v2_payload(wire_payload: dict[str, Any]) -> bool:
    return int(wire_payload.get("schema_version") or 0) >= 2 or isinstance(wire_payload.get("workflow"), dict)


def assert_interaction_tree(wire_payload: dict[str, Any], manifest: RunManifest) -> None:
    interactions = wire_payload.get("interactions") or []
    if len(interactions) != manifest.interaction_count:
        raise AssertionError(
            f"interaction count: expected {manifest.interaction_count}, got {len(interactions)}"
        )

    by_ref = {str(ix.get("interaction_ref")): ix for ix in interactions if ix.get("interaction_ref")}
    roots = [ix for ix in interactions if not ix.get("parent_interaction_ref")]
    if len(roots) != 1:
        raise AssertionError(f"expected exactly one root interaction, got {len(roots)}")

    root = roots[0]
    if root.get("interaction_ref") != "ix_0":
        raise AssertionError(f"root must be ix_0, got {root.get('interaction_ref')!r}")

    for ix in interactions:
        parent = ix.get("parent_interaction_ref")
        if parent is not None and str(parent) not in by_ref:
            raise AssertionError(f"parent_interaction_ref {parent!r} not found for {ix.get('name')!r}")
        if not ix.get("started_at") or not ix.get("ended_at"):
            raise AssertionError(f"interaction {ix.get('name')!r} missing started_at/ended_at")

    primitives = {ix.get("primitive") for ix in interactions if ix.get("primitive")}
    if manifest.tools_picked:
        missing = REQUIRED_PRIMITIVES - primitives
        if missing:
            raise AssertionError(f"missing primitives on tree: {missing}")

    tool_ixs = [ix for ix in interactions if ix.get("primitive") == "external_interaction"]
    if manifest.tools_picked and len(tool_ixs) != len(manifest.tools_picked):
        raise AssertionError(
            f"external_interaction count {len(tool_ixs)} != tools picked {len(manifest.tools_picked)}"
        )

    workflow = wire_payload.get("workflow") or {}
    if not workflow.get("name") or not workflow.get("status"):
        raise AssertionError("workflow missing name or status")


def _count_tool_spans(compiled_ix: dict[str, Any]) -> int:
    layers = compiled_ix.get("layers") or {}
    spans = layers.get("spans") if isinstance(layers, dict) else []
    if not isinstance(spans, list):
        return 0
    return sum(1 for s in spans if isinstance(s, dict) and s.get("kind") == "tool_call")


def _spans(compiled_ix: dict[str, Any]) -> list[dict[str, Any]]:
    layers = compiled_ix.get("layers") or {}
    spans = layers.get("spans") if isinstance(layers, dict) else []
    return [s for s in spans if isinstance(s, dict)] if isinstance(spans, list) else []


def assert_full_coverage(
    manifest: RunManifest,
    wire_payload: dict[str, Any],
    compiled_interactions: list[dict[str, Any]],
) -> None:
    if _is_v2_payload(wire_payload):
        assert_interaction_tree(wire_payload, manifest)
        if len(compiled_interactions) != manifest.interaction_count:
            raise AssertionError(
                f"compiled interaction count: expected {manifest.interaction_count}, "
                f"got {len(compiled_interactions)}"
            )
        return

    if len(compiled_interactions) != manifest.interaction_count:
        raise AssertionError(
            f"interaction count: expected {manifest.interaction_count}, got {len(compiled_interactions)}"
        )

    indices = [int(ix.get("interaction_index", -1)) for ix in compiled_interactions]
    if indices != list(range(len(indices))):
        raise AssertionError(f"interaction_index not contiguous 0..n-1: {indices}")

    wire_ixs = wire_payload.get("interactions") or []
    for i, compiled_ix in enumerate(compiled_interactions):
        if i >= len(wire_ixs):
            raise AssertionError(f"missing wire interaction[{i}]")

        spans = _spans(compiled_ix)
        expected = (
            manifest.per_ix_expected_span_count[i]
            if i < len(manifest.per_ix_expected_span_count)
            else manifest.expected_span_count
        )
        if expected and len(spans) != expected:
            raise AssertionError(f"interaction[{i}] span count expected {expected}, got {len(spans)}")

        kinds = {s.get("kind") for s in spans}
        tools_for_ix = (
            manifest.per_ix_tools_picked[i]
            if i < len(manifest.per_ix_tools_picked)
            else manifest.tools_picked
        )
        if tools_for_ix:
            missing_kinds = {"llm_call", "tool_call", "tool_dispatch"} - kinds
            if missing_kinds:
                raise AssertionError(f"interaction[{i}] missing span kinds: {missing_kinds}")

        if not compiled_ix.get("start_time") or not compiled_ix.get("end_time"):
            raise AssertionError(f"interaction[{i}] missing start_time/end_time")

        for s in spans:
            if not s.get("started_at") or not s.get("ended_at"):
                raise AssertionError(f"interaction[{i}] span missing started_at/ended_at: {s.get('kind')}")

    _assert_features_across_trace(manifest, compiled_interactions)


def _assert_features_across_trace(
    manifest: RunManifest,
    compiled_interactions: list[dict[str, Any]],
) -> None:
    for fname in manifest.features_emitted:
        found = any(
            fname in (ix.get("features") or {})
            for ix in compiled_interactions
            if isinstance(ix.get("features"), dict)
        )
        if not found and fname not in ("user_language",):
            raise AssertionError(f"missing feature {fname!r} in compiled features on any interaction")


def assert_mapping_fidelity(
    wire_ix: dict[str, Any],
    norm_ix: dict[str, Any],
    compiled_ix: dict[str, Any],
) -> None:
    if wire_ix.get("interaction_ref"):
        if str(wire_ix.get("input") or "") != str(norm_ix.get("input_text") or ""):
            raise AssertionError("input text mismatch normalized")
        if str(wire_ix.get("output") or "") != str(norm_ix.get("output_text") or ""):
            raise AssertionError("output text mismatch normalized")
    else:
        if str(wire_ix.get("source") or "") != str(norm_ix.get("input_role") or ""):
            raise AssertionError("source != input_role")
        if str(wire_ix.get("target") or "") != str(norm_ix.get("output_role") or ""):
            raise AssertionError("target != output_role")

    if compiled_ix.get("adapter_key") != "sdk.instrumentation.v1":
        raise AssertionError("adapter_key must be sdk.instrumentation.v1")
    if not compiled_ix.get("id") or not compiled_ix.get("trace_id") or not compiled_ix.get("customer_id"):
        raise AssertionError("compiled row missing id/trace_id/customer_id")


def assert_reconstructed_complete(
    compiled_ix: dict[str, Any],
    manifest: RunManifest,
    process_result: dict[str, Any],
    *,
    ix_index: int = 0,
) -> None:
    for key in (
        "id",
        "trace_id",
        "customer_id",
        "adapter_key",
        "event_version",
    ):
        if not compiled_ix.get(key):
            raise AssertionError(f"compiled interaction missing {key}")

    if not (compiled_ix.get("input_text") or compiled_ix.get("output_text")):
        raise AssertionError("compiled interaction must have input_text or output_text")

    signals = process_result.get("signal_registry") or []
    if not any(s.get("name") == "simulation_anomaly" for s in signals if isinstance(s, dict)):
        raise AssertionError("signal_registry missing simulation_anomaly")

    index_preview = process_result.get("index_preview") or {}
    if int(index_preview.get("chunk_count") or 0) < 1:
        raise AssertionError("index_preview.chunk_count must be >= 1")
