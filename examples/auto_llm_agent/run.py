#!/usr/bin/env python3
"""Run auto-instrumented LLM sample agent (OpenAI / Anthropic / Gemini)."""

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

from auto_llm_agent.agent import assert_auto_capture, print_tree, run_auto_agent  # noqa: E402

_KEY_ENV = {
    "openai": ("OPENAI_API_KEY",),
    "anthropic": ("ANTHROPIC_API_KEY",),
    "gemini": ("GEMINI_API_KEY", "GOOGLE_API_KEY"),
}


def main() -> int:
    p = argparse.ArgumentParser(description="Ollie multi-provider auto-LLM agent")
    p.add_argument("--provider", default="openai", choices=sorted(_KEY_ENV))
    p.add_argument("--local-only", action="store_true", default=True)
    p.add_argument("--flush", action="store_true")
    p.add_argument("--print-tree", action="store_true")
    p.add_argument("--validate", action="store_true")
    p.add_argument("--print-wire", action="store_true")
    args = p.parse_args()

    keys = _KEY_ENV[args.provider]
    if not any((os.getenv(k) or "").strip() for k in keys):
        print(f"one of {keys} is required for provider={args.provider}", file=sys.stderr)
        return 1

    result, wire = run_auto_agent(provider=args.provider, local_only=not args.flush)

    if args.validate:
        assert_auto_capture(wire, provider=args.provider)
        print("validate: ok", file=sys.stderr)
    if args.print_tree:
        print(print_tree(wire), file=sys.stderr)
    if args.print_wire:
        print(json.dumps(wire, indent=2))

    interactions = wire.get("interactions") or []
    gens = sum(1 for i in interactions if i.get("primitive") == "generation")
    tools = sum(1 for i in interactions if i.get("primitive") == "external_interaction")
    print(
        f"OK provider={args.provider} interactions={len(interactions)} "
        f"generation={gens} tools={tools} accepted={result.get('accepted')}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
