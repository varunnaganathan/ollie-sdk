import { EXTERNAL_INTERACTION, GENERATION } from "../primitives.js";

export function attrsMap(ix: Record<string, unknown>): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const a of (ix.attributes as Record<string, unknown>[]) ?? []) {
    if (a && a.name != null) out[String(a.name)] = a.value;
  }
  return out;
}

export function interactionStatus(ix: Record<string, unknown>): "success" | "failure" {
  const attrs = attrsMap(ix);
  if (attrs.success === false) return "failure";
  const status = String(attrs.status ?? "")
    .trim()
    .toLowerCase();
  if (["error", "failure", "failed"].includes(status)) return "failure";
  return "success";
}

export function interactionToSpan(ix: Record<string, unknown>): Record<string, unknown> | null {
  if (!ix.parent_interaction_ref) return null;
  const prim = String(ix.primitive ?? "").trim();
  let spanType: string | null = null;
  if (prim === GENERATION) spanType = "llm";
  else if (prim === EXTERNAL_INTERACTION) spanType = "tool";
  else return null;

  const span: Record<string, unknown> = {
    type: spanType,
    name: String(ix.name ?? spanType),
    status: interactionStatus(ix),
    span_ref: String(ix.interaction_ref ?? ""),
  };
  if (ix.parent_interaction_ref) span.parent_span_ref = String(ix.parent_interaction_ref);
  return span;
}

export function interactionsToSpans(interactions: Record<string, unknown>[]): Record<string, unknown>[] {
  const spans: Record<string, unknown>[] = [];
  for (const ix of interactions) {
    const span = interactionToSpan(ix);
    if (span?.span_ref) spans.push(span);
  }
  return spans;
}
