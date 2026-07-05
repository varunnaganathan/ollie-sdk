import { OllieError } from "../errors.js";
import { Instruments, resolveInstruments } from "../instruments.js";
import { instrumentAnthropic, uninstrumentAnthropic } from "./anthropic.js";
import { instrumentGemini, uninstrumentGemini } from "./gemini.js";
import { instrumentOpenai, uninstrumentOpenai } from "./openai.js";
import { setupTracerProvider, shutdownTracerProvider } from "./otelSetup.js";
import {
  activeInstruments as getActive,
  getTracingState,
  setTracingState,
} from "./state.js";

export const TRACING_INSTALL_HINT =
  "Auto-instrumentation requires optional peer deps. Install @opentelemetry/* and provider instrumentors.";

const LOADERS: Record<
  Instruments,
  { enable: () => Promise<boolean>; disable: () => Promise<void> }
> = {
  [Instruments.OPENAI]: { enable: instrumentOpenai, disable: uninstrumentOpenai },
  [Instruments.ANTHROPIC]: { enable: instrumentAnthropic, disable: uninstrumentAnthropic },
  [Instruments.GEMINI]: { enable: instrumentGemini, disable: uninstrumentGemini },
};

export async function install(options?: {
  instruments?: Iterable<Instruments | string> | null;
  blockInstruments?: Iterable<Instruments | string> | null;
  autoInstrument?: boolean;
  providers?: Iterable<string> | null;
  captureContent?: boolean;
}): Promise<Set<Instruments>> {
  const state = getTracingState();
  if (state.installed) return getActive();

  const wanted = resolveInstruments({
    instruments: options?.instruments,
    blockInstruments: options?.blockInstruments,
    autoInstrument: options?.autoInstrument,
    providers: options?.providers,
  });
  const cap = options?.captureContent !== false;

  if (!wanted.size) {
    await Promise.all(Object.values(LOADERS).map((l) => l.disable()));
    await shutdownTracerProvider();
    setTracingState({ installed: true, active: new Set(), captureContent: cap });
    return new Set();
  }

  try {
    await import("@opentelemetry/api");
    await import("@opentelemetry/sdk-trace");
  } catch (err) {
    throw new OllieError(TRACING_INSTALL_HINT + ` (${err})`);
  }

  await Promise.all(Object.values(LOADERS).map((l) => l.disable()));
  await setupTracerProvider({ captureContent: cap });

  const enabled = new Set<Instruments>();
  for (const inst of [...wanted].sort((a, b) => a.localeCompare(b))) {
    try {
      if (await LOADERS[inst].enable()) enabled.add(inst);
    } catch (err) {
      console.error(`Ollie tracing: failed to enable ${inst}`, err);
    }
  }

  setTracingState({ installed: true, active: enabled, captureContent: cap });
  return new Set(enabled);
}

export async function uninstall(): Promise<void> {
  await Promise.all(Object.values(LOADERS).map((l) => l.disable()));
  await shutdownTracerProvider();
  setTracingState({ installed: false, active: new Set() });
}

export function isInstalled(): boolean {
  return getTracingState().installed;
}

export { getActive as activeInstruments };
