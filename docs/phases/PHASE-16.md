# Phase 16 — Export and restore (Stage 6, part 3)

> **Status: complete (2026-09-29), approved the same day with every proposed answer (Q0–Q9); the phone check of the
> panel's Export is the owner's (K38).** Stage 6 of `docs/ROADMAP-1.0.md` (original §89,
> §66–67; Track B, B7): "export and restore of the ledger, repairs and settings", and Stage 6's last done criterion,
> "export, restore into a fresh install and replay give the same packets". Phase 14 Q0 gave it its own phase; Phase 15
> (a packet that fills its budget) ran first at the owner's choice (2026-09-29).

## Questions and proposed answers

Each answer in bold was NMOS's proposal; the owner accepted all of them (2026-09-29).

| # | Question | Proposed answer | Alternatives |
|---|---|---|---|
| Q0 | What is it for? | **Moving NMOS and keeping it safe, in a form that outlives the schema:** a new machine or a fresh install, a chat kept before it is deleted, and a copy the owner can inspect. `pg_dump` backups stay the way to roll back an upgrade (they are exact, but tied to this schema and to PostgreSQL). | Backups only (`pg_dump`); a sync service. |
| Q1 | What goes in? | **Everything that cannot be rebuilt, and by default what costs money to rebuild.** Always: the source ledger (conversations, source objects and revisions, commits, appends and membership, host observations), canon (revisions, manifests), the owner's input (repairs, entity links, per-chat memory mode), the recorded requests (traces: they are the audit, and replay needs them), and the settings without secrets. By default also: extractions and assertions, summaries and canon reads (a model's work: re-extracting the owner's chats would cost calls). Optional: embeddings (the largest part, 26 of ≈47 MB in production; rebuilt locally at no model cost). Never: jobs, derived text (`revision_text`, state), API keys, the auth token. | Ledger only (§89's minimum: every projection rebuilt, at the provider's cost); everything including embeddings by default. |
| Q2 | Whole install or one chat? | **Both, one format:** an archive holds one or more conversations and, for a whole install, the settings. A branch chosen without the chat it branched from keeps its origin's host refs; its link to the origin is restored when the origin is in the archive or already in the install, and otherwise cleared, as deleting the origin clears it (ADR 0009). | Whole install only. |
| Q3 | Format? | **"NMOS Archive" (§89): one `.nmos.zip` with `manifest.json` (archive format version, NMOS version, schema migration level, generation keys, per-file row counts and SHA-256) and one JSON Lines file per table, rows as named columns.** Readable without NMOS, independent of PostgreSQL. | A `pg_dump` per chat; a single JSON file. |
| Q4 | Restore into what? | **A fresh install, or an install that does not hold the archive's conversations.** A conversation already present (the same host chat) is refused, never merged: two histories of one chat cannot be joined safely (invariant 1). Rows keep their ids, so traces, repairs and links still point at what they named. | Merge into an existing chat; new ids on restore. |
| Q5 | Across versions? | **An archive restores into its own or a newer NMOS.** The importer creates the archive's schema level from the bundled migrations, loads the rows, then applies the later migrations, the path the upgrade tests already cover (`tests/test_upgrade.py`). A newer archive into an older NMOS is refused. Generation keys come along, so the new install serves the same facts until its settings name another model. | Current version only; a converter per version. |
| Q6 | How is it run? | **Export from the panel as well as a command** (owner, 2026-09-29): an **Export** button in the NMOS panel, for this chat on its Inspector page and for everything in the Settings tab, and a command in the sidecar image (`docker compose exec sidecar python -m nmos_sidecar.archive export|restore …`). Whether the plugin's frame may save a file is host evidence to gather first (PocketRisu v1.13.0 already blocks plugins from opening tabs); if it may not, the button shows a link to the same file on the sidecar, opened from the browser Inspector. Restore stays a command: it writes a whole database. | Command and Inspector link only; restore from the panel too. |
| Q7 | Secrets and privacy? | **No keys or tokens, ever** (K21). The archive holds chat text, so the guide says to keep it like the chat itself. It is not encrypted (a password-protected zip gives little); the owner can encrypt the file. | Encrypted archives. |
| Q8 | How is it measured? | **Round trip on the owner's two measured chats (copies, read-only source):** export, restore into a fresh database, then (1) the ledger state is equal row for row; (2) every recorded request replays reproduced, as on the source; (3) M0 and the secret gate give the same numbers; (4) a rebuild gives the same projections as a rebuild of the source. Also: an archive of Phase 15 `main` restored into this phase's code (Q5); a chat restored after it was deleted (ADR 0009); a restore refused for a chat present; sizes and times on the production-sized copy; a review per AGENTS.md §14 (high risk: stored data). | Synthetic chats only. |
| Q9 | Release? | **None until the owner asks.** Stage 6's done criteria would then all be met except transition rules (still unscheduled). | A release after this phase. |

## Goal

The owner can move all of NMOS, or one chat, to a fresh install and get the same memory back: the same history, the
same repairs and links, the same answers to recorded requests, without paying for extraction again.

## Evidence behind the scope

- **What NMOS keeps** (production, 2026-09-29, counts only): 9 conversations, 459 source revisions, 7,510 assertions
  in 1,447 extractions, 852 embedding rows (26 MB of ≈47 MB), 201 recorded requests, 13 summaries, one canon manifest.
  A `pg_dump` of it is 17 MB.
- **What cannot be rebuilt:** the ledger and canon (invariant 1), the owner's input (ADR 0025, 0035, 0044, 0047), and
  the recorded requests (ADR 0027). Every projection is rebuildable (invariant 2), but extraction and summaries cost
  model calls: 1,447 extractions on the owner's chats.
- **What exists:** `pg_dump` backups before every deploy (restore-tested), upgrade fixtures restored and migrated in
  tests, per-chat rebuild and delete (ADR 0008, 0009), and the ledger-state comparison used by the tests.

## In scope (Phase 16)

1. **This document**, approved.
2. **Host evidence (Q6):** whether a V3 plugin's frame on PocketRisu v1.13.0 can save a file (a download link, a Blob URL),
   in `HOST-FACTS.md`.
3. **The archive format** (Q1–Q3; ADR 0050, D60): manifest, one JSON Lines file per table, what is always in,
   in by default, optional, never; a format version.
4. **Export** (Q2, Q6): the command for the whole install or chosen conversations, and the panel's Export buttons
   (this chat; everything) with the Inspector link as the fallback. Read-only, one consistent snapshot. A new plugin
   build.
5. **Restore** (Q4, Q5): into an empty database or one without the archive's conversations; checks every file's hash
   and count before writing; one transaction; refuses a present chat or a newer archive; migrates after loading.
6. **Evaluation (Q8)**, a real-host smoke of the panel's export, review, and documentation (README, the Korean guide, KNOWN-ISSUES, CHANGELOG).

## Out of scope (Phase 16)

- Importing another plugin's memory (proposal P4): a separate source kind, later if at all.
- Merging two histories of one chat; restoring into a different host chat id.
- Scheduled or remote backups; encryption.
- Transition rules (Stage 6, unscheduled).

## Acceptance criteria

- [x] Every existing test passes (sidecar 657, plugin 162).
- [x] Deterministic cases: a round trip of a chat with edits, swipes, a branch, a deleted message, canon, repairs,
      links and a memory mode gives an equal ledger state and reproduced replays; a branch exported without its origin
      restores with its host refs and no link; embeddings optional; secrets never
      exported; a changed or truncated file refused before anything is written; a present chat refused; a newer
      archive refused; an archive from an older NMOS restored and migrated (Phase 13 `main`, level 0024; the measured
      copies, level 0025; Phase 15 `main` is this schema's level).
- [x] Host evidence on PocketRisu v1.13.0 for saving a file from the plugin's frame, in `HOST-FACTS.md` (H21); a
      real-host smoke of the panel's Export (this chat and everything), `fixtures/host/export-smoke-v1.13.0-2026-09-29/`.
      Not on a phone (K38).
- [x] On the owner's two measured chats (copies): the ledger state equal, every recorded request compiled again the
      same as on the source (lexical; replays with vectors are covered by the deterministic cases), M0 and the secret
      gate unchanged, a rebuild equal to the source's (`docs/perf/archive.md`).
- [x] Size and time of export and restore of the production-sized copy reported: 15.3 MB with embeddings (2.1 MB
      without), export 2.6 s, restore 2.9 s.
- [x] A review per AGENTS.md §14 (high risk): one Codex review each for export (step 3) and restore (step 4).
- [x] `ARCHITECTURE.md` (D60), ADR 0050, README, the Korean guide, KNOWN-ISSUES, CHANGELOG, the roadmap's Stage 6.

## Steps (one pull request each)

1. This document, approved.
2. Host evidence: can the plugin's frame save a file.
3. The archive format and export (command, panel buttons, Inspector link), ADR 0050, a plugin build.
4. Restore, with its checks and migrations.
5. Evaluation, real-host smoke, review, documentation.

Every merge reaches the owner's `:edge`; no tag (AGENTS.md §13).

## Stop conditions

Stop and ask the owner when:

- a restored install does not reproduce a recorded request the source reproduces;
- restoring needs a schema change to existing tables (a migration beyond an index);
- an archive would have to hold a secret, or the owner's chat text would have to leave the machine.
