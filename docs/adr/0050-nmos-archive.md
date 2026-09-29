# 0050 — NMOS Archive: export and restore

Status: accepted, 2026-09-29. Phase 16 step 3 (`docs/phases/PHASE-16.md` Q1–Q3, Q6, Q7, approved by the owner). A new
endpoint, a command and a plugin build; no migration. Restore is step 4: amendment 1.

## Context

A `pg_dump` is exact but tied to this schema and to PostgreSQL, and holds everything, keys included. The owner wants
to move NMOS, or one chat, to a fresh install and keep it safe in a form that outlives the schema (Q0), from the panel
as well as a command (Q6). The plugin's frame can save a Blob, and `nativeFetch` carries a binary body whole on both
routes; a link to the file would navigate the frame instead (H21).

What NMOS keeps falls in four parts. The ledger (invariant 1), canon, the owner's input and the recorded requests
cannot be rebuilt. Extractions, summaries and canon reads can, at model cost. Embeddings can, locally. Jobs, the
normalized text and the parsed state are recomputed from the rest.

## Decision

1. **One `.nmos.zip`.** One JSON Lines file per table, `tables/<table>.jsonl`, then `manifest.json`, the last entry:
   `format` `nmos-archive`, `format_version` 1, `nmos_version`, `created_at`, `scope` (`install` or `conversations`),
   `contents` (`ledger`, `settings`, `projections`, `embeddings`), `schema` (`level`, the last migration, and every
   applied migration with its checksum), `generations` (the latest activated key of each kind), `conversations` (id,
   host chat ref, character and chat names, the conversation it branched from), `omitted_settings`, and `files` (path,
   table, rows, bytes, SHA-256 of the file as stored). Deflate.
2. **Rows are PostgreSQL's `row_to_json`**, one per line, columns by name in the table's order: timestamps in UTC to
   the microsecond, numbers inside jsonb as stored, `real` as the shortest text that reads back exactly
   (`extra_float_digits` 1), vectors as their text. A restore reads them back with `json_populate_record` into the
   same schema level, so nothing is converted by hand either way. Rows are ordered by a total order per table, so the
   same state gives the same files, byte for byte.
3. **What goes in** (Q1):

   | Part | Tables | When |
   |---|---|---|
   | ledger | `conversation`, `host_observation`, `observation_base`, `source_object`, `source_revision` (messages and canon), `worldline_commit`, `worldline_append`, `active_membership`, `canon_manifest`, `canon_applied`, `entity_link`, `owner_repair`, `retrieval_trace`, and every `projection_generation` | always |
   | settings | `app_config`: the editable settings but the keys, and the parser rules | the whole install |
   | projections | `extraction`, `assertion` (message facts and canon reads), `summary` | by default |
   | embeddings | `revision_embedding` | when asked |

   Never: `job`, `revision_text`, `state_observation` (recomputed), `schema_migrations` (the manifest names them).
   Chosen conversations take their own rows only; a branch keeps its link column as stored (PHASE-16 Q2 governs
   restore). Every generation goes in, since rows of any conversation may name any of them and they are small.
4. **No credential, ever** (Q7, K21). Settings are an allowlist (`runtime.EDITABLE` without `runtime.SECRET`, plus
   the parser rules), so a key saved in the panel never qualifies. An endpoint setting whose URL has a user, a
   password, a query string (`?key=`) or a fragment is left out and named in `omitted_settings`. A generation whose
   endpoint has a user or a password refuses the export (its key hashes it; it cannot be left out). Every string of
   every row, decoded (so an escaped quote or backslash still matches), and of the manifest is checked against every
   credential NMOS holds of four characters or more (the saved keys, the environment's keys, the auth token, a service
   account's private key); a match anywhere refuses the export (HTTP 409, command exit 2) and names the table, never
   the value. The step's Codex review found the first cut missed short and quoted keys and a user in a URL. The archive holds chat text
   and is not encrypted: the guide says to keep it as the chat itself.
5. **One consistent snapshot.** The export reads in one `REPEATABLE READ, READ ONLY` transaction: syncs and workers
   carry on, and the archive is the state at its start.
6. **Three ways to run it** (Q6):
   - `GET /v1/archive` (auth as every endpoint): no parameter for the whole install with its settings;
     `conversation=<id>` (repeatable) for chosen conversations; `projections=false`, `embeddings=true`. A zip
     attachment named `nmos-all-…` or `nmos-N-chat-…`; 404 for an unknown conversation, 409 for a refusal. Built in a
     temporary file, removed once sent.
   - `python -m nmos_sidecar.archive export [--conversation ID …] [--no-projections] [--embeddings] [-o FILE|-]`:
     written beside the target and moved into place only when complete; `-o -` writes to stdout
     (`docker compose exec -T sidecar python -m nmos_sidecar.archive export -o - > nmos.nmos.zip`).
   - The panel (a new plugin build): **Export this chat** on a conversation's Inspector page, **Export everything**
     (and "Include embeddings") in the Settings tab. The plugin fetches the file through `nativeFetch` on the chosen
     route and saves it as a Blob (H21), named `nmos-chat-…` or `nmos-all-…` in local time, and says its size or the
     sidecar's refusal. Mobile browsers are not yet observed (H21); where the button saves nothing, `/v1/archive`
     opened in a browser that reaches the sidecar, or the command, gives the same file.

## Consequences

- The file is readable without NMOS: a zip of JSON, one object per row, a manifest with counts and hashes.
- An archive names its schema level; a restore creates that level, loads the rows and migrates (Q5, step 4).
- A restore must keep ids and timestamps exactly: replays compare the assertion ids recorded in each request's
  lines, and read "as of" the request's time through `created_at`, `discarded_at`, `activated_at`, `removed_at` and
  `applied_at` (step 4).
- The export holds the whole archive in a temporary file (≈ the zip's size) while it is sent.
- Production-sized numbers are measured in step 5.

## Amendment 1 — restore (2026-09-29, Phase 16 step 4; Q4, Q5)

1. **A command, never the panel:** `python -m nmos_sidecar.archive restore [--check] FILE|-`, with the sidecar and
   the worker stopped (`docker compose stop sidecar worker`, then `docker compose run --rm -T sidecar python -m
   nmos_sidecar.archive restore - < file.nmos.zip`, then `docker compose up -d`). It writes a whole database.
2. **Checked before anything is written:** the manifest's format and version; that the zip holds exactly the files
   the manifest lists, each named after a known table; each file's size, row count and SHA-256. The archive's
   migrations must be the first of this NMOS's, checksums equal: an archive from a newer NMOS is refused ("upgrade
   first"), one with other migrations too. `--check` stops there.
3. **Into an install without its conversations:** this install is migrated first (a fresh database too); if any
   archived conversation is here, by id or by host chat, the restore is refused whole and names it. Nothing is
   merged (invariant 1).
4. **The archive's own schema, then the upgrade it would have had** (Q5): in one transaction, a scratch schema gets
   the bundled migrations up to the archive's level (foreign keys dropped there), the rows are loaded as written
   (`json_populate_recordset`, identity values kept), the later migrations run on them, and the rows are copied into
   the install, parents first, and the scratch schema dropped. An archive of the current level runs no migration.
5. **Ids and timestamps kept.** Every uuid and timestamp is the archive's. The sequenced ids shared by all
   conversations (`assertion.id`, `worldline_commit.seq`, `worldline_append.seq`) are kept when no row here has them
   (a fresh install; a chat deleted here and restored), else moved past this install's largest, order kept, and the
   assertion ids a recorded request's lines name (`ref`, `restates`, `repeats`; not the negative ids of owner
   corrections) moved with them, so its replay still compares. The sequences are set past the largest id.
6. **Rows of no conversation:** a generation already here keeps its own row (the same key is the same generation);
   a setting already set here stays and is reported, the rest are the archive's.
7. **Branches:** a restored branch whose origin is restored with it or already here keeps its link; else the link is
   cleared (host refs kept, reported), as deleting the origin clears it (ADR 0009). A branch here whose origin is the
   restored conversation (by its host refs) is linked again.
8. **Derived data follows:** jobs, the normalized text and the parsed state are not archived; the sidecar's startup
   writes the text and state and queues the missing extraction, embedding, summary and canon work of the active
   generations, as for any chat (the first-sight backfill limits apply).

Consequences:

- A restore of the archive of a whole install into a fresh one gives an archive of the same bytes and the same
  replays (tested).
- **Replays and embeddings.** A replay reads vectors as of its request; a vector embedded again after a restore is
  newer than every recorded request. So a recorded request that used vectors replays exactly only when the archive
  held the embeddings; without them its excerpts from vectors are missing from the replay (its packet in the ledger
  is unchanged). The guide says to tick "Include embeddings" to keep that audit.
- Recorded requests older than `NMOS_TRACE_RETENTION_DAYS` (30) are pruned by the worker's next pass, as on the
  source.
