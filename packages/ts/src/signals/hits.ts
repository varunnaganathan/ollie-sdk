/** Anchored signal hit helpers (warehouse shape). */
const SPAN_ANCHORED = new Set([
  "tool_error",
  "llm_error",
  "output_truncated",
  "safety_stop",
  "llm_empty_output",
  "llm_empty_input",
  "io_error_in_output",
  "llm_token_blowup",
]);

export type SignalHit = {
  signal: string;
  kind: string;
  anchor_kind: "span" | "interaction";
  anchor_id: string;
};

export function makeSignalHit(opts: {
  signal: string;
  kind: string;
  anchorKind: "span" | "interaction";
  anchorId: string;
}): SignalHit {
  return {
    signal: opts.signal.trim(),
    kind: opts.kind.trim(),
    anchor_kind: opts.anchorKind,
    anchor_id: opts.anchorId.trim(),
  };
}

export function hitsFromNamedSignals(opts: {
  trigger: Record<string, unknown>[];
  context: Record<string, unknown>[];
  spans: Record<string, unknown>[];
  interactionRef: string;
}): SignalHit[] {
  const { trigger, context, spans, interactionRef } = opts;
  const spansByName = new Map<string, Record<string, unknown>[]>();
  for (const sp of spans) {
    const n = String(sp.name ?? "").trim();
    if (!n) continue;
    const list = spansByName.get(n) ?? [];
    list.push(sp);
    spansByName.set(n, list);
  }
  const pending: SignalHit[] = [];
  const seen = new Set<string>();

  const append = (sig: Record<string, unknown>, kind: string) => {
    const name = String(sig.name ?? "").trim();
    if (!name || seen.has(name)) return;
    seen.add(name);
    let anchorKind: "span" | "interaction" = "interaction";
    let anchorId = interactionRef;
    if (SPAN_ANCHORED.has(name)) {
      anchorKind = "span";
      anchorId = "";
      const toolOrLlm = String(sig.tool ?? sig.llm ?? "").trim();
      if (toolOrLlm) {
        for (const sp of spansByName.get(toolOrLlm) ?? []) {
          anchorId = String(sp.span_ref ?? "");
          if (anchorId) break;
        }
      }
      if (!anchorId && name === "tool_error") {
        for (const sp of spans) {
          if (sp.type === "tool" && sp.status === "failure") {
            anchorId = String(sp.span_ref ?? "");
            break;
          }
        }
      }
      if (
        !anchorId &&
        [
          "llm_error",
          "output_truncated",
          "safety_stop",
          "llm_empty_output",
          "llm_empty_input",
          "io_error_in_output",
          "llm_token_blowup",
        ].includes(name)
      ) {
        for (const sp of spans) {
          if (sp.type !== "llm") continue;
          if (name === "llm_error" && sp.status !== "failure") continue;
          anchorId = String(sp.span_ref ?? "");
          if (anchorId) break;
        }
      }
      if (!anchorId) {
        anchorKind = "interaction";
        anchorId = interactionRef;
      }
    }
    pending.push(makeSignalHit({ signal: name, kind, anchorKind, anchorId }));
  };

  for (const sig of trigger) append(sig, "trigger");
  for (const sig of context) append(sig, "context");
  return pending;
}
