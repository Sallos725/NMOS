# 0015 — Retention of superseded projections

Status: accepted, 2026-09-24. Implements owner decision O5 for superseded generations (2026-09-23,
`docs/proposals/TRACK-B-PHASE-5-PLUS.md` §4 "Owner decisions" item 4). Decision D29. Known issue K17.

## Context

ADR 0006 keeps every projection generation. Changing the embedding model or endpoint, or a new
normalizer or chunker, leaves the previous vectors in place next to the new ones; they are never
searched again. Every revision still has one `revision_text` row per normalizer that ever ran
(`clean-v1` rows stay after the `clean-v2` upgrade of beta.12), although only the current one is read.
Embeddings are the largest derived table (137 MB of 303 MB at 25,000 messages with one chunk per
revision, `docs/perf/scale.md`), so one model change roughly doubles it.

The owner decided: keep what is costly to recreate, prune what is cheap. Superseded LLM extractions
and their assertions are kept for audit and rollback (they also serve older turns, ADR 0014).
Superseded embeddings and deterministic projections may be pruned once a new generation fully covers
the chat. Abandoned worldlines and host observations stay open.

## Decision

1. **Superseded vectors go once the active projection replaced them.** A vector of any embedding
   projection other than the active one (the most recently activated, ADR 0006 §3; `legacy:*` rows
   included) is deleted when:
   - the active projection has embedded the same revision, and
   - the revision's chat is fully covered: every eligible head revision that an older projection had
     embedded has an active vector (the coverage ADR 0006 §4 restores on activation), and no job of
     the active projection is queued or running for that chat.

   Eligible head revisions that no projection ever embedded (history beyond the first-sight backfill)
   do not block pruning: pruning never lowers coverage. A revision whose active job is `dead` does
   block it, so a failed re-embed keeps the old vectors.
2. **Only what was replaced.** Vectors of revisions the active projection did not embed (edited-away
   or rerolled revisions, abandoned branches, disabled messages) stay. Their retention is part of the
   open O5 question on abandoned worldlines.
3. **Switching back re-embeds.** Pruned work's `done` jobs become `obsolete` in the same statement, so
   activating the pruned projection again revives them in place (the job key is unique across
   statuses, ADR 0006 §2) and re-embeds the chat, at the provider's cost.
4. **Older normalized text goes once the current row exists.** At sidecar startup, after the
   normalized-text backfill, `revision_text` rows of other normalizers are deleted for revisions that
   have a current-normalizer row. Nothing reads them.
5. **Extractions are never pruned.** Superseded extractions, their assertions and discarded
   extractions (D22 rebuild) stay.
6. **When.** The worker prunes vectors in its 10-minute maintenance pass (with jobs and traces),
   500 revisions per transaction under the activation lock, so the active projection cannot change
   between the coverage check and the delete. The sidecar prunes text at startup. Both are idempotent.

## Consequences

- A model or endpoint change no longer leaves a second copy of every vector. Disk space is reused by
  PostgreSQL after autovacuum; the files do not shrink without a manual `VACUUM FULL`.
- Rolling back an embedding change after its coverage completed costs a full re-embed of what the old
  projection had covered. Before completion nothing is lost.
- Cost of a pass (`tools/bench_prune.py`, synthetic 10,000-message chat, two chunks per revision, two
  projections): the first pass deletes 20,000 vectors in ≈0.9 s in 500-revision transactions; a pass
  with nothing to prune takes ≈45 ms (≈3 ms at 1,000 messages).
- Abandoned worldlines, host observations and old vectors of revisions off the head still grow (K17).
