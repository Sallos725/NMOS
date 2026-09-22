#!/usr/bin/env python3
"""Throwaway Phase 0A HTTP collector for NMOS PocketRisu spike observations.

This is intentionally NOT the NMOS sidecar.
It uses only the Python standard library.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

MAX_BODY_BYTES = 64 * 1024 * 1024


def safe_label(value: object) -> str:
    text = str(value or "unlabeled")
    text = re.sub(r"[^A-Za-z0-9._-]+", "-", text).strip("-")
    return text[:80] or "unlabeled"


class CollectorHandler(BaseHTTPRequestHandler):
    server_version = "NMOSSpikeCollector/0.1"

    @property
    def root(self) -> Path:
        return self.server.output_root  # type: ignore[attr-defined]

    def _json_response(self, status: int, payload: dict[str, Any]) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(data)

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/health":
            self._json_response(200, {"ok": True, "kind": "phase-0a-spike-collector"})
            return
        self._json_response(404, {"error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path not in {"/spike", "/"}:
            self._json_response(404, {"error": "not_found"})
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._json_response(400, {"error": "invalid_content_length"})
            return

        if length <= 0 or length > MAX_BODY_BYTES:
            self._json_response(413, {"error": "invalid_body_size", "bytes": length})
            return

        raw = self.rfile.read(length)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except Exception as exc:
            self._json_response(400, {"error": "invalid_json", "detail": str(exc)})
            return

        scenario = safe_label(payload.get("scenario"))
        kind = safe_label(payload.get("kind"))
        now = datetime.now(timezone.utc)
        stamp = now.strftime("%Y%m%dT%H%M%S.%fZ")
        filename = f"{stamp}__{scenario}__{kind}__{uuid.uuid4().hex[:8]}.json"

        self.root.mkdir(parents=True, exist_ok=True)
        target = self.root / filename
        target.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        print(f"[saved] {target}", flush=True)
        self._json_response(201, {"ok": True, "file": str(target)})

    def log_message(self, fmt: str, *args: object) -> None:
        print(f"[http] {self.address_string()} - {fmt % args}", file=sys.stderr)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument(
        "--output",
        default="fixtures/host/incoming",
        help="Directory for captured JSON observations",
    )
    args = parser.parse_args()

    output_root = Path(args.output).resolve()
    server = ThreadingHTTPServer((args.host, args.port), CollectorHandler)
    server.output_root = output_root  # type: ignore[attr-defined]

    print(f"NMOS Phase 0A spike collector listening on http://{args.host}:{args.port}")
    print(f"Writing observations to: {output_root}")
    print("This is throwaway measurement tooling, NOT the production sidecar.")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
