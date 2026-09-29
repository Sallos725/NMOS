"""NMOS Archive restore (Phase 16 step 4, ADR 0050 amendment 1): the same memory back, or nothing written.

Synthetic names only."""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import psycopg
import pytest

from conftest import make_client
from nmos_sidecar import archive
from nmos_sidecar.migrate import apply_migrations
from test_archive import play, read, story
from test_generations import EMB, LLM, conv_id
from test_sidecar_integration import ledger_state, recall, sync
from test_upgrade import restore as restore_dump
from test_vectors import FakeEmbedder

ROOT = Path(__file__).resolve().parents[3]


def client(url: str):
    return make_client(url, embedder=FakeEmbedder(), **LLM, **EMB)


def export_to(tmp_path: Path, url: str, name: str, **kwargs) -> Path:
    path = tmp_path / f"{name}{archive.SUFFIX}"
    archive.export_file(url, str(path), **kwargs)
    return path


def tables(path: Path) -> dict[str, bytes]:
    return read(path.read_bytes())[2]


def replays(url: str, conversations: list[str] | None = None) -> dict[str, bool | None]:
    """Every recorded request's replay: reproduced or not (None when the replay could not compare)."""
    with psycopg.connect(url) as conn:
        ids = [str(r[0]) for r in conn.execute(
            "SELECT id FROM retrieval_trace WHERE %s::uuid[] IS NULL OR conversation_id = ANY(%s::uuid[])"
            " ORDER BY created_at, id", (conversations, conversations)).fetchall()]
    with client(url) as c:
        out = {}
        for i in ids:
            res = c.get(f"/v1/trace/{i}/replay")
            assert res.status_code == 200, res.text
            out[i] = res.json().get("reproduced")
    return out


def counts(url: str) -> dict[str, int]:
    with psycopg.connect(url) as conn:
        return {t.name: conn.execute(f"SELECT count(*) FROM {t.name}").fetchone()[0] for t in archive.TABLES}


def test_the_whole_install_comes_back_the_same(migrated, database_url_factory, tmp_path):
    with client(migrated) as c:
        chat, branch = play(c, migrated)
        assert c.put("/v1/config", json={"recall_top_k": 7}).status_code == 200
    source = export_to(tmp_path, migrated, "a", embeddings=True)
    target = database_url_factory()
    done = archive.restore_file(target, str(source))
    assert {x["host_chat_ref"] for x in done.conversations} == {chat.id, branch.id}
    assert done.renumbered == [] and done.links_cleared == [] and done.migrated == []
    # Row for row: the restored install's archive is the same bytes.
    assert tables(export_to(tmp_path, target, "b", embeddings=True)) == tables(source)
    assert ledger_state(target) == ledger_state(migrated)
    # Every recorded request replays as it did on the source.
    before = replays(migrated)
    assert list(before.values()).count(True) >= 2  # the first request's prefix was edited since: not comparable
    assert replays(target) == before
    # The restored install goes on: the next sync of the chat is a no-op, the derived text and state are there.
    with client(target) as c:
        assert sync(c, chat)["status"] == "noop"
        assert recall(c, chat, "keeper", budget=2000)["packet"]["text"]


def test_one_chat_into_an_install_with_its_own_chats_moves_its_ids(migrated, database_url_factory, tmp_path):
    with client(migrated) as c:
        chat, _ = play(c, migrated)
        cid = conv_id(c, chat)
    source = export_to(tmp_path, migrated, "one", conversations=[cid], embeddings=True)
    target = database_url_factory()
    with client(target) as c:
        play(c, target)  # its own chats: its assertion ids and commit numbers are taken
    before = counts(target)
    done = archive.restore_file(target, str(source))
    assert set(done.renumbered) >= {"assertion", "worldline_commit"}
    after = counts(target)
    for name, rows in read(source.read_bytes())[1].items():
        if name != "projection_generation":
            assert after[name] - before[name] == len(rows), name
    assert replays(target, [cid]) == replays(migrated, [cid])
    assert True in replays(target, [cid]).values()


def test_a_deleted_chat_comes_back_and_its_branch_finds_it_again(migrated, tmp_path):
    with client(migrated) as c:
        chat, branch = play(c, migrated)
        cid, bid = conv_id(c, chat), conv_id(c, branch)
        # With embeddings: a vector embedded again after a restore is newer than every recorded request, so a replay
        # as of one could not use it.
        source = export_to(tmp_path, migrated, "chat", conversations=[cid], embeddings=True)
        before = replays(migrated, [cid])
        assert c.post(f"/v1/conversations/{cid}/delete").status_code == 200
    with psycopg.connect(migrated) as conn:
        assert conn.execute("SELECT branched_from_conversation_id FROM conversation WHERE id = %s",
                            (bid,)).fetchone()[0] is None
    done = archive.restore_file(migrated, str(source))
    assert done.renumbered == []  # its ids were freed by the delete
    assert tables(export_to(tmp_path, migrated, "again", conversations=[cid], embeddings=True)) == tables(source)
    with psycopg.connect(migrated) as conn:
        assert str(conn.execute("SELECT branched_from_conversation_id FROM conversation WHERE id = %s",
                                (bid,)).fetchone()[0]) == cid
    assert replays(migrated, [cid]) == before


def test_a_branch_without_its_origin_keeps_its_host_refs_and_no_link(migrated, database_url_factory, tmp_path):
    with client(migrated) as c:
        _, branch = play(c, migrated)
        bid = conv_id(c, branch)
    source = export_to(tmp_path, migrated, "branch", conversations=[bid])
    target = database_url_factory()
    done = archive.restore_file(target, str(source))
    assert done.links_cleared == [bid]
    with psycopg.connect(target) as conn:
        link, ref, msg = conn.execute("SELECT branched_from_conversation_id, branched_from_host_chat_ref,"
                                      " branched_from_message_ref FROM conversation WHERE id = %s", (bid,)).fetchone()
    assert link is None and ref and msg


def rewrite(path: Path, out: Path, change) -> Path:
    """A copy of the archive with `change(name, data)` applied to each entry (None drops it)."""
    with zipfile.ZipFile(path) as src, zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as dst:
        for name in src.namelist():
            data = change(name, src.read(name))
            if data is not None:
                dst.writestr(name, data)
    return out


def test_a_changed_cut_or_padded_archive_is_refused_before_anything_is_written(migrated, database_url_factory,
                                                                              tmp_path):
    with client(migrated) as c:
        play(c, migrated)
    source = export_to(tmp_path, migrated, "a")
    target = database_url_factory()

    def edited(name, data):
        return data.replace(b"Hana", b"Hanb", 1) if name == "tables/source_revision.jsonl" else data

    def cut(name, data):
        return data[: data.rstrip(b"\n").rfind(b"\n") + 1] if name == "tables/assertion.jsonl" else data

    def manifest(change):
        def apply(name, data):
            if name != "manifest.json":
                return data
            m = json.loads(data)
            change(m)
            return json.dumps(m).encode()
        return apply

    def newer(m):
        m["schema"]["migrations"].append({"version": "9999_future.sql", "checksum": "0" * 64})
        m["schema"]["level"] = "9999_future.sql"

    def other(m):
        m["schema"]["migrations"][0]["checksum"] = "0" * 64

    def listed(m):
        m["files"] = [f for f in m["files"] if f["table"] != "owner_repair"]

    cases = {
        "edited": (edited, "changed or cut"),
        "cut": (cut, "bytes; the manifest says|changed or cut"),
        "extra": (lambda n, d: d if n != "manifest.json" else d, None),
        "newer": (manifest(newer), "newer NMOS"),
        "other": (manifest(other), "differ from this NMOS"),
        "unlisted": (manifest(listed), "differ from its manifest"),
        "format": (manifest(lambda m: m.update(format_version=2)), "archive format 2"),
    }
    for label, (change, message) in cases.items():
        if message is None:
            continue
        bad = rewrite(source, tmp_path / f"{label}{archive.SUFFIX}", change)
        with pytest.raises(archive.ArchiveError, match=message):
            archive.restore_file(target, str(bad))
    with zipfile.ZipFile(tmp_path / f"extra{archive.SUFFIX}", "w") as zf, zipfile.ZipFile(source) as src:
        for name in src.namelist():
            zf.writestr(name, src.read(name))
        zf.writestr("tables/job.jsonl", b"")
    with pytest.raises(archive.ArchiveError, match="differ from its manifest"):
        archive.restore_file(target, str(tmp_path / f"extra{archive.SUFFIX}"))
    (tmp_path / "junk.nmos.zip").write_bytes(b"not a zip")
    with pytest.raises(archive.ArchiveError, match="not a readable archive"):
        archive.restore_file(target, str(tmp_path / "junk.nmos.zip"))
    assert set(counts(target).values()) == {0}


def test_a_chat_already_here_is_refused_whole(migrated, database_url_factory, tmp_path):
    with client(migrated) as c:
        chat, _ = play(c, migrated)
    source = export_to(tmp_path, migrated, "a")
    target = database_url_factory()
    with client(target) as c:
        sync(c, chat)  # the same host chat, synced here on its own
        other = story()
        sync(c, other)
    before = counts(target)
    with pytest.raises(archive.ArchiveError, match=f"already holds .*{chat.id}"):
        archive.restore_file(target, str(source))
    assert counts(target) == before
    with pytest.raises(archive.ArchiveError, match="already holds"):
        archive.restore_file(migrated, str(source))  # into itself


def test_an_archive_of_an_older_schema_is_migrated_as_an_upgrade_would(database_url, database_url_factory, tmp_path):
    """Phase 13 `main` (migrations to 0024): exported at its own level, restored here, the same as that database
    upgraded in place (PHASE-16 Q5)."""
    dump = ROOT / "fixtures/upgrade/main-phase13.sql"
    restore_dump(database_url, dump)
    old = export_to(tmp_path, database_url, "old", embeddings=True)
    level = read(old.read_bytes())[0]["schema"]["level"]
    assert level < max(p.name for p in (ROOT / "migrations").glob("[0-9][0-9][0-9][0-9]_*.sql"))
    assert "canon_manifest" not in read(old.read_bytes())[1]
    target = database_url_factory()
    done = archive.restore_file(target, str(old))
    assert done.migrated and done.migrated[0] > level
    apply_migrations(database_url)  # the same database, upgraded in place
    assert tables(export_to(tmp_path, target, "t", embeddings=True)) == \
        tables(export_to(tmp_path, database_url, "u", embeddings=True))
    assert replays(target) == replays(database_url)


def test_the_command_checks_restores_and_refuses(migrated, database_url_factory, tmp_path, monkeypatch, capsys):
    with client(migrated) as c:
        play(c, migrated)
    source = export_to(tmp_path, migrated, "a")
    target = database_url_factory()
    monkeypatch.setenv("NMOS_DATABASE_URL", target)
    assert archive.main(["restore", "--check", str(source)]) == 0
    assert set(counts(target).values()) == {0}
    monkeypatch.setattr("sys.stdin", io.TextIOWrapper(io.BytesIO(source.read_bytes())))
    assert archive.main(["restore", "-"]) == 0
    assert "restored" in capsys.readouterr().err
    assert tables(export_to(tmp_path, target, "b")) == tables(source)
    assert archive.main(["restore", str(source)]) == 2
    assert "already holds" in capsys.readouterr().err


def test_settings_already_chosen_here_stay(migrated, database_url_factory, tmp_path):
    with client(migrated) as c:
        assert c.put("/v1/config", json={"recall_top_k": 7, "facts_limit": 9}).status_code == 200
        sync(c, story())
    source = export_to(tmp_path, migrated, "a")
    target = database_url_factory()
    with client(target) as c:
        assert c.put("/v1/config", json={"recall_top_k": 3}).status_code == 200
    done = archive.restore_file(target, str(source))
    assert done.settings_kept == ["recall_top_k"]
    with client(target) as c:
        recall = c.get("/v1/config").json()["recall"]
    assert recall["top_k"] == 3 and recall["facts_limit"] == 9


def reseal(path: Path, out: Path, table: str, change) -> Path:
    """A copy whose `table` rows went through `change(row)`, with the manifest's size, rows and hash made to match:
    an archive that passes every file check but was not written by NMOS's export."""
    import hashlib
    with zipfile.ZipFile(path) as src:
        manifest = json.loads(src.read("manifest.json"))
        data = {n: src.read(n) for n in src.namelist() if n != "manifest.json"}
    rows = [change(json.loads(x)) for x in data[f"tables/{table}.jsonl"].splitlines()]
    body = b"".join(json.dumps(r).encode() + b"\n" for r in rows)
    data[f"tables/{table}.jsonl"] = body
    for f in manifest["files"]:
        if f["table"] == table:
            f.update(bytes=len(body), rows=len(rows), sha256=hashlib.sha256(body).hexdigest())
    with zipfile.ZipFile(out, "w") as dst:
        for n, b in data.items():
            dst.writestr(n, b)
        dst.writestr("manifest.json", json.dumps(manifest))
    return out


def test_rows_that_name_a_chat_outside_the_archive_are_refused(migrated, database_url_factory, tmp_path):
    with client(migrated) as c:
        chat, _ = play(c, migrated)
        cid = conv_id(c, chat)
    source = export_to(tmp_path, migrated, "one", conversations=[cid])
    target = database_url_factory()
    with client(target) as c:
        other = story()
        sync(c, other)
        victim = conv_id(c, other)
    before = counts(target)
    for table in ("source_object", "retrieval_trace", "owner_repair", "canon_applied"):
        forged = reseal(source, tmp_path / f"forged-{table}{archive.SUFFIX}", table,
                        lambda r: {**r, "conversation_id": victim})
        with pytest.raises(archive.ArchiveError, match="does not hold"):
            archive.restore_file(target, str(forged))
    assert counts(target) == before
