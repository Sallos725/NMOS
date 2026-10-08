# 0068 — What a line is for, and memory that stops repeating itself (`packet-v14`)

Status: accepted, the default since 2026-10-08 (owner, on the live run, PHASE-34 Q6); proposed 2026-10-07
(`docs/phases/PHASE-34.md` Q1–Q5, approved by the owner, Q1/Q2/Q3/Q9 amended on the measurement; AGE-10). Adds the
policy `packet-v14` on top of `packet-v13`; it replaces `packet-v12` as the default. No prompt, generation key, stored
row or migration changes.

## Context

Phase 33's baseline (`docs/perf/phase33-baseline.md`): in live play 61 % of a packet's lines were placed in the request
before it too. (Its echo figures came from the bench's scripted replies and say nothing of how a model uses repeated
memory; that is measured on real replies, PHASE-34 Q8 d.) Nothing looked across requests: every packet was chosen from
scratch. The original asks for labels (§48) and for supportive memory to stop
coming back merely because it is related (§49).

## Decision

Under `packet-v14` (`packet.LABEL_POLICIES`, `REST_POLICIES`):

1. **Labels** (Q1), by rule at compile time, on every ledger line. **Required**: the state, the cast, the story-so-far
   summary, Private and Secret lines, a fact, claim or thread the question names, a quote, and the first excerpt (the
   one the budget keeps room for, ADR 0026). **Risky**: a disputed or contradicted line. **Supportive**: the rest (scene
   summaries, facts and excerpts found by overlap, vectors or the previous reply).
2. **The rest** (Q2, Q3; `overuse`): a supportive line placed in each of the last `rest_after` requests of the chat
   (`RecallOptions.rest_after`, recorded, `NMOS_REST_AFTER`, 2 by default), none of whose replies echoed it
   (`spans.reuse`, ADR 0027), is **left out** for the next two requests and its slot goes to the next candidate. It does
   not rest when the question names it, when the question's own words found it (an excerpt hit lexically or by
   keyword), when the question asks about the past or how it started (`HISTORY_CUE`), or when a reply used it. Required
   lines never rest, a line with a knowledge mark among them wherever it is placed, and the first excerpt (the
   reserved one) among them: a resting excerpt, and one under the activation threshold (item 3), is offered marked, and
   the compiler, after its repeat check and the filters, reserves the first excerpt that survives and is neither, or else
   the first that survives; it leaves out only the other marked ones. A scene summary rests as the other supportive lines do; the story so far
   never does. A risky line is offered after the other supportive lines: ranked after them inside `relevant_facts`,
   before its limit and event quota choose, and after the ordinary facts when it is a lead line (how two stand). (Corrected 2026-10-08 on a review and its follow-up: the rest had run before the first excerpt was
   chosen, then before the repeat check; scene summaries had never rested; risky lines had only been labeled, then
   ordered after the limits.) The requests are the chat's recorded traces and the replies the messages after them; nothing is
   stored. The trace counts the lines left out (`rested`).
3. **The activation threshold** (Q4): an excerpt after the first needs `EXCERPT_FLOOR` (0.5) of the best fused score or
   a word hit (`below_floor`); the compiler applies it at the reserved place's stage (item 2), so it never takes the
   first excerpt that survives the repeat check.
4. **Replay** (Q5): a replay reads the traces recorded before the request (`audit.replay`), each with the reply after
   it as it stood then: the membership rebuilt from the commits' and appends' ops recorded before the request, as the
   ledger rebuild replays them (corrected 2026-10-08 on a review and its follow-ups: a reply written later had
   counted, then a reply edited and edited back read as its edit, then a reorder that records only a `set`), and a sequential replay passes its own packets instead
   (`tools/replay_sequence.py`).

## Consequences

- On S1's live run replayed request by request (241 requests, three replays alike; `docs/perf/phase34-rest.md`):
  supportive lines repeat 23 % less and their stale tokens fall 71 % (re-measured after the review fixes); the whole
  packet repeats less too. The bench and the quote set answer as `packet-v13` does. That memory repeats less does not by itself show that replies use memory
  better: the bench's replies are scripted; real replies are compared under Q8 (d).
- A resting line is out of the packet for two requests: a later question that needs it without naming it, without its
  words and without asking about the past finds it missing then. The live run (Q8 d) measures it; `NMOS_REST_AFTER=3`
  rests less often.
- Rejected: a tired line offered after the others (placed anyway whenever the budget had room, nearly always on S1:
  −6 % repeats); the story so far as supportive (70 % of the supportive stale tokens, but the continuity every packet
  should carry); waking a line the previous reply names (the reply names the main characters nearly always, so nothing
  rested); a stored cooldown per line.
