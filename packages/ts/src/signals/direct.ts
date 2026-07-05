import { EXTERNAL_INTERACTION, GENERATION } from "../primitives.js";
import { attrsMap, interactionStatus } from "./spans.js";

const SAFETY_FINISH = new Set(["safety", "content_filter", "content_filtered", "blocklist"]);
const TRUNCATED_FINISH = new Set(["length", "max_tokens", "max_output_tokens", "truncated"]);

const IO_ERROR_RE =
  /(traceback|exception|rate\s*limit|quota|credit\s*balance|resource_exhausted|permission\s*denied|\b401\b|\b403\b|\b429\b|api\s*error|billing)/i;

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

export function directSignalsForInteractions(
  interactions: Record<string, unknown>[],
): [Record<string, unknown>[], Record<string, unknown>[]] {
  const trigger: Record<string, unknown>[] = [];
  const context: Record<string, unknown>[] = [];

  const gens = interactions.filter((ix) => String(ix.primitive ?? "") === GENERATION);
  const tools = interactions.filter((ix) => String(ix.primitive ?? "") === EXTERNAL_INTERACTION);

  for (const ix of gens) {
    const status = interactionStatus(ix);
    const name = String(ix.name ?? "llm");
    const attrs = attrsMap(ix);
    if (status === "failure") {
      context.push({ name: "llm_error", llm: name });
    } else if (!String(ix.output ?? "").trim()) {
      context.push({ name: "llm_empty_output", llm: name });
    }
    if (!String(ix.input ?? "").trim()) {
      context.push({ name: "llm_empty_input", llm: name });
    }
    const fr = String(attrs.finish_reason ?? "")
      .trim()
      .toLowerCase();
    if (TRUNCATED_FINISH.has(fr)) {
      context.push({ name: "output_truncated", llm: name });
    } else if (SAFETY_FINISH.has(fr)) {
      context.push({ name: "safety_stop", llm: name });
    }
    const outText = String(ix.output ?? "");
    if (outText && IO_ERROR_RE.test(outText)) {
      context.push({ name: "io_error_in_output", llm: name });
    }
  }

  const failedTools: Record<string, unknown>[] = [];
  for (const ix of tools) {
    const status = interactionStatus(ix);
    const name = String(ix.name ?? "tool");
    if (status === "failure") {
      failedTools.push(ix);
      context.push({ name: "tool_error", tool: name });
    }
  }

  if (tools.length) context.push({ name: "used_tool" });
  if (failedTools.length >= 2) trigger.push({ name: "repeated_tool_error" });

  return [trigger, dedupe(context)];
}

export function directSignalsForUnit(
  ix: Record<string, unknown>,
): [Record<string, unknown>[], Record<string, unknown>[]] {
  if (!ix.parent_interaction_ref) return [[], []];
  return directSignalsForInteractions([ix]);
}

export { dedupe };
