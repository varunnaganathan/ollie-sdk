import { DeliveryPipeline } from "./delivery.js";
import { Instruments } from "./instruments.js";
import { SessionContext } from "./session.js";
import { Transport } from "./transport.js";
import { WorkflowSession } from "./workflow.js";

export interface ClientOptions {
  apiKey?: string;
  baseUrl?: string;
  ingestBaseUrl?: string;
  agentId?: string;
  tracing?: boolean;
  instruments?: Iterable<Instruments | string> | null;
  blockInstruments?: Iterable<Instruments | string> | null;
  autoInstrument?: boolean;
  providers?: string[] | null;
  captureContent?: boolean;
}

export class Client {
  readonly apiKey: string;
  readonly baseUrl: string;
  readonly ingestBaseUrl: string;
  readonly agentId: string;
  readonly tracing: boolean;
  readonly instruments: Iterable<Instruments | string> | null | undefined;
  readonly blockInstruments: Iterable<Instruments | string> | null | undefined;
  readonly autoInstrument: boolean;
  readonly providers: string[] | null | undefined;
  readonly captureContent: boolean;
  readonly transport: Transport;
  readonly delivery: DeliveryPipeline;
  sessionId: string | null = null;

  constructor(options: ClientOptions = {}) {
    this.apiKey = (options.apiKey ?? process.env.OLLIE_API_KEY ?? "").trim();
    if (options.baseUrl != null) {
      this.baseUrl = options.baseUrl.trim();
    } else {
      this.baseUrl = (process.env.OLLIE_BASE_URL ?? "http://127.0.0.1:8001").trim();
    }
    if (options.ingestBaseUrl != null) {
      this.ingestBaseUrl = options.ingestBaseUrl.trim();
    } else if (options.baseUrl != null) {
      this.ingestBaseUrl = this.baseUrl;
    } else {
      const envIngest = (process.env.OLLIE_INGEST_BASE_URL ?? "").trim();
      this.ingestBaseUrl = envIngest || "http://127.0.0.1:8002";
    }
    this.agentId = (options.agentId ?? process.env.OLLIE_AGENT_ID ?? "").trim();
    if (!this.apiKey) throw new Error("OLLIE_API_KEY or apiKey is required");
    if (!this.agentId) throw new Error("OLLIE_AGENT_ID or agentId is required");

    this.transport = new Transport({
      baseUrl: this.baseUrl,
      ingestBaseUrl: this.ingestBaseUrl,
      apiKey: this.apiKey,
    });
    this.delivery = new DeliveryPipeline(this.transport, {
      sdkMeta: () => this.transport.sdkMeta(),
    });

    this.tracing = Boolean(options.tracing);
    this.instruments = options.instruments;
    this.blockInstruments = options.blockInstruments;
    this.autoInstrument = options.autoInstrument !== false;
    this.providers = options.providers ?? null;
    this.captureContent = options.captureContent !== false;

    if (this.tracing) {
      void import("./tracing/index.js").then(({ install }) =>
        install({
          instruments: this.instruments,
          blockInstruments: this.blockInstruments,
          autoInstrument: this.autoInstrument,
          providers: this.providers,
          captureContent: this.captureContent,
        }),
      );
    }
  }

  async flushDelivery() {
    return this.delivery.flushPending();
  }

  async retryFailedDelivery() {
    return this.delivery.retryFailed();
  }

  async shutdown(): Promise<void> {
    await this.delivery.shutdown();
    if (this.tracing) {
      try {
        const { uninstall } = await import("./tracing/index.js");
        uninstall();
      } catch {
        // ignore
      }
    }
  }

  async defineFeature(
    name: string,
    options: {
      kind?: string;
      description: string;
      type?: string;
      allowedValues?: string[];
    },
  ): Promise<void> {
    const body: Record<string, unknown> = {
      name,
      kind: options.kind ?? "observable",
      description: options.description,
      type: options.type ?? "categorical",
    };
    if (options.allowedValues) body.allowed_values = options.allowedValues;
    const resp = await this.transport.postJson("/v1/sdk/registry/features", body);
    if (resp._conflict) return;
  }

  async defineSpanType(name: string, options: { description: string }): Promise<void> {
    const resp = await this.transport.postJson("/v1/sdk/registry/span-types", {
      name,
      description: options.description,
    });
    if (resp._conflict) return;
  }

  async defineSignal(
    name: string,
    options: { description: string; detectorType?: string },
  ): Promise<void> {
    const resp = await this.transport.postJson("/v1/sdk/registry/signals", {
      name,
      description: options.description,
      detector_type: options.detectorType ?? "stub",
    });
    if (resp._conflict) return;
  }

  session(sessionId: string): SessionContext {
    return new SessionContext(this, sessionId);
  }

  workflow(options: { name: string; input?: string | null }): WorkflowSession {
    return new WorkflowSession(this, options);
  }
}
