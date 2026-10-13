# 0075 — Small talk keeps the configured limits

Status: accepted by the owner, 2026-10-13, PHASE-46. `packet-v19` is the default.

## Context

ADR 0049's budget fill (`packet-v9`) grows recall with the budget. At the default 4,000 tokens it adds fact slots, up
to twice the fact limit, and claim slots with them. The added slots go to facts kept from no one.

A question that relates to nothing still has candidates, because the previous reply names the scene's characters. So
the fill handed small talk 30 facts and 8 claims. On the 1.0 gate's comparison with `0.1.x`
(`docs/perf/phase46-related-fill.md`), this put `irrelevant` below `0.1.x`: 20 → 16. It was the one category to fall.

## Decision

Under `packet-v19`, a message gets no added fact or claim slots when all of these hold:
- it ends with a question mark;
- it names no one: no fact is selected by a name it holds;
- it shares no fact's or claim's words at `LEXICAL_BAR`.

The configured limits still choose, in the same ranked order. Excerpt growth, secrets, `<Private>`, events and every
other `packet-v18` rule are unchanged.

## Why a question

A rule without the question mark caught role-play turns written as narration without a name. Replayed on the trial
install, it changed 14 of 80 real requests and took 1–9 memory lines from each. Limited to questions, it changed
none of those 80 requests' fact or claim lines.

## Consequences

- **Gate replay (338 probes ×3, zero calls):** 0 lost. Bench 296 → 300; quotes unchanged.
- **Against `packet-v1`:** 273 → 319, with no category worse.
- **Edge cases:**
  - A question in other words about something only an excerpt holds still gets its excerpts.
  - A question naming no one about a fact it shares no word with gets the configured limit, as at 2,000 tokens.
