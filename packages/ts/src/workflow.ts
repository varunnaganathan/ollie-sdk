import {
  setActiveInteraction,
  setActiveWorkflow,
} from "./context.js";
import { InteractionHandle, WorkflowInteractionController } from "./interaction.js";
import { finalizeInteractions } from "./signals/instrument.js";
import { utcNowIso } from "./version.js";
import type { Client } from "./client.js";

export type WorkflowStatus = "completed" | "failed" | "cancelled" | "abandoned";

export class WorkflowSession implements Disposable {
  private readonly client: Client;
  readonly name: string;
  input: string | null;
  output: string | null = null;
  private readonly sessionId: string | null;
  private startedAt: string | null = null;
  private endedAt: string | null = null;
  private status: WorkflowStatus = "completed";
  private interactions: Record<string, unknown>[] = [];
  private open = new Map<string, InteractionHandle>();
  private stack: string[] = [];
  private seq = 0;
  root: InteractionHandle | null = null;
  readonly interaction: WorkflowInteractionController;

  constructor(client: Client, options: { name: string; input?: string | null }) {
    this.client = client;
    this.name = options.name.trim();
    this.input = options.input ?? null;
    this.sessionId = client.sessionId;
    this.interaction = new WorkflowInteractionController(this);
  }

  private nextRef(): string {
    const ref = `ix_${this.seq}`;
    this.seq += 1;
    return ref;
  }

  startInteraction(options: {
    name: string;
    primitive: string | null;
    parent: InteractionHandle | null;
    input: string | null;
    startedAt?: string;
  }): InteractionHandle {
    const parentRef =
      options.parent?.interactionRef ??
      (this.stack.length ? this.stack[this.stack.length - 1] : null);
    const ref = this.nextRef();
    const handle = new InteractionHandle({
      workflow: this,
      interactionRef: ref,
      parentInteractionRef: parentRef,
      name: options.name,
      primitive: options.primitive,
      input: options.input,
      startedAt: options.startedAt,
    });
    this.open.set(ref, handle);
    this.stack.push(ref);
    setActiveInteraction(handle);
    return handle;
  }

  endInteraction(handle: InteractionHandle, output?: string | null): void {
    const wire = handle.close(output);
    this.interactions.push(wire as unknown as Record<string, unknown>);
    this.open.delete(handle.interactionRef);
    if (this.stack.at(-1) === handle.interactionRef) {
      this.stack.pop();
    } else if (this.stack.includes(handle.interactionRef)) {
      this.stack = this.stack.filter((r) => r !== handle.interactionRef);
    }
    const parentRef = handle.parentInteractionRef;
    if (parentRef && this.open.has(parentRef)) {
      setActiveInteraction(this.open.get(parentRef)!);
    } else if (this.root && !this.root.closed && handle !== this.root) {
      setActiveInteraction(this.root);
    } else {
      setActiveInteraction(null);
    }
  }

  recordCompletedInteraction(options: {
    name: string;
    primitive: string | null;
    parent: InteractionHandle | null;
    input?: string | null;
    output?: string | null;
    startedAt: string;
    endedAt: string;
    events?: Record<string, unknown> | unknown[] | null;
    attributes?: Array<{ name: string; value: boolean | number | string }> | null;
  }): string {
    let parentRef: string | null = null;
    if (options.parent) {
      parentRef = options.parent.interactionRef;
    } else if (this.root) {
      parentRef = this.root.interactionRef;
    }
    const ref = this.nextRef();
    const wire = {
      interaction_ref: ref,
      parent_interaction_ref: parentRef,
      name: options.name,
      primitive: options.primitive,
      input: options.input ?? null,
      output: options.output ?? null,
      events:
        options.events && !Array.isArray(options.events)
          ? options.events
          : { trigger: [], context: [], spans: [] },
      attributes: [...(options.attributes ?? [])],
      started_at: options.startedAt,
      ended_at: options.endedAt,
    };
    this.interactions.push(wire);
    return ref;
  }

  private workflowLatencyMs(): number {
    const started = this.startedAt;
    const ended = this.endedAt ?? utcNowIso();
    if (!started) return 0;
    try {
      const a = Date.parse(started);
      const b = Date.parse(ended);
      if (Number.isNaN(a) || Number.isNaN(b)) return 0;
      return Math.max(0, b - a);
    } catch {
      return 0;
    }
  }

  toValidatePayload(): Record<string, unknown> {
    const interactions = finalizeInteractions([...this.interactions], {
      workflowSuccess: this.status === "completed",
      workflowLatencyMs: this.workflowLatencyMs(),
    });
    const payload: Record<string, unknown> = {
      schema_version: 2,
      sdk: this.client.transport.sdkMeta(),
      agent_id: this.client.agentId,
      workflow: {
        name: this.name,
        status: this.status,
        started_at: this.startedAt ?? utcNowIso(),
        ended_at: this.endedAt ?? utcNowIso(),
      },
      interactions,
    };
    if (this.sessionId) payload.session_id = this.sessionId;
    return payload;
  }

  async flush(): Promise<Record<string, unknown>> {
    return this.client.transport.validateTrace(this.toValidatePayload(), this.client.delivery);
  }

  async flushProcess(): Promise<Record<string, unknown>> {
    return this.client.transport.processTrace(this.toValidatePayload(), this.client.delivery);
  }

  async flushIngest(): Promise<Record<string, unknown>> {
    return this.client.transport.ingestTrace(this.toValidatePayload(), this.client.delivery);
  }

  enter(): this {
    this.startedAt = utcNowIso();
    setActiveWorkflow(this);
    this.root = this.startInteraction({
      name: this.name,
      primitive: null,
      parent: null,
      input: this.input,
    });
    return this;
  }

  exit(exc?: unknown): void {
    if (exc) this.status = "failed";
    this.endedAt = utcNowIso();
    if (this.root && !this.root.closed) {
      this.endInteraction(this.root, this.output);
    }
    for (const ref of [...this.stack].reverse()) {
      const handle = this.open.get(ref);
      if (handle && !handle.closed) {
        this.endInteraction(handle, handle.output);
      }
    }
    setActiveWorkflow(null);
  }

  [Symbol.dispose](): void {
    this.exit();
  }
}
