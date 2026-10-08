# Phase 38 — Restore from the panel, while NMOS runs

> **Status: approved 2026-10-08 (the owner: the phase, and a restore that runs while NMOS runs); Q1, Q2, Q4–Q7 as
> proposed, Q3 amended by the owner (2026-10-08). Step 2 next.** A correction phase (AGENTS §7 item 5),
> not a roadmap stage: it completes Phase 16 (ADR 0050), whose export reached the panel while its restore stayed a
> command. It amends ADR 0050 amendment 1 item 1 ("a command, never the panel"). Aimed at `0.4.0`. **High risk
> (AGENTS §14): stored data, and an HTTP route that writes the database.**

## Why now

The panel exports an NMOS Archive (Settings → **Export everything**; Inspector → **Export this chat**), but nothing
in the panel takes one back. The restore is a command that needs the sidecar and the worker stopped, and every
documented form of it is `docker compose …`:

- **A bundle user cannot restore at all.** A portable install (Phase 23) has no documented way to stop its services and
  run the command against its own PostgreSQL.
- **The docs promise paths that need it.** A bundle moves to a later PostgreSQL major "through the NMOS Archive"
  (ADR 0060), and Phase 37's follow-up tells a Docker user moving to a bundle to export and restore.
- **For a panel user the export is half a feature.** The file it saves can only be used from a terminal.

Amendment 1 chose the command because the restore writes a whole database: with the services running, (a) the
restored rows keep their ids in three tables whose ids come from one shared sequence (`assertion.id`,
`worldline_commit.seq`, `worldline_append.seq`, `archive.SEQUENCED`), so a worker or a sync drawing ids at the same
time could take the ids the restore is placing; and (b) the derived rows a restore leaves out (normalized text, state
observations, jobs) are written by the sidecar's startup, so a running sidecar would not write them. This phase
answers both inside the running sidecar.

## Questions and proposed answers

| | Question | Proposed answer | Alternative |
|---|---|---|---|
| Q1 | Where is it? | **The panel's Settings tab, under Export**: **Restore from an archive…** opens the file chooser (observed in the plugin frame, HOST-FACTS 2026-10-04), the same place for a Docker and a bundle install. | The Inspector's pages as well: a browser upload there needs a form parser (a new dependency) or page script the Inspector does not have. |
| Q2 | One click or two? | **Two steps.** The file is uploaded and checked first (every file's size, row count and hash, the schema, as `archive restore --check`), and the panel shows what it holds: scope, the NMOS version that made it, each chat by character and chat name, the chats already here (which refuse the whole restore), and the settings it would add. **Restore** then writes it and shows the result (rows, ids moved, links cleared, migrations). An upload not restored within an hour, or replaced by another, is deleted. | One click: a chat already here or an unexpected setting is found only after the fact. |
| Q3 | How does the file travel? | **Amended by the owner: in chunks, for the host's proxy, not for the iPhone.** Each chunk is a request of its own, under any body size or time limit of the host's proxy (unobserved), and the panel shows the progress; it reads one `File.slice()` at a time. The chunk size is step 2's (4 MB until measured). **The iPhone is not a target:** a restore is a desktop task; nothing here is measured or accepted on it. The sidecar appends them to a spool file in its temporary directory, checks each chunk's length and SHA-256 and their order, and refuses past `NMOS_RESTORE_MAX_MB` (default 2048) or when free space is under twice the declared size. A chunk's body is binary if step 2's host evidence shows a binary request body arriving whole through `nativeFetch` on both routes; else base64 in JSON (the request form every panel call uses). | The whole file in one request: bounded by the host proxy's body limit, unobserved, and held whole in the frame. |
| Q4 | What happens to requests while it runs? | **Writers wait; readers do not.** The restore's transaction starts by taking `EXCLUSIVE` locks on `assertion`, `worldline_commit`, `worldline_append` and `conversation` (reads continue; an insert or update waits before it draws an id), so every id drawn afterwards comes after the restored ones and the sequences' `setval`. A lock not obtained within 30 s (a long job holding it) refuses with "busy, try again", writing nothing. A chat request arriving meanwhile keeps the plugin's deadline: its reply goes without that turn's sync, fail-open, as when the sidecar is slow. After the commit the sidecar runs, for the new rows, the same idempotent steps as its startup (normalized text, turn data, state rules, each active generation's missing jobs); the worker picks the jobs up. | Pause the worker with a flag: syncs on the request path still draw ids. Or restore at the next start: needs a restart the user must do. |
| Q5 | Settings in a whole-install archive? | **As the command does:** a setting already set here stays; one not set takes the archive's value; keys and the token are never in an archive (ADR 0050 item 4). Step 1 lists the settings it would add, the model endpoints named. | Never take settings from a panel restore. |
| Q6 | Who may restore? | **Whoever may export or delete a conversation:** the same guard (the token when one is set; loopback and the allowed hosts otherwise). The upload, the check and the restore are three routes behind it. | An extra confirmation phrase: the two steps already show what will be written. |
| Q7 | The command? | **Unchanged** (`python -m nmos_sidecar.archive restore`, services stopped), kept for scripts and Docker users who prefer it; the docs point bundle users to the panel. | Make the command live as well: two ways to run the same locks. |

## In scope

- `apps/sidecar/src/nmos_sidecar/archive.py`: the locks and their timeout at the start of `restore_archive` (Q4),
  a summary of a checked archive with the chats already here and the settings it would add (Q2, Q5).
- `apps/sidecar/src/nmos_sidecar/api.py`: an upload (create, chunk, check, restore, discard) behind the auth guard,
  its spool files and expiry; after a restore, the startup steps for the new rows (Q4). A setting
  `NMOS_RESTORE_MAX_MB` (Q3).
- `adapters/pocketrisu-plugin/src/ui.ts`, `host.ts`, `i18n.ts`: Settings → **Restore from an archive…**, the chunked
  upload with its progress, the summary, **Restore** and the result; `dist` rebuilt.
- Host evidence (step 2): a request body through `nativeFetch` on both routes, binary and base64, at the chunk size
  and above, recorded in `docs/HOST-FACTS.md` like H21.
- Tests: the restore through the API into an install that is running, with a worker and syncs writing at the same
  time (no id taken twice; the sequences past every id; the derived rows and the missing jobs there); every refusal
  (a chat already here, a newer NMOS, a cut or changed chunk, a chunk out of order, over the size, an expired upload,
  the lock timeout) writing nothing; the plugin's chunking and its screens (vitest).
- `README.md`, `docs/guide.ko.md` (restore from the panel, for Docker and bundles), `CHANGELOG.md`, ADR 0050
  amendment 2, `ARCHITECTURE.md` where it names the restore.

## Out of scope

- Merging an archive into a chat that is here: restores never merge (invariant 1); the chat is deleted first.
- Restoring part of an archive (some of its chats): the whole archive or nothing, as now.
- A live mode for the command (Q7).
- Writing anything into PocketRisu: a restored conversation is NMOS's record; a host chat that matches it syncs against
  it on its next request, as after an upgrade.
- The Docker → bundle note itself (Phase 37's follow-up, which will point to this restore).

## Steps

1. This spec, with the owner's answers.
2. Host evidence: a request body through `nativeFetch` on both routes (binary and base64; 1, 4 and 30 MB) on an
   isolated PocketRisu, as H21 did for responses. It picks Q3's body form and chunk size.
3. The sidecar: the upload, the check summary, the locked restore, the startup steps after it; its tests.
4. The panel; its tests; `dist`.
5. Measured: a restore of a 10,000-message archive into a running install: its time, and how long a sync waited.
   Docs and ADR 0050 amendment 2.
6. **The owner's check:** an export from the trial install restored through the panel of a fresh install (an isolated
   PocketRisu and a sidecar on a throwaway database), on the desktop.

## Acceptance criteria

1. An archive exported by the panel restores through the panel into a running install, Docker and bundle (the bundle
   smoke drives the routes), with the same rows the command would have written.
2. While a restore runs, a worker and syncs writing at the same time take no id the restore holds; afterwards every
   sequence is past every id, and the restored chats have their derived rows and their missing jobs without a restart
   (test).
3. Every refusal in In scope writes nothing to the database and leaves no spool file once it is answered (tests).
4. The panel reads the file one chunk at a time (test), and an upload through each route arrives whole (host
   evidence, desktop Chromium and Firefox).
5. Step 5's measurement is reported: the restore's time and the longest wait of a sync during it.
6. The owner's check passes.

## Stop conditions

- Neither a binary nor a base64 chunk arrives whole through a route the panel uses.
- The locks would block reads (recall) for the restore's duration.
- A restore would have to merge into a chat that is here.
- The host's limits leave no chunk size that uploads a 2 GB archive in a practical time on the desktop.

## Risk

**High (AGENTS §14).** The guarantees at risk: a restore never corrupts or merges what the install holds (one
transaction, refused whole, ids never taken twice), and the route that writes the database is behind the same guard
as every other write. Requests that write wait for the restore; they fail open on the plugin's deadline.
