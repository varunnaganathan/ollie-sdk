import type { ExportResult } from "@opentelemetry/core";
import type { ReadableSpan } from "@opentelemetry/sdk-trace";

import { adaptLlmSpan, isLlmSpan } from "./adapter.js";
import { getActiveParent, getActiveWorkflow } from "../context.js";
import { Instruments } from "../instruments.js";
import { activeInstruments } from "./state.js";

const PROVIDER_TO_INSTRUMENT: Record<string, Instruments> = {
  openai: Instruments.OPENAI,
  anthropic: Instruments.ANTHROPIC,
  gemini: Instruments.GEMINI,
};

let warnedNoWorkflow = false;

export class OllieSpanExporter {
  captureContent: boolean;
  enabled = true;

  constructor(options?: { captureContent?: boolean }) {
    this.captureContent = options?.captureContent !== false;
  }

  export(spans: ReadableSpan[], resultCallback: (result: ExportResult) => void): void {
    if (!this.enabled) {
      resultCallback({ code: 0 });
      return;
    }
    for (const span of spans) this.handleSpan(span);
    resultCallback({ code: 0 });
  }

  shutdown(): Promise<void> {
    return Promise.resolve();
  }

  forceFlush(): Promise<void> {
    return Promise.resolve();
  }

  private handleSpan(span: ReadableSpan): void {
    if (!isLlmSpan(span)) return;
    const allowed = activeInstruments();
    if (!allowed.size) return;

    const fields = adaptLlmSpan(span, { captureContent: this.captureContent });
    let provider = "openai";
    for (const attr of (fields.attributes as Array<{ name: string; value: unknown }>) ?? []) {
      if (attr.name === "provider") {
        provider = String(attr.value ?? "openai");
        break;
      }
    }
    const inst = PROVIDER_TO_INSTRUMENT[provider];
    if (!inst || !allowed.has(inst)) return;

    const wf = getActiveWorkflow();
    if (!wf) {
      if (!warnedNoWorkflow) {
        console.warn(
          "Ollie auto-instrumentation: LLM span dropped (no active workflow). Wrap LLM calls in client.workflow().",
        );
        warnedNoWorkflow = true;
      }
      return;
    }

    const parent = getActiveParent();
    try {
      wf.recordCompletedInteraction({
        name: String(fields.name),
        primitive: String(fields.primitive),
        parent,
        input: (fields.input as string | null) ?? null,
        output: (fields.output as string | null) ?? null,
        startedAt: String(fields.started_at),
        endedAt: String(fields.ended_at),
        attributes: fields.attributes as Array<{ name: string; value: boolean | number | string }>,
      });
    } catch (err) {
      console.error("Ollie auto-instrumentation: failed to record LLM interaction", err);
    }
  }
}
