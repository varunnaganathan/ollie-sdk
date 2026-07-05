import { GENERATION, EXTERNAL_INTERACTION } from "../../src/primitives.js";
import { renderInteractionTree } from "../../src/tree.js";

const PROVIDER_INSTRUMENT = {
  openai: "openai",
  anthropic: "anthropic",
  gemini: "gemini",
} as const;

export function assertAutoCapture(wire: Record<string, unknown>, provider: string): void {
  const interactions = (wire.interactions as Record<string, unknown>[]) ?? [];
  const gens = interactions.filter((i) => i.primitive === GENERATION);
  const tools = interactions.filter((i) => i.primitive === EXTERNAL_INTERACTION);
  if (!gens.length) throw new Error(`expected auto generation for ${provider}`);
  if (!tools.length) throw new Error("expected tool interaction");

  const attrs = Object.fromEntries(
    ((gens[0]!.attributes as Array<{ name: string; value: unknown }>) ?? []).map((a) => [
      a.name,
      a.value,
    ]),
  );
  if (attrs.provider !== provider) {
    throw new Error(`expected provider=${provider}, got ${attrs.provider}`);
  }

  const roots = interactions.filter((i) => !i.parent_interaction_ref);
  if (roots.length !== 1) throw new Error(`expected one root, got ${roots.length}`);
  const events = roots[0]!.events;
  if (!events || typeof events !== "object" || Array.isArray(events)) {
    throw new Error(`root events must be object, got ${typeof events}`);
  }
  const ev = events as Record<string, unknown>;
  for (const key of ["trigger", "context", "spans"]) {
    if (!(key in ev)) throw new Error(`root events missing ${key}`);
  }
  const spans = (ev.spans as Record<string, unknown>[]) ?? [];
  if (!spans.length) throw new Error("root events.spans empty");
  for (const s of spans) {
    for (const req of ["type", "name", "status", "span_ref"]) {
      if (!s[req]) throw new Error(`span missing ${req}: ${JSON.stringify(s)}`);
    }
    const extra = Object.keys(s).filter(
      (k) => !["type", "name", "status", "span_ref", "parent_span_ref"].includes(k),
    );
    if (extra.length) throw new Error(`span has unexpected fields ${extra.join(", ")}`);
  }
  const ctxNames = new Set(((ev.context as Array<{ name: string }>) ?? []).map((s) => s.name));
  if (!ctxNames.has("used_tool")) {
    throw new Error(`expected used_tool in context signals, got ${[...ctxNames].join(", ")}`);
  }
}

export function printTree(wire: Record<string, unknown>): string {
  return renderInteractionTree(wire);
}

export type Provider = keyof typeof PROVIDER_INSTRUMENT;

export { PROVIDER_INSTRUMENT };
