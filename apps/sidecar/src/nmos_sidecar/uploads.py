"""An archive uploaded from the panel for a restore (PHASE-38 Q2, Q3): received in chunks into a spool file, checked,
then restored, each step in the background so no request waits for minutes behind the host's proxy.

One upload at a time: a new one discards the others. An upload not restored within an hour is discarded, and so is
its file once it is restored, refused or discarded. Chunks come in order, each with its SHA-256; the same chunk sent
again (a retry after a lost answer) is accepted once more without being written twice. The archive's own manifest
hashes check its content (`archive.check_archive`); the chunk hashes check its transport."""

from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

CHUNK = 8 * 1024 * 1024  # H23: 8 MB of base64 in JSON per request
TTL = 3600.0


class UploadError(Exception):
    def __init__(self, status: int, detail: str) -> None:
        super().__init__(detail)
        self.status, self.detail = status, detail


@dataclass
class Upload:
    id: str
    path: Path
    size: int
    created: float
    received: int = 0
    next_index: int = 0
    last_sha: str = ""
    # receiving → received → checking → checked | refused → restoring → restored | failed
    state: str = "receiving"
    detail: str = ""
    summary: dict[str, Any] | None = None
    result: dict[str, Any] | None = None
    checked: Any = None  # archive.Checked once checked
    busy: bool = field(default=False, repr=False)

    def view(self) -> dict[str, Any]:
        out: dict[str, Any] = {"id": self.id, "state": self.state, "bytes": self.size, "received": self.received,
                               "chunk_bytes": CHUNK}
        if self.detail:
            out["detail"] = self.detail
        if self.summary is not None:
            out["summary"] = self.summary
        if self.result is not None:
            out["result"] = self.result
        return out


def spool_dir() -> Path:
    """This sidecar's own spool directory in the system's temporary directory; another's left by a crash more than an
    hour ago is removed (nothing here is kept past an hour)."""
    base = Path(tempfile.gettempdir())
    for old in base.glob("nmos-restore-*"):
        try:
            if time.time() - old.stat().st_mtime > TTL:
                shutil.rmtree(old, ignore_errors=True)
        except OSError:
            pass
    return Path(tempfile.mkdtemp(prefix="nmos-restore-", dir=base))


class Uploads:
    def __init__(self, directory: Path, max_bytes: int, clock: Callable[[], float] = time.monotonic) -> None:
        self.dir, self.max_bytes, self.clock = directory, max_bytes, clock
        self.items: dict[str, Upload] = {}
        self.lock = threading.Lock()
        self.dir.mkdir(parents=True, exist_ok=True)

    def _drop(self, up: Upload) -> None:
        self.items.pop(up.id, None)
        up.path.unlink(missing_ok=True)

    def _expire(self) -> None:
        for up in list(self.items.values()):
            if not up.busy and self.clock() - up.created > TTL:
                self._drop(up)

    def create(self, size: int) -> Upload:
        if size <= 0:
            raise UploadError(422, "an archive has at least one byte")
        if size > self.max_bytes:
            raise UploadError(413, f"the archive is {size} bytes; this NMOS takes up to {self.max_bytes}"
                                   " (NMOS_RESTORE_MAX_MB)")
        with self.lock:
            if any(up.busy for up in self.items.values()):
                raise UploadError(409, "another archive is being checked or restored; wait for it")
            for up in list(self.items.values()):  # Q2: a new upload replaces the others
                self._drop(up)
            free = shutil.disk_usage(self.dir).free
            if free < 2 * size:
                raise UploadError(507, f"not enough free space for the archive: {free} bytes free, {2 * size} needed")
            up = Upload(id=uuid.uuid4().hex, path=self.dir / f"{uuid.uuid4().hex}.nmos.zip", size=size,
                        created=self.clock())
            up.path.touch(mode=0o600)
            self.items[up.id] = up
            return up

    def get(self, upload_id: str) -> Upload:
        with self.lock:
            self._expire()
            up = self.items.get(upload_id)
            if up is None:
                raise UploadError(404, "no such upload (it expired, or another replaced it)")
            return up

    def chunk(self, upload_id: str, index: int, data: bytes, sha256: str) -> Upload:
        up = self.get(upload_id)
        with self.lock:
            if self.items.get(upload_id) is not up:
                raise UploadError(404, "no such upload (another replaced it)")
            if up.state != "receiving":
                raise UploadError(409, f"the upload is {up.state}, not receiving")
            if hashlib.sha256(data).hexdigest() != sha256:
                raise UploadError(422, f"chunk {index} arrived changed (its SHA-256 differs); send it again")
            if index == up.next_index - 1 and sha256 == up.last_sha:
                return up  # the same chunk again: its answer was lost
            if index != up.next_index:
                raise UploadError(409, f"chunk {index} out of order; the next is {up.next_index}")
            last = up.received + len(data) >= up.size
            if len(data) != CHUNK and not last or up.received + len(data) > up.size:
                raise UploadError(422, f"chunk {index} is {len(data)} bytes; chunks are {CHUNK} but the last")
            with up.path.open("ab") as f:
                f.write(data)
            up.received += len(data)
            up.next_index += 1
            up.last_sha = sha256
            if up.received == up.size:
                up.state = "received"
            return up

    def run(self, upload_id: str, want: str, then: str, work: Callable[[Upload], None]) -> Upload:
        """Start `work` in the background on an upload in state `want`, moving it to `then` (checking, restoring)."""
        up = self.get(upload_id)
        with self.lock:
            if up.state != want or up.busy:
                raise UploadError(409, f"the upload is {up.state}; it must be {want}")
            up.state, up.busy, up.detail = then, True, ""

        def go() -> None:
            try:
                work(up)
            finally:
                with self.lock:
                    up.busy = False
                    if up.state in ("refused", "restored", "failed"):
                        up.path.unlink(missing_ok=True)

        threading.Thread(target=go, name=f"nmos-{then}", daemon=True).start()
        return up

    def discard(self, upload_id: str) -> None:
        up = self.get(upload_id)
        with self.lock:
            if up.busy:
                raise UploadError(409, f"the upload is {up.state}; it cannot be discarded now")
            self._drop(up)
