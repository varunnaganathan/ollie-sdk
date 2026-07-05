import { trace } from "@opentelemetry/api";
import { resourceFromAttributes } from "@opentelemetry/resources";
import { SimpleSpanProcessor, TracerProvider } from "@opentelemetry/sdk-trace";

import { OllieSpanExporter } from "./exporter.js";

let provider: TracerProvider | null = null;
let exporter: OllieSpanExporter | null = null;

export async function setupTracerProvider(options?: { captureContent?: boolean }): Promise<TracerProvider> {
  if (exporter) {
    exporter.captureContent = options?.captureContent !== false;
    exporter.enabled = true;
  } else {
    exporter = new OllieSpanExporter({ captureContent: options?.captureContent });
  }

  if (provider) return provider;

  provider = new TracerProvider({
    resource: resourceFromAttributes({ "service.name": "ollie-sdk-ts" }),
    spanProcessors: [new SimpleSpanProcessor({ exporter })],
  });
  trace.setGlobalTracerProvider(provider);
  return provider;
}

export async function shutdownTracerProvider(): Promise<void> {
  if (exporter) exporter.enabled = false;
  if (provider) {
    await provider.shutdown();
    provider = null;
  }
}
