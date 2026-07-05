import type { Client } from "./client.js";

export class SessionContext {
  private readonly client: Client;
  readonly sessionId: string;
  private previous: string | null = null;

  constructor(client: Client, sessionId: string) {
    this.client = client;
    this.sessionId = sessionId.trim();
  }

  enter(): this {
    this.previous = this.client.sessionId;
    this.client.sessionId = this.sessionId;
    return this;
  }

  exit(): void {
    this.client.sessionId = this.previous;
  }

  [Symbol.dispose](): void {
    this.exit();
  }
}
