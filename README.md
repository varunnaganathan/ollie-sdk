# ollie-sdk

Instrumentation SDK for Ollie Sentry — trace sessions, features, spans, signals, and batched delivery to the ingest service.

**New customer?** See **[docs/CLIENT_ONBOARDING.md](docs/CLIENT_ONBOARDING.md)** (env vars, instrumentation, production checklist).

## Install

### Python

From GitHub (recommended for production pins):

```bash
pip install "ollie-sdk[tracing] @ git+https://github.com/varunnaganathan/ollie-sdk.git@v0.2.0"
```

Core only (no auto LLM instrumentation):

```bash
pip install "ollie-sdk @ git+https://github.com/varunnaganathan/ollie-sdk.git@v0.2.0"
```

### TypeScript (`@ollie/sdk`)

Same repo, subdirectory install:

```bash
npm install "github:varunnaganathan/ollie-sdk#v0.2.0:packages/ts"
```

See [packages/ts/README.md](packages/ts/README.md) for tracing peer deps and `initAsync` usage.

### Local development

```bash
git clone git@github.com:varunnaganathan/ollie-sdk.git
cd ollie-sdk
pip install -e ".[dev]"
```

TypeScript:

```bash
cd packages/ts && npm install && npm test
```

## Configure

### Production (Render)

Point registry at the **analysis** API and event batches at the **ingest** service:

```bash
export OLLIE_API_KEY=your-tenant-api-key
export OLLIE_AGENT_ID=your-agent-id
export OLLIE_BASE_URL=https://YOUR-ANALYSIS-SERVICE.onrender.com
export OLLIE_INGEST_BASE_URL=https://YOUR-INGEST-SERVICE.onrender.com
```

| Call | URL |
|------|-----|
| `define_feature`, `define_span_type`, `define_signal` | `OLLIE_BASE_URL` → `/v1/sdk/registry/*` |
| `flush` / `flush_ingest` / buffered delivery | `OLLIE_INGEST_BASE_URL` → `/v1/sdk/events/batch` |

Ensure the backend **ingest worker** is running so queued batches become traces and Pinecone indexes.

### Local (Docker / three processes)

```bash
export OLLIE_API_KEY=sdk-test-key-1
export OLLIE_BASE_URL=http://127.0.0.1:8001          # registry + intelligence API
export OLLIE_INGEST_BASE_URL=http://127.0.0.1:8002   # POST /v1/sdk/events/batch
export OLLIE_AGENT_ID=agent_sdk_test_1
```

## Usage (workflow v2)

```python
import ollie

client = ollie.Client()

with client.workflow(name="Answer ticket", input=user_msg) as wf:
    with ollie.tool("lookup_policy", input=ticket_id) as t:
        t.output = policy_text
    wf.output = "done"

payload = wf.to_validate_payload()
# wf.flush_ingest()
client.shutdown()
```

Legacy v1 (`client.trace()` + dialogue interactions + nested spans) remains available.

## Experimental: auto LLM instrumentation

Optional extra — **not required** for core SDK. Uses OpenTelemetry provider instrumentors internally (OpenAI, Anthropic, Gemini); customers never import OTel. LLM calls become `generation` interactions under the active workflow. Manual `ollie.tool` covers blind spots.

```bash
pip install -e ".[tracing,simulation]"
pip install anthropic google-genai   # only the client SDKs you use
```

```python
from ollie import Instruments
import ollie

# Default: auto-instrument all supported libraries that are installed
ollie.init(tracing=True)

# Only Anthropic
ollie.init(tracing=True, instruments={Instruments.ANTHROPIC})

# Everything except OpenAI
ollie.init(tracing=True, block_instruments={Instruments.OPENAI})

# Disable all auto LLM spans (manual workflow/tool still works)
ollie.init(tracing=True, auto_instrument=False)
```

```python
from openai import OpenAI
import ollie
from ollie import Instruments

client = ollie.init(tracing=True, instruments={Instruments.OPENAI})
oai = OpenAI()

with client.workflow(name="Auto OpenAI Demo", input=msg) as wf:
    r = oai.chat.completions.create(model="gpt-4o-mini", messages=[...])  # auto
    with ollie.tool("math.add", input="15+27") as t:
        t.output = "42"
    wf.output = r.choices[0].message.content
```

Sample agent (`--provider openai|anthropic|gemini`):

```bash
PYTHONPATH=src:examples python examples/auto_llm_agent/run.py --provider gemini --print-tree --validate
```

Workflows finalize ADK-compatible `events` on each interaction:

```json
{
  "trigger": [],
  "context": [{ "name": "used_tool" }],
  "spans": [
    { "type": "llm", "name": "openai.chat", "status": "success", "span_ref": "ix_1", "parent_span_ref": "ix_0" },
    { "type": "tool", "name": "math.add", "status": "success", "span_ref": "ix_2", "parent_span_ref": "ix_0" }
  ]
}
```

Default context signals (same for OpenAI / Anthropic / Gemini) include language defaults (`llm_error`, `tool_error`, `used_tool`, `high_latency`, `output_truncated`, `safety_stop`, `tool_loop`, `runtime_failure`, `empty_final_response`, `repeated_tool_error`) plus AI-SDK signals (`llm_empty_input`, `llm_empty_output`, `llm_provider_error_rate`, `llm_token_blowup`, `io_error_in_output`). Spans carry only `type` / `name` / `status` / `span_ref` for cold-path auto-fix.

`providers=["openai"]` remains as a legacy alias for `instruments={Instruments.OPENAI}`. Do not tag a release for this path until ready.

## Layer 1 delivery (buffer, gzip, retry)

All `flush_*` calls use one pipeline: wrap trace payload in an event envelope → buffer → `POST /v1/sdk/events/batch` (gzip). A single `flush_ingest()` is a **batch of one**.

| Env | Default | Meaning |
|-----|---------|---------|
| `OLLIE_BUFFER_MAX_EVENTS` | `50` | Flush when buffer reaches this many events |
| `OLLIE_BUFFER_FLUSH_INTERVAL_S` | `5` | Flush non-empty buffer on timer |
| `OLLIE_COMPRESSION` | `1` | Gzip request bodies |
| `OLLIE_RETRY_MAX` | `5` | Whole-batch retries with backoff |

Backend docs: [olliejudge-sentry-backend — SDK Phase 2](https://github.com/varunnaganathan/olliejudge-sentry-backend/blob/main/docs/SDK_PHASE2.md).

## Simulated testing agent

Live OpenAI agent with math/string tools (`examples/simulated_agent/`):

```bash
pip install -e ".[dev,simulation]"
PYTHONPATH=src:examples python -m simulated_agent.run --case random_single_ix --validate
```

See backend [SDK_AGENT_SIMULATION.md](https://github.com/varunnaganathan/olliejudge-sentry-backend/blob/main/docs/SDK_AGENT_SIMULATION.md).

## Tests

Unit + serializer tests (no database):

```bash
pytest -m "not integration and not openai"
```

E2E tests send **real HTTP** to a **log-only collector** (no Postgres):

```bash
pytest -m e2e
```

**Live e2e** (OpenAI + shared Postgres + running backend ingest worker) — optional, dev only:

```bash
pytest tests/e2e/test_simulated_agent_live.py -m "e2e and openai" -v
```

Requires `OPENAI_API_KEY`, `DATABASE_URL`, and [olliejudge-sentry-backend](https://github.com/varunnaganathan/olliejudge-sentry-backend) with `ingest-api` + `ingest-worker`.

Manual collector:

```bash
python -m tests.collector_server --port 19999
export OLLIE_BASE_URL=http://127.0.0.1:19999
export OLLIE_INGEST_BASE_URL=http://127.0.0.1:19999
python examples/sdk_test_agent_loop.py
```
