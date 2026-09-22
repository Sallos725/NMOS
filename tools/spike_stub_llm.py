#!/usr/bin/env python3
"""Throwaway Phase 0A stub model endpoint (OpenAI-compatible chat completions).

Lets the S1-S14 host scenarios run without a real model or API key. The host behavior under
observation (PocketRisu hooks, message IDs, retries) does not depend on what the model says.

- POST /v1/chat/completions   deterministic canned reply; honours `stream`
- POST /control               {"fail_next": N, "fail_status": 500, "delay_ms": 0}
- GET  /stats                 request counter and remaining forced failures
- GET  /health

Request bodies are never printed; only message counts and roles (and, with --show-packets, the
injected NMOS packet text).
Standard library only. NOT the NMOS sidecar.
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

LOCK = threading.Lock()
STATE: dict[str, Any] = {"requests": 0, "fail_next": 0, "fail_status": 500, "delay_ms": 0}
SHOW_PACKETS = False


def reply_text(n: int, messages: list[dict[str, Any]]) -> str:
    roles = ",".join(str(m.get("role", "?")) for m in messages[-4:])
    return f"Stub reply #{n}. The prompt had {len(messages)} messages (tail roles: {roles})."


class StubHandler(BaseHTTPRequestHandler):
    server_version = "NMOSSpikeStubLLM/0.1"

    def _cors(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")

    def _json(self, status: int, payload: dict[str, Any]) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self._cors()
        self.end_headers()
        self.wfile.write(data)

    def _body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0") or 0)
        raw = self.rfile.read(length) if length > 0 else b"{}"
        return json.loads(raw.decode("utf-8") or "{}")

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/health":
            self._json(200, {"ok": True, "kind": "phase-0a-stub-llm"})
        elif self.path == "/stats":
            with LOCK:
                self._json(200, dict(STATE))
        elif self.path.rstrip("/").endswith("/models"):
            self._json(200, {"object": "list", "data": [{"id": "nmos-stub", "object": "model"}]})
        else:
            self._json(404, {"error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802
        try:
            body = self._body()
        except (ValueError, json.JSONDecodeError):
            self._json(400, {"error": "invalid_json"})
            return

        if self.path == "/control":
            with LOCK:
                for key in ("fail_next", "fail_status", "delay_ms"):
                    if key in body:
                        STATE[key] = int(body[key])
                self._json(200, dict(STATE))
            return

        if not self.path.rstrip("/").endswith("/chat/completions"):
            self._json(404, {"error": "not_found"})
            return

        messages = body.get("messages") if isinstance(body.get("messages"), list) else []
        with LOCK:
            STATE["requests"] += 1
            n = STATE["requests"]
            fail = STATE["fail_next"] > 0
            if fail:
                STATE["fail_next"] -= 1
            fail_status = STATE["fail_status"]
            delay_ms = STATE["delay_ms"]

        packets = [str(m.get("content")) for m in messages if "<NarrativeMemory" in str(m.get("content"))]
        print(
            f"[stub] request #{n} messages={len(messages)} "
            f"roles={[m.get('role') for m in messages]} stream={bool(body.get('stream'))} "
            f"forced_fail={fail} nmos_packets={len(packets)} "
            f"nmos_excerpts={sum(p.count('<Excerpt ') for p in packets)}",
            flush=True,
        )
        if SHOW_PACKETS:
            for packet in packets:
                print(packet, flush=True)
        if delay_ms > 0:
            time.sleep(delay_ms / 1000)
        if fail:
            self._json(fail_status, {"error": {"message": f"forced failure for request #{n}"}})
            return

        text = reply_text(n, messages)
        created = int(time.time())
        if body.get("stream"):
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self._cors()
            self.end_headers()
            for piece in (text[: len(text) // 2], text[len(text) // 2 :]):
                chunk = {
                    "id": f"stub-{n}", "object": "chat.completion.chunk", "created": created,
                    "model": "nmos-stub",
                    "choices": [{"index": 0, "delta": {"content": piece}, "finish_reason": None}],
                }
                self.wfile.write(f"data: {json.dumps(chunk)}\n\n".encode("utf-8"))
                self.wfile.flush()
            done = {
                "id": f"stub-{n}", "object": "chat.completion.chunk", "created": created,
                "model": "nmos-stub", "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
            }
            self.wfile.write(f"data: {json.dumps(done)}\n\ndata: [DONE]\n\n".encode("utf-8"))
            self.wfile.flush()
            return

        self._json(200, {
            "id": f"stub-{n}", "object": "chat.completion", "created": created, "model": "nmos-stub",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": text}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        })

    def log_message(self, fmt: str, *args: object) -> None:
        print(f"[http] {self.address_string()} - {fmt % args}", file=sys.stderr)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--show-packets", action="store_true", help="print injected NMOS packets (test data only)")
    args = parser.parse_args()
    global SHOW_PACKETS
    SHOW_PACKETS = args.show_packets
    server = ThreadingHTTPServer((args.host, args.port), StubHandler)
    print(f"NMOS Phase 0A stub LLM on http://{args.host}:{args.port}/v1/chat/completions", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
