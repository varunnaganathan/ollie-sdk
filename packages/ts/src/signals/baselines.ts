import { EXTERNAL_INTERACTION, GENERATION } from "../primitives.js";
import { attrsMap, interactionStatus } from "./spans.js";

function toolLoopThreshold(): number {
  const raw = process.env.OLLIE_TOOL_LOOP_THRESHOLD;
  if (!raw) return 5;
  const n = Number.parseInt(raw, 10);
  return Number.isNaN(n) ? 5 : Math.max(2, n);
}

function highLatencyMs(): number {
  const raw = process.env.OLLIE_HIGH_LATENCY_MS;
  if (!raw) return 30_000;
  const n = Number.parseInt(raw, 10);
  return Number.isNaN(n) ? 30_000 : Math.max(1, n);
}

function tokenBlowup(): number {
  const raw = process.env.OLLIE_TOKEN_BLOWUP;
  if (!raw) return 8000;
  const n = Number.parseInt(raw, 10);
  return Number.isNaN(n) ? 8000 : Math.max(1, n);
}

function llmErrorRate(): number {
  const raw = process.env.OLLIE_LLM_ERROR_RATE;
  if (!raw) return 0.5;
  const n = Number.parseFloat(raw);
  return Number.isNaN(n) ? 0.5 : Math.min(1, Math.max(0, n));
}

function dedupe(signals: Record<string, unknown>[]): Record<string, unknown>[] {
  const seen = new Set<string>();
  const out: Record<string, unknown>[] = [];
  for (const sig of signals) {
    const name = String(sig.name ?? "");
    if (!name || seen.has(name)) continue;
    seen.add(name);
    out.push(sig);
  }
  return out;
}

export function baselineSignals(options: {
  interactions: Record<string, unknown>[];
  rootOutput: string | null;
  workflowSuccess: boolean;
  workflowLatencyMs?: number;
}): [Record<string, unknown>[], Record<string, unknown>[]] {
  const trigger: Record<string, unknown>[] = [];
  const context: Record<string, unknown>[] = [];

  const gens = options.interactions.filter((ix) => String(ix.primitive ?? "") === GENERATION);
  const tools = options.interactions.filter((ix) => String(ix.primitive ?? "") === EXTERNAL_INTERACTION);

  const anyFailure = [...gens, ...tools].some((ix) => interactionStatus(ix) === "failure");
  if (!options.workflowSuccess || anyFailure) {
    context.push({ name: "runtime_failure" });
  }

  if (!String(options.rootOutput ?? "").trim()) {
    context.push({ name: "empty_final_response" });
  }

  if (tools.length >= toolLoopThreshold()) {
    context.push({ name: "tool_loop" });
  }

  let latencyHit = (options.workflowLatencyMs ?? 0) >= highLatencyMs();
  for (const ix of gens) {
    const attrs = attrsMap(ix);
    const lat = Number(attrs.latency_ms ?? 0);
    if (!Number.isNaN(lat) && lat >= highLatencyMs()) latencyHit = true;

    const inTok = Number(attrs.input_tokens ?? 0);
    const outTok = Number(attrs.output_tokens ?? 0);
    const total = inTok + outTok;
    if (
      total >= tokenBlowup() ||
      (inTok > 0 && outTok >= Math.max(10, inTok * 10))
    ) {
      context.push({ name: "llm_token_blowup", llm: ix.name });
    }
  }

  if (latencyHit) context.push({ name: "high_latency" });

  if (gens.length) {
    const failed = gens.filter((ix) => interactionStatus(ix) === "failure").length;
    const rate = failed / gens.length;
    if (rate >= llmErrorRate()) {
      context.push({
        name: "llm_provider_error_rate",
        failed,
        total: gens.length,
        rate,
      });
    }
  }

  return [trigger, dedupe(context)];
}
