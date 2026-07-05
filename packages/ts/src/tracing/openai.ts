import { registerInstrumentations } from "@opentelemetry/instrumentation";

let instrumentor: { enable: () => void; disable: () => void } | null = null;
let instrumented = false;

export async function instrumentOpenai(): Promise<boolean> {
  if (instrumented) return true;
  try {
    await import("openai" as string);
  } catch {
    return false;
  }

  try {
    const { OpenAIInstrumentation } = await import("@opentelemetry/instrumentation-openai");
    instrumentor = new OpenAIInstrumentation();
    registerInstrumentations({ instrumentations: [instrumentor as never] });
    instrumentor.enable();
    instrumented = true;
    return true;
  } catch (err) {
    throw new Error(
      `OpenAI OTel instrumentor not found. Install peers: @opentelemetry/instrumentation-openai. ${err}`,
    );
  }
}

export async function uninstrumentOpenai(): Promise<void> {
  if (instrumentor) {
    try {
      instrumentor.disable();
    } catch {
      // ignore
    }
  }
  instrumented = false;
}
