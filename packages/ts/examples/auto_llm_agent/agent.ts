import { initAsync, Instruments, tool } from "../../src/index.js";
import type { Client } from "../../src/client.js";
import { assertAutoCapture, printTree, type Provider } from "./validators.js";

async function callOpenai(prompt: string): Promise<string> {
  const { default: OpenAI } = await import("openai");
  const client = new OpenAI({ apiKey: process.env.OPENAI_API_KEY });
  const resp = await client.chat.completions.create({
    model: process.env.OLLIE_SIM_OPENAI_MODEL ?? "gpt-4o-mini",
    messages: [{ role: "user", content: prompt }],
    max_tokens: 32,
  });
  return (resp.choices[0]?.message?.content ?? "").trim();
}

async function callAnthropic(prompt: string): Promise<string> {
  const Anthropic = (await import("@anthropic-ai/sdk")).default;
  const client = new Anthropic({ apiKey: process.env.ANTHROPIC_API_KEY });
  const msg = await client.messages.create({
    model: process.env.OLLIE_SIM_ANTHROPIC_MODEL ?? "claude-3-5-haiku-latest",
    max_tokens: 32,
    messages: [{ role: "user", content: prompt }],
  });
  return msg.content
    .map((b) => ("text" in b ? b.text : ""))
    .join("")
    .trim();
}

async function callGemini(prompt: string): Promise<string> {
  const { GoogleGenAI } = await import("@google/genai");
  const apiKey = (process.env.GEMINI_API_KEY ?? process.env.GOOGLE_API_KEY ?? "").trim();
  const client = new GoogleGenAI({ apiKey });
  const model = process.env.OLLIE_SIM_GEMINI_MODEL ?? "gemini-2.0-flash";
  const resp = await client.models.generateContent({ model, contents: prompt });
  return String(resp.text ?? resp).slice(0, 200).trim();
}

const CALLERS: Record<Provider, (prompt: string) => Promise<string>> = {
  openai: callOpenai,
  anthropic: callAnthropic,
  gemini: callGemini,
};

const PROVIDER_INSTRUMENT: Record<Provider, Instruments> = {
  openai: Instruments.OPENAI,
  anthropic: Instruments.ANTHROPIC,
  gemini: Instruments.GEMINI,
};

export async function runAutoAgent(options?: {
  provider?: Provider;
  client?: Client;
  localOnly?: boolean;
  userMessage?: string;
}): Promise<[Record<string, unknown>, Record<string, unknown>]> {
  const provider = (options?.provider ?? "openai").trim().toLowerCase() as Provider;
  if (!CALLERS[provider]) throw new Error(`unknown provider ${provider}`);

  let client = options?.client;
  if (!client) {
    client = await initAsync({
      tracing: true,
      instruments: new Set([PROVIDER_INSTRUMENT[provider]]),
      apiKey: process.env.OLLIE_API_KEY ?? "sdk-test-key-1",
      agentId: process.env.OLLIE_AGENT_ID ?? "agent_sdk_test_1",
      baseUrl: process.env.OLLIE_BASE_URL ?? "http://127.0.0.1:8001",
      ingestBaseUrl: process.env.OLLIE_INGEST_BASE_URL ?? "http://127.0.0.1:8002",
    });
  }

  const userMessage =
    options?.userMessage ?? "What is 15+27? Reply with just the number.";
  const caller = CALLERS[provider];

  const wf = client.workflow({ name: `Auto ${provider[0].toUpperCase()}${provider.slice(1)} Demo`, input: userMessage });
  wf.enter();
  try {
    const llmText = await caller(userMessage);
    using t = tool("math.add", { input: "15+27" });
    t.enter();
    t.handle!.output = "42";
    t.exit();
    wf.output = llmText;
  } finally {
    wf.exit();
  }

  const wire = wf.toValidatePayload();
  if (options?.localOnly !== false) {
    return [{ accepted: true, local_only: true }, wire];
  }
  const result = await wf.flushProcess();
  return [result, wire];
}

export { assertAutoCapture, printTree };
