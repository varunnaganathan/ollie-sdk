import { baselineSignals } from "./baselines.js";
import { dedupe, directSignalsForInteractions, directSignalsForUnit } from "./direct.js";
import { interactionToSpan, interactionsToSpans } from "./spans.js";

export function emptyEvents(): Record<string, unknown> {
  return { trigger: [], context: [], spans: [] };
}

export function instrumentRun(options: {
  interactions: Record<string, unknown>[];
  rootOutput: string | null;
  workflowSuccess: boolean;
  workflowLatencyMs?: number;
}): Record<string, unknown> {
  const spans = interactionsToSpans(options.interactions);
  const [trigD, ctxD] = directSignalsForInteractions(options.interactions);
  const [trigB, ctxB] = baselineSignals({
    interactions: options.interactions,
    rootOutput: options.rootOutput,
    workflowSuccess: options.workflowSuccess,
    workflowLatencyMs: options.workflowLatencyMs,
  });
  return {
    trigger: dedupe([...trigD, ...trigB]),
    context: dedupe([...ctxD, ...ctxB]),
    spans,
  };
}

export function instrumentUnit(ix: Record<string, unknown>): Record<string, unknown> {
  const span = interactionToSpan(ix);
  const spans = span ? [span] : [];
  if (!ix.parent_interaction_ref) return emptyEvents();

  const [trig, ctx] = directSignalsForUnit(ix);
  const [, ctxB] = baselineSignals({
    interactions: [ix],
    rootOutput: String(ix.output ?? ""),
    workflowSuccess: true,
    workflowLatencyMs: 0,
  });
  const skip = new Set(["empty_final_response", "runtime_failure", "used_tool", "tool_loop"]);
  const filtered = ctxB.filter((s) => !skip.has(String(s.name)));
  return {
    trigger: dedupe(trig),
    context: dedupe([...ctx, ...filtered]),
    spans,
  };
}

export function finalizeInteractions(
  interactions: Record<string, unknown>[],
  options: {
    workflowSuccess: boolean;
    workflowLatencyMs?: number;
  },
): Record<string, unknown>[] {
  if (!interactions.length) return [];

  const roots = interactions.filter((ix) => !ix.parent_interaction_ref);
  const root = roots[0] ?? interactions[0]!;
  const rootRef = String(root.interaction_ref ?? "");

  const runEvents = instrumentRun({
    interactions,
    rootOutput: String(root.output ?? ""),
    workflowSuccess: options.workflowSuccess,
    workflowLatencyMs: options.workflowLatencyMs,
  });

  return interactions.map((ix) => {
    const row = { ...ix };
    const ref = String(ix.interaction_ref ?? "");
    if (ref === rootRef || !ix.parent_interaction_ref) {
      row.events = runEvents;
    } else {
      row.events = instrumentUnit(ix);
    }
    return row;
  });
}
