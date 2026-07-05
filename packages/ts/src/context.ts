import { AsyncLocalStorage } from "node:async_hooks";
import type { InteractionHandle } from "./interaction.js";
import type { WorkflowSession } from "./workflow.js";

interface OllieContext {
  workflow: WorkflowSession | null;
  interaction: InteractionHandle | null;
}

const storage = new AsyncLocalStorage<OllieContext>();

function getStore(): OllieContext {
  return storage.getStore() ?? { workflow: null, interaction: null };
}

export function getActiveWorkflow(): WorkflowSession | null {
  return getStore().workflow;
}

export function getActiveInteraction(): InteractionHandle | null {
  return getStore().interaction;
}

export function getActiveParent(): InteractionHandle | null {
  const current = getActiveInteraction();
  if (current && !current.closed) return current;
  const wf = getActiveWorkflow();
  if (wf?.root && !wf.root.closed) return wf.root;
  return null;
}

export function runWithWorkflow<T>(workflow: WorkflowSession | null, fn: () => T): T {
  const prev = getStore();
  return storage.run({ ...prev, workflow }, fn);
}

export function runWithInteraction<T>(interaction: InteractionHandle | null, fn: () => T): T {
  const prev = getStore();
  return storage.run({ ...prev, interaction }, fn);
}

export function setActiveWorkflow(workflow: WorkflowSession | null): void {
  const prev = getStore();
  storage.enterWith({ ...prev, workflow });
}

export function setActiveInteraction(interaction: InteractionHandle | null): void {
  const prev = getStore();
  storage.enterWith({ ...prev, interaction });
}
