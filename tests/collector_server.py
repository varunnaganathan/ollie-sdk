"""Log-only HTTP server that mimics the SDK API surface (no Postgres, no ingest).

Use in E2E tests and manual smoke runs so you can confirm the SDK actually sends HTTP
requests and observe payloads under concurrent load.

    python -m tests.collector_server --port 19999
    OLLIE_BASE_URL=http://127.0.0.1:19999 OLLIE_API_KEY=test OLLIE_AGENT_ID=a1 \\
        python examples/sdk_test_agent_loop.py
"""

from __future__ import annotations

import argparse
import gzip
import json
import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


@dataclass
class RecordedRequest:
    method: str
    path: str
    headers: dict[str, str]
    body: dict[str, Any] | list[Any] | None
    received_at: str


@dataclass
class SDKCollector:
    """Thread-safe in-memory log of SDK HTTP calls."""

    host: str = "127.0.0.1"
    port: int = 0
    _server: ThreadingHTTPServer | None = field(default=None, repr=False)
    _thread: threading.Thread | None = field(default=None, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    _requests: list[RecordedRequest] = field(default_factory=list, repr=False)
    _seen_event_ids: set[str] = field(default_factory=set, repr=False)

    @property
    def base_url(self) -> str:
        if not self._server:
            raise RuntimeError("collector not started")
        return f"http://{self.host}:{self._server.server_port}"

    def start(self) -> SDKCollector:
        collector = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, format: str, *args: Any) -> None:
                return

            def do_POST(self) -> None:
                collector._handle(self)

            def do_GET(self) -> None:
                collector._handle(self)

        self._server = ThreadingHTTPServer((self.host, self.port), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        logger.info("SDK log collector listening on %s", self.base_url)
        return self

    def stop(self) -> None:
        if self._server:
            self._server.shutdown()
            self._server.server_close()
        if self._thread:
            self._thread.join(timeout=5)
        self._server = None
        self._thread = None

    def clear(self) -> None:
        with self._lock:
            self._requests.clear()
            self._seen_event_ids.clear()

    def requests(self) -> list[RecordedRequest]:
        with self._lock:
            return list(self._requests)

    def count_path(self, path: str) -> int:
        return sum(1 for r in self.requests() if r.path == path)

    def _record(self, handler: BaseHTTPRequestHandler, body: Any) -> None:
        rec = RecordedRequest(
            method=handler.command,
            path=urlparse(handler.path).path,
            headers={k: v for k, v in handler.headers.items()},
            body=body,
            received_at=datetime.now(timezone.utc).isoformat(),
        )
        with self._lock:
            self._requests.append(rec)
        logger.info(
            "SDK HTTP %s %s body_keys=%s",
            rec.method,
            rec.path,
            list(body.keys()) if isinstance(body, dict) else type(body).__name__,
        )

    def _handle(self, handler: BaseHTTPRequestHandler) -> None:
        length = int(handler.headers.get("Content-Length", "0") or "0")
        raw = handler.rfile.read(length) if length else b""
        encoding = (handler.headers.get("content-encoding") or "").strip().lower()
        if raw and encoding == "gzip":
            try:
                raw = gzip.decompress(raw)
            except Exception:
                raw = b""
        body: Any = None
        if raw:
            try:
                body = json.loads(raw.decode("utf-8"))
            except json.JSONDecodeError:
                body = {"_raw": raw.decode("utf-8", errors="replace")}

        path = urlparse(handler.path).path
        self._record(handler, body)

        if handler.command == "GET" and path == "/v1/sdk/registry":
            self._json(handler, 200, {"features": [], "span_types": [], "signals": []})
            return

        if handler.command == "POST" and path.startswith("/v1/sdk/registry/"):
            self._json(
                handler,
                201,
                {
                    "id": "collector-stub",
                    "kind": path.rsplit("/", 1)[-1].replace("-", "_"),
                    "name": (body or {}).get("name", "stub"),
                    "description": (body or {}).get("description", ""),
                    "config": {},
                },
            )
            return

        if handler.command == "POST" and path in ("/v1/sdk/traces/validate", "/v1/sdk/traces/process"):
            accepted = isinstance(body, dict) and isinstance(body.get("interactions"), list)
            if not accepted:
                self._json(handler, 200, {"accepted": False, "errors": ["interactions required"]})
                return
            if path == "/v1/sdk/traces/process":
                interactions = []
                for i, raw_ix in enumerate(body.get("interactions") or []):
                    if not isinstance(raw_ix, dict):
                        continue
                    interactions.append(
                        {
                            "interaction_index": i,
                            "adapter_key": "sdk.instrumentation.v1",
                            "id": f"collector-{i}",
                            "layers": {"spans": raw_ix.get("spans") or []},
                        }
                    )
                self._json(
                    handler,
                    200,
                    {
                        "accepted": True,
                        "trace_id": body.get("conversation_id") or "collector-trace",
                        "conversation_id": body.get("conversation_id"),
                        "normalized": body,
                        "interactions": interactions,
                        "manifest_preview": {"adapter_key": "sdk.instrumentation.v1", "dim": 0},
                        "sparse_previews": [],
                        "signal_registry": [],
                        "index_preview": {"chunk_count": len(interactions)},
                        "errors": [],
                        "warnings": [],
                    },
                )
            else:
                self._json(
                    handler,
                    200,
                    {
                        "accepted": True,
                        "normalized": body,
                        "errors": [],
                        "warnings": [],
                    },
                )
            return

        if handler.command == "POST" and path == "/v1/sdk/events/batch":
            if not isinstance(body, dict) or not isinstance(body.get("events"), list):
                self._json(handler, 200, {"accepted_count": 0, "rejected_count": 1, "duplicate_count": 0, "results": []})
                return
            results = []
            accepted = duplicate = rejected = 0
            for ev in body.get("events") or []:
                if not isinstance(ev, dict):
                    rejected += 1
                    continue
                eid = str(ev.get("event_id") or "")
                if eid in self._seen_event_ids:
                    duplicate += 1
                    results.append({"event_id": eid, "status": "duplicate"})
                else:
                    self._seen_event_ids.add(eid)
                    accepted += 1
                    item: dict[str, Any] = {"event_id": eid, "status": "accepted"}
                    etype = str(ev.get("event_type") or "")
                    payload = ev.get("payload") if isinstance(ev.get("payload"), dict) else {}
                    if etype == "sdk.trace.validate":
                        item["validate_result"] = {
                            "accepted": True,
                            "normalized": payload,
                            "errors": [],
                            "warnings": [],
                        }
                    elif etype == "sdk.trace.process":
                        interactions = []
                        for i, raw_ix in enumerate(payload.get("interactions") or []):
                            if isinstance(raw_ix, dict):
                                interactions.append(
                                    {
                                        "interaction_index": i,
                                        "adapter_key": "sdk.instrumentation.v1",
                                        "id": f"collector-{i}",
                                    }
                                )
                        item["process_result"] = {
                            "accepted": True,
                            "trace_id": payload.get("conversation_id"),
                            "interactions": interactions,
                            "errors": [],
                            "warnings": [],
                        }
                    elif etype == "sdk.trace.ingest":
                        item["ingest"] = {
                            "accepted": True,
                            "trace_id": payload.get("conversation_id"),
                            "interaction_count": len(payload.get("interactions") or []),
                            "errors": [],
                            "warnings": [],
                        }
                    results.append(item)
            self._json(
                handler,
                200,
                {
                    "batch_id": body.get("batch_id") or "collector-batch",
                    "accepted_count": accepted,
                    "duplicate_count": duplicate,
                    "rejected_count": rejected,
                    "results": results,
                },
            )
            return

        self._json(handler, 404, {"detail": f"unknown path {path}"})

    @staticmethod
    def _json(handler: BaseHTTPRequestHandler, status: int, payload: dict[str, Any]) -> None:
        data = json.dumps(payload).encode("utf-8")
        handler.send_response(status)
        handler.send_header("Content-Type", "application/json")
        handler.send_header("Content-Length", str(len(data)))
        handler.end_headers()
        handler.wfile.write(data)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    p = argparse.ArgumentParser(description="Log-only SDK HTTP collector")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=19999)
    args = p.parse_args()
    c = SDKCollector(host=args.host, port=args.port).start()
    print(f"Collector at {c.base_url} (Ctrl+C to stop)", flush=True)
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        c.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
