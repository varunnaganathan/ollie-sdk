import { BUILTIN_PRIMITIVES } from "./primitives.js";
import { utcNowIso } from "./version.js";
import type { WorkflowSession } from "./workflow.js";

export type AttributeValue = boolean | number | string;

export interface WireInteraction {
  interaction_ref: string;
  parent_interaction_ref: string | null;
  name: string;
  primitive: string | null;
  input: string | null;
  output: string | null;
  events: Record<string, unknown> | unknown[];
  attributes: Array<{ name: string; value: AttributeValue }>;
  started_at: string;
  ended_at: string;
}

export class InteractionHandle {
  private readonly workflow: WorkflowSession;
  readonly interactionRef: string;
  readonly parentInteractionRef: string | null;
  readonly name: string;
  readonly primitive: string | null;
  private _input: string | null;
  private _output: string | null = null;
  private readonly _startedAt: string;
  private _endedAt: string | null = null;
  private _attributes: Array<{ name: string; value: AttributeValue }> = [];
  closed = false;
  private _success: boolean | null = null;

  get success(): boolean | null {
    return this._success;
  }

  constructor(options: {
    workflow: WorkflowSession;
    interactionRef: string;
    parentInteractionRef: string | null;
    name: string;
    primitive: string | null;
    input: string | null;
    startedAt?: string;
  }) {
    this.workflow = options.workflow;
    this.interactionRef = options.interactionRef;
    this.parentInteractionRef = options.parentInteractionRef;
    this.name = options.name;
    this.primitive = options.primitive;
    this._input = options.input;
    this._startedAt = options.startedAt ?? utcNowIso();
  }

  get input(): string | null {
    return this._input;
  }

  set input(value: string | null) {
    this._input = value;
  }

  get output(): string | null {
    return this._output;
  }

  set output(value: string | null) {
    this._output = value;
  }

  markSuccess(success = true): void {
    this._success = success;
    this.setAttr("success", success);
    this.setAttr("status", success ? "ok" : "error");
  }

  private setAttr(name: string, value: AttributeValue): void {
    this._attributes = this._attributes.filter((a) => a.name !== name);
    this._attributes.push({ name, value });
  }

  attribute(name: string, value: AttributeValue): void {
    this.setAttr(name, value);
    if (name === "success") this._success = Boolean(value);
  }

  close(output?: string | null): WireInteraction {
    if (this.closed) {
      throw new Error(`interaction ${JSON.stringify(this.interactionRef)} already ended`);
    }
    if (output !== undefined) this._output = output;
    this._endedAt = utcNowIso();
    if (this._success === null && this.primitive !== null) {
      this.markSuccess(true);
    }
    this.closed = true;
    return this.toWireDict();
  }

  toWireDict(): WireInteraction {
    return {
      interaction_ref: this.interactionRef,
      parent_interaction_ref: this.parentInteractionRef,
      name: this.name,
      primitive: this.primitive,
      input: this._input,
      output: this._output,
      events: { trigger: [], context: [], spans: [] },
      attributes: [...this._attributes],
      started_at: this._startedAt,
      ended_at: this._endedAt ?? utcNowIso(),
    };
  }
}

export class WorkflowInteractionController {
  private readonly workflow: WorkflowSession;

  constructor(workflow: WorkflowSession) {
    this.workflow = workflow;
  }

  start(options: {
    name: string;
    primitive?: string | null;
    parent?: InteractionHandle | null;
    input?: string | null;
  }): InteractionHandle {
    if (options.primitive != null && !BUILTIN_PRIMITIVES.has(options.primitive)) {
      throw new Error(
        `unknown primitive ${JSON.stringify(options.primitive)}; expected one of ${[...BUILTIN_PRIMITIVES].sort().join(", ")}`,
      );
    }
    return this.workflow.startInteraction({
      name: options.name,
      primitive: options.primitive ?? null,
      parent: options.parent ?? null,
      input: options.input ?? null,
    });
  }

  end(handle: InteractionHandle, output?: string | null): void {
    this.workflow.endInteraction(handle, output);
  }

  open(options: {
    name: string;
    primitive?: string | null;
    parent?: InteractionHandle | null;
    input?: string | null;
  }): InteractionScope {
    return new InteractionScope(this, options);
  }

  call(options: {
    name: string;
    primitive?: string | null;
    parent?: InteractionHandle | null;
    input?: string | null;
  }): InteractionScope {
    return this.open(options);
  }
}

export class InteractionScope implements Disposable {
  private readonly controller: WorkflowInteractionController;
  private readonly options: {
    name: string;
    primitive?: string | null;
    parent?: InteractionHandle | null;
    input?: string | null;
  };
  handle: InteractionHandle | null = null;

  constructor(controller: WorkflowInteractionController, options: InteractionScope["options"]) {
    this.controller = controller;
    this.options = options;
  }

  enter(): InteractionHandle {
    this.handle = this.controller.start(this.options);
    return this.handle;
  }

  exit(exc?: unknown): void {
    const handle = this.handle;
    if (!handle || handle.closed) return;
    if (exc) handle.markSuccess(false);
    this.controller.end(handle, handle.output);
    this.handle = null;
  }

  [Symbol.dispose](): void {
    this.exit();
  }
}
