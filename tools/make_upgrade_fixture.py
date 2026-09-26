"""Record a database written by an earlier release, for the upgrade test (audit A-16).

    cd apps/sidecar && uv run python ../../tools/make_upgrade_fixture.py v0.1.0-beta.7

Checks the release out in a temporary git worktree and runs *its* sidecar and worker as processes
(with `PYTHONPATH` pointing at its source), against a fresh database on the compose Postgres, with a
deterministic stub model and embedder served from this script. A scripted chat goes through them: turns
with facts, an edit, a reroll, a swipe back, a disabled message and a branch, with recalls in between;
the worker drains extraction and embedding. The result is dumped with `pg_dump` (run inside the
Postgres container) to `fixtures/upgrade/<ref>.sql`, and the chats as the host last showed them to
`fixtures/upgrade/<ref>.chat.json`. `apps/sidecar/tests/test_upgrade.py` restores the dump and upgrades it.

Standard library plus the sidecar's own dependencies (httpx, psycopg); no model or network access.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import socket
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import httpx
import psycopg

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps/sidecar/tests"))
from simchat import SimChat  # noqa: E402  (hash format v1, unchanged since the first release)

ADMIN_URL = os.environ.get("NMOS_TEST_ADMIN_URL", "postgresql://nmos:nmos@127.0.0.1:5436/postgres")
EMBED_DIM = 8

# The stub extractor: sentences of these shapes in the TARGET part of the prompt become assertions.
RULES = [
    (re.compile(r"(?P<s>[A-Z]\w+) (?:is in|moved to|went to) the (?P<o>\w+(?: \w+)?)\."),
     lambda m: {"subject": m["s"], "subject_type": "character", "predicate": "located_in",
                "object": m["o"], "object_type": "place"}),
    (re.compile(r"(?P<s>[A-Z]\w+) (?:has|carries|keeps) the (?P<o>\w+(?: \w+)?)\."),
     lambda m: {"subject": m["s"], "subject_type": "character", "predicate": "possesses",
                "object": m["o"], "object_type": "item"}),
    (re.compile(r"(?P<s>[A-Z]\w+) promised (?P<o>[A-Z]\w+) to (?P<v>[^.]+)\."),
     lambda m: {"subject": m["s"], "subject_type": "character", "predicate": "promised",
                "object": m["o"], "object_type": "character", "value": m["v"]}),
    (re.compile(r"(?P<s>[A-Z]\w+) is (?P<o>[A-Z]\w+)'s (?P<v>sister|brother|rival|friend)\."),
     lambda m: {"subject": m["s"], "subject_type": "character", "predicate": "relationship",
                "object": m["o"], "object_type": "character", "value": m["v"]}),
]


def extract(prompt: str) -> dict:
    target = prompt.split("\nTARGET", 1)[-1]
    items = []
    for pattern, build in RULES:
        for m in pattern.finditer(target):
            items.append({**build(m), "epistemic": "stated", "confidence": 0.9, "evidence": m.group(0),
                          "modality": "actual"})
    return {"assertions": items}


def embed(text: str) -> list[float]:
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    vec = [b - 127.5 for b in digest[:EMBED_DIM]]
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


class Stub(BaseHTTPRequestHandler):
    def log_message(self, *args) -> None:  # quiet
        pass

    def _send(self, body: dict) -> None:
        data = json.dumps(body).encode()
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        self._send({"data": [{"id": "stub"}, {"id": "stub-embed"}]})

    def do_POST(self) -> None:
        body = json.loads(self.rfile.read(int(self.headers["content-length"])))
        if self.path.endswith("/chat/completions"):
            user = next(m["content"] for m in body["messages"] if m["role"] == "user")
            self._send({"choices": [{"message": {"content": json.dumps(extract(user))}}]})
        elif self.path.endswith("/embeddings"):
            texts = body["input"] if isinstance(body["input"], list) else [body["input"]]
            self._send({"data": [{"index": i, "embedding": embed(t)} for i, t in enumerate(texts)]})
        else:
            self.send_error(404)


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class OldRelease:
    """The release's sidecar and worker as processes, against `db_url`."""

    def __init__(self, worktree: Path, db_url: str, stub_url: str) -> None:
        self.port = free_port()
        self.env = {**os.environ, "PYTHONPATH": str(worktree / "apps/sidecar/src"),
                    "NMOS_MIGRATIONS_DIR": str(worktree / "migrations"), "NMOS_DATABASE_URL": db_url,
                    "NMOS_AUTH_TOKEN": "", "NMOS_LLM_URL": stub_url, "NMOS_LLM_MODEL": "stub",
                    "NMOS_EMBED_URL": stub_url, "NMOS_EMBED_MODEL": "stub-embed", "NMOS_EXTRACT_BACKFILL": "1000",
                    "NMOS_EMBED_BACKFILL": "1000", "NMOS_WORKER_CONCURRENCY": "1", "NMOS_EMBED_TIMEOUT_MS": "3000"}
        self.db_url = db_url
        self.procs: list[subprocess.Popen] = []
        self.http = httpx.Client(base_url=f"http://127.0.0.1:{self.port}", timeout=30)

    def run(self, *args: str) -> subprocess.Popen:
        proc = subprocess.Popen([sys.executable, *args], env=self.env, stdout=subprocess.DEVNULL,
                                stderr=subprocess.PIPE, text=True)
        self.procs.append(proc)
        return proc

    def start(self) -> None:
        subprocess.run([sys.executable, "-m", "nmos_sidecar.migrate"], env=self.env, check=True,
                       stdout=subprocess.DEVNULL)
        self.run("-m", "uvicorn", "nmos_sidecar.api:app_factory", "--factory", "--port", str(self.port),
                 "--log-level", "warning")
        for _ in range(100):
            try:
                if self.http.get("/v1/health").status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(0.2)
        else:
            raise RuntimeError("the old sidecar did not start: " + self.procs[-1].stderr.read())
        self.run("-m", "nmos_sidecar.worker")

    def sync(self, chat: SimChat, **labels) -> dict:
        manifest = {**chat.manifest(), **labels}
        out = self.http.post("/v1/sync/reconcile", json=manifest).raise_for_status().json()
        if out["status"] == "needs_bodies":
            res = self.http.post("/v1/sync/bodies", json={"chat_id": chat.id, "bodies": chat.bodies(out["needed_bodies"]),
                                                           "then_reconcile": manifest}).raise_for_status().json()
            assert res["ok"], res
            out = res["reconcile"]
        return out

    def recall(self, chat: SimChat, query: str, out: dict) -> None:
        self.http.post("/v1/retrieve", json={
            "chat_id": chat.id, "active_commit": out["active_commit"], "manifest_hash": out["manifest_hash"],
            "query": query, "in_context_ids": [m["chatId"] for m in chat.messages[-4:]],
            "budget_tokens": 600}).raise_for_status()

    def step(self, chat: SimChat, query: str, **labels) -> None:
        self.recall(chat, query, self.sync(chat, **labels))

    def drain(self, timeout: float = 120) -> None:
        deadline = time.monotonic() + timeout
        with psycopg.connect(self.db_url) as conn:
            while time.monotonic() < deadline:
                row = conn.execute("SELECT count(*) FILTER (WHERE status IN ('queued', 'running')),"
                                   " count(*) FILTER (WHERE last_error IS NOT NULL) FROM job").fetchone()
                if row[1]:
                    raise RuntimeError(f"{row[1]} jobs failed in the old worker")
                if row[0] == 0:
                    return
                time.sleep(0.5)
        raise RuntimeError("the old worker did not drain its queue")

    def stop(self) -> None:
        for proc in self.procs:
            proc.terminate()
        for proc in self.procs:
            proc.wait(timeout=15)


def scenario(old: OldRelease) -> list[SimChat]:
    labels = {"character_name": "Mina", "chat_name": "Upgrade fixture", "persona_name": "Yuuma"}
    chat = SimChat()
    lines = [
        ("We should rest somewhere safe.", "Mina is in the old chapel. Mina has the brass key."),
        ("Is Rin with you?", "Rin is Mina's sister. Rin went to the harbor."),
        ("What did Mina say before she left?", "Mina promised Yuuma to return before the bell rings."),
        ("Let's check the market.", "Idle reply about lanterns and rain."),
        ("Any news from the harbor?", "Rin has the silver compass. The gulls are loud today."),
        ("Where do we meet tonight?", "Mina moved to the bell tower."),
    ]
    for i, (user, reply) in enumerate(lines):
        chat.user(user)
        chat.reply(reply)
        if i % 2:
            old.step(chat, user, **labels)
    chat.user("Where is Mina now?")
    old.step(chat, "Where is Mina now?", **labels)
    old.drain()

    chat.edit(3, "Rin is Mina's rival. Rin went to the lighthouse.")        # edit an old reply
    chat.reply("Mina keeps the brass key close.")                           # the pending turn's reply
    chat.user("And the compass?")
    old.step(chat, "And the compass?", **labels)
    chat.reply("Rin has the silver compass.")
    chat.reroll("Rin carries the silver compass and a map.")                  # live reroll (H14)
    old.step(chat, "compass", **labels)
    chat.swipe(0)                                                             # swipe back
    chat.disable(8)                                                           # hide a message
    chat.user("Let's go.")
    old.step(chat, "Let's go.", **labels)
    old.drain()

    branch = chat.branch(5, "Harbor route")
    branch.user("Rin moved to the market.")
    old.step(branch, "Where is Rin?", **labels)
    old.drain()
    return [chat, branch]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("ref", help="release tag, e.g. v0.1.0-beta.7")
    parser.add_argument("--pg-container", default="nmos-postgres-1", help="container that runs pg_dump")
    args = parser.parse_args()

    stub = ThreadingHTTPServer(("127.0.0.1", 0), Stub)
    threading.Thread(target=stub.serve_forever, daemon=True).start()
    stub_url = f"http://127.0.0.1:{stub.server_address[1]}/v1"
    name = f"nmos_fixture_{uuid.uuid4().hex[:8]}"
    base = ADMIN_URL.rpartition("/")[0]
    out_dir = ROOT / "fixtures/upgrade"
    out_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        worktree = Path(tmp) / "release"
        subprocess.run(["git", "-C", str(ROOT), "worktree", "add", "--detach", "-q", str(worktree), args.ref], check=True)
        with psycopg.connect(ADMIN_URL, autocommit=True) as admin:
            admin.execute(f'CREATE DATABASE "{name}"')
        old = OldRelease(worktree, f"{base}/{name}", stub_url)
        try:
            old.start()
            chats = scenario(old)
            old.stop()
            dump = subprocess.run(["docker", "exec", args.pg_container, "pg_dump", "-U", "nmos", "-d", name, "--inserts",
                                   "--no-owner", "--no-privileges"], check=True, capture_output=True, text=True).stdout
            # psql meta-commands (`\\restrict`, pg_dump ≥ 16.10) cannot run through psycopg.
            dump = "".join(line for line in dump.splitlines(keepends=True) if not line.startswith("\\"))
            (out_dir / f"{args.ref}.sql").write_text(dump)
            (out_dir / f"{args.ref}.chat.json").write_text(json.dumps(
                {"ref": args.ref, "chats": [{"id": c.id, "messages": c.messages} for c in chats]},
                ensure_ascii=False, indent=1) + "\n")
        finally:
            old.stop()
            with psycopg.connect(ADMIN_URL, autocommit=True) as admin:
                admin.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
            subprocess.run(["git", "-C", str(ROOT), "worktree", "remove", "--force", str(worktree)], check=False)
    print(f"wrote fixtures/upgrade/{args.ref}.sql and .chat.json")


if __name__ == "__main__":
    main()
