# 0063 — The excerpt lands on the answer (`packet-v11`)

Status: accepted, 2026-10-02 (step 2); amended the same day (step 3): **`packet-v11` is the default** and its tie-break
anchor is the question's keywords, both decided by the owner on the measurement in `docs/perf/answer-span.md`
(`docs/phases/PHASE-27.md` Q1–Q3, Q1b, Q5; AGE-31 under AGE-24). `packet-v10` stays available as
`NMOS_PACKET_POLICY=packet-v10`. No migration, no plugin build; one recorded recall option added.

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
   0040) or the contents cue (`packet.CONTENTS`: `내용`, "contents", "content of" — not the adjective), the excerpt grows
   from its best sentence
   by whole neighbouring sentences, after then before, up to `CUE_GROW_CHARS` (320) with no sentence cap — within the
   budget's `excerpt_chars` when that is smaller. Other questions keep `packet-v10`'s rule (four sentences within
   `excerpt_chars`). The prototype measured 320 for every question at a lost case and two more forbidden phrases, which
   is why the cue bounds it (`grown_excerpt(..., max_sentences=None)`).
3. **A new packet policy, not a recall option** (Q3): the excerpt's text changes, which is what a policy names (ADR 0053
   did the same for `packet-v10`). `packet-v11` is `packet-v10` in every other respect (the sections, the fill, the turn
   numbering, the bars). A trace records its policy, so recorded `packet-v10` requests replay as they were (ADR 0027).
   The default stayed `packet-v10` until Phase 27's evaluation (Q6) had run on the implementation, since every `main`
   merge that passes CI publishes `:edge` (AGENTS.md §13); **step 3 made `packet-v11` the default** (2026-10-02) on the
   results below.
4. **The tie-break anchor is a recorded recall option, `excerpt_anchor`, and `packet-v11`'s is the question's
   keywords** (Q1b). `packet-v10` breaks a tie between sentences holding the same keywords by the trigrams they share
   with the question and the previous reply (`"focus"`). The prototype's measurements used the question's keywords
   alone, so step 2 measured both: with `"focus"` `packet-v11` gained +2 on the M0 main cases that need memory but
   raised the forbidden-phrase total over the twelve sets 93 → 96 (Phase 27's stop condition); with `"keywords"` it
   gained +3 (16 → 19 of 23) and lowered it to 87, no set worse by more than one case. So `excerpt_anchor` defaults to
   `"keywords"` — the question's keywords, or the question itself when it has none; never the previous reply — which
   only a `SPAN_POLICIES` policy reads (`packet-v10` keeps `"focus"` whatever the option says). It is recorded with the
   other recall options, so a trace replays with the anchor it had, and a trace from before the option (every one
   `packet-v10`) replays with `"focus"`; `tools/eval_rp.py --anchor focus` replays the other for an evaluation. No
   request sets it; nothing in the UI.

## Consequences

- Under `packet-v11` a paraphrased question about a long message gets the chunk it is about, and a why or contents
  question gets the whole of a short-sentence explanation up to 320 characters; everything else in the packet is
  `packet-v10`'s. Measured (`docs/perf/answer-span.md`, the owner's replays, twelve sets, three runs each, every run
  the same): the M0 main cases that need memory 16 → 19 of 23 with vectors and 14 → 16 without; over the twelve sets
  forbidden phrases 93 → 87; no set worse by more than one case; packets never larger, and on sample 2 smaller
  (−14.88 % with vectors, −6.96 % without), which the owner allowed by rewording Q5's bound to one side: the rules
  bound excerpts below `excerpt_chars` by construction (a chunk ≤ 700 characters, a why or contents excerpt ≤ 320
  against 960 at 4,000 tokens), and that set lost nothing measurable (+1 case, forbidden 2 → 0).
- Risks that remain: a word hit whose keyword sentence lies outside the chunk the vector found loses that sentence
  (measured net positive); a why or contents excerpt without the four-sentence cap can carry a value the story has
  since replaced (K39, within 320 characters); a smaller packet offers less context on chats with many such
  questions (not a loss on the sets measured). Request-path latency was not part of the replays; the live bench is.
- Deterministic cases: `test_packet_v11.py`, one per branch of Q1–Q3 and Q1b. High risk (AGENTS.md §14): memory
  selection — what text an excerpt shows; pinned by those cases, and the unchanged default by `test_packet_v10.py`
  and `test_memory_eval.py`.
