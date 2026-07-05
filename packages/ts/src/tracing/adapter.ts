import type { ReadableSpan } from "@opentelemetry/sdk-trace";

const MODEL_KEYS = [
  "gen_ai.request.model",
  "gen_ai.response.model",
  "llm.model_name",
  "llm.request.model",
];
const PROVIDER_KEYS = ["gen_ai.system", "llm.system", "llm.provider"];
const INPUT_TOKENS_KEYS = [
  "gen_ai.usage.input_tokens",
  "gen_ai.usage.prompt_tokens",
  "llm.token_count.prompt",
  "llm.usage.prompt_tokens",
];
const OUTPUT_TOKENS_KEYS = [
  "gen_ai.usage.output_tokens",
  "gen_ai.usage.completion_tokens",
  "llm.token_count.completion",
  "llm.usage.completion_tokens",
];
const FINISH_REASON_KEYS = [
  "gen_ai.response.finish_reasons",
  "gen_ai.response.finish_reason",
  "llm.response.finish_reason",
];
const INPUT_TEXT_KEYS = [
  "gen_ai.prompt",
  "gen_ai.input.messages",
  "llm.input_messages",
  "llm.prompts",
];
const OUTPUT_TEXT_KEYS = [
  "gen_ai.completion",
  "gen_ai.output.messages",
  "llm.output_messages",
  "llm.completions",
];

const PROVIDER_DEFAULT_NAMES: Record<string, string> = {
  openai: "openai.chat",
  anthropic: "anthropic.messages",
  gemini: "gemini.generate_content",
};

function attrs(span: ReadableSpan): Record<string, unknown> {
  return { ...span.attributes };
}

function first(map: Record<string, unknown>, keys: string[]): unknown {
  for (const k of keys) {
    if (map[k] != null) return map[k];
  }
  return null;
}

function hrTimeToIso(hr?: [number, number]): string {
  if (!hr) return new Date().toISOString();
  const ns = hr[0] * 1e9 + hr[1];
  return new Date(ns / 1e6).toISOString();
}

function latencyMs(start?: [number, number], end?: [number, number]): number | null {
  if (!start || !end) return null;
  const startNs = start[0] * 1e9 + start[1];
  const endNs = end[0] * 1e9 + end[1];
  return Math.max(0, Math.floor((endNs - startNs) / 1e6));
}

function statusStr(span: ReadableSpan): string {
  const code = span.status?.code;
  if (code === 2) return "error";
  return "ok";
}

function stringify(value: unknown, maxLen = 2000): string | null {
  if (value == null) return null;
  let text: string;
  if (Array.isArray(value)) {
    try {
      text = JSON.stringify(value);
    } catch {
      text = String(value);
    }
  } else {
    text = String(value);
  }
  if (text.length > maxLen) return `${text.slice(0, maxLen - 3)}...`;
  return text;
}

function scopeName(span: ReadableSpan): string {
  return String(span.instrumentationScope?.name ?? "");
}

function normalizeProvider(raw: unknown, scope: string, spanName: string): string {
  const text = String(raw ?? "")
    .trim()
    .toLowerCase();
  const blob = `${text} ${scope.toLowerCase()} ${spanName.toLowerCase()}`;
  if (blob.includes("anthropic") || blob.includes("claude")) return "anthropic";
  if (
    blob.includes("gemini") ||
    blob.includes("google_genai") ||
    blob.includes("google.genai") ||
    blob.includes("generativeai")
  ) {
    return "gemini";
  }
  if (blob.includes("openai") || ["openai", "openai.com", "azure.ai.openai"].includes(text)) {
    return "openai";
  }
  return text || "openai";
}

function defaultInteractionName(provider: string, spanName: string): string {
  const fallback = PROVIDER_DEFAULT_NAMES[provider] ?? `${provider}.llm`;
  const name = spanName.trim();
  if (!name) return fallback;
  const lower = name.toLowerCase();
  if (provider === "openai" && (lower.includes("chat") || name.startsWith("openai."))) {
    return "openai.chat";
  }
  if (provider === "anthropic" && (lower.includes("message") || lower.includes("anthropic"))) {
    return "anthropic.messages";
  }
  if (
    provider === "gemini" &&
    (lower.includes("generate") || lower.includes("gemini") || lower.includes("content"))
  ) {
    return "gemini.generate_content";
  }
  if (name.startsWith("openai.") || name.startsWith("anthropic.") || name.startsWith("gemini.")) {
    return name;
  }
  return fallback;
}

export function isLlmSpan(span: ReadableSpan): boolean {
  const map = attrs(span);
  const name = String(span.name ?? "");
  const scope = scopeName(span).toLowerCase();

  for (const token of [
    "openai",
    "anthropic",
    "google_genai",
    "google.generativeai",
    "gemini",
    "genai",
  ]) {
    if (scope.includes(token)) return true;
  }
  if (Object.keys(map).some((k) => k.startsWith("gen_ai."))) return true;
  if (Object.keys(map).some((k) => k.startsWith("llm."))) return true;
  const lower = name.toLowerCase();
  if (
    ["chat", "completion", "message", "generate_content", "openai", "anthropic", "gemini"].some(
      (t) => lower.includes(t),
    )
  ) {
    if (lower.includes("http") && !Object.keys(map).some((k) => k.startsWith("gen_ai."))) {
      return false;
    }
    return true;
  }
  return false;
}

export function adaptLlmSpan(
  span: ReadableSpan,
  options?: { captureContent?: boolean },
): Record<string, unknown> {
  const map = attrs(span);
  const status = statusStr(span);
  const model = first(map, MODEL_KEYS);
  const scope = scopeName(span);
  const spanName = String(span.name ?? "").trim();
  const provider = normalizeProvider(first(map, PROVIDER_KEYS), scope, spanName);
  const name = defaultInteractionName(provider, spanName);

  const attributes: Array<{ name: string; value: boolean | number | string }> = [
    { name: "provider", value: provider },
    { name: "status", value: status },
  ];
  if (model != null) attributes.push({ name: "model", value: String(model) });
  const latency = latencyMs(span.startTime, span.endTime);
  if (latency != null) attributes.push({ name: "latency_ms", value: latency });

  const inTok = first(map, INPUT_TOKENS_KEYS);
  if (inTok != null) {
    const n = Number(inTok);
    if (!Number.isNaN(n)) attributes.push({ name: "input_tokens", value: n });
  }
  const outTok = first(map, OUTPUT_TOKENS_KEYS);
  if (outTok != null) {
    const n = Number(outTok);
    if (!Number.isNaN(n)) attributes.push({ name: "output_tokens", value: n });
  }

  let finish = first(map, FINISH_REASON_KEYS);
  if (Array.isArray(finish)) finish = finish[0];
  if (finish != null) attributes.push({ name: "finish_reason", value: String(finish) });

  const spanId = span.spanContext().spanId;
  if (spanId) attributes.push({ name: "otel_span_id", value: spanId });

  attributes.push({ name: "success", value: status !== "error" });

  let inputText: string | null = null;
  let outputText: string | null = null;
  if (options?.captureContent !== false) {
    inputText = stringify(first(map, INPUT_TEXT_KEYS));
    outputText = stringify(first(map, OUTPUT_TEXT_KEYS));
  }

  return {
    name,
    primitive: "generation",
    input: inputText,
    output: outputText,
    started_at: hrTimeToIso(span.startTime),
    ended_at: hrTimeToIso(span.endTime),
    attributes,
  };
}

export type { ReadableSpan };
