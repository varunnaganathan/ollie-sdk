#!/usr/bin/env python3
"""Register custom defs, instrument one trace, POST validate. Requires seed_sdk_test_customer + API."""

from __future__ import annotations

import os
import sys

import ollie


def main() -> int:
    client = ollie.Client(
        api_key=os.getenv("OLLIE_API_KEY", "sdk-test-key-1"),
        base_url=os.getenv("OLLIE_BASE_URL", "http://127.0.0.1:8001"),
        agent_id=os.getenv("OLLIE_AGENT_ID", "agent_sdk_test_1"),
    )

    client.define_feature(
        "discount_denied",
        kind="behavioral",
        description="Agent refused discount",
        type="bool",
    )
    client.define_feature(
        "user_tier",
        kind="attribution",
        description="Subscription tier",
        type="categorical",
        allowed_values=["free", "enterprise"],
    )
    client.define_span_type("checkout_validation", description="Checkout validation")
    client.define_signal("User Frustration", description="User dissatisfaction")

    trace = client.trace(conversation_id="sdk-example-1")
    with trace.interaction(source="planner", target="browser", input="plan", output="go") as ix:
        ix.feature("retry_count", 2)
        ix.feature("discount_denied", False)
        ix.feature("user_tier", "enterprise")
        with ix.span("tool_call", name="browser.open"):
            pass
        with ix.span("checkout_validation"):
            pass

    if os.getenv("OLLIE_SDK_PROCESS", "").strip().lower() in ("1", "true", "yes"):
        result = trace.flush_process()
        n_ix = len(result.get("interactions") or [])
        print(f"Process OK interactions={n_ix}", file=sys.stderr)
    else:
        trace.flush()
        print("Validate OK", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
