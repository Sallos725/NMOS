"""Upload expiry and shutdown preserve a busy archive and reclaim only this spool's files."""

import threading
import time

import pytest

from nmos_sidecar import uploads


def wait_for(predicate):
    until = time.monotonic() + 2
    while not predicate() and time.monotonic() < until:
        time.sleep(0.005)
    assert predicate()


def test_idle_upload_expires_without_another_request(tmp_path):
    now = [0.0]
    spool = uploads.Uploads(100, make_dir=lambda: tmp_path / "spool", clock=lambda: now[0], cleanup_interval=0.01)
    unrelated = tmp_path / "keep.txt"
    unrelated.write_text("not an upload")
    try:
        up = spool.create(10)
        now[0] = uploads.TTL
        wait_for(lambda: not up.path.exists())
        assert up.id not in spool.items
        assert unrelated.read_text() == "not an upload"
        wait_for(lambda: spool._timer is None)
    finally:
        spool.close()


@pytest.mark.parametrize("close", [False, True])
def test_expiry_and_close_keep_the_busy_file_until_work_finishes(tmp_path, close):
    now = [0.0]
    spool = uploads.Uploads(100, make_dir=lambda: tmp_path / "spool", clock=lambda: now[0], cleanup_interval=0.01)
    entered, release = threading.Event(), threading.Event()
    cleanup_seen = threading.Event()
    expire = spool._expire

    def observed_expiry():
        expire()
        if now[0] >= uploads.TTL:
            cleanup_seen.set()

    spool._expire = observed_expiry
    up = spool.create(10)
    up.path.write_bytes(b"archive")
    up.state = "received"

    def work(active):
        entered.set()
        assert release.wait(2)
        assert active.path.read_bytes() == b"archive"
        active.state = "checked"

    try:
        spool.run(up.id, "received", "checking", work)
        assert entered.wait(2)
        now[0] = uploads.TTL + 1
        if close:
            spool.close()
            assert spool._timer is None
            with pytest.raises(uploads.UploadError) as error:
                spool.create(10)
            assert error.value.status == 503
        else:
            assert cleanup_seen.wait(2)  # a real cleanup tick at the expired logical clock
        assert up.path.exists() and up.busy
        release.set()
        wait_for(lambda: not up.path.exists())
        assert up.id not in spool.items
        if close:
            assert not (tmp_path / "spool").exists()
    finally:
        release.set()
        spool.close()


@pytest.mark.parametrize("operation", ["run", "discard"])
def test_replaced_upload_cannot_be_used_after_get(tmp_path, monkeypatch, operation):
    spool = uploads.Uploads(100, make_dir=lambda: tmp_path / "spool")
    original = spool.get
    up = spool.create(10)
    up.state = "received"
    ran = threading.Event()

    def replaced(upload_id):
        old = original(upload_id)
        spool.create(10)
        return old

    monkeypatch.setattr(spool, "get", replaced)
    try:
        with pytest.raises(uploads.UploadError) as error:
            if operation == "run":
                spool.run(up.id, "received", "checking", lambda active: ran.set())
            else:
                spool.discard(up.id)
        assert error.value.status == 404
        assert not ran.is_set()
        assert len(spool.items) == 1
    finally:
        spool.close()
