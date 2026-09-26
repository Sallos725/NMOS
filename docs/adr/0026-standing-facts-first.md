# 0026 — How the cast stand with each other comes first

Status: accepted, 2026-09-26. Owner report after `v0.1.0-beta.18` (not a phase feature): characters
forget things that were settled, for example a character who agreed to speak 반말 goes back to 존댓말.
Read side only: no extractor generation, no migration. Amends the fact ranking of D19 (the `known_by`
bonus) and the budget order of D32 (threads before facts).

## Context

The owner's report was reproduced read-only from the owner's database. The packets were rebuilt offline
with the sidecar's own functions from the stored assertions, the stored query and the head membership,
and the host's prompt window was inferred from the excluded candidates (about the last 11 messages).

- At turn 46 of a 69-turn chat, 라디아 started speaking 반말 to the persona (`event`, `major`,
  current). At turn 63 her reply used 존댓말 ("괜찮아요", "유우마 씨"), and the user's next message
  was "누나, 반말.".
- The packet for that reply held three threads and four facts: three `knows` facts about 블랑 and one
  about the persona. Among the relevant facts the agreement ranked 23rd and "라디아 relationship
  {{user}}: 누나" 30th, although the user's message named 라디아 twice.
- The next request that named 라디아 together with others ranked them 13th and 20th, behind "엘피 knows:
  계란 껍질이 들어갔을 때 …". The one request that brought the agreement named 라디아 alone.

Two causes, both on the read side:

1. **Ranking.** The owner's messages are long and name three or four characters, so every fact about any
   of them gets the same mention score (2.0). The tie was decided by `+1.0` for a name in `known_by`
   present in the message. `knows` facts carry long `known_by` lists, which name most of a scene's cast,
   so trivia came first. The lexical part of the score, divided by the query's trigrams, was below 0.05
   for every fact and ordered nothing.
2. **Budget.** At the default 600 tokens (Hangul counted at 1.5 tokens per character), the frame and
   Note take about 110 tokens and three threads about 150, which leaves room for four facts. Excerpts did
   not fit in any recent request.

## Decision

1. **A name in `known_by` is not a mention.** The `+1.0` is removed. A character in `hidden_from` who is
   addressed now still adds `+2.5` (D19: that fact is ranked first).
2. **Priors for equal mentions.** A fact that is mentioned (in the message, the previous reply, or as the
   persona's own fact for a first-person question) adds a prior to its score: `+0.5` for how two
   characters stand (`STANDING`: `relationship`, `feels_toward`) and `+0.3` for a `major` event. Both are
   below the 1.0 gap between a mention in the user's message and one in the previous reply, so they order
   facts of equal mention only. An unmentioned fact gets no prior and still needs the lexical bar.
   `STANDING` is a read-side set outside `REGISTRY`, like `HOLDER_PER_ITEM`, so it needs no new generation.
3. **Standing facts get the budget before threads.** `compile_packet` takes `lead_facts`. They are filled
   after state and before threads, and open the `<Facts>` section. The output order of the sections
   (state, threads, facts, excerpts) is unchanged. `STANDING` values are single per (subject, object), so
   a scene's cast has few of them.
4. **The trace records what fit.** `retrieval_trace.latency_ms` gains `kept_state`, `kept_facts` and
   `kept_threads` next to the offered `facts` and `threads`. The Inspector's Retrievals table shows facts
   as kept/offered (`?/n` for older traces).

## Evidence

The same request rebuilt with this change (`apps/sidecar/tests/test_fact_ranking.py` holds a synthetic
case of the same shape):

| Budget | Facts kept | What changed |
|---|---|---|
| 600 (before) | 4 of 12 | 3 × `블랑 knows …`, `{{user}} knows …` |
| 600 (after) | 6 of 12 | 라디아 → {{user}}: 누나, {{user}} → 라디아: 동생, 라디아 feels toward {{user}}: 설렘, and three more `feels_toward` of the cast; the agreement ranks 7th and does not fit |
| 1200 (after) | 12 of 12 | also "라디아 event: 유우마에게 말을 놓기 시작함" |

## Consequences

- At the default budget, a speech-level change that is stored only as an event can still be cut in a
  crowded scene. The budget is the user's setting (D2). A dedicated predicate for speech level and forms of
  address, which would join `STANDING`, needs a new extractor generation and an owner decision
  (`docs/proposals/SPEECH-AND-ADDRESS.md`; decided and implemented as ADR 0028).
- A stale relationship (K24) is now more likely to reach the packet, because standing facts come first.
- Threads fit less often at small budgets. They still come before other facts and excerpts.
- No stored row changes. The effect starts at the next request after the sidecar update.
