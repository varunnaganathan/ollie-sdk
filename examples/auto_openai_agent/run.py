#!/usr/bin/env python3
"""Run auto-instrumented OpenAI sample agent (OTel → Ollie generation interactions)."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[4]
for _env in (_ROOT / ".env", _ROOT / "ollie_sentry_backend" / ".env"):
    if _env.exists():
        try:
            from dotenv import load_dotenv

            load_dotenv(_env)
        except ImportError:
            pass
        break

_PKG = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PKG / "src"))
sys.path.insert(0, str(_PKG / "examples"))

from auto_openai_agent.agent import assert_auto_capture, print_tree, run_auto_agent  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser(description="Ollie auto-OpenAI agent experiment")
    p.add_argument("--local-only", action="store_true", default=True)
    p.add_argument("--flush", action="store_true", help="flush_process to backend")
    p.add_argument("--print-tree", action="store_true")
    p.add_argument("--validate", action="store_true")
    p.add_argument("--print-wire", action="store_true")
    args = p.parse_args()

    if not (os.getenv("OPENAI_API_KEY") or "").strip():
        print("OPENAI_API_KEY is required", file=sys.stderr)
        return 1

    local_only = not args.flush
    result, wire = run_auto_agent(local_only=local_only)

    if args.validate:
        assert_auto_capture(wire)
        print("validate: ok", file=sys.stderr)

    if args.print_tree:
        print(print_tree(wire), file=sys.stderr)

    if args.print_wire:
        print(json.dumps(wire, indent=2))

    interactions = wire.get("interactions") or []
    gens = sum(1 for i in interactions if i.get("primitive") == "generation")
    tools = sum(1 for i in interactions if i.get("primitive") == "external_interaction")
    print(
        f"OK interactions={len(interactions)} generation={gens} tools={tools} "
        f"accepted={result.get('accepted')}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
