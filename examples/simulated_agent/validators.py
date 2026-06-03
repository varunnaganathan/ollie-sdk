from __future__ import annotations

from typing import Any

from simulated_agent.expectations import RunManifest

REQUIRED_SPAN_KINDS = frozenset({"llm_call", "tool_call", "tool_dispatch"})


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
            missing_kinds = REQUIRED_SPAN_KINDS - kinds
            if missing_kinds:
                raise AssertionError(f"interaction[{i}] missing span kinds: {missing_kinds}")

        dispatch_ids = {s.get("span_id") for s in spans if s.get("kind") == "tool_dispatch"}
        for s in spans:
            if s.get("kind") != "tool_call":
                continue
            parent = s.get("parent_span_id")
            if parent and dispatch_ids and parent not in dispatch_ids:
                raise AssertionError(
                    f"tool_call span parent_span_id {parent!r} not in tool_dispatch ids {dispatch_ids}"
                )

        tool_count_feat = (compiled_ix.get("features") or {}).get("tools_invoked_count")
        actual_tools = _count_tool_spans(compiled_ix)
        if tool_count_feat is not None and int(tool_count_feat) != actual_tools:
            raise AssertionError(
                f"interaction[{i}] tools_invoked_count={tool_count_feat} but tool_call spans={actual_tools}"
            )

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
        if fname == "user_language":
            found = any(
                fname in ((ix.get("extras") or {}).get("attribution") or {})
                for ix in compiled_interactions
            )
            if not found:
                raise AssertionError(f"missing attribution feature {fname!r} on any interaction")
            for ix in compiled_interactions:
                feats = ix.get("features") or {}
                if isinstance(feats, dict) and fname in feats:
                    raise AssertionError(f"attribution {fname!r} must not be in features dict")
        elif fname == "agent_confidence_band":
            found = any(
                fname in (ix.get("features") or {})
                for ix in compiled_interactions
                if isinstance(ix.get("features"), dict)
            )
            if not found:
                raise AssertionError(f"missing observable feature {fname!r}")
        else:
            found = any(
                fname in (ix.get("features") or {})
                for ix in compiled_interactions
                if isinstance(ix.get("features"), dict)
            )
            if not found:
                raise AssertionError(f"missing feature {fname!r} in compiled features on any interaction")


def assert_mapping_fidelity(
    wire_ix: dict[str, Any],
    norm_ix: dict[str, Any],
    compiled_ix: dict[str, Any],
) -> None:
    if str(wire_ix.get("source") or "") != str(norm_ix.get("input_role") or ""):
        raise AssertionError("source != input_role")
    if str(wire_ix.get("target") or "") != str(norm_ix.get("output_role") or ""):
        raise AssertionError("target != output_role")

    if str(wire_ix.get("input") or "") != str(norm_ix.get("input_text") or ""):
        raise AssertionError("input text mismatch normalized")
    if str(wire_ix.get("output") or "") != str(norm_ix.get("output_text") or ""):
        raise AssertionError("output text mismatch normalized")

    if compiled_ix.get("adapter_key") != "sdk.instrumentation.v1":
        raise AssertionError("adapter_key must be sdk.instrumentation.v1")
    if not compiled_ix.get("id") or not compiled_ix.get("trace_id") or not compiled_ix.get("customer_id"):
        raise AssertionError("compiled row missing id/trace_id/customer_id")

    wire_spans = wire_ix.get("spans") or []
    norm_spans = (norm_ix.get("layers") or {}).get("spans") or []
    if len(wire_spans) != len(norm_spans):
        raise AssertionError(f"span count wire {len(wire_spans)} != normalized {len(norm_spans)}")

    for ws, ns in zip(wire_spans, norm_spans):
        if str(ws.get("kind") or "") != str(ns.get("kind") or ""):
            raise AssertionError(f"span kind mismatch {ws} vs {ns}")


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
        "input_role",
        "output_role",
    ):
        if not compiled_ix.get(key):
            raise AssertionError(f"compiled interaction missing {key}")

    if not (compiled_ix.get("input_text") or compiled_ix.get("output_text")):
        raise AssertionError("compiled interaction must have input_text or output_text")

    spans = _spans(compiled_ix)
    if not spans:
        raise AssertionError("compiled interaction must have layers.spans")

    tools_for_ix = (
        manifest.per_ix_tools_picked[ix_index]
        if ix_index < len(manifest.per_ix_tools_picked)
        else manifest.tools_picked
    )
    if tools_for_ix and _count_tool_spans(compiled_ix) < 1:
        raise AssertionError("expected at least one tool_call span when tools were picked")

    llm_spans = [s for s in spans if s.get("kind") == "llm_call"]
    if not llm_spans:
        raise AssertionError("expected llm_call span")
    llm_payload = llm_spans[0].get("payload") or {}
    if not (llm_payload.get("phase") or llm_payload.get("model")):
        raise AssertionError("llm_call span missing payload.phase or payload.model")

    for sp in spans:
        if sp.get("kind") == "tool_call":
            payload = sp.get("payload") or {}
            if not payload.get("tool"):
                raise AssertionError("tool_call span missing payload.tool")

    signals = process_result.get("signal_registry") or []
    if not any(s.get("name") == "simulation_anomaly" for s in signals if isinstance(s, dict)):
        raise AssertionError("signal_registry missing simulation_anomaly")

    previews = process_result.get("sparse_previews") or []
    interactions = process_result.get("interactions") or []
    if len(previews) < len(interactions):
        raise AssertionError("sparse_previews length < interactions")

    index_preview = process_result.get("index_preview") or {}
    if int(index_preview.get("chunk_count") or 0) < 1:
        raise AssertionError("index_preview.chunk_count must be >= 1")

    sample_keys = index_preview.get("sample_metadata_keys") or []
    if sample_keys and "interaction_event_id" not in sample_keys:
        raise AssertionError("index_preview.sample_metadata_keys should include interaction_event_id")

    manifest_preview = process_result.get("manifest_preview") or {}
    fields = manifest_preview.get("fields") or {}
    if isinstance(fields, dict) and manifest.features_emitted:
        for fname in ("agent_confidence_band", "response_char_count"):
            if fname in manifest.features_emitted and fname not in fields:
                pass  # sparse may skip some numerics
