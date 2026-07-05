import { createRequire } from "node:module";
import { trace, SpanStatusCode } from "@opentelemetry/api";

const require = createRequire(import.meta.url);

let manualWrapped = false;
let instrumented = false;

type GenerateContentFn = (...args: unknown[]) => Promise<unknown>;

async function tryCommunityInstrumentor(): Promise<boolean> {
  try {
    await import("@google/genai" as string);
  } catch {
    return false;
  }
  const candidates = ["@traceai/google-genai", "@traceloop/instrumentation-google-genai"];
  for (const mod of candidates) {
    try {
      const loaded = (await import(mod)) as Record<string, new () => { instrument: () => void }>;
      const cls =
        loaded.GoogleGenAIInstrumentation ??
        loaded.GoogleGenAiInstrumentation ??
        loaded.default;
      if (typeof cls === "function") {
        new cls().instrument();
        return true;
      }
    } catch {
      continue;
    }
  }
  return false;
}

function wrapGoogleGenai(): boolean {
  if (manualWrapped) return true;
  try {
    const genai = require("@google/genai") as {
      GoogleGenAI?: new (opts: { apiKey: string }) => {
        models: { generateContent: GenerateContentFn };
      };
    };
    if (!genai.GoogleGenAI) return false;

    const Original = genai.GoogleGenAI;
    const tracer = trace.getTracer("ollie-sdk-ts-gemini");

    genai.GoogleGenAI = class PatchedGoogleGenAI extends Original {
      constructor(opts: { apiKey: string }) {
        super(opts);
        const models = this.models;
        const original = models.generateContent.bind(models);
        models.generateContent = async (...args: unknown[]) => {
          return tracer.startActiveSpan("gemini.generate_content", async (span) => {
            span.setAttribute("gen_ai.system", "gemini");
            try {
              const result = await original(...args);
              const text = (result as { text?: string })?.text;
              if (text) span.setAttribute("gen_ai.completion", text.slice(0, 2000));
              span.setStatus({ code: SpanStatusCode.OK });
              return result;
            } catch (err) {
              span.setStatus({ code: SpanStatusCode.ERROR, message: String(err) });
              throw err;
            } finally {
              span.end();
            }
          });
        };
      }
    } as typeof genai.GoogleGenAI;

    manualWrapped = true;
    return true;
  } catch {
    return false;
  }
}

export async function instrumentGemini(): Promise<boolean> {
  if (instrumented) return true;
  if (await tryCommunityInstrumentor()) {
    instrumented = true;
    return true;
  }
  if (wrapGoogleGenai()) {
    instrumented = true;
    return true;
  }
  console.warn("Gemini OTel instrumentor not found; install @google/genai for manual wrap fallback.");
  return false;
}

export async function uninstrumentGemini(): Promise<void> {
  instrumented = false;
  manualWrapped = false;
}
