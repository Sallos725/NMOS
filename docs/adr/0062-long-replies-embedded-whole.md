# 0062 — Long replies embedded whole: the chunk cap, a setting of the projection

Status: accepted, 2026-10-02. A correction under AGE-24 (real-chat recall), for K13's embedding half; amends the cap
of #13 (Track A) that `vectors.MAX_CHUNKS` fixed at 8. No migration, no plugin build, no recall option; a new embedding
projection (D20) for every install, re-embedded in the background once (ADR 0014 item 5, K18).

## Context

A message is embedded in chunks of 700 normalized characters, at most 8 of them from its start (#13): 5,600 characters.
The owner's long chats — the chats AGE-24 measures — write replies of about 10,000 characters (the main M0 chat:
≈12,000 characters a turn, 73 turns). Under the cap, nothing said in the second half of such a reply had a vector:
lexical recall and the keyword route read the whole message, but a paraphrased question — what vectors are for —
could not reach it. Vectors are worth cases on these chats (one or two cases that need memory per M0 run,
`docs/perf/lexical-recall.md`), and half of each reply was outside their reach.

The cap protected two things: the worker's embedding time (one call per chunk; `process_embed`) and the request path's
exact cosine search, which grows with the number of vectors (≈11 µs a chunk, `docs/perf/scale.md`). Neither needs a
cap at 8 for the chats it hurts: a 73-turn chat with 18 chunks a reply holds ≈1,300 vectors, the search takes a few
milliseconds, and embedding 18 chunks instead of 8 takes a few seconds more per reply in the background. The 10,000-
message benchmark chat (1,200-character replies, two chunks each) is untouched by any cap above 2.

## Decision

1. **The cap is a setting, `NMOS_EMBED_MAX_CHUNKS`, default 24** (`Settings.embed_max_chunks`): 16,800 characters,
   which covers the owner's replies whole and anything up to that length. Beyond it a message is still partly embedded
   and the Inspector still says so (K13 stays listed, narrower).
2. **The cap belongs to the projection.** It is in the projection key as `max_chunks` (it already was, as the constant),
   so a projection embeds by its own cap: `process_embed` reads the cap from the generation's spec, not from the
   current setting, and a projection recorded before the cap was in the spec cuts at 8, as it did. A changed cap is a
   new projection: activation queues the latest `NMOS_EMBED_BACKFILL` messages of each chat first and the rest an
   earlier projection had covered at background priority (ADR 0006 §4), and the superseded vectors are pruned once
   the chat is covered (ADR 0015).
3. **Nothing else changes.** `vector_candidates` still takes the best chunk per message (one candidate per message),
   the excerpt of a vector-only hit is still its chunk, the similarity bar (`NMOS_VECTOR_MIN_SIM`) and the fusion are
   as they were. Extraction's own limits (6,000 characters of the target turn, 2,000 of a context message) are not
   touched here.

## Consequences

- A paraphrased question about something said late in a long reply can now find it; on chats with short replies
  nothing changes.
- Every install re-embeds once on upgrade (local embeddings, in the background; a 10,000-message chat with two chunks
  a message is the same work as any projection change; a chat with long replies up to 2.25× that). Until a chat is
  embedded again, its requests search the vectors the new projection has so far — the recent window first.
- A chat with long replies holds up to three times the vectors it did; the exact search grows with them (≈11 µs a
  chunk). For the owner's chats that is milliseconds. A user who wants the old cost sets `NMOS_EMBED_MAX_CHUNKS=8`
  (its own projection, re-embedded once).
- Recorded requests replay as they were: a replay searches the trace's projection (ADR 0027), and when that projection's
  vectors were pruned, the replay says so, as after any projection change.
