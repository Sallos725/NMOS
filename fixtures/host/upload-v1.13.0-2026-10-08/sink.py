"""Receives a request body and answers with its length and SHA-256, CORS open (Phase 38 step 2).

    python3 sink.py PORT

A body sent as JSON {"data": "<base64>"} is decoded first, so both forms are hashed as the bytes the frame meant."""
import base64, hashlib, json, sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class H(BaseHTTPRequestHandler):
    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.send_header("Access-Control-Allow-Methods", "*")

    def do_OPTIONS(self):
        self.send_response(204); self._cors(); self.end_headers()

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n) if n else b""
        ct = self.headers.get("Content-Type", "")
        form = "binary"
        if ct.startswith("application/json"):
            form = "base64"
            try:
                raw = base64.b64decode(json.loads(raw)["data"])
            except Exception as e:  # noqa: BLE001 — answered as it is
                raw = b""; form = f"base64-unreadable {type(e).__name__}"
        out = {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(), "form": form, "content_type": ct,
               "content_length": n, "ua": self.headers.get("User-Agent", "")[:40]}
        body = json.dumps(out).encode()
        self.send_response(200); self._cors()
        self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(body)))
        self.end_headers(); self.wfile.write(body)
        print(f"POST {self.path} {out}", flush=True)

    def log_message(self, *a):
        pass


ThreadingHTTPServer(("0.0.0.0", int(sys.argv[1])), H).serve_forever()
