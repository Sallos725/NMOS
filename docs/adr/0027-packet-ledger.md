# 0027 — Packet ledger, excerpt room, echo and as-of replay

Status: accepted, 2026-09-26 (`docs/phases/PHASE-9.md`). The owner asked for this work on a new branch
("새 브랜치 만들어서 하고싶은대로 해봐") and approved merging it after review. Invariants 8 and 10 are implemented at packet level. No invariant changes.

## Context

Retrieval gathers candidates (state, open promises, facts, claims, excerpts). `compile_packet` then fills
the reserved budget in that order. Before this ADR the trace recorded the excerpts it placed, but for
state, threads and facts only how many lines were offered, not which ones reached the model:

- **Invariant 8** (retrieved, placed, used are separate decisions) had no record of "placed" for
  semantic memory, and nothing at all about "used".
- **Invariant 10** (provenance) held in storage but broke at the packet. A packet line carried a turn
  number, and no stored row said which assertion it was.
- **Selection could not be evaluated.** Changing the packet compiler could only be judged on synthetic
  cases whose packets averaged 167 tokens against a 600-token budget, so they never tested the budget.

The owner's production traces (168 requests, 2026-09-23 to 09-25, 4 chats, read as aggregates only;
`docs/perf/phase9-packets.md`) show what the budget did:
- The median packet was 566 of 600 estimated tokens. The most common packet held 12 fact and claim lines
  and 3 promises.
- An excerpt was placed in 7 of 168 requests (12 excerpts in all). 114 packets had facts and
  no excerpt. 42 dropped an eligible excerpt.
- The Korean estimate is 1.5 tokens per character. A two-sentence Korean excerpt of up to 480 characters
  is estimated at up to 720 tokens, so after the fact lines, raw evidence almost never fit.
- Exact wording (a password, a promise's words, a line of dialogue) exists only in raw evidence.

## Decision

1. **Packet ledger.** The compiler records every offered line in order: `kind` (state, thread, fact,
   claim, excerpt), `ref` (the assertion id; the revision id for an excerpt; the key for state), `turn`,
   estimated cost `tok`, `placed`, `why` (`placed`, `budget`, `state_cap`, `repeats`), display `text`, and
   the `content` a reply could reuse. A shortened excerpt also records its `form` and the text actually
   placed. A repeating excerpt records the line it `repeats`, and a placed secret its `marks.hidden_from`.
   Migration 0020 stores the ledger on `retrieval_trace.lines`, together with the request's inputs:
   - `previous_ai`, `in_context`, `budget_tokens`;
   - `upto_position` (the head's last position, i.e. the user's message);
   - `policy`, `extractor_key`, `embed_projection`, `rules_version`;
   - `recall_options` (top_k, bars and limits).

   The trace keeps its retention (`NMOS_TRACE_RETENTION_DAYS`) and is deleted with its conversation.
2. **Packet policies.** Compilers are named, and a trace records which one built its packet:
   - `packet-v0` is the compiler before this ADR.
   - `packet-v1` (default, `NMOS_PACKET_POLICY`) first sets aside excerpts that mostly restate an offered
     thread, fact or claim line: half of the excerpt's spans are in that line's content, names left out
     (`why: repeats`).
   - It then keeps `EXCERPT_SHARE` (30 %) of the budget inside the frame for the best-ranked remaining
     excerpt, and fills state, threads and facts. To fit, the excerpt falls back to its best sentence
     (`Excerpt.short`), or is cut at a character boundary (at least 24 characters). Whatever the other
     sections leave may bring it back to full length.
   - Other excerpts are placed only whole or as one sentence, never cut.
   - Parser state may take at most `STATE_SHARE` (40 %), so a sim bot's status window cannot take the
     whole packet.
   - Section order in the output, the Note and the XML are unchanged. Only the budget split differs.
3. **Echo (report only).** The reply to a request is the head message right after `upto_position`, when
   it is the character's. A placed line is echoed when that reply reuses a span of its content that the
   request itself did not hold:
   - **Korean (or other CJK) content:** 4 characters, spaces ignored, whose first or last 3 characters
     occur in neither the query nor the previous reply. A question's word with another particle does not
     count.
   - **Latin-script content:** a word of at least 4 letters that is not a common word.

   A line's echo value is the share of its spans reused. Echo is a surface measure: a secret the reply
   rightly keeps is used without being echoed, and a reply can repeat what the prompt held anyway. It never
   feeds ranking in this ADR. A placed line with `hidden_from` that the reply echoes is flagged as a
   possible leak (K11).

   *Revised during implementation:* the first definition, the share of a line's trigrams found in the
   reply with a bar of 0.5, found no echo at all in real replies that plainly used their packet. The
   replies take the key phrase ("보라일곱이야", "은빛갈매기호"), not the line (`docs/perf/phase9-packets.md`).
4. **As-of replay (bitemporal).** A recorded request can be gathered again as of its own time, along two
   axes:
   - **Story position:** the head cut at `upto_position`, for lexical, vector, state, allBefore cut and
     facts.
   - **Knowledge time:** only extractions created by the trace's time and not yet discarded then,
     vectors written by then (new `revision_embedding.created_at`; older rows count as known), and owner
     links in force then.

   The request's own recall options, generations and budget are used. It is valid only while the story up
   to `upto_position` is unchanged: the head is the trace's commit, or descends from it through commits
   whose changes all lie after that position (a reroll of the reply, later edits). Otherwise the replay
   and the echo report `changed`. With the same policy and inputs, a replay reproduces the recorded
   ledger exactly (CI). With another policy it is an offline A/B on real requests. The request path keeps
   its SQL: the as-of read is a separate statement.
5. **Read-only surfaces.**
   - `GET /v1/trace/{id}/audit`: the ledger with echo.
   - `GET /v1/trace/{id}/replay?policy=`: the packet compiled again.
   - Inspector "Last packet": every offered line with its outcome, cost and echo. The retrievals table
     shows what each packet held.
   - `tools/replay_packets.py`: runs a policy A/B over recorded traces in a read-only session.

## Consequences

- Each trace grows by its ledger and inputs: about 2–15 KB depending on the reply length and the prompt
  window (`docs/perf/phase9-packets.md`). Traces stay pruned after 30 days by default.
- `packet-v1` gives excerpts room that facts used to take, so fewer fact lines fit: about 1–3 fewer
  lines when a non-repeating excerpt is eligible, and none fewer otherwise. The memory evaluation's two
  budget-pressure cases answer only with `packet-v1`, and every other case answers the same under both
  (`docs/perf/eval-baseline.md`). In the answer probe (two response models, synthetic scenes), questions
  whose answer was only in a message's words were answered in every run in which recall found the
  message, and never with `packet-v0`. Questions about facts answered alike under both
  (`docs/perf/phase9-packets.md`). Real chats are to be compared with the replay tool once traces with a
  ledger exist.
- Traces from before migration 0020 are listed as `not_recorded` by replay and audit.
- A replay compiles with the code that runs it. The packet compiler is named (`policy`), but the
  gathering code is not versioned. A trace recorded before a change to gathering reproduces only while
  the change does not touch it. The fix below changed the first request of the Phase 9 smoke chat, for
  example.
- **Found with the ledger (fixed with this ADR).** The plugin anchors in-context detection only on
  messages of at least 16 characters. A short first message therefore reached the sidecar with no
  in-context ids and was recalled as an excerpt of itself. Gathering now always treats the head's last
  message as in the prompt: the host always sends the latest message, and D13 injects only when it is
  there. The recorded `in_context` stays what the plugin sent.
- A replay is exact except for an extraction or vector committed concurrently with the request (its
  `created_at` precedes the trace, but the request did not see it), a re-activated generation, a
  changed parser rule set (state rows are rewritten), and the persona name (the current one is used).
  Each of these can only differ, never inject stale memory: replay never writes a packet or a trace.
- The token estimate itself is unchanged (conservative, 1.5 per non-ASCII character). On three measured
  tokenizers Korean prose costs 0.74–0.98 tokens per character, so the reserve is under-used for Korean
  (K26). Changing the estimate is a separate decision: a smaller estimate can overflow the reserve for
  tokenizers that were not measured.
