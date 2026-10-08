"""Restore from the panel, while NMOS runs (PHASE-38, ADR 0050 amendment 2): an archive uploaded in chunks, checked and
summarized, then restored with the shared ids' sequences held; reads go on, writes that draw an id wait; every refusal
writes nothing and leaves no file.

Synthetic names only."""

from __future__ import annotations

import base64
import hashlib
import json
import threading
import time
from pathlib import Path

import psycopg
import pytest

from nmos_sidecar import archive, uploads
from simchat import SimChat
from test_archive import play
from test_restore import client, counts, export_to, rewrite, tables
from test_sidecar_integration import recall, sync

SMALL = 64 * 1024  # chunks in these tests: several per archive


@pytest.fixture(autouse=True)
def small_chunks(monkeypatch):
    monkeypatch.setattr(uploads, "CHUNK", SMALL)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def put(c, upload_id: str, index: int, part: bytes):
    return c.put(f"/v1/archive/uploads/{upload_id}/chunks/{index}",
                 json={"data": base64.b64encode(part).decode(), "sha256": sha(part)})


def upload(c, data: bytes) -> str:
    made = c.post("/v1/archive/uploads", json={"bytes": len(data)})
    assert made.status_code == 200, made.text
    up = made.json()
    assert up["chunk_bytes"] == SMALL and up["state"] == "receiving"
    for i in range(0, len(data), SMALL):
        res = put(c, up["id"], i // SMALL, data[i:i + SMALL])
        assert res.status_code == 200, res.text
    assert res.json() == {"state": "received", "received": len(data), "bytes": len(data)}
    return up["id"]


def wait(c, upload_id: str, *states: str, seconds: float = 120) -> dict:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        view = c.get(f"/v1/archive/uploads/{upload_id}").json()
        if view["state"] in states:
            return view
        time.sleep(0.05)
    raise AssertionError(f"upload {upload_id} never reached {states}: {view}")


def check(c, upload_id: str) -> dict:
    assert c.post(f"/v1/archive/uploads/{upload_id}/check").status_code == 202
    return wait(c, upload_id, "checked", "refused")


def restore(c, upload_id: str) -> dict:
    assert c.post(f"/v1/archive/uploads/{upload_id}/restore").status_code == 202
    return wait(c, upload_id, "restored", "failed")


def files_left() -> list[Path]:
    import tempfile
    return [f for d in Path(tempfile.gettempdir()).glob("nmos-restore-*") for f in d.iterdir()]


def test_an_archive_from_the_panel_restores_while_nmos_runs(migrated, database_url_factory, tmp_path):
    with client(migrated) as c:
        chat, branch = play(c, migrated)
        assert c.put("/v1/config", json={"recall_top_k": 7}).status_code == 200
        data = c.get("/v1/archive").content  # what the panel's Export everything saves
    target = database_url_factory()
    with client(target) as c:  # a running install
        uid = upload(c, data)
        view = check(c, uid)
        assert view["state"] == "checked", view
        s = view["summary"]
        assert s["scope"] == "install" and s["migrations"] == []
        assert {x["host_chat_ref"] for x in s["conversations"]} == {chat.id, branch.id}
        assert not any(x["here"] for x in s["conversations"])
        assert "recall_top_k" in {x["key"] for x in s["settings_added"]}
        done = restore(c, uid)
        assert done["state"] == "restored", done
        assert {x["host_chat_ref"] for x in done["result"]["conversations"]} == {chat.id, branch.id}
        assert done["result"]["queued_jobs"] > 0  # the archive has no embeddings: their jobs are queued now
        by_panel = tables(export_to(tmp_path, target, "t"))
        # Without a restart: the restored setting is in force, the derived text is there, recall and sync work.
        assert c.get("/v1/config").json()["recall"]["top_k"] == 7
        assert sync(c, chat)["status"] == "noop"
        assert recall(c, chat, "keeper", budget=2000)["packet"]["text"]
    with psycopg.connect(target) as conn:
        assert conn.execute("SELECT count(*) FROM revision_text").fetchone()[0] > 0
    # The same rows the command writes, once a sidecar has started on them.
    by_command = database_url_factory()
    source = tmp_path / f"panel{archive.SUFFIX}"
    source.write_bytes(data)
    archive.restore_file(by_command, str(source))
    with client(by_command):
        pass
    by_cmd = tables(export_to(tmp_path, by_command, "k"))
    # Generations are the install's own rows (GLOBAL): the same keys, activated when each install started.
    gens = "tables/projection_generation.jsonl"
    keys = lambda b: sorted(json.loads(line)["key"] for line in b.splitlines())
    assert keys(by_panel.pop(gens)) == keys(by_cmd.pop(gens))
    assert by_panel == by_cmd
    assert files_left() == []


def test_while_a_restore_runs_reads_go_on_and_writes_that_draw_an_id_wait(migrated, database_url_factory, monkeypatch):
    with client(migrated) as c:
        play(c, migrated)
        data = c.get("/v1/archive").content
    target = database_url_factory()
    own = SimChat()
    for i in range(3):
        own.user(f"Mina is in the tower {i}.")
        own.reply("Noted.")
    slow = archive._make_room

    def held(conn, scratch, out):  # the sequences are held from here to the commit
        time.sleep(2.0)
        slow(conn, scratch, out)

    monkeypatch.setattr(archive, "_make_room", held)
    with client(target) as c:
        sync(c, own)
        uid = upload(c, data)
        assert check(c, uid)["state"] == "checked"
        assert c.post(f"/v1/archive/uploads/{uid}/restore").status_code == 202
        time.sleep(0.5)
        t0 = time.monotonic()
        assert recall(c, own, "tower", budget=1000)["packet"]  # a read that records the request
        read_s = time.monotonic() - t0
        own.user("Mina moved to the harbor.")
        t0 = time.monotonic()
        assert sync(c, own)["status"] != "noop"  # draws a commit number: waits for the restore
        write_s = time.monotonic() - t0
        assert wait(c, uid, "restored", "failed")["state"] == "restored"
    assert read_s < 1.0, read_s
    assert write_s > 0.8, write_s
    with psycopg.connect(target) as conn:
        for table, col in archive.SEQUENCED.items():
            seq = conn.execute("SELECT pg_get_serial_sequence(%s, %s)", (table, col)).fetchone()[0]
            last, top = conn.execute(f"SELECT (SELECT last_value FROM {seq}), (SELECT max({col}) FROM {table})").fetchone()
            assert last >= top, table
        # The sync drew its number after the restore's (an append to an unchanged head, ADR 0010): it is the latest.
        newest = conn.execute("SELECT c.host_chat_ref FROM worldline_append a JOIN worldline_commit w ON w.id = a.commit_id"
                              " JOIN conversation c ON c.id = w.conversation_id ORDER BY a.seq DESC LIMIT 1").fetchone()[0]
        assert newest == own.id


def test_a_restore_that_cannot_take_the_locks_is_busy_and_writes_nothing(migrated, database_url_factory, monkeypatch):
    with client(migrated) as c:
        play(c, migrated)
        data = c.get("/v1/archive").content
    target = database_url_factory()
    monkeypatch.setattr(archive, "LOCK_TIMEOUT", "1s")
    holder = psycopg.connect(target)  # a write in flight that drew a commit number and has not committed
    holder.execute("SELECT nextval(pg_get_serial_sequence('worldline_commit', 'seq'))")
    try:
        with client(target) as c:
            before = counts(target)
            uid = upload(c, data)
            assert check(c, uid)["state"] == "checked"
            done = restore(c, uid)
            assert done["state"] == "failed" and "busy" in done["detail"], done
            assert counts(target) == before
            assert files_left() == []
    finally:
        holder.rollback()
        holder.close()
    with client(target) as c:  # once the other write is done, the same archive restores
        uid = upload(c, data)
        assert check(c, uid)["state"] == "checked"
        assert restore(c, uid)["state"] == "restored"


def test_a_chat_already_here_is_summarized_and_refuses_the_restore_with_nothing_written(migrated):
    with client(migrated) as c:
        chat, _ = play(c, migrated)
        data = c.get("/v1/archive").content
        before = counts(migrated)
        uid = upload(c, data)
        view = check(c, uid)
        assert view["state"] == "checked" and all(x["here"] for x in view["summary"]["conversations"])
        done = restore(c, uid)
        assert done["state"] == "failed" and "already holds" in done["detail"]
        assert counts(migrated) == before
        assert files_left() == []
        assert sync(c, chat)["status"] == "noop"


def test_an_archive_that_is_not_one_nmos_wrote_is_refused_at_the_check(migrated, database_url_factory, tmp_path):
    with client(migrated) as c:
        play(c, migrated)
        data = c.get("/v1/archive").content
    source = tmp_path / f"a{archive.SUFFIX}"
    source.write_bytes(data)
    cut = rewrite(source, tmp_path / f"cut{archive.SUFFIX}",
                  lambda name, b: b[: len(b) // 2] if name == "tables/source_revision.jsonl" else b)
    target = database_url_factory()
    with client(target) as c:
        before = counts(target)
        for bad in (cut.read_bytes(), b"not a zip at all"):
            uid = upload(c, bad)
            view = check(c, uid)
            assert view["state"] == "refused" and view["detail"], view
            assert c.post(f"/v1/archive/uploads/{uid}/restore").status_code == 409
        assert counts(target) == before
        assert files_left() == []


def test_chunks_come_whole_and_in_order(migrated):
    with client(migrated) as c:
        data = bytes(range(256)) * 600  # 153,600 bytes: two full chunks and a short last one
        uid = c.post("/v1/archive/uploads", json={"bytes": len(data)}).json()["id"]
        first, second, last = data[:SMALL], data[SMALL:2 * SMALL], data[2 * SMALL:]
        assert put(c, uid, 1, second).status_code == 409  # out of order
        changed = c.put(f"/v1/archive/uploads/{uid}/chunks/0",
                        json={"data": base64.b64encode(first).decode(), "sha256": sha(first[:-1] + b"x")})
        assert changed.status_code == 422  # arrived changed
        assert put(c, uid, 0, first[:-1]).status_code == 422  # short, and not the last
        assert put(c, uid, 0, first).json()["received"] == SMALL
        assert put(c, uid, 0, first).json()["received"] == SMALL  # sent again after a lost answer: not written twice
        assert put(c, uid, 1, second).status_code == 200
        assert put(c, uid, 2, last).json()["state"] == "received"
        assert c.post(f"/v1/archive/uploads/{uid}/restore").status_code == 409  # not checked
        assert c.put(f"/v1/archive/uploads/{uid}/chunks/3", json={"data": "!!", "sha256": "0" * 64}).status_code == 422
        assert c.delete(f"/v1/archive/uploads/{uid}").json() == {"discarded": True}
        assert c.get(f"/v1/archive/uploads/{uid}").status_code == 404
        assert files_left() == []


def test_the_routes_need_the_token(migrated):
    with client(migrated) as c:
        del c.headers["Authorization"]
        assert c.post("/v1/archive/uploads", json={"bytes": 10}).status_code == 401


# --- the spool, without a database ------------------------------------------------------------------------------------

def test_an_upload_too_large_or_without_room_is_refused(tmp_path, monkeypatch):
    spool = uploads.Uploads(tmp_path, max_bytes=1000)
    with pytest.raises(uploads.UploadError) as e:
        spool.create(1001)
    assert e.value.status == 413
    monkeypatch.setattr(uploads.shutil, "disk_usage", lambda p: type("U", (), {"free": 1500})())
    with pytest.raises(uploads.UploadError) as e:
        spool.create(800)  # twice its size is needed
    assert e.value.status == 507
    assert list(tmp_path.iterdir()) == []


def test_a_new_upload_replaces_the_others_and_an_old_one_expires(tmp_path):
    now = [0.0]
    spool = uploads.Uploads(tmp_path, max_bytes=10_000, clock=lambda: now[0])
    a = spool.create(10)
    b = spool.create(10)
    assert not a.path.exists() and b.path.exists()
    with pytest.raises(uploads.UploadError):
        spool.get(a.id)
    now[0] = uploads.TTL + 1
    with pytest.raises(uploads.UploadError) as e:
        spool.get(b.id)
    assert e.value.status == 404 and not b.path.exists()


def test_a_finished_or_refused_upload_leaves_no_file(tmp_path):
    spool = uploads.Uploads(tmp_path, max_bytes=10_000)
    up = spool.create(3)
    spool.chunk(up.id, 0, b"abc", sha(b"abc"))
    finished = threading.Event()

    def work(u):
        u.state = "refused"
        finished.set()

    spool.run(up.id, "received", "checking", work)
    assert finished.wait(5)
    for _ in range(100):
        if not up.path.exists():
            break
        time.sleep(0.01)
    assert not up.path.exists() and spool.get(up.id).state == "refused"
