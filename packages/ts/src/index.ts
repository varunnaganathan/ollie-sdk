import { Client, type ClientOptions } from "./client.js";
import { Instruments } from "./instruments.js";
import { BUILTIN_PRIMITIVES } from "./primitives.js";
import { renderInteractionTree } from "./tree.js";
import { tool, toolDecorator } from "./tool.js";
import { WorkflowSession } from "./workflow.js";
import { __version__ } from "./version.js";

export {
  BUILTIN_PRIMITIVES,
  Client,
  Instruments,
  WorkflowSession,
  __version__,
  renderInteractionTree,
  tool,
  toolDecorator,
};

let defaultClient: Client | null = null;

export function init(options: ClientOptions = {}): Client {
  defaultClient = new Client(options);
  return defaultClient;
}

export function getDefaultClient(): Client {
  if (!defaultClient) defaultClient = new Client();
  return defaultClient;
}

export async function initAsync(options: ClientOptions = {}): Promise<Client> {
  const client = new Client({ ...options, tracing: false });
  if (options.tracing) {
    const { install } = await import("./tracing/index.js");
    await install({
      instruments: options.instruments,
      blockInstruments: options.blockInstruments,
      autoInstrument: options.autoInstrument,
      providers: options.providers,
      captureContent: options.captureContent,
    });
    (client as { tracing: boolean }).tracing = true;
  }
  defaultClient = client;
  return client;
}
