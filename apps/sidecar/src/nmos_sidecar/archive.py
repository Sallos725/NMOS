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


class ArchiveError(Exception):
    """An archive that cannot be written (or read) as asked; the message says why."""


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
    """A URL that may carry a credential: a password in it, or a query string (`?key=`)."""
    parts = urlsplit(url.strip())
    return parts.password is not None or bool(parts.query)


def _secrets(conn: psycopg.Connection, settings: Settings | None) -> list[str]:
    """Every credential NMOS holds (saved keys, the environment's keys, the auth token), to refuse an archive that
    would carry one anywhere (K21). A service-account key also counts by its private key alone."""
    out: set[str] = set()
    for (value,) in _q(conn, "SELECT value FROM app_config WHERE key = ANY(%s)", (sorted(runtime.SECRET),)):
        if isinstance(value, str):
            out.add(value)
    if settings is not None:
        out.update(v for v in (settings.llm_api_key, settings.embed_api_key, settings.auth_token) if v)
    for value in list(out):
        try:
            key = json.loads(value)
        except ValueError:
            continue
        if isinstance(key, dict) and isinstance(key.get("private_key"), str):
            out.add(key["private_key"])
            out.update(line for line in key["private_key"].splitlines() if len(line) >= 16 and "-----" not in line)
    return sorted(s for s in out if len(s.strip()) >= 8)


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
        raise ArchiveError(f"no such conversation: {', '.join(missing)}")
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
                  projections: bool = True, embeddings: bool = False, settings: Settings | None = None) -> Export:
    """Write an archive to `out` (a binary file) from one consistent, read-only snapshot. `conversations` None is
    the whole install (every conversation and the settings); a list is those conversations only. Raises
    ArchiveError, with nothing useful written, when a chosen conversation is missing or a credential would be
    archived. `conn` must not be in a transaction."""
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
            if urlsplit(endpoint).password is not None:
                raise ArchiveError("a generation's endpoint holds a password; an archive never holds one (K21)")
        labels = _q(conn, "SELECT id, host, host_chat_ref, host_character_name, host_chat_name,"
                          " branched_from_conversation_id FROM conversation WHERE id = ANY(%s) ORDER BY created_at, id",
                    (convs,))
        latest = dict(_q(conn, "SELECT DISTINCT ON (kind) kind, key FROM projection_generation"
                               " ORDER BY kind, activated_at DESC, key"))
        export = Export(manifest={})
        omitted: list[str] = []
        with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
            for table in TABLES:
                if table.part not in parts:
                    continue
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
                        if any(s in line for s in secrets):
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


def default_name(export: Export, when: datetime | None = None) -> str:
    stamp = (when or datetime.now(timezone.utc)).strftime("%Y%m%d-%H%M%S")
    scope = "all" if export.manifest["scope"] == "install" else f"{len(export.manifest['conversations'])}-chat"
    return f"nmos-{scope}-{stamp}{SUFFIX}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m nmos_sidecar.archive", description="NMOS Archive (ADR 0050).")
    sub = parser.add_subparsers(dest="command", required=True)
    ex = sub.add_parser("export", help="write an archive of the whole install or of chosen conversations")
    ex.add_argument("--conversation", action="append", metavar="ID",
                    help="archive this conversation only (repeatable; default: the whole install with its settings)")
    ex.add_argument("--no-projections", action="store_true",
                    help="leave out extractions, summaries and canon reads (a restore extracts again, at model cost)")
    ex.add_argument("--embeddings", action="store_true", help="include embeddings (larger; rebuilt locally otherwise)")
    ex.add_argument("-o", "--output", help=f"file to write ('-' for stdout; default: nmos-….{SUFFIX.lstrip('.')} here)")
    args = parser.parse_args(argv)
    settings = Settings()
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
            path = args.output or os.path.join(os.getcwd(), "nmos-archive" + SUFFIX)
            result = export_file(settings.database_url, path, **kwargs)
            if not args.output:
                final = os.path.join(os.path.dirname(path), default_name(result))
                os.replace(path, final)
                path = final
            print(f"wrote {path}", file=sys.stderr)
    except ArchiveError as error:
        print(f"export refused: {error}", file=sys.stderr)
        return 2
    summary = ", ".join(f"{f['table']} {f['rows']}" for f in result.manifest["files"] if f["rows"])
    print(f"{len(result.manifest['conversations'])} conversation(s); {summary}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
