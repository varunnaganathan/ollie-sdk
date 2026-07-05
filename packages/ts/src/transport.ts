import { gzipSync } from "node:zlib";

import {
  buildEvent,
  EVENT_TYPE_TRACE_INGEST,
  EVENT_TYPE_TRACE_PROCESS,
  EVENT_TYPE_TRACE_VALIDATE,
} from "./event.js";
import { OllieHTTPError, OllieValidationError } from "./errors.js";
import { __version__ } from "./version.js";
import type { DeliveryPipeline } from "./delivery.js";

export class Transport {
  readonly baseUrl: string;
  readonly ingestBaseUrl: string;
  readonly apiKey: string;
  readonly timeout: number;

  constructor(options: {
    baseUrl: string;
    apiKey: string;
    ingestBaseUrl?: string;
    timeout?: number;
  }) {
    this.baseUrl = options.baseUrl.replace(/\/$/, "");
    this.ingestBaseUrl = (options.ingestBaseUrl ?? options.baseUrl).replace(/\/$/, "");
    this.apiKey = options.apiKey;
    this.timeout = options.timeout ?? 30_000;
  }

  private apiHeaders(contentEncoding?: string): Record<string, string> {
    const headers: Record<string, string> = {
      "X-API-Key": this.apiKey,
      "Content-Type": "application/json",
    };
    if (contentEncoding) headers["Content-Encoding"] = contentEncoding;
    return headers;
  }

  async postJson(path: string, body: Record<string, unknown>): Promise<Record<string, unknown>> {
    const url = `${this.baseUrl}${path}`;
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), this.timeout);
    try {
      const r = await fetch(url, {
        method: "POST",
        headers: this.apiHeaders(),
        body: JSON.stringify(body),
        signal: controller.signal,
      });
      return await this.parseResponse(r);
    } finally {
      clearTimeout(timer);
    }
  }

  async sendEventBatch(
    body: Record<string, unknown>,
    options?: { compression?: boolean },
  ): Promise<Record<string, unknown>> {
    const url = `${this.ingestBaseUrl}/v1/sdk/events/batch`;
    let data = Buffer.from(JSON.stringify(body));
    const headers = this.apiHeaders();
    if (options?.compression !== false) {
      data = gzipSync(data);
      headers["Content-Encoding"] = "gzip";
    }
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), this.timeout);
    try {
      const r = await fetch(url, {
        method: "POST",
        headers,
        body: data,
        signal: controller.signal,
      });
      return await this.parseResponse(r);
    } finally {
      clearTimeout(timer);
    }
  }

  private async parseResponse(r: Response): Promise<Record<string, unknown>> {
    if (r.status === 200 || r.status === 201) {
      return (await r.json()) as Record<string, unknown>;
    }
    if (r.status === 409) {
      return { _conflict: true, detail: await r.text() };
    }
    let detail = await r.text();
    try {
      const json = JSON.parse(detail) as { detail?: string };
      detail = json.detail ?? detail;
    } catch {
      // keep text
    }
    throw new OllieHTTPError(r.status, detail);
  }

  private async submitTraceEvent(
    eventType: string,
    payload: Record<string, unknown>,
    delivery: DeliveryPipeline,
  ): Promise<Record<string, unknown>> {
    const event = buildEvent({ eventType, payload });
    delivery.submit(event);
    const results = await delivery.flushPending();
    if (!results.length) return {};
    const result = results[results.length - 1]!;
    if (!result.ok) {
      const errs: string[] = [];
      if (result.response) {
        for (const item of (result.response.results as Record<string, unknown>[]) ?? []) {
          if (item.status === "rejected") {
            errs.push(...((item.errors as string[]) ?? []));
          }
        }
      }
      throw new OllieValidationError(errs.length ? errs : ["batch delivery failed"]);
    }
    return this.extractTraceResponse(eventType, result.response, String(event.event_id));
  }

  private extractTraceResponse(
    eventType: string,
    batchResponse: Record<string, unknown> | null,
    eventId: string,
  ): Record<string, unknown> {
    if (!batchResponse) return {};
    for (const item of (batchResponse.results as Record<string, unknown>[]) ?? []) {
      if (String(item.event_id) !== eventId) continue;
      if (item.status === "duplicate") {
        if (eventType === EVENT_TYPE_TRACE_INGEST) {
          return { accepted: true, trace_id: null, duplicate: true };
        }
        return { accepted: true, duplicate: true };
      }
      if (eventType === EVENT_TYPE_TRACE_VALIDATE && item.validate_result) {
        return { ...(item.validate_result as Record<string, unknown>) };
      }
      if (eventType === EVENT_TYPE_TRACE_PROCESS && item.process_result) {
        return { ...(item.process_result as Record<string, unknown>) };
      }
      if (eventType === EVENT_TYPE_TRACE_INGEST) {
        if (item.ingest) return { ...(item.ingest as Record<string, unknown>) };
        if (item.status === "accepted") {
          return { accepted: true, queued: Boolean(item.queued), trace_id: null };
        }
      }
    }
    throw new OllieValidationError([`no result for event_id ${eventId}`]);
  }

  async validateTrace(
    payload: Record<string, unknown>,
    delivery: DeliveryPipeline,
  ): Promise<Record<string, unknown>> {
    const body = await this.submitTraceEvent(EVENT_TYPE_TRACE_VALIDATE, payload, delivery);
    if (!body.accepted && !body.duplicate) {
      throw new OllieValidationError((body.errors as string[]) ?? []);
    }
    return body;
  }

  async processTrace(
    payload: Record<string, unknown>,
    delivery: DeliveryPipeline,
  ): Promise<Record<string, unknown>> {
    const body = await this.submitTraceEvent(EVENT_TYPE_TRACE_PROCESS, payload, delivery);
    if (!body.accepted && !body.duplicate) {
      throw new OllieValidationError((body.errors as string[]) ?? []);
    }
    return body;
  }

  async ingestTrace(
    payload: Record<string, unknown>,
    delivery: DeliveryPipeline,
  ): Promise<Record<string, unknown>> {
    const body = await this.submitTraceEvent(EVENT_TYPE_TRACE_INGEST, payload, delivery);
    if (!body.accepted && !body.duplicate) {
      throw new OllieValidationError((body.errors as string[]) ?? []);
    }
    return body;
  }

  sdkMeta(): Record<string, string> {
    return { name: "ollie-sdk-ts", version: __version__ };
  }
}
