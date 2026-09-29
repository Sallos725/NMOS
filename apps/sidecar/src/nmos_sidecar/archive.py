"""NMOS Archive (ADR 0050): the whole install, or chosen conversations, in one `.nmos.zip`.

An archive is a zip of JSON Lines files, one per table (`tables/<table>.jsonl`, one row per line as named columns,
written by PostgreSQL's `row_to_json` so timestamps, numbers inside jsonb and vectors come out exactly as stored) and a
`manifest.json` last: the format version, the NMOS version, the schema's migrations, what the archive holds and each
file's row count, size and SHA-256. It is readable without NMOS and does not depend on PostgreSQL's dump format.

What goes in (PHASE-16 Q1): always the source ledger, canon, the owner's input, the recorded requests and the
generations they name, and for the whole install the settings without secrets; by default the model's work
(extractions and assertions, summaries, canon reads); embeddings only when asked. Never jobs, derived text
(`revision_text`, `state_observation`), API keys or the auth token.

    python -m nmos_sidecar.archive export [--conversation ID ...] [--no-projections] [--embeddings] [-o FILE]
    python -m nmos_sidecar.archive restore [--check] FILE|-
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import IO, Any, Iterable
from urllib.parse import urlsplit
from uuid import UUID

import psycopg
from psycopg.rows import tuple_row

from . import __version__, runtime
from .config import Settings

FORMAT = "nmos-archive"
FORMAT_VERSION = 1
SUFFIX = ".nmos.zip"

# Rows of the chosen conversations: %(c)s is the uuid[] of those conversations.
_REVS = ("SELECT sr.id FROM source_revision sr JOIN source_object so ON so.id = sr.source_object_id"
         " WHERE so.conversation_id = ANY(%(c)s)")
_COMMITS = "SELECT id FROM worldline_commit WHERE conversation_id = ANY(%(c)s)"


@dataclass(frozen=True)
class Table:
    name: str
    part: str  # 'ledger' (always), 'projections' (default), 'embeddings' (optional), 'settings' (whole install)
    where: str  # rows of the chosen conversations ('' for global tables)
    order: str  # a total order, so the same state gives the same file


# In an order a restore can insert them in (parents first; ADR 0050 §4).
TABLES: tuple[Table, ...] = (
    Table("projection_generation", "ledger", "", "key"),
    Table("app_config", "settings", "", "key"),
    Table("conversation", "ledger", "id = ANY(%(c)s)", "created_at, id"),
    Table("host_observation", "ledger", "conversation_id = ANY(%(c)s)", "conversation_id, observed_at, id"),
    Table("observation_base", "ledger", "conversation_id = ANY(%(c)s)", "observation_id"),
    Table("source_object", "ledger", "conversation_id = ANY(%(c)s)", "conversation_id, id"),
    Table("source_revision", "ledger", f"id IN ({_REVS})", "recorded_at, id"),
    Table("worldline_commit", "ledger", "conversation_id = ANY(%(c)s)", "seq"),
    Table("worldline_append", "ledger", f"commit_id IN ({_COMMITS})", "seq"),
    Table("active_membership", "ledger", f"commit_id IN ({_COMMITS})", "commit_id, position"),
    Table("canon_manifest", "ledger", "conversation_id = ANY(%(c)s)", "conversation_id, id"),
    Table("canon_applied", "ledger", "conversation_id = ANY(%(c)s)",
          "conversation_id, applied_at, manifest_id, observed_at"),
    Table("entity_link", "ledger", "conversation_id = ANY(%(c)s)", "conversation_id, created_at, id"),
    Table("owner_repair", "ledger", "conversation_id = ANY(%(c)s)", "conversation_id, created_at, id"),
    Table("extraction", "projections", f"source_revision_id IN ({_REVS})", "created_at, id"),
    Table("assertion", "projections", f"source_revision_id IN ({_REVS})", "id"),
    Table("summary", "projections", "conversation_id = ANY(%(c)s)", "created_at, id"),
    Table("revision_embedding", "embeddings", f"source_revision_id IN ({_REVS})",
          "source_revision_id, projection, chunk"),
    Table("retrieval_trace", "ledger", "conversation_id = ANY(%(c)s)", "created_at, id"),
)
# Never archived: rebuilt or recomputed from what is (ADR 0050 §2).
NEVER = ("job", "revision_text", "state_observation", "schema_migrations")
# Settings an archive may hold: the editable ones but the keys (K21), and the parser rules.
SETTINGS = tuple(sorted(set(runtime.EDITABLE) - runtime.SECRET)) + (runtime.PARSERS_KEY,)
URL_SETTINGS = ("llm_url", "embed_url")
# A credential shorter than this is not looked for: a key of one or two characters would refuse nearly every chat.
MIN_SECRET = 4


class ArchiveError(Exception):
    """An archive that cannot be written (or read) as asked; the message says why."""


class NoSuchConversation(ArchiveError):
    """A chosen conversation is not in this install."""


@dataclass
class Written:
    path: str
    table: str
    rows: int = 0
    bytes: int = 0
    sha256: str = ""


@dataclass
class Export:
    manifest: dict[str, Any]
    files: list[Written] = field(default_factory=list)


def _q(conn: psycopg.Connection, sql: str, params: Any = None) -> list[tuple[Any, ...]]:
    """Rows as tuples, whatever the connection's row factory (the API's pool gives dicts)."""
    with conn.cursor(row_factory=tuple_row) as cur:
        return cur.execute(sql, params).fetchall()


def _url_has_secret(url: str) -> bool:
    """A URL that may carry a credential: a user or password in it, a query string (`?key=`) or a fragment."""
    parts = urlsplit(url.strip())
    return parts.username is not None or parts.password is not None or bool(parts.query) or bool(parts.fragment)


def _secrets(conn: psycopg.Connection, settings: Settings | list[Settings] | None) -> list[str]:
    """Every credential NMOS holds (saved keys, the environment's keys, the auth token), to refuse an archive that
    would carry one anywhere (K21). A service-account key also counts by its private key alone."""
    out: set[str] = set()
    for (value,) in _q(conn, "SELECT value FROM app_config WHERE key = ANY(%s)", (sorted(runtime.SECRET),)):
        if isinstance(value, str):
            out.add(value)
    for s in ([settings] if isinstance(settings, Settings) else settings or []):
        out.update(v for v in (s.llm_api_key, s.embed_api_key, s.auth_token) if v)
    for value in list(out):
        try:
            key = json.loads(value)
        except ValueError:
            continue
        if isinstance(key, dict) and isinstance(key.get("private_key"), str):
            out.add(key["private_key"])
            out.update(line for line in key["private_key"].splitlines() if len(line) >= 16 and "-----" not in line)
    return sorted(s for s in out if len(s.strip()) >= MIN_SECRET)


def _strings(value: Any) -> Iterable[str]:
    """Every string in a decoded JSON value, object keys included."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for k, v in value.items():
            yield k
            yield from _strings(v)
    elif isinstance(value, list):
        for v in value:
            yield from _strings(v)


def _holds(line: str, secrets: list[str]) -> bool:
    """A row (JSON text) holds a credential: checked on its decoded strings, so an escaped quote or backslash in a
    key still matches."""
    return bool(secrets) and any(s in text for text in _strings(json.loads(line)) for s in secrets)


def _conversations(conn: psycopg.Connection, wanted: list[str] | None) -> list[UUID]:
    if wanted is None:
        return [r[0] for r in _q(conn, "SELECT id FROM conversation ORDER BY created_at, id")]
    ids: list[UUID] = []
    for raw in wanted:
        try:
            ids.append(UUID(str(raw)))
        except ValueError:
            raise ArchiveError(f"not a conversation id: {raw!r}") from None
    found = {r[0] for r in _q(conn, "SELECT id FROM conversation WHERE id = ANY(%s)", (ids,))}
    missing = [str(i) for i in ids if i not in found]
    if missing:
        raise NoSuchConversation(f"no such conversation: {', '.join(missing)}")
    return list(dict.fromkeys(ids))


def _lines(conn: psycopg.Connection, table: Table, convs: list[UUID]) -> Iterable[str]:
    """The table's rows as JSON text, one per row, from PostgreSQL (`row_to_json`: column order kept, jsonb values
    as stored, timestamps in UTC with microseconds, vectors as their text)."""
    where = f" WHERE {table.where}" if table.where else ""
    if table.name == "app_config":
        where = " WHERE key = ANY(%(settings)s)"
    sql = f"SELECT row_to_json(t)::text FROM (SELECT * FROM {table.name}{where} ORDER BY {table.order}) t"
    with conn.cursor(name=f"archive_{table.name}", row_factory=tuple_row) as cur:
        cur.itersize = 500
        cur.execute(sql, {"c": convs, "settings": list(SETTINGS)})
        for (line,) in cur:
            yield line


def _setting_line(line: str) -> str | None:
    """A settings row as archived: an endpoint URL that may carry a credential is left out (ADR 0050 §3)."""
    row = json.loads(line)
    if row["key"] in URL_SETTINGS and isinstance(row["value"], str) and _url_has_secret(row["value"]):
        return None
    return line


def write_archive(conn: psycopg.Connection, out: IO[bytes], conversations: list[str] | None = None,
                  projections: bool = True, embeddings: bool = False,
                  settings: Settings | list[Settings] | None = None) -> Export:
    """Write an archive to `out` (a binary file) from one consistent, read-only snapshot. `conversations` None is
    the whole install (every conversation and the settings); a list is those conversations only. Raises
    ArchiveError, with nothing useful written, when a chosen conversation is missing or a credential would be
    archived. `settings`: every Settings whose credentials to look for (the environment's and the effective ones: a key
    saved in the panel replaces the environment's in the effective settings, and either may be in a chat). `conn` must
    not be in a transaction."""
    parts = {"ledger", "settings" if conversations is None else "", "projections" if projections else "",
             "embeddings" if embeddings else ""}
    with conn.transaction():
        conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        conn.execute("SET LOCAL TimeZone = 'UTC'")
        conn.execute("SET LOCAL extra_float_digits = 1")  # the shortest text that reads back exactly
        migrations = [{"version": v, "checksum": c}
                      for v, c in _q(conn, "SELECT version, checksum FROM schema_migrations ORDER BY version")]
        if not migrations:
            raise ArchiveError("the database has no applied migrations")
        convs = _conversations(conn, conversations)
        secrets = _secrets(conn, settings)
        for (endpoint,) in _q(conn, "SELECT endpoint FROM projection_generation"):
            where = urlsplit(endpoint)
            if where.username is not None or where.password is not None:
                raise ArchiveError("a generation's endpoint holds a user or password; an archive never holds one (K21)")
        labels = _q(conn, "SELECT id, host, host_chat_ref, host_character_name, host_chat_name,"
                          " branched_from_conversation_id FROM conversation WHERE id = ANY(%s) ORDER BY created_at, id",
                    (convs,))
        latest = dict(_q(conn, "SELECT DISTINCT ON (kind) kind, key FROM projection_generation"
                               " ORDER BY kind, activated_at DESC, key"))
        export = Export(manifest={})
        omitted: list[str] = []
        with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
            for table in TABLES:
                if table.part not in parts or _q(conn, "SELECT to_regclass(%s::text)", (table.name,))[0][0] is None:
                    continue  # not asked for, or not yet in this schema (an older NMOS: its level says so)
                written = Written(path=f"tables/{table.name}.jsonl", table=table.name)
                digest = hashlib.sha256()
                with zf.open(written.path, "w", force_zip64=True) as f:
                    for line in _lines(conn, table, convs):
                        if table.name == "app_config":
                            kept = _setting_line(line)
                            if kept is None:
                                omitted.append(json.loads(line)["key"])
                                continue
                            line = kept
                        if _holds(line, secrets):
                            raise ArchiveError(f"a row of {table.name} holds a credential NMOS keeps; an archive never"
                                               " holds one (K21)")
                        data = line.encode("utf-8") + b"\n"
                        f.write(data)
                        digest.update(data)
                        written.rows += 1
                        written.bytes += len(data)
                written.sha256 = digest.hexdigest()
                export.files.append(written)
            export.manifest = {
                "format": FORMAT,
                "format_version": FORMAT_VERSION,
                "nmos_version": __version__,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "scope": "install" if conversations is None else "conversations",
                "contents": {"ledger": True, "settings": "settings" in parts, "projections": projections,
                             "embeddings": embeddings},
                "schema": {"level": migrations[-1]["version"], "migrations": migrations},
                "generations": latest,
                "conversations": [{"id": str(r[0]), "host": r[1], "host_chat_ref": r[2], "character": r[3],
                                   "chat": r[4], "branched_from": str(r[5]) if r[5] else None} for r in labels],
                "omitted_settings": sorted(omitted),
                "files": [{"path": w.path, "table": w.table, "rows": w.rows, "bytes": w.bytes, "sha256": w.sha256}
                          for w in export.files],
            }
            if any(s in t for t in _strings(export.manifest) for s in secrets):  # a chat or character named after a key
                raise ArchiveError("the manifest holds a credential NMOS keeps; an archive never holds one (K21)")
            zf.writestr("manifest.json", json.dumps(export.manifest, ensure_ascii=False, indent=2) + "\n")
    return export


def export_file(database_url: str, path: str, **kwargs: Any) -> Export:
    """`write_archive` into `path`, written beside it first and moved into place only when complete."""
    directory = os.path.dirname(os.path.abspath(path))
    fd, tmp = tempfile.mkstemp(prefix=".nmos-archive-", suffix=".part", dir=directory)
    try:
        with os.fdopen(fd, "wb") as f, psycopg.connect(database_url) as conn:
            result = write_archive(conn, f, **kwargs)
        os.replace(tmp, path)
        return result
    except BaseException:
        os.unlink(tmp)
        raise


def default_name(conversations: int | None, when: datetime | None = None) -> str:
    """`nmos-all-<UTC time>.nmos.zip` for the whole install, `nmos-<n>-chat-…` for chosen conversations."""
    stamp = (when or datetime.now(timezone.utc)).strftime("%Y%m%d-%H%M%S")
    scope = "all" if conversations is None else f"{conversations}-chat"
    return f"nmos-{scope}-{stamp}{SUFFIX}"


# --- restore (Phase 16 step 4; ADR 0050 amendment 1) ----------------------------------------------------------------

KNOWN = {t.name for t in TABLES}
# Rows whose ids come from a sequence shared by every conversation: kept when free in the install, else moved past
# its largest id with their order kept (and the assertion ids a recorded request's lines name moved with them).
SEQUENCED = {"assertion": "id", "worldline_commit": "seq", "worldline_append": "seq"}
# Rows that belong to no conversation: the install's own row wins (the same key is the same generation; settings
# already chosen stay).
GLOBAL = {"projection_generation": "key", "app_config": "key"}
BATCH = 500


@dataclass
class Checked:
    """An archive whose manifest, files, sizes, row counts and hashes were all verified."""
    path: str
    manifest: dict[str, Any]
    files: dict[str, dict[str, Any]]  # table -> manifest entry


@dataclass
class Restored:
    conversations: list[dict[str, Any]]
    rows: dict[str, int]
    renumbered: list[str]
    settings_kept: list[str]
    links_cleared: list[str]
    migrated: list[str]


def _bundled() -> list[tuple[str, str]]:
    from .migrate import migration_files
    return [(f.name, hashlib.sha256(f.read_text(encoding="utf-8").encode("utf-8")).hexdigest())
            for f in migration_files()]


MANIFEST_MAX = 4 * 1024 * 1024  # a manifest is a few kilobytes; more is not one NMOS wrote
SHA256 = frozenset("0123456789abcdef")


def _entries(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """The manifest's files by table, each checked for its shape; the ledger's tables must be there."""
    files: dict[str, dict[str, Any]] = {}
    listed = manifest.get("files")
    if not isinstance(listed, list):
        raise ArchiveError("the manifest lists no files")
    for f in listed:
        table = f.get("table") if isinstance(f, dict) else None
        if (table not in KNOWN or f.get("path") != f"tables/{table}.jsonl" or table in files
                or not isinstance(f.get("rows"), int) or not isinstance(f.get("bytes"), int)
                or f["rows"] < 0 or f["bytes"] < 0 or not isinstance(f.get("sha256"), str)
                or len(f["sha256"]) != 64 or not set(f["sha256"]) <= SHA256):
            raise ArchiveError(f"the manifest lists an unexpected file: {f!r:.120}")
        files[table] = f
    for table in ("conversation", "source_object", "source_revision", "worldline_commit", "projection_generation"):
        if table not in files:
            raise ArchiveError(f"the archive has no {table} file; it was not made by NMOS's export")
    return files


def check_archive(path: str) -> Checked:
    """Verify an archive before anything is written: its manifest, that it holds exactly the files listed (no
    duplicate, no encrypted member), and each file's size, row count and SHA-256. Refuses an archive from a newer
    NMOS or with other migrations (Q5). A restore checks each file's hash again as it loads it."""
    try:
        zf = zipfile.ZipFile(path)
    except (OSError, zipfile.BadZipFile) as error:
        raise ArchiveError(f"not a readable archive: {error}") from None
    with zf:
        infos = zf.infolist()
        names = [i.filename for i in infos]
        if len(names) != len(set(names)):
            raise ArchiveError("the archive holds a file twice")
        if any(i.flag_bits & 0x1 for i in infos):
            raise ArchiveError("the archive holds an encrypted file")
        if "manifest.json" not in names:
            raise ArchiveError("the archive has no manifest.json")
        if zf.getinfo("manifest.json").file_size > MANIFEST_MAX:
            raise ArchiveError("the archive's manifest is too large to be NMOS's")
        try:
            manifest = json.loads(zf.read("manifest.json"))
        except (ValueError, zipfile.BadZipFile, EOFError, OSError) as error:
            raise ArchiveError(f"the archive's manifest cannot be read: {error}") from None
        if not isinstance(manifest, dict) or manifest.get("format") != FORMAT:
            raise ArchiveError("not an NMOS archive")
        if manifest.get("format_version") != FORMAT_VERSION:
            raise ArchiveError(f"archive format {manifest.get('format_version')!r}; this NMOS reads {FORMAT_VERSION}")
        files = _entries(manifest)
        if set(names) != {f["path"] for f in files.values()} | {"manifest.json"}:
            extra = sorted(set(names) - {f["path"] for f in files.values()} - {"manifest.json"})
            missing = sorted({f["path"] for f in files.values()} - set(names))
            raise ArchiveError(f"the archive's files differ from its manifest (extra {extra}, missing {missing})")
        for f in files.values():
            if zf.getinfo(f["path"]).file_size != f["bytes"]:
                raise ArchiveError(f"{f['path']} is {zf.getinfo(f['path']).file_size} bytes; the manifest says {f['bytes']}")
            for _ in _rows(zf, f):
                pass
    schema = manifest.get("schema") if isinstance(manifest.get("schema"), dict) else {}
    raw = schema.get("migrations") if isinstance(schema.get("migrations"), list) else []
    migrations = [(m.get("version"), m.get("checksum")) if isinstance(m, dict) else (None, None) for m in raw]
    if not migrations or schema.get("level") != migrations[-1][0]:
        raise ArchiveError("the manifest names no schema, or a level that is not its last migration")
    bundled = _bundled()
    if len(migrations) > len(bundled) or migrations != bundled[:len(migrations)]:
        newer = [v for v, _ in migrations if v not in {b for b, _ in bundled}]
        if newer:
            raise ArchiveError(f"the archive was made by a newer NMOS (schema {migrations[-1][0]}); upgrade NMOS first")
        raise ArchiveError("the archive's migrations differ from this NMOS's; it was not made by a release of it")
    conversations = manifest.get("conversations")
    if not isinstance(conversations, list) or len(conversations) != files["conversation"]["rows"]:
        raise ArchiveError("the manifest's conversations differ from its conversation file")
    return Checked(path=path, manifest=manifest, files=files)


def _rows(zf: zipfile.ZipFile, entry: dict[str, Any]) -> Iterable[list[str]]:
    """A file's rows in batches, its size, row count and SHA-256 checked against the manifest as it is read: the
    archive's last batch is given only once the whole file matched (so a file replaced after the check is refused
    too, with the transaction)."""
    batch: list[str] = []
    digest, rows, size = hashlib.sha256(), 0, 0
    try:
        with zf.open(entry["path"]) as fh:
            for line in fh:
                size += len(line)
                if size > entry["bytes"]:
                    raise ArchiveError(f"{entry['path']} is longer than the manifest says")
                digest.update(line)
                rows += 1
                batch.append(line.decode("utf-8").rstrip("\n"))
                if len(batch) >= BATCH:
                    yield batch
                    batch = []
    except (zipfile.BadZipFile, EOFError, OSError, UnicodeDecodeError, ValueError) as error:
        raise ArchiveError(f"{entry['path']} cannot be read: {error}") from None
    if digest.hexdigest() != entry["sha256"] or rows != entry["rows"] or size != entry["bytes"]:
        raise ArchiveError(f"{entry['path']} was changed or cut: its hash or row count differs from the manifest")
    if batch:
        yield batch


def _columns(conn: psycopg.Connection, schema: str, table: str) -> list[str]:
    return [r[0] for r in _q(conn, "SELECT attname FROM pg_attribute WHERE attrelid = format('%%I.%%I', %s::text, %s::text)::regclass"
                                   " AND attnum > 0 AND NOT attisdropped ORDER BY attnum", (schema, table))]


def restore_archive(database_url: str, checked: Checked) -> Restored:
    """Restore a checked archive into this install, in one transaction: refused whole if any of its conversations
    (by id or host chat) is here already. The archive's schema level is created in a scratch schema from the bundled
    migrations, the rows loaded there as they were written, the later migrations applied to them, and the result
    copied in, ids and timestamps kept (ADR 0050 amendment 1). Migrates this install first."""
    from .migrate import apply_migrations, migration_files
    apply_migrations(database_url)
    manifest = checked.manifest
    level = manifest["schema"]["level"]
    files = migration_files()
    before = [f for f in files if f.name <= level]
    after = [f for f in files if f.name > level]
    scratch = f"nmos_restore_{os.urandom(6).hex()}"
    out = Restored(conversations=manifest.get("conversations") or [], rows={}, renumbered=[], settings_kept=[],
                   links_cleared=[], migrated=[f.name for f in after])
    try:
        with psycopg.connect(database_url, row_factory=tuple_row) as conn, zipfile.ZipFile(checked.path) as zf:
            with conn.transaction():
                _restore_in(conn, zf, checked, scratch, before, after, out)
    except psycopg.Error as error:
        raise ArchiveError(f"the archive's rows could not be restored here; none were written: {error}") from None
    return out


def _restore_in(conn: psycopg.Connection, zf: zipfile.ZipFile, checked: Checked, scratch: str, before: list,
                after: list, out: Restored) -> None:
    conn.execute("SELECT pg_advisory_xact_lock(727003)")
    conn.execute("SET LOCAL TimeZone = 'UTC'")
    # The archive's schema, in a scratch schema: tables as its NMOS made them, without foreign keys.
    conn.execute(f'CREATE SCHEMA "{scratch}"')
    conn.execute(f'SET LOCAL search_path = "{scratch}", public')
    for f in before:
        conn.execute(f.read_text(encoding="utf-8"))
    for table, name in _q(conn, "SELECT c.conrelid::regclass::text, c.conname FROM pg_constraint c"
                                " JOIN pg_namespace n ON n.oid = c.connamespace"
                                " WHERE n.nspname = %s AND c.contype = 'f'", (scratch,)):
        conn.execute(f'ALTER TABLE {table} DROP CONSTRAINT "{name}"')
    for table, entry in checked.files.items():
        for batch in _rows(zf, entry):
            conn.execute(f'INSERT INTO "{scratch}".{table} OVERRIDING SYSTEM VALUE'
                         f' SELECT * FROM json_populate_recordset(NULL::"{scratch}".{table}, %s::json)',
                         ("[" + ",".join(batch) + "]",))
    for f in after:  # the upgrade those rows would have had (Q5)
        conn.execute(f.read_text(encoding="utf-8"))
    conn.execute("SET LOCAL search_path = public")
    _self_contained(conn, scratch)
    out.conversations = [
        {"id": r[0], "host": r[1], "host_chat_ref": r[2], "character": r[3], "chat": r[4]}
        for r in _q(conn, f'SELECT id::text, host, host_chat_ref, host_character_name, host_chat_name'
                          f' FROM "{scratch}".conversation ORDER BY created_at, id')]
    # Refused whole when a conversation is here already (Q4: never merged).
    present = _q(conn, f'SELECT c.host, c.host_chat_ref FROM public.conversation c'
                       f' JOIN "{scratch}".conversation s ON s.id = c.id'
                       f' OR (s.host = c.host AND s.host_chat_ref = c.host_chat_ref)')
    if present:
        raise ArchiveError("this install already holds " + ", ".join(f"{h} chat {r}" for h, r in present)
                           + "; delete it there first to restore it (restores never merge)")
    _make_room(conn, scratch, out)
    _copy_in(conn, scratch, checked, out)
    conn.execute(f'DROP SCHEMA "{scratch}" CASCADE')


def _self_contained(conn: psycopg.Connection, scratch: str) -> None:
    """Every reference of an archived row stays inside the archive, so a restore can add rows to no conversation that
    is here: each single-column foreign key of this install's tables, checked on the scratch rows (generations,
    rows of no conversation, may be here instead; a branch's origin is resolved later)."""
    fks = _q(conn, """
        SELECT cl.relname, a.attname, rf.relname, af.attname
        FROM pg_constraint c
        JOIN pg_class cl ON cl.oid = c.conrelid JOIN pg_namespace n ON n.oid = cl.relnamespace
        JOIN pg_class rf ON rf.oid = c.confrelid
        JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = c.conkey[1]
        JOIN pg_attribute af ON af.attrelid = c.confrelid AND af.attnum = c.confkey[1]
        WHERE c.contype = 'f' AND n.nspname = 'public' AND cardinality(c.conkey) = 1 ORDER BY 1, 2""")
    for table, col, ref, ref_col in fks:
        if table not in KNOWN or ref in GLOBAL or (table, col) == ("conversation", "branched_from_conversation_id"):
            continue
        if _q(conn, "SELECT to_regclass(%s::text)", (f'"{scratch}".{table}',))[0][0] is None:
            continue
        stray = _q(conn, f'SELECT count(*) FROM "{scratch}".{table} t WHERE t."{col}" IS NOT NULL AND NOT EXISTS'
                         f' (SELECT 1 FROM "{scratch}".{ref} r WHERE r."{ref_col}" = t."{col}")')[0][0]
        if stray:
            raise ArchiveError(f"{stray} row(s) of {table} name a {ref} the archive does not hold; it was not made by"
                               " NMOS's export")
    # A commit's parents: earlier commits of its own conversation, in the archive (ledger.py: the head it followed).
    stray = _q(conn, f'SELECT count(*) FROM "{scratch}".worldline_commit w, unnest(w.parent_commit_ids) p(id)'
                     f' WHERE NOT EXISTS (SELECT 1 FROM "{scratch}".worldline_commit x'
                     f' WHERE x.id = p.id AND x.conversation_id = w.conversation_id)')[0][0]
    if stray:
        raise ArchiveError(f"{stray} commit parent(s) are not commits of the same conversation in the archive")
    # Conversation-scoped tables without a foreign key.
    for table in ("observation_base", "canon_applied"):
        if _q(conn, "SELECT to_regclass(%s::text)", (f'"{scratch}".{table}',))[0][0] is None:
            continue
        stray = _q(conn, f'SELECT count(*) FROM "{scratch}".{table} t WHERE NOT EXISTS'
                         f' (SELECT 1 FROM "{scratch}".conversation c WHERE c.id = t.conversation_id)')[0][0]
        if stray:
            raise ArchiveError(f"{stray} row(s) of {table} name a conversation the archive does not hold")


def _make_room(conn: psycopg.Connection, scratch: str, out: Restored) -> None:
    """Keep each sequenced id when no row here has it; else move the archive's ids past this install's largest,
    order kept, and move the assertion ids recorded requests name with them."""
    for table, col in SEQUENCED.items():
        clash = _q(conn, f'SELECT EXISTS (SELECT 1 FROM public.{table} p JOIN "{scratch}".{table} s USING ({col}))')[0][0]
        if not clash:
            continue
        shift = _q(conn, f'SELECT greatest((SELECT max({col}) FROM public.{table}),'
                         f' (SELECT max({col}) FROM "{scratch}".{table}))')[0][0]
        conn.execute(f'ALTER TABLE "{scratch}".{table} ALTER COLUMN {col} DROP IDENTITY IF EXISTS')  # scratch only
        conn.execute(f'UPDATE "{scratch}".{table} SET {col} = {col} + %s', (shift,))
        out.renumbered.append(table)
        if table == "assertion":
            conn.execute(f"""
                UPDATE "{scratch}".retrieval_trace t SET lines = (
                    SELECT jsonb_agg(
                        CASE WHEN jsonb_typeof(l) <> 'object' THEN l ELSE (
                            SELECT jsonb_object_agg(k, CASE
                                WHEN k IN ('ref', 'restates', 'repeats') AND jsonb_typeof(v) = 'object'
                                     AND jsonb_typeof(v->'assertion') = 'number' AND (v->>'assertion')::bigint > 0
                                THEN jsonb_set(v, '{{assertion}}', to_jsonb((v->>'assertion')::bigint + %(shift)s))
                                ELSE v END)
                            FROM jsonb_each(l) AS e(k, v)) END
                        ORDER BY i)
                    FROM jsonb_array_elements(t.lines) WITH ORDINALITY AS a(l, i))
                WHERE jsonb_typeof(t.lines) = 'array' AND jsonb_array_length(t.lines) > 0""", {"shift": shift})


def _copy_in(conn: psycopg.Connection, scratch: str, checked: Checked, out: Restored) -> None:
    """Copy the scratch rows into this install, parents first, then link heads and branches."""
    for table in [t.name for t in TABLES]:
        if _q(conn, "SELECT to_regclass(%s::text)", (f'"{scratch}".{table}',))[0][0] is None:
            continue
        cols = _columns(conn, "public", table)
        names = ", ".join(f'"{c}"' for c in cols)
        picked = ", ".join(("NULL" if table == "conversation" and c in ("head_commit_id", "branched_from_conversation_id")
                            else f'"{c}"') for c in cols)
        if table in GLOBAL:
            key = GLOBAL[table]
            if table == "app_config":
                out.settings_kept = [r[0] for r in _q(conn, f'SELECT s.key FROM "{scratch}".app_config s'
                                                            f" JOIN public.app_config p USING (key) ORDER BY 1")]
            cur = conn.execute(f'INSERT INTO public.{table} ({names}) SELECT {picked} FROM "{scratch}".{table}'
                               f" ON CONFLICT ({key}) DO NOTHING")
        else:
            cur = conn.execute(f'INSERT INTO public.{table} ({names}) OVERRIDING SYSTEM VALUE'
                               f' SELECT {picked} FROM "{scratch}".{table}')
        out.rows[table] = cur.rowcount
    # Heads, then branch links: to an origin restored with it or already here; else cleared, as a delete clears it
    # (ADR 0009), host refs kept.
    conn.execute(f'UPDATE public.conversation c SET head_commit_id = s.head_commit_id FROM "{scratch}".conversation s'
                 " WHERE c.id = s.id")
    conn.execute(f'UPDATE public.conversation c SET branched_from_conversation_id = s.branched_from_conversation_id'
                 f' FROM "{scratch}".conversation s WHERE c.id = s.id AND s.branched_from_conversation_id IN'
                 " (SELECT id FROM public.conversation)")
    out.links_cleared = [r[0] for r in _q(conn, f'SELECT s.id::text FROM "{scratch}".conversation s'
                                                " JOIN public.conversation c ON c.id = s.id"
                                                " WHERE s.branched_from_conversation_id IS NOT NULL"
                                                " AND c.branched_from_conversation_id IS NULL")]
    for table, col in SEQUENCED.items():
        conn.execute(f"SELECT setval(pg_get_serial_sequence('public.{table}', %s),"
                     f" greatest((SELECT max({col}) FROM public.{table}), 1))", (col,))


def restore_file(database_url: str, path: str) -> Restored:
    return restore_archive(database_url, check_archive(path))


def _restore_command(settings: Settings, source: str, check_only: bool) -> int:
    spool = None
    try:
        if source == "-":
            spool = tempfile.NamedTemporaryFile(prefix="nmos-restore-", suffix=SUFFIX, delete=False)
            with spool:
                shutil.copyfileobj(sys.stdin.buffer, spool)
            source = spool.name
        checked = check_archive(source)
        m = checked.manifest
        print(f"archive: {m['scope']}, {len(m.get('conversations') or [])} conversation(s), schema {m['schema']['level']},"
              f" NMOS {m.get('nmos_version')}, made {m.get('created_at')}; every file checked", file=sys.stderr)
        if check_only:
            return 0
        done = restore_archive(settings.database_url, checked)
    except ArchiveError as error:
        print(f"restore refused: {error}", file=sys.stderr)
        return 2
    finally:
        if spool is not None:
            os.unlink(spool.name)
    for c in done.conversations:
        print(f"restored {c['host']} chat {c['host_chat_ref']} ({c.get('character') or '?'}) as {c['id']}", file=sys.stderr)
    print("rows: " + ", ".join(f"{t} {n}" for t, n in done.rows.items() if n), file=sys.stderr)
    if done.migrated:
        print(f"migrated from {m['schema']['level']}: {', '.join(done.migrated)}", file=sys.stderr)
    if done.renumbered:
        print(f"ids moved past this install's own: {', '.join(done.renumbered)}", file=sys.stderr)
    if done.settings_kept:
        print(f"settings already set here were kept: {', '.join(done.settings_kept)}", file=sys.stderr)
    if done.links_cleared:
        print(f"branches whose origin is not here lost their link: {', '.join(done.links_cleared)}", file=sys.stderr)
    print("start the sidecar and worker: they write the derived text and state and queue what is missing",
          file=sys.stderr)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m nmos_sidecar.archive", description="NMOS Archive (ADR 0050).")
    sub = parser.add_subparsers(dest="command", required=True)
    ex = sub.add_parser("export", help="write an archive of the whole install or of chosen conversations")
    ex.add_argument("--conversation", action="append", metavar="ID",
                    help="archive this conversation only (repeatable; default: the whole install with its settings)")
    ex.add_argument("--no-projections", action="store_true",
                    help="leave out extractions, summaries and canon reads (a restore extracts again, at model cost)")
    ex.add_argument("--embeddings", action="store_true", help="include embeddings (larger; rebuilt locally otherwise)")
    rs = sub.add_parser("restore", help="restore an archive into this install (stop the sidecar and worker first)")
    rs.add_argument("archive", help=f"the {SUFFIX} file ('-' for stdin)")
    rs.add_argument("--check", action="store_true", help="verify the archive only; write nothing")
    ex.add_argument("-o", "--output", help=f"file to write ('-' for stdout; default: nmos-….{SUFFIX.lstrip('.')} here)")
    args = parser.parse_args(argv)
    settings = Settings()
    if args.command == "restore":
        return _restore_command(settings, args.archive, args.check)
    kwargs = {"conversations": args.conversation, "projections": not args.no_projections,
              "embeddings": args.embeddings, "settings": settings}
    try:
        if args.output == "-":
            buffer = tempfile.TemporaryFile()
            with psycopg.connect(settings.database_url) as conn:
                result = write_archive(conn, buffer, **kwargs)
            buffer.seek(0)
            shutil.copyfileobj(buffer, sys.stdout.buffer)
            sys.stdout.buffer.flush()
        else:
            path = args.output or default_name(len(set(args.conversation)) if args.conversation else None)
            result = export_file(settings.database_url, path, **kwargs)
            print(f"wrote {path}", file=sys.stderr)
    except ArchiveError as error:
        print(f"export refused: {error}", file=sys.stderr)
        return 2
    summary = ", ".join(f"{f['table']} {f['rows']}" for f in result.manifest["files"] if f["rows"])
    print(f"{len(result.manifest['conversations'])} conversation(s); {summary}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
