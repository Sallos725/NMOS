# 0062 — The chunk cap, a setting of the projection

Status: accepted, 2026-10-02. Under AGE-24 (real-chat recall), for K13's embedding half; amends the cap of #13 (Track
A) that `vectors.MAX_CHUNKS` fixed at 8 in where it is set, not in its value. No migration, no plugin build, no recall
option, and — the default being the cap it was — no new projection for an install that keeps the default.

## Context

A message is embedded in chunks of 700 normalized characters, at most 8 of them from its start (#13): 5,600
characters. Beyond that a message is embedded in part, which the Inspector shows (K13). The cap protects the worker's
embedding time (one call per chunk, `process_embed`) and the request path's exact cosine search, which grows with the
number of vectors (≈11 µs a chunk, `docs/perf/scale.md`).

The owner's long chats — the chats AGE-24 measures — write replies of ≈10,000–15,000 raw characters, and the first
draft of this ADR took the cap to cut their second half off from vectors, and raised the default to 24. Measured on
the evaluation copy of the M0 v2 main chat (Codex, on #242), it does not: the chat's 147 active messages run to 15,621
raw characters but to **5,481 normalized** (`clean-v3`, the text the chunks are cut from: `packet.clean_text` drops
the status HTML, the style and script blocks and NMOS's own markup that make the raw text long). No message is cut at
8 chunks, no message's spans change between a cap of 8 and 24, and the 40 evaluation cases compiled the same packets
under both (16 of the 23 cases that need memory, 32 of 40 in all, under either; `docs/perf/query-embedding.md`). So
the cap was never the reason a question about that chat lost its answer; the diagnosis of its seven failing cases is
Phase 27's (the excerpt's span, `docs/phases/PHASE-27.md`).

What stays true: a chat whose *normalized* messages exceed 5,600 characters (long documents pasted into the chat, a
model that writes long prose without markup) has nothing past that in vectors, and the cap was a constant no install
could change without a build.

## Decision

1. **The cap is a setting, `NMOS_EMBED_MAX_CHUNKS`, default 8** (`Settings.embed_max_chunks`): the cap it was, so an
   install that keeps the default embeds as before and does not re-embed on upgrade. A value under 1 is refused at
   startup (it would embed nothing and mark every embed job done).
2. **The cap belongs to the projection.** It is in the projection key as `max_chunks` (it already was, as the constant:
   the default's key is the release before's, pinned by `test_long_messages.py`), so a projection embeds by its own
   cap: `process_embed` reads the cap from the generation's spec, not from the current setting, and a projection
   recorded before the cap was in the spec cuts at 8, as it did. A changed cap is a new projection: activation queues
   the latest `NMOS_EMBED_BACKFILL` messages of each chat first and the rest an earlier projection had covered at
   background priority (ADR 0006 §4), and the superseded vectors are pruned once the chat is covered (ADR 0015).
3. **Nothing else changes.** `vector_candidates` still takes the best chunk per message (one candidate per message),
   the excerpt of a vector-only hit is still its chunk, the similarity bar (`NMOS_VECTOR_MIN_SIM`) and the fusion are
   as they were. Extraction's own limits (6,000 characters of the target turn, 2,000 of a context message) are not
   touched here.

## Consequences

- An install that keeps the default is unchanged: the same projection key, the same vectors, nothing re-embedded on
  upgrade.
- A user whose normalized messages are longer than 5,600 characters raises the cap (24 covers 16,800) and gets their
  own projection, re-embedded once in the background (local embeddings; the recent window first; until a chat is
  embedded again its requests search what the new projection has so far). The exact search grows with the vectors
  (≈11 µs a chunk): milliseconds for a chat of a few thousand messages. Going back to the default is a projection
  change too: the default's projection again, re-embedded once where its vectors were pruned (ADR 0015).
- The owner's chats gain nothing from a higher cap: their messages are within the default once normalized. AGE-24's
  recall gaps are not here.
- Recorded requests replay as they were: a replay searches the trace's projection (ADR 0027), and when that projection's
  vectors were pruned, the replay says so, as after any projection change.
