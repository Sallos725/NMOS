# 0063 — The excerpt lands on the answer (`packet-v11`)

Status: accepted, 2026-10-02. Phase 27 step 2 (`docs/phases/PHASE-27.md` Q1–Q3 and Q1b, approved by the owner; AGE-31
under AGE-24). A new packet policy behind `NMOS_PACKET_POLICY`; the default stays `packet-v10` until Phase 27's
evaluation passes (step 3). No migration, no plugin build; one recorded recall option added.

## Context

On the M0 v2 main chat the request often retrieves the message that holds the answer and excerpts another part of it:
of the seven cases that need memory and fail, five had an answer-bearing message among the candidates offered to the
packet (the diagnosis of draft PR #241, `docs/phases/PHASE-27.md`). Two causes, both in how `packet-v10` chooses the
excerpt's text (ADR 0053):

- A message found by a word route (lexical recall or the keyword route) is excerpted from the whole message, grown from
  the sentence holding most of the message's keywords; only a vector-only hit is excerpted from its chunk. When the
  question paraphrases what the message says — which is what the vector found — the keywords point at another part of a
  long message and the excerpt misses the chunk the question is about.
- The excerpt grows by whole neighbouring sentences up to four (`GROW_MAX_SENTENCES`, the owner's bound against stale
  values, K39). Dialogue is cut into short sentences, so an explanation that follows a question is left out while the
  excerpt's length has hundreds of characters free.

The embedding chunk cap was the other suspect and is not the cause: the M0 main packets are the same under a cap of 24
(ADR 0062, `docs/perf/query-embedding.md`).

## Decision

1. **`packet-v11`: a word hit with a qualifying vector excerpts within its chunk** (Q1). A candidate found by lexical
   recall or the keyword route whose vector similarity is at or above `vector_min_sim` takes its excerpt from the chunk
   the vector found (`text_start`–`text_end`), as a vector-only hit always did; a word hit whose vector is below the
   bar, or that has none, is still excerpted from the whole message; a vector-only hit is unchanged. The chunk is the
   part of the message the question is about; the words only say the message is relevant (`retrieval.gather`,
   `packet.SPAN_POLICIES`).
2. **A why or contents question grows by characters** (Q2). When the user's message has the why cue (`facts.WHY`, ADR
   0040) or the contents cue (`packet.CONTENTS`: `내용`, "content", "contents"), the excerpt grows from its best sentence
   by whole neighbouring sentences, after then before, up to `CUE_GROW_CHARS` (320) with no sentence cap — within the
   budget's `excerpt_chars` when that is smaller. Other questions keep `packet-v10`'s rule (four sentences within
   `excerpt_chars`). The prototype measured 320 for every question at a lost case and two more forbidden phrases, which
   is why the cue bounds it (`grown_excerpt(..., max_sentences=None)`).
3. **A new packet policy, not a recall option** (Q3): the excerpt's text changes, which is what a policy names (ADR 0053
   did the same for `packet-v10`). `packet-v11` is `packet-v10` in every other respect (the sections, the fill, the turn
   numbering, the bars). A trace records its policy, so recorded `packet-v10` requests replay as they were (ADR 0027).
   **The default stays `packet-v10`** until Phase 27's evaluation (Q6) passes on the implementation: every `main` merge
   that passes CI publishes `:edge` (AGENTS.md §13), and the policy must not be served before the other sets are
   checked. The step 3 PR that carries the passing results switches the default.
4. **The tie-break anchor is a recorded recall option, `excerpt_anchor`** (Q1b). `packet-v10` breaks a tie between
   sentences holding the same keywords by the trigrams they share with the question and the previous reply (`focus`).
   The prototype's measurements (16 → 17 → 19 of 23) used the question's keywords alone as that anchor, so which anchor
   the gain needs is unknown. `excerpt_anchor` is `"focus"` (today's; the default; every policy) or `"keywords"` (the
   prototype's; `packet-v11` only: `packet-v10` keeps today's whatever the option says). It is recorded with the other
   recall options, so a trace replays with the anchor it had and a trace from before it replays with `"focus"`;
   `tools/eval_rp.py --anchor` sets it for an evaluation. Step 2's measurement decides: the anchor stays `"focus"`
   unless the gain needs the other, in which case `packet-v11` takes it and this ADR is amended. No request sets it;
   nothing in the UI.

## Consequences

- Under `packet-v11` a paraphrased question about a long message gets the chunk it is about, and a why or contents
  question gets the whole of a short-sentence explanation up to 320 characters; everything else in the packet is
  `packet-v10`'s. Measured so far only by the prototype on the development set (16 → 19 of 23 with its anchor); the
  policy's own numbers come from Phase 27's replays (Q6, both anchors) before it becomes the default.
- Risks the evaluation watches (Phase 27's stop conditions): a word hit whose keyword sentence lies outside the chunk
  the vector found loses that sentence (Q1's effect was +1 net on the development set); a longer why or contents
  excerpt can carry a value the story has since replaced (K39; step 3 records it); the median packet size per set
  must stay within ±5 %.
- Deterministic cases: `test_packet_v11.py`, one per branch of Q1–Q3 and Q1b. High risk (AGENTS.md §14): memory
  selection — what text an excerpt shows; pinned by those cases, and the unchanged default by `test_packet_v10.py`
  and `test_memory_eval.py`.
