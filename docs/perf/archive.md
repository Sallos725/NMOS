# NMOS Archive: export and restore measured (Phase 16 step 5)

`docs/phases/PHASE-16.md` Q8. ADR 0050 and its amendment 1 define the archive and the restore. Numbers only: the
measured chats are the owner's, and their copies, cases and scripts stay outside the repository
(`~/nmos-eval/phase16-archive/`).

## Round trip on the two measured chats

**Setup.** The Phase 15 evaluation copies of the owner's two measured databases (restored backups on the test
PostgreSQL; schema level `0025_canon.sql`, one migration behind this NMOS): the longest chat's (7 conversations) and
sample 2's (8 conversations, the production-sized one: 7,508 assertions, 850 embedding rows and 202 recorded requests
against production's 7,510, 852 and 201). Each copy was cloned (A); A was exported whole with embeddings at its own
level, then upgraded in place (`0026_canon_facts.sql`); the archive was restored into a fresh database (R), which
created level 0025 in a scratch schema, loaded the rows and applied 0026, as the upgrade did to A. No model was
called and no worker ran. The sidecar's startup derivations (normalized text, turns, state) were run on both, without
activating a generation.

| | Longest chat | Sample 2 |
|---|---|---|
| Rows archived (with embeddings) | 10,292 | 11,441 |
| Archive, with embeddings | 13.7 MB (48.3 MB of JSON Lines) | 15.3 MB (53.7 MB) |
| Archive, without embeddings (the default) | 1.8 MB | 2.1 MB |
| Export time, with / without embeddings | 2.3 s / 0.4 s | 2.6 s / 0.5 s |
| Restore time (migrating 0025 → 0026) | 2.6 s | 2.9 s |
| Database size, source copy / restored | 43 / 38 MB | 42 / 40 MB |
| Ids moved | none | none |

The restored database is smaller: it has no jobs and no dead tuples (the sizes are before the startup derivations).

**(1) Ledger state, row for row.** R's archive and A's (both after the upgrade, with embeddings) hold the same bytes
in every table file, on both chats: every conversation, observation, source object and revision (messages and
canon), commit, append, membership row, canon manifest, link, repair, generation, setting, extraction, assertion,
summary, embedding and recorded request.

**(2) Recorded requests.** Every recorded request compiled again (ADR 0027 replay, lexical) gives the same status,
packet text and lines on R as on A: 186 of 186 and 202 of 202 (13 and 25 replayable; the others were recorded before
lines were, or their prefix changed since). Before the startup derivations R lacked the normalized text and 2 replays
on sample 2 differed, as expected: the sidecar writes it at start. A replay with vectors needs the embedding model of
each request; those point at the owner's endpoint, and the local model is the one production uses on request paths,
so they were not run on these copies (the deterministic tests cover replays with vectors after a restore).

**(3) M0 and the secret gate** (lexical, `packet-v9` at 4,000 tokens; the same tools and keys as Phase 15): every
output file identical between A and R.

| | A | R |
|---|---|---|
| Longest chat, M0 28 cases | 26 (7 of 9 needing memory) | the same cases |
| Longest chat, M0 12 cases | 7 | the same cases |
| Longest chat, secret gate | 6 of 6 | 6 of 6 |
| Sample 2, M0 15 cases | 10 (9 of 13), 1 forbidden phrase placed | the same cases |

**(4) Rebuild.** `rebuild_all` on A and on R, then an archive of each: the same bytes. (A rebuild rewrites
`active_membership` rows on both; that is the rebuild's own behaviour, not the restore's.)

## Deterministic cases (`apps/sidecar/tests/test_restore.py`, `test_archive.py`)

A synthetic chat with edits, rerolls and a swipe, a deleted message, canon, a repair, an entity link, a memory mode,
summaries, embeddings, recorded requests, an append and a branch:

- the whole install into a fresh one: the same archive bytes, the same `ledger_state`, the same replays (with
  vectors); the next sync is a no-op and a recall works;
- one chat into an install with its own chats: its assertion and commit ids moved past the install's, its requests'
  assertion refs with them, the same replays;
- a chat deleted and restored into the same install: the same bytes, the same replays; a branch left here keeps its
  cleared link;
- a branch without its origin: host refs kept, link cleared and reported;
- refused with nothing of the archive written: a changed, cut or padded file, one replaced after its check, an
  unlisted, duplicate or encrypted member, a newer or foreign schema, a wrong level, another format version, a junk
  file, rows or commit parents naming anything outside the archive, a chat already here (by id or host chat);
- a Phase 13 `main` database (level 0024) archived and restored equals that database upgraded in place, with the same
  replays;
- settings already set here stay; the command's `--check`, stdin and refusal.

## Real host

On PocketRisu v1.13.0 (isolated, synthetic), the panel's **Export everything** and **Export this chat** saved their
files through the browser; the first held the same table bytes as the command's archive of the same database and
restored into a fresh one (`fixtures/host/export-smoke-v1.13.0-2026-09-29/`). Phones are not observed (K38).
