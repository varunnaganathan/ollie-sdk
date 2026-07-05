# @ollie/sdk (TypeScript) v0.2.0

Node/TypeScript SDK — behavioral parity with Python `ollie-sdk` v0.2.0.

## Install

```bash
npm install "github:varunnaganathan/ollie-sdk#v0.2.0:packages/ts"
# optional tracing peers:
npm install @opentelemetry/api @opentelemetry/sdk-trace-base @opentelemetry/sdk-trace-node \
  @opentelemetry/instrumentation @opentelemetry/instrumentation-openai \
  @traceloop/instrumentation-anthropic
```

## Quick start

```typescript
import { initAsync, Instruments, tool } from "@ollie/sdk";

// init BEFORE dynamic import of provider SDKs
const client = await initAsync({
  tracing: true,
  instruments: new Set([Instruments.OPENAI]),
  apiKey: process.env.OLLIE_API_KEY,
  agentId: process.env.OLLIE_AGENT_ID,
});

const { default: OpenAI } = await import("openai");
const oai = new OpenAI();

const wf = client.workflow({ name: "answer_ticket", input: "hello" });
wf.enter();
try {
  await oai.chat.completions.create({ model: "gpt-4o-mini", messages: [{ role: "user", content: "hi" }] });
  using t = tool("lookup_policy");
  t.enter();
  t.handle!.output = "policy text";
  t.exit();
  wf.output = "done";
} finally {
  wf.exit();
}

const payload = wf.toValidatePayload();
await client.shutdown();
```

## Wire format

- `schema_version: 2`
- `workflow` + flat `interactions[]` with `parent_interaction_ref`
- `events: { trigger, context, spans }` (ADK-shaped signals)

## Example

```bash
cd packages/ts
npm install && npm test
npx tsx examples/auto_llm_agent/run.ts --provider openai --print-tree --validate
```

## OTel note

Instrumentors must be registered **before** importing `openai`, `@anthropic-ai/sdk`, or `@google/genai`. Use `initAsync({ tracing: true })` then dynamic `import()`.
