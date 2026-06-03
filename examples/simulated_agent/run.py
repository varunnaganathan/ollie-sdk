#!/usr/bin/env python3
"""Run synthetic testing agent and print process results."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# Repo root .env
_ROOT = Path(__file__).resolve().parents[4]
for _env in (_ROOT / ".env", _ROOT / "ollie_sentry_backend" / ".env"):
    if _env.exists():
        try:
            from dotenv import load_dotenv

            load_dotenv(_env)
        except ImportError:
            pass
        break

# ollie-sdk src + examples on path
_PKG = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PKG / "src"))
sys.path.insert(0, str(_PKG / "examples"))

import ollie  # noqa: E402
from simulated_agent.agent import run_simulation  # noqa: E402
from simulated_agent.cases import get_case  # noqa: E402
from simulated_agent.registry import ensure_registry  # noqa: E402
from simulated_agent.validators import (  # noqa: E402
    assert_full_coverage,
    assert_mapping_fidelity,
    assert_reconstructed_complete,
    assert_triple_run_variance,
)


def _print_span_summary(interactions: list[dict]) -> None:
    for i, ix in enumerate(interactions):
        spans = (ix.get("layers") or {}).get("spans") or []
        print(f"\n--- interaction[{i}] spans ({len(spans)}) ---", file=sys.stderr)
        for sp in spans:
            if not isinstance(sp, dict):
                continue
            payload_keys = list((sp.get("payload") or {}).keys())
            print(
                f"  {sp.get('kind')} name={sp.get('name')!r} parent={sp.get('parent_span_id')!r} payload_keys={payload_keys}",
                file=sys.stderr,
            )


def _print_triple_diff(manifests: list) -> None:
    print("\n=== triple-run diff ===", file=sys.stderr)
    for m in manifests:
        print(
            f"seed={m.seed} tools={m.tools_picked} lang={m.user_language} "
            f"spans={m.span_names} features={len(m.features_emitted)}",
            file=sys.stderr,
        )


def main() -> int:
    p = argparse.ArgumentParser(description="Ollie simulated testing agent")
    p.add_argument("--case", default="random_single_ix")
    p.add_argument("--seed", type=int, default=None)
    p.add_argument("--triple-run", action="store_true")
    p.add_argument("--print-interactions", action="store_true")
    p.add_argument("--print-normalized", action="store_true")
    p.add_argument("--print-spans", action="store_true")
    p.add_argument("--print-diff", action="store_true")
    p.add_argument("--validate", action="store_true", help="run V2-V4 validators locally")
    p.add_argument("--print-registry", action="store_true", help="print signal_registry + manifest_preview")
    args = p.parse_args()

    client = ollie.Client(
        api_key=os.getenv("OLLIE_API_KEY", "sdk-test-key-1"),
        base_url=os.getenv("OLLIE_BASE_URL", "http://127.0.0.1:8001"),
        agent_id=os.getenv("OLLIE_AGENT_ID", "agent_sdk_test_1"),
    )
    ensure_registry(client)
    case = get_case(args.case)

    if args.triple_run:
        seeds = [101, 202, 303]
        manifests = []
        last_result = None
        for s in seeds:
            last_result, m = run_simulation(client, case=case, seed=s)
            manifests.append(m)
        if args.print_diff:
            _print_triple_diff(manifests)
        if args.validate:
            assert_triple_run_variance(manifests)
        result = last_result
        manifest = manifests[-1]
    else:
        result, manifest = run_simulation(client, case=case, seed=args.seed)

    if not result.get("accepted"):
        print(json.dumps(result, indent=2), file=sys.stderr)
        return 1

    if args.validate and manifest.wire_payload:
        compiled = result.get("interactions") or []
        normalized = result.get("normalized") or {}
        norm_ixs = normalized.get("interactions") or []
        wire_ixs = manifest.wire_payload.get("interactions") or []
        assert_full_coverage(manifest, manifest.wire_payload, compiled)
        for i, (w, n, c) in enumerate(zip(wire_ixs, norm_ixs, compiled)):
            assert_mapping_fidelity(w, n, c)
            assert_reconstructed_complete(c, manifest, result, ix_index=i)

    if args.print_normalized:
        print(json.dumps(result.get("normalized"), indent=2))
    if args.print_interactions:
        print(json.dumps(result.get("interactions"), indent=2))
    if args.print_spans:
        _print_span_summary(result.get("interactions") or [])
    if args.print_registry:
        print(json.dumps(
            {
                "signal_registry": result.get("signal_registry"),
                "manifest_preview": result.get("manifest_preview"),
            },
            indent=2,
        ))

    print(f"OK case={args.case} accepted=True interactions={len(result.get('interactions') or [])}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
