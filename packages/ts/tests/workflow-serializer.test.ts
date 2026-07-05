import { describe, expect, it } from "vitest";

import { Client } from "../src/client.js";
import { GENERATION } from "../src/primitives.js";

describe("workflow serializer", () => {
  it("produces v2 payload with structured events", () => {
    const client = new Client({
      apiKey: "k",
      baseUrl: "http://example.com",
      agentId: "a1",
    });

    const session = client.session("sess-1");
    session.enter();
    const wf = client.workflow({ name: "W", input: "in" });
    wf.enter();
    const child = wf.interaction.start({
      name: "Child",
      primitive: GENERATION,
      parent: wf.root,
      input: "in",
    });
    child.attribute("latency_ms", 1);
    child.output = "out";
    wf.interaction.end(child);
    wf.output = "done";
    wf.exit();
    session.exit();

    const payload = wf.toValidatePayload();
    expect(payload.schema_version).toBe(2);
    expect(payload.session_id).toBe("sess-1");
    expect((payload.workflow as Record<string, unknown>).name).toBe("W");
    const interactions = payload.interactions as Record<string, unknown>[];
    expect(interactions).toHaveLength(2);

    const childIx = interactions.find((i) => i.name === "Child")!;
    expect(childIx.primitive).toBe(GENERATION);
    expect(childIx.events).toMatchObject({
      trigger: expect.any(Array),
      context: expect.any(Array),
      spans: expect.any(Array),
    });
    const spans = (childIx.events as Record<string, unknown>).spans as Record<string, unknown>[];
    expect(spans[0]?.span_ref).toBeTruthy();

    const root = interactions.find((i) => !i.parent_interaction_ref)!;
    expect((root.events as Record<string, unknown>).spans).toBeTruthy();
  });
});
