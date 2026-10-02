# Phase 27 — The excerpt lands on the answer: a vector hit's span, and room for an explanation

> **Status: approved 2026-10-02 (every proposed answer; the owner's order: before 0.3.0, AGE-7). Step 1 done; step 2
> (`packet-v11`, the deterministic cases, the ADR) next.** Not a roadmap stage: a correction found by measurement under AGE-24
> (the real-chat recall gaps), proposed from the diagnosis of draft PR #241 (`docs/perf/age24-recall-candidate.md` on
> its branch): on the M0 v2 main chat the request often *retrieves* the message that holds the answer and then excerpts
> another part of it. This phase ports the two general rules of that prototype into the packet compiler, behind a new
> packet policy, so that they run in production and are measured on every set. The prototype's one-case rules
> (enumerated lists, "what was it packed in") and its passage embeddings stay out. The review of #242 measured the
> other suspected cause, the embedding chunk cap: the M0 main packets are the same under a cap of 24, so the excerpt's
> span is the open lever (`docs/perf/query-embedding.md`).

## Questions and proposed answers

| # | Question | Proposed answer | Alternatives |
|---|---|---|---|
| Q1 | Where does the excerpt of a message found by **both** a word route and vectors come from? | **The vector chunk.** Today a lexical or keyword hit excerpts the whole message (`retrieval.gather`: `clean = c["clean"]` when `user_score` or `keyword_score`), grown from the sentence that holds most of the message's keywords; a vector-only hit excerpts its chunk. With `packet-v11`, a candidate whose vector similarity is at or above `vector_min_sim` excerpts within that chunk (`text_start`–`text_end`) even when the word routes also found the message: the chunk is the part of the message the question is about, and the words only say the message is relevant. The prototype measured this rule alone at +1 case that needs memory (16 → 17 of 23). | Keep the whole message and raise the chunk's sentences in the rank (more code, same intent); the whole message as today. |
| Q2 | How does an excerpt grow when the message asks **why**, or for the **contents** of something? | **By characters, not by four sentences.** `packet-v10` grows an excerpt from its best sentence by whole neighbouring sentences, at most `GROW_MAX_SENTENCES` (4), within its length. Dialogue is often cut into short sentences, so an explanation that follows a question is left out although the excerpt's length has hundreds of characters free. With `packet-v11`, when the message has the why cue (`facts.WHY`, ADR 0040) or asks for contents (`내용`, "contents"), the excerpt grows by whole sentences up to **320 characters** with no sentence cap; other questions keep the four-sentence rule. The prototype measured this at +2 (17 → 19); applied to every question it lost a case and placed two more forbidden phrases, which is why the cue bounds it. | 320 characters for every question (rejected by measurement); a larger figure (480: untested). |
| Q3 | A new packet policy or a recall option? | **A new packet policy, `packet-v11`** (the default; `packet-v10` stays available as `NMOS_PACKET_POLICY`): the excerpt's text changes, and that is what a policy names (ADR 0053 bumped to `packet-v10` for the same reason). A trace records its policy, so recorded `packet-v10` requests replay as they were (ADR 0027). | A recorded recall option (the excerpt is compiled, not recalled: a policy is the right place). |
| Q4 | What is **not** in this phase? | The prototype's enumerated-list span, its container-question span (each gained one case on the development set and names a question shape), its local passage embeddings (rejected by its own measurement), and any change to candidates, fusion, ranking, the budget or the fitter. The anchor of the excerpt stays the message's keywords and the question (the prototype also dropped the previous reply from the tie-break; measured together with Q1, not apart: left out until measured alone). | Take the one-case rules too (no held-out evidence). |
| Q5 | Does the packet grow? | **Within the length it has.** An excerpt's length is still `excerpt_chars` from the budget (960 at 4,000 tokens; ADR 0049); Q2 only lets more short sentences into that length, Q1 only moves the excerpt into the chunk. Measured: the median packet size per set must stay within ±5 % of `packet-v10`'s. | A larger excerpt length (changes the budget's shape; not this phase). |
| Q6 | How is it measured? | **Replays only, no model call**, by the owner on the local copies (the cases stay outside the repository): the M0 main chat (vectors on and off; the cases that need memory), M0 sample 2, the synthetic 240-turn chat's four cuts and its first-cue cases, the restored copies' probes of Phases 21 and 24; `packet-v11` against `packet-v10` at 4,000 tokens with the keyword route on, each set three times. The prototype's frozen-candidate gate (`tools/check_recall_candidate.py` on its branch) may serve as the per-case regression check. Then the live bench harness (the NMOS lane) on the merged commit, which is where AGE-24's criterion is measured. Deterministic cases for Q1–Q3. | The M0 main chat only (the prototype's set: tuned on it, so it cannot validate itself). |

## Goal

When the message that holds the answer is retrieved, the excerpt shows the answer: the chunk the question is about,
and the whole of a short-sentence explanation.

## Evidence behind the scope

From draft PR #241 (`codex/age24-recall-improvement`), an evaluation-only prototype that patches `retrieval.fuse` and
`retrieval.grown_excerpt` inside a read-only replay of the M0 v2 main chat (`extract-v15`, vectors on, keyword route on,
`packet-v10`, 4,000 tokens; 23 cases that need memory; the old traces replay with `first_cue`, `history_marks` and
`name_variants` off, as a replay of a trace that did not record them does):

| Variant | needing memory | all | forbidden |
|---|---:|---:|---:|
| `packet-v10` as today | 16/23 | 32/40 | 1 |
| Q1 alone (vector span, question-anchored) | 17/23 | 33/40 | 1 |
| Q2 for every question | 18/23 | 33/40 | **3** |
| Q1 + Q2 for why/contents questions only (this phase) | 19/23 | 35/40 | 1 |
| + enumerated-list and container spans (not this phase) | 20/23 | 36/40 | 1 |

Caveats the prototype states itself: tuned on this set, no held-out validation; packet-evidence scores, not generated
answers; the original evaluation's runtime commit is unknown. Its diagnosis of the seven failures: five of them had an
answer-bearing message among the candidates offered to the packet, and the excerpt missed the span. None of this ran in
production: the prototype does not change the sidecar.

## In scope (Phase 27)

1. `packet-v11` (Q1–Q3) in `packet.py` and `retrieval.gather`: the chunk as the excerpt's source for a candidate with
   a qualifying vector similarity, and character-bounded growth for why/contents questions; the default policy.
2. Deterministic cases: a message found by a keyword and by vectors excerpts within its chunk under `packet-v11` and
   the whole message under `packet-v10`; a why question's excerpt takes five short sentences within 320 characters
   under `packet-v11` and four under `packet-v10`; an ordinary question keeps four; a recorded `packet-v10` request
   replays as it was.
3. Evaluation (Q6) and docs: an ADR, `ARCHITECTURE.md` (a decision), CHANGELOG, README (`NMOS_PACKET_POLICY`),
   KNOWN-ISSUES (K39: longer windows carry more replaced values), `docs/perf/answer-span.md`.

## Out of scope (Phase 27)

- Q4's items; passage embeddings; a model call; changes to candidates, fusion, ranking, the budget or the fitter.
- The evaluation harness of PR #241 as repository tooling (its hard-coded copy identifiers and test configuration are
  that PR's to settle).

## Acceptance criteria

- [ ] Every existing test and memory-evaluation case passes; recorded `packet-v10` requests replay as they were.
- [ ] The deterministic cases of In scope 2.
- [ ] Q6's sets, three runs each: the M0 main cases that need memory at least +2 (vectors on) and not fewer (vectors
      off); no other set worse by more than one case in any run; forbidden phrases placed not higher in total; the
      median packet size per set within ±5 %.
- [ ] Request-path latency unchanged within noise (`tools/bench_story.py`, 10,000 messages; the excerpt rules are pure
      functions on text already read).

## Steps (one pull request each)

1. This document, approved; AGENTS §2 and STATUS name Phase 27 current.
2. `packet-v11`, the deterministic cases, the ADR.
3. The evaluation and docs; Phase 27 complete.

## Stop conditions

Stop and ask the owner when:

- a recorded `packet-v10` request replays differently;
- any Q6 set gets worse by more than one case, or forbidden phrases rise in total;
- the M0 main gain needs one of Q4's one-case rules to appear.

High risk (AGENTS.md §14): memory selection (what text an excerpt shows); K39.
