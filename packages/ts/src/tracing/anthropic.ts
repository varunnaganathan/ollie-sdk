import { registerInstrumentations } from "@opentelemetry/instrumentation";

let instrumentor: { enable: () => void; disable: () => void } | null = null;
let instrumented = false;

export async function instrumentAnthropic(): Promise<boolean> {
  if (instrumented) return true;
  try {
    await import("@anthropic-ai/sdk" as string);
  } catch {
    return false;
  }

  try {
    const { AnthropicInstrumentation } = await import("@traceloop/instrumentation-anthropic");
    instrumentor = new AnthropicInstrumentation();
    registerInstrumentations({ instrumentations: [instrumentor as never] });
    instrumentor.enable();
    instrumented = true;
    return true;
  } catch (err) {
    throw new Error(
      `Anthropic OTel instrumentor not found. Install peers: @traceloop/instrumentation-anthropic. ${err}`,
    );
  }
}

export async function uninstrumentAnthropic(): Promise<void> {
  if (instrumentor) {
    try {
      instrumentor.disable();
    } catch {
      // ignore
    }
  }
  instrumented = false;
}
