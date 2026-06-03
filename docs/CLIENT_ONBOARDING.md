# Client onboarding — ollie-sdk

Guide for integrating a **new tenant** with Ollie Sentry using the Python SDK. Your Ollie contact provisions credentials; you install the SDK, set environment variables, register instrumentation, and send traces to production ingest.

---

## What you receive from Ollie

Before writing code, confirm you have:

| Item | Example | Used as |
|------|---------|---------|
| **API key** | `ollie_live_abc123...` | `OLLIE_API_KEY` — authenticates all SDK HTTP calls |
| **Agent ID** | `agent_acme_support_1` | `OLLIE_AGENT_ID` — which agent produced the trace |
| **Analysis API URL** | `https://olliejudge-api.onrender.com` | `OLLIE_BASE_URL` — registry (`define_*`) |
| **Ingest API URL** | `https://ollie-ingest.onrender.com` | `OLLIE_INGEST_BASE_URL` — event batches (`flush_*`) |

Optional tuning (defaults are fine for most agents):

| Variable | Default | Purpose |
|----------|---------|---------|
| `OLLIE_BUFFER_MAX_EVENTS` | `50` | Auto-flush when buffer is full |
| `OLLIE_BUFFER_FLUSH_INTERVAL_S` | `5` | Timer flush for partial buffers |
| `OLLIE_COMPRESSION` | `1` | Gzip batch bodies |
| `OLLIE_RETRY_MAX` | `5` | Retries on batch POST failure |

---

## Install

Python **3.10+** required.

```bash
pip install "git+https://github.com/varunnaganathan/ollie-sdk.git@v0.1.0#egg=ollie-sdk"
```

Pin the tag in `requirements.txt` or lockfile so upgrades are deliberate.

---

## Environment variables

Set these in your agent runtime (Kubernetes secret, Render env, `.env`, etc.). **Never commit API keys to git.**

```bash
export OLLIE_API_KEY="<from Ollie>"
export OLLIE_AGENT_ID="<from Ollie>"
export OLLIE_BASE_URL="https://<analysis-host>"
export OLLIE_INGEST_BASE_URL="https://<ingest-host>"
```

### Which URL handles what

| SDK call | Service | Path |
|----------|---------|------|
| `client.define_feature` / `define_span_type` / `define_signal` | Analysis | `/v1/sdk/registry/*` |
| `trace.flush()`, `flush_ingest()`, buffered delivery | Ingest | `/v1/sdk/events/batch` |

If `OLLIE_INGEST_BASE_URL` is unset, the SDK defaults to `http://127.0.0.1:8002` and batches will fail in production.

---

## Instrumentation model

Four primitives:

1. **Registry** (once per tenant, or at startup) — declare custom features, span types, and signals.
2. **Trace session** — one conversation / task (`conversation_id`).
3. **Interaction** — one turn (e.g. user → agent); attach **features** and **spans**.
4. **Flush** — send data to Ollie (validate, process preview, or full ingest).

Built-in feature kinds include `observable`, `behavioral`, and `attribution`. Custom names must be registered before use on the wire.

---

## Minimal integration

### 1. One shared client per process

Create a single `ollie.Client()` at startup and reuse it (registry + delivery buffer are per client).

```python
import os
import ollie

client = ollie.Client(
    api_key=os.environ["OLLIE_API_KEY"],
    agent_id=os.environ["OLLIE_AGENT_ID"],
    base_url=os.environ["OLLIE_BASE_URL"],
    ingest_base_url=os.environ["OLLIE_INGEST_BASE_URL"],
)
```

Or rely entirely on env vars:

```python
client = ollie.Client()  # reads OLLIE_* from environment
```

### 2. Register definitions (startup)

Run before first trace, or idempotently on each deploy:

```python
client.define_feature(
    "user_tier",
    kind="attribution",
    description="Subscription tier",
    type="categorical",
    allowed_values=["free", "pro", "enterprise"],
)
client.define_span_type("tool_call", description="Tool invocation wrapper")
client.define_signal("Escalation Risk", description="Likelihood of human escalation")
```

### 3. Instrument a conversation

```python
with client.trace(conversation_id="session-uuid-or-task-id") as trace:
    with trace.interaction(source="user", target="agent", input="...", output="...") as ix:
        ix.feature("user_tier", "pro")
        ix.feature("retry_count", 1)
        with ix.span("tool_call", name="search.run"):
            pass  # work inside span context
```

Using `with client.trace(...)` calls **`flush()`** (validate) on exit if interactions were recorded.

### 4. Production: persist and index

For real telemetry (Postgres + search index), use **ingest**:

```python
with client.trace(conversation_id="session-123") as trace:
    ...
    result = trace.flush_ingest()
```

Or exit the context without auto-validate and flush explicitly:

```python
trace = client.trace(conversation_id="session-123")
# ... build interactions ...
trace.flush_ingest()
```

`flush_ingest()` returns quickly with `queued: true` when ingest async mode is on; the **ingest worker** writes traces and runs Pinecone indexing.

### 5. Shutdown

On process exit, drain the delivery buffer:

```python
client.shutdown()
```

Register `atexit` or your framework’s shutdown hook so buffered events are not lost.

---

## Recommended production pattern

```python
import atexit
import os
import ollie

client = ollie.Client()

def _register_instrumentation() -> None:
    client.define_feature("user_tier", kind="attribution", description="Tier", type="categorical", allowed_values=["free", "enterprise"])
    client.define_span_type("tool_call", description="Tool call")

_register_instrumentation()
atexit.register(client.shutdown)

def run_agent_turn(session_id: str, user_message: str, agent_reply: str) -> None:
    trace = client.trace(conversation_id=session_id)
    with trace.interaction(source="user", target="agent", input=user_message, output=agent_reply) as ix:
        ix.feature("user_tier", "enterprise")
        with ix.span("tool_call", name="retrieval.query"):
            pass
    trace.flush_ingest()
```

---

## Flush modes

| Method | Event type | Use when |
|--------|------------|----------|
| `trace.flush()` | `sdk.trace.validate` | CI / dry-run; checks schema only |
| `trace.flush_process()` | `sdk.trace.process` | Debug compile preview (no DB persist) |
| `trace.flush_ingest()` | `sdk.trace.ingest` | **Production** — persist + queue index |

All three use the same batch pipeline (buffer, gzip, retry) to **ingest**.

---

## Verify connectivity

### Health (ingest)

```bash
curl -sS "$OLLIE_INGEST_BASE_URL/health"
# {"status":"ok","service":"sdk-ingest"}
```

### Smoke script

Clone the SDK repo and run the example loop (after env is set):

```bash
git clone https://github.com/varunnaganathan/ollie-sdk.git
cd ollie-sdk
pip install -e .
export OLLIE_API_KEY=...
export OLLIE_AGENT_ID=...
export OLLIE_BASE_URL=...
export OLLIE_INGEST_BASE_URL=...
python examples/sdk_test_agent_loop.py

# Production path (persist + index queue):
OLLIE_SDK_FLUSH=ingest python examples/sdk_test_agent_loop.py
```

`OLLIE_SDK_FLUSH` values: `validate` (default), `process`, `ingest`.

Expect HTTP **200** from batch POST. Traces appear in Ollie UI after the ingest worker processes the queue (usually within a minute).

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|----------------|-----|
| `401` on registry or batch | Wrong or missing `OLLIE_API_KEY` | Confirm key with Ollie; header is `X-API-Key` |
| `401` / agent errors on ingest | `OLLIE_AGENT_ID` not in your project | Use agent ID Ollie created for your tenant |
| Connection refused / localhost | `OLLIE_INGEST_BASE_URL` not set | Set ingest Render URL |
| `200` but no traces in UI | Ingest worker down or backlog | Confirm ingest-worker service; check Redis `sdk-ingest:process` |
| Batch to analysis URL | Old SDK or wrong env | Batches must use **ingest** URL only |
| Custom feature rejected | Not registered | Call `define_feature` before trace |

---

## Security

- Treat `OLLIE_API_KEY` like a password; rotate via Ollie if leaked.
- Use HTTPS URLs only in production.
- Do not log full API keys or end-user PII in application logs unless policy allows.

---

## Further reading

- [README](../README.md) — install and env summary
- [examples/sdk_test_agent_loop.py](../examples/sdk_test_agent_loop.py) — minimal script
- [examples/simulated_agent/](../examples/simulated_agent/) — full primitive coverage
- Backend: [SDK Phase 2](https://github.com/varunnaganathan/olliejudge-sentry-backend/blob/main/docs/SDK_PHASE2.md), [Phase A ingest deploy](https://github.com/varunnaganathan/olliejudge-sentry-backend/blob/main/docs/PHASE_A_DEPLOY_INGEST.md)
