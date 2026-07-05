import { randomUUID } from "node:crypto";
import { utcNowIso } from "./version.js";

export const EVENT_TYPE_TRACE_VALIDATE = "sdk.trace.validate";
export const EVENT_TYPE_TRACE_PROCESS = "sdk.trace.process";
export const EVENT_TYPE_TRACE_INGEST = "sdk.trace.ingest";

export function newEventId(): string {
  return randomUUID();
}

export function sessionIdFromPayload(payload: Record<string, unknown>): string {
  const sid = String(payload.session_id ?? "").trim();
  if (sid) return sid;
  const cid = String(payload.conversation_id ?? "").trim();
  if (cid) return cid;
  const aid = String(payload.agent_id ?? "").trim();
  return aid || "session-unknown";
}

export function buildEvent(options: {
  eventType: string;
  payload: Record<string, unknown>;
  eventId?: string;
}): Record<string, unknown> {
  const agentId = String(options.payload.agent_id ?? "").trim();
  if (!agentId) {
    throw new Error("payload.agent_id is required");
  }
  return {
    event_id: options.eventId ?? newEventId(),
    agent_id: agentId,
    session_id: sessionIdFromPayload(options.payload),
    timestamp: utcNowIso(),
    event_type: options.eventType,
    payload: options.payload,
  };
}
