import { describe, expect, it } from "vitest";

import { adaptLlmSpan, isLlmSpan } from "../src/tracing/adapter.js";
import { finalizeInteractions } from "../src/signals/instrument.js";
import { GENERATION, EXTERNAL_INTERACTION } from "../src/primitives.js";

describe("otel adapter", () => {
  it("detects gen_ai spans", () => {
    const span = {
      name: "chat",
      attributes: { "gen_ai.system": "openai", "gen_ai.request.model": "gpt-4o-mini" },
      startTime: [1_700_000_000, 0] as [number, number],
      endTime: [1_700_000_001, 0] as [number, number],
      instrumentationScope: { name: "@opentelemetry/instrumentation-openai" },
      spanContext: () => ({ spanId: "abc123" }),
    };
    expect(isLlmSpan(span)).toBe(true);
    const fields = adaptLlmSpan(span);
    expect(fields.primitive).toBe("generation");
    expect(fields.name).toBe("openai.chat");
    const attrs = Object.fromEntries(
      ((fields.attributes as Array<{ name: string; value: unknown }>) ?? []).map((a) => [
        a.name,
        a.value,
      ]),
    );
    expect(attrs.provider).toBe("openai");
    expect(attrs.model).toBe("gpt-4o-mini");
  });
});

describe("signals", () => {
  it("finalizes root events with used_tool", () => {
    const interactions = [
      {
        interaction_ref: "ix_0",
        parent_interaction_ref: null,
        name: "root",
        primitive: null,
        input: "hi",
        output: "bye",
        attributes: [],
      },
      {
        interaction_ref: "ix_1",
        parent_interaction_ref: "ix_0",
        name: "tool",
        primitive: EXTERNAL_INTERACTION,
        input: "q",
        output: "a",
        attributes: [{ name: "success", value: true }],
      },
      {
        interaction_ref: "ix_2",
        parent_interaction_ref: "ix_0",
        name: "openai.chat",
        primitive: GENERATION,
        input: "hi",
        output: "bye",
        attributes: [{ name: "success", value: true }, { name: "provider", value: "openai" }],
      },
    ];
    const out = finalizeInteractions(interactions, { workflowSuccess: true, workflowLatencyMs: 10 });
    const root = out.find((i) => i.interaction_ref === "ix_0")!;
    const events = root.events as Record<string, unknown>;
    const ctx = (events.context as Array<{ name: string }>) ?? [];
    expect(ctx.some((s) => s.name === "used_tool")).toBe(true);
    const spans = (events.spans as Array<Record<string, string>>) ?? [];
    expect(spans.every((s) => s.type && s.name && s.status && s.span_ref)).toBe(true);
  });
});
