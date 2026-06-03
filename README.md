# ollie-sdk

Instrumentation SDK for Ollie Sentry — trace sessions, features, spans, signals, and batched delivery to the ingest service.

## Install

From GitHub (recommended for production pins):

```bash
pip install "git+https://github.com/varunnaganathan/ollie-sdk.git@v0.1.0#egg=ollie-sdk"
```

Local development:

```bash
git clone git@github.com:varunnaganathan/ollie-sdk.git
cd ollie-sdk
pip install -e ".[dev]"
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

## Usage

```python
import ollie

client = ollie.Client()

client.define_feature("user_tier", kind="attribution", description="Tier", type="categorical", allowed_values=["free", "enterprise"])
client.define_span_type("checkout_validation", description="Checkout validation step")
client.define_signal("User Frustration", description="User dissatisfaction")

with client.trace(conversation_id="task-1") as trace:
    with trace.interaction(source="user", target="agent") as ix:
        ix.feature("retry_count", 3)
        ix.feature("user_tier", "enterprise")
        with ix.span("tool_call", name="browser.open"):
            pass

result = trace.flush()  # validate via event batch (batch-of-1)
# result = trace.flush_process()
# result = trace.flush_ingest()  # persist + index queue

client.shutdown()  # flush any buffered events
```

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
