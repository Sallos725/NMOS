# 0066 — Recall that knows what changed (`packet-v12`)

Status: accepted, 2026-10-05 (`docs/phases/PHASE-31.md` Q1–Q4, approved by the owner; AGE-24). Adds the policy
`packet-v12` behind `NMOS_PACKET_POLICY`; **the default stays `packet-v11`** until step 3's measurement and the owner's
decision. No prompt, generation key, stored row or migration changes.

## Context

The PHASE-28 live gate on the focused `extract-v16` (`docs/perf/phase28-live-gate-9947d2c.md`) passed everything
extraction decides and missed three sets on recall, each a miss `extract-v15` shows too: on S1 turn 240 and S2 a packet
carried an older excerpt stating a value the story had since replaced (K39) and printed an ended role on a question
about now; on S3 the lent-book question (K43) placed the lending message, but its excerpt anchored on a sentence 13
sentences before the title, because the question's keywords tied across three sentences and `keywords()` drops the
one-character word 책 that separated them (`docs/perf/k43-offline-diagnosis.md`).

## Decision

Under `packet-v12` (`packet.CHANGE_POLICIES`), in `retrieval.gather`:

1. **An excerpt of a replaced value is left out** (Q1). A selected fact whose history holds a superseded version of the
   same predicate gives that version's object and value; an excerpt is dropped when its turn is earlier than the
   fact's current version, it repeats the old object or value (`spans.reuse` at `REPEATS`, the measure that drops an
   excerpt restating a withheld line, with the current value's and the characters' names' spans not counted) and it
   does not repeat the current one. The freed slot goes to the next candidate. The trace records the count
   (`replaced_left_out`).
2. **An ended role is printed only for a question about the past** (Q2): a `role_toward` fact with negative polarity
   leaves the selected facts, unless no fact about the same two is current and the question names both. The trace
   records the count (`ended_left_out`).
3. **The excerpt's anchor breaks a tie on the question's one-character words** (Q3, first part). After the keyword
   count, the number of the question's one-character words (any script but a lone Latin letter) a sentence holds is
   the second key, before the trigram tie-break. A one-character word never outranks a keyword.
4. **A history cue keeps the past** (Q4). `facts.HISTORY_CUE` is `FIRST_CUE` (ADR 0056) plus 전에, 이전, 첫날, "before",
   "used to" and "previously". A question with it keeps items 1 and 2's excerpts and roles; item 3 applies either way.

Q3's second part (earlier holders counted as mentions and printed) is measured after the first and added only if
needed.

## Consequences

- Retrieval routes, ranking and the fitter are unchanged; a request under `packet-v11` is unchanged, and its trace
  replays as it was. A trace records its policy, so a `packet-v12` request replays under `packet-v12`.
- A question about the past without a cue word ("어디서 지냈었지?") loses the replaced value's excerpt; the cue list
  is the trade-off, reported per case in the measurement.
- An excerpt can still carry a replaced value when no selected fact is about it (the fact was not selected, or its
  history holds the value under another predicate); K39 stays listed for that.
- Rejected: demoting instead of dropping, labelling the excerpt `superseded`, trimming it to its short form (Q1);
  printing "ended at turn N" without the value (Q2); earlier holders first, a transfer event on a lending cue, always
  printing possession history (Q3); a model call to classify the question (Q4).
