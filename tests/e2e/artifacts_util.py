"""Write inspectable JSON artifacts under tests/e2e/artifacts/."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ARTIFACTS_DIR = Path(__file__).resolve().parent / "artifacts"


def manifest_to_dict(manifest: Any) -> dict[str, Any]:
    return {
        "seed": manifest.seed,
        "case_id": manifest.case_id,
        "conversation_id": manifest.conversation_id,
        "tools_picked": manifest.tools_picked,
        "user_language": manifest.user_language,
        "features_emitted": manifest.features_emitted,
        "span_kinds": manifest.span_kinds,
        "span_names": manifest.span_names,
        "interaction_count": manifest.interaction_count,
        "expected_span_count": manifest.expected_span_count,
        "per_ix_expected_span_count": manifest.per_ix_expected_span_count,
        "per_ix_tools_picked": manifest.per_ix_tools_picked,
        "log_events": [
            {"kind": e.kind, "detail": e.detail} for e in manifest.log.events
        ],
    }


def write_json_artifact(filename: str, payload: dict[str, Any]) -> Path:
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    path = ARTIFACTS_DIR / filename
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return path


def write_sim_artifact(
    filename: str,
    *,
    manifest: Any,
    result: dict[str, Any],
    wire: dict[str, Any],
) -> Path:
    return write_json_artifact(
        filename,
        {
            "manifest": manifest_to_dict(manifest),
            "wire": wire,
            "accepted": result.get("accepted"),
            "trace_id": result.get("trace_id"),
            "conversation_id": result.get("conversation_id"),
            "interaction_count": result.get("interaction_count"),
            "span_count": result.get("span_count"),
            "manifest_revision": result.get("manifest_revision"),
            "instrumentation_revision": result.get("instrumentation_revision"),
            "queue_enqueued": result.get("queue_enqueued"),
            "normalized": result.get("normalized"),
            "interactions": result.get("interactions"),
            "sparse_previews": result.get("sparse_previews"),
            "signal_registry": result.get("signal_registry"),
            "index_preview": result.get("index_preview"),
        "manifest_preview": result.get("manifest_preview"),
        "instrumentation_catalog": result.get("instrumentation_catalog"),
    },
    )
