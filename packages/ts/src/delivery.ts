import { randomUUID } from "node:crypto";

import { OllieDeliveryError } from "./errors.js";
import type { Transport } from "./transport.js";

export interface DeliveryConfig {
  maxBufferEvents: number;
  flushIntervalS: number;
  compression: boolean;
  maxRetries: number;
  retryBackoffBaseS: number;
}

export function deliveryConfigFromEnv(): DeliveryConfig {
  const int = (name: string, fallback: number) => {
    const raw = process.env[name];
    if (!raw) return fallback;
    const n = Number.parseInt(raw, 10);
    return Number.isNaN(n) ? fallback : n;
  };
  const float = (name: string, fallback: number) => {
    const raw = process.env[name];
    if (!raw) return fallback;
    const n = Number.parseFloat(raw);
    return Number.isNaN(n) ? fallback : n;
  };
  const comp = (process.env.OLLIE_COMPRESSION ?? "1").trim().toLowerCase();
  return {
    maxBufferEvents: int("OLLIE_BUFFER_MAX_EVENTS", 50),
    flushIntervalS: float("OLLIE_BUFFER_FLUSH_INTERVAL_S", 5),
    compression: !["0", "false", "no"].includes(comp),
    maxRetries: int("OLLIE_RETRY_MAX", 5),
    retryBackoffBaseS: float("OLLIE_RETRY_BACKOFF_BASE", 0.5),
  };
}

export interface DeliveryBatch {
  batchId: string;
  events: Record<string, unknown>[];
  attempt: number;
}

export interface DeliveryResult {
  batchId: string;
  attempt: number;
  eventCount: number;
  acceptedCount: number;
  duplicateCount: number;
  rejectedCount: number;
  response: Record<string, unknown> | null;
  retried: boolean;
  ok: boolean;
}

export class DeliveryPipeline {
  private readonly transport: Transport;
  private readonly config: DeliveryConfig;
  private readonly sdkMeta: () => Record<string, string>;
  private readonly clock: () => number;
  private readonly sleep: (ms: number) => Promise<void>;
  private buffer: Record<string, unknown>[] = [];
  private failedBatches: DeliveryBatch[] = [];
  private timer: ReturnType<typeof setInterval> | null = null;
  private closed = false;

  constructor(
    transport: Transport,
    options?: {
      config?: DeliveryConfig;
      sdkMeta?: () => Record<string, string>;
      clock?: () => number;
      sleep?: (ms: number) => Promise<void>;
    },
  ) {
    this.transport = transport;
    this.config = options?.config ?? deliveryConfigFromEnv();
    this.sdkMeta = options?.sdkMeta ?? (() => ({ name: "ollie-sdk-ts", version: "0.0.0" }));
    this.clock = options?.clock ?? (() => Date.now());
    this.sleep = options?.sleep ?? ((ms) => new Promise((r) => setTimeout(r, ms)));
    this.startTimer();
  }

  get failedBatchList(): DeliveryBatch[] {
    return [...this.failedBatches];
  }

  private startTimer(): void {
    if (this.closed || this.config.flushIntervalS <= 0) return;
    this.timer = setInterval(() => {
      void this.flushPending().catch(() => undefined);
    }, this.config.flushIntervalS * 1000);
    if (this.timer.unref) this.timer.unref();
  }

  submit(event: Record<string, unknown>): void {
    this.buffer.push(event);
    if (this.buffer.length >= this.config.maxBufferEvents) {
      const pending = this.buffer;
      this.buffer = [];
      void this.sendBatch(pending);
    }
  }

  async flushPending(): Promise<DeliveryResult[]> {
    const pending = this.buffer;
    this.buffer = [];
    const results: DeliveryResult[] = [];
    if (pending.length) results.push(await this.sendBatch(pending));
    return results;
  }

  async retryFailed(): Promise<DeliveryResult[]> {
    const batches = [...this.failedBatches];
    this.failedBatches = [];
    const out: DeliveryResult[] = [];
    for (const batch of batches) {
      out.push(
        await this.sendBatch(batch.events, {
          batchId: batch.batchId,
          attempt: batch.attempt,
        }),
      );
    }
    return out;
  }

  async shutdown(): Promise<void> {
    this.closed = true;
    if (this.timer) {
      clearInterval(this.timer);
      this.timer = null;
    }
    await this.flushPending();
  }

  private async sendBatch(
    events: Record<string, unknown>[],
    options?: { batchId?: string; attempt?: number },
  ): Promise<DeliveryResult> {
    if (!events.length) {
      return {
        batchId: "",
        attempt: 0,
        eventCount: 0,
        acceptedCount: 0,
        duplicateCount: 0,
        rejectedCount: 0,
        response: {},
        retried: false,
        ok: true,
      };
    }

    const bid = options?.batchId ?? randomUUID();
    const attempt = options?.attempt ?? 0;
    const body = {
      sdk: this.sdkMeta(),
      batch_id: bid,
      events,
    };

    let lastError: unknown = null;
    let response: Record<string, unknown> | null = null;
    let retried = false;

    for (let i = 0; i <= this.config.maxRetries; i++) {
      const tryAttempt = attempt + i;
      if (i > 0) {
        retried = true;
        const delay = this.config.retryBackoffBaseS * 2 ** (i - 1) * 1000;
        await this.sleep(delay);
      }
      try {
        response = await this.transport.sendEventBatch(body, {
          compression: this.config.compression,
        });
        const rejected = Number(response.rejected_count ?? 0);
        const accepted = Number(response.accepted_count ?? 0);
        const duplicate = Number(response.duplicate_count ?? 0);
        const result: DeliveryResult = {
          batchId: bid,
          attempt: tryAttempt,
          eventCount: events.length,
          acceptedCount: accepted,
          duplicateCount: duplicate,
          rejectedCount: rejected,
          response,
          retried,
          ok: rejected === 0 && accepted + duplicate >= events.length,
        };
        if (result.ok) return result;
        lastError = new OllieDeliveryError(bid, tryAttempt, `batch rejected_count=${rejected}`);
      } catch (exc) {
        lastError = exc;
      }
    }

    const failed: DeliveryBatch = {
      batchId: bid,
      events,
      attempt: attempt + this.config.maxRetries,
    };
    this.failedBatches.push(failed);
    throw new OllieDeliveryError(
      bid,
      failed.attempt,
      lastError instanceof Error ? lastError.message : "batch delivery failed",
    );
  }
}
