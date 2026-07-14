import { baselineSignals } from "./baselines.js";
import { dedupe, directSignalsForInteractions, directSignalsForUnit } from "./direct.js";
import { hitsFromNamedSignals, type SignalHit } from "./hits.js";
import { interactionToSpan, interactionsToSpans } from "./spans.js";

export function emptyEvents(): Record<string, unknown> {
  return { trigger: [], context: [], spans: [] };
}

export function instrumentRun(options: {
  interactions: Record<string, unknown>[];
  rootOutput: string | null;
  workflowSuccess: boolean;
  workflowLatencyMs?: number;
  interactionRef?: string;
}): { events: Record<string, unknown>; signalHits: SignalHit[] } {
  const spans = interactionsToSpans(options.interactions);
  const [trigD, ctxD] = directSignalsForInteractions(options.interactions);
  const [trigB, ctxB] = baselineSignals({
    interactions: options.interactions,
    rootOutput: options.rootOutput,
    workflowSuccess: options.workflowSuccess,
    workflowLatencyMs: options.workflowLatencyMs,
  });
  const trigger = dedupe([...trigD, ...trigB]);
  const context = dedupe([...ctxD, ...ctxB]);
  const interactionRef = options.interactionRef ?? "ix_0";
  return {
    events: { trigger: [], context: [], spans },
    signalHits: hitsFromNamedSignals({ trigger, context, spans, interactionRef }),
  };
}

export function instrumentUnit(ix: Record<string, unknown>): {
  events: Record<string, unknown>;
  signalHits: SignalHit[];
} {
  const span = interactionToSpan(ix);
  const spans = span ? [span] : [];
  const ref = String(ix.interaction_ref ?? "");
  if (!ix.parent_interaction_ref) return { events: emptyEvents(), signalHits: [] };

  const [trig, ctx] = directSignalsForUnit(ix);
  const [, ctxB] = baselineSignals({
    interactions: [ix],
    rootOutput: String(ix.output ?? ""),
    workflowSuccess: true,
    workflowLatencyMs: 0,
  });
  const skip = new Set(["empty_final_response", "runtime_failure", "used_tool", "tool_loop"]);
  const filtered = ctxB.filter((s) => !skip.has(String(s.name)));
  const trigger = dedupe(trig);
  const context = dedupe([...ctx, ...filtered]);
  return {
    events: { trigger: [], context: [], spans },
    signalHits: hitsFromNamedSignals({
      trigger,
      context,
      spans,
      interactionRef: ref || "ix_0",
    }),
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

  const { events: runEvents, signalHits: runHits } = instrumentRun({
    interactions,
    rootOutput: String(root.output ?? ""),
    workflowSuccess: options.workflowSuccess,
    workflowLatencyMs: options.workflowLatencyMs,
    interactionRef: rootRef || "ix_0",
  });

  return interactions.map((ix) => {
    const row = { ...ix };
    const ref = String(ix.interaction_ref ?? "");
    if (ref === rootRef || !ix.parent_interaction_ref) {
      row.events = runEvents;
      row._signal_hits = runHits;
    } else {
      const { events, signalHits } = instrumentUnit(ix);
      row.events = events;
      row._signal_hits = signalHits;
    }
    return row;
  });
}
