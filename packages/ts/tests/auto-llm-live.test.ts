import { describe, expect, it } from "vitest";

import { initAsync, Instruments } from "../src/index.js";
import { runAutoAgent, assertAutoCapture } from "../examples/auto_llm_agent/agent.js";

function requireEnv(name: string): string | null {
  const v = process.env[name]?.trim();
  return v || null;
}

function shouldSkipProvider(provider: string): boolean {
  if (provider === "openai" && !requireEnv("OPENAI_API_KEY")) return true;
  if (provider === "anthropic" && !requireEnv("ANTHROPIC_API_KEY")) return true;
  if (provider === "gemini" && !requireEnv("GEMINI_API_KEY") && !requireEnv("GOOGLE_API_KEY")) return true;
  return false;
}

describe("live auto LLM capture", () => {
  it.skipIf(shouldSkipProvider("openai"))("openai", async () => {
    await initAsync({
      tracing: true,
      instruments: new Set([Instruments.OPENAI]),
      apiKey: process.env.OLLIE_API_KEY ?? "sdk-test-key-1",
      agentId: process.env.OLLIE_AGENT_ID ?? "agent_sdk_test_1",
    });
    const [, wire] = await runAutoAgent({ provider: "openai", localOnly: true });
    assertAutoCapture(wire, "openai");
    const gens = ((wire.interactions as Record<string, unknown>[]) ?? []).filter(
      (i) => i.primitive === "generation",
    );
    expect(gens.length).toBeGreaterThanOrEqual(1);
  });

  it.skipIf(shouldSkipProvider("anthropic"))("anthropic", async () => {
    await initAsync({
      tracing: true,
      instruments: new Set([Instruments.ANTHROPIC]),
      apiKey: process.env.OLLIE_API_KEY ?? "sdk-test-key-1",
      agentId: process.env.OLLIE_AGENT_ID ?? "agent_sdk_test_1",
    });
    const [, wire] = await runAutoAgent({ provider: "anthropic", localOnly: true });
    assertAutoCapture(wire, "anthropic");
  });

  it.skipIf(shouldSkipProvider("gemini"))("gemini", async () => {
    await initAsync({
      tracing: true,
      instruments: new Set([Instruments.GEMINI]),
      apiKey: process.env.OLLIE_API_KEY ?? "sdk-test-key-1",
      agentId: process.env.OLLIE_AGENT_ID ?? "agent_sdk_test_1",
    });
    const [, wire] = await runAutoAgent({ provider: "gemini", localOnly: true });
    assertAutoCapture(wire, "gemini");
  });
});
