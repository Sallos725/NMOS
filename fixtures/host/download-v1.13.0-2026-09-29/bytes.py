"""Serves N MB of deterministic bytes as an attachment, with their SHA-256, CORS open."""
import hashlib, sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
CACHE = {}
def body(mb):
    if mb not in CACHE:
        seed = hashlib.sha256(b"nmos").digest(); out = bytearray()
        while len(out) < int(mb * 1024 * 1024):
            seed = hashlib.sha256(seed).digest(); out += seed * 32
        b = bytes(out[: int(mb * 1024 * 1024)]); CACHE[mb] = (b, hashlib.sha256(b).hexdigest())
    return CACHE[mb]
class H(BaseHTTPRequestHandler):
    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.send_header("Access-Control-Expose-Headers", "*")
    def do_OPTIONS(self):
        self.send_response(204); self._cors(); self.end_headers()
    def do_GET(self):
        q = parse_qs(urlparse(self.path).query); mb = float(q.get("mb", ["1"])[0])
        b, h = body(mb)
        self.send_response(200); self._cors()
        self.send_header("Content-Type", "application/zip")
        self.send_header("Content-Disposition", 'attachment; filename="probe.nmos.zip"')
        self.send_header("X-Sha256", h); self.send_header("Content-Length", str(len(b)))
        self.end_headers(); self.wfile.write(b)
        print(f"GET {self.path} ua={self.headers.get('User-Agent','')[:40]} -> {len(b)} {h[:12]}", flush=True)
    do_POST = do_GET
    def log_message(self, *a): pass
ThreadingHTTPServer(("0.0.0.0", int(sys.argv[1])), H).serve_forever()
