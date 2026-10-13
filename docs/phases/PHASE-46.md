# Phase 46 — Small talk keeps the configured limits (`packet-v19`)

Status: **approved** (owner, 2026-10-13); measured, every criterion met. A correction found by the 1.0 gate's evaluation against `0.1.x`. Not a
roadmap stage. The owner chose to fix it narrowly rather than accept it. The default switch is a separate decision
(Q1). Linear AGE-13.

## Why

1. **The 1.0 gate asks that no evaluation category is worse than in `0.1.x`.** On the 1.0 candidate (`main` at
   `bdae2eb`) the 338 replay probes were compiled under `packet-v1` (the `0.1.x` default) and `packet-v18`. Both
   used the same databases and extraction, three rounds each, with zero model calls.
   - Total: 273 → 315.
   - 26 of 27 categories are equal or better.
   - `irrelevant` is 20 → 16. The two M0 small-talk probes ("오늘 저녁은 뭐 해 먹을까?", "내일 날씨 어떨까?") fail
     in both sets that hold them.
2. **The cause is the budget fill of `packet-v9` (ADR 0049).**
   - At the default 4,000 tokens, the fill adds fact slots up to twice the fact limit, and claim slots with them.
   - A question that relates to nothing still has candidates, because the previous reply names the scene's characters.
   - So the fill takes 30 facts and 8 claims, two of which carry the probes' forbidden words.
   - At 2,000 tokens (no fill) both probes pass.
   - Phase 15 accepted +2 forbidden phrases for +6 cases needing memory. This is that trade-off, seen by a category
     comparison the gate asks for.
3. **A wider rule costs real turns.** The first rule tried was "no fill for a message that names no one and shares no
   fact's words". Replayed on the trial install's 80 latest requests (read-only), it changed 14 of them, each losing
   1–9 facts or claims. Those were role-play turns written as narration without a name. So the rule is limited to
   questions.

## Proposal

S1. **`packet-v19` = `packet-v18` plus one rule.**
- The rule covers a message that meets all three conditions (`retrieval.unrelated_question`):
  - it ends with a question mark (`?` or `？`);
  - it names no one (no fact is selected by a name it holds);
  - it shares no fact's or claim's words at the lexical bar (`facts.lexically_related`, `LEXICAL_BAR`).
- Such a message gets no added fact or claim slots from the budget. The configured limits still choose, in the same
  ranked order.
- Excerpt growth, secrets, `<Private>`, events and every other rule are unchanged.

S2. **Every set that holds `packet-v18` holds `packet-v19`.** The two places that named `packet-v18` by value now use
sets, so `packet-v19` keeps their behavior:
- the status as core values and changes (PHASE-43 S4), `STATUS_CHANGE_POLICIES`;
- the source clock (PHASE-42), `SOURCE_CLOCK_POLICIES`.

S3. **`packet-v18` stays the default until Q1.**

## Out of scope

- Any change to the fill itself for related messages, or to the budget.
- Narration without a name (left as it is, see Why 3).
- The other small-talk probes: 18 of 20 already pass.

## Questions for the owner

- **Q1 — the default.** Make `packet-v19` the default once the measurements below hold. A packet-policy change is a
  heavy change for the two quiet weeks, so it goes in before the 1.0 candidate is deployed, not after.

## Measurement (zero calls, `AGENTS.md §7.6` recall-only gate)

- The 338 probes under `packet-v18` and `packet-v19`, three rounds each, majority deciding.
  - Pass: 0 lost, and the two `irrelevant` probes back.
- The trial install's 80 latest requests replayed read-only under both policies.
  - Pass: no request loses a fact or claim line.
- **Result under `packet-v19` (2026-10-13, `docs/perf/phase46-related-fill.md`): met.**
  - Gate: bench 296/314 → 300/314, quotes 19 = 19. 0 cases lost; 4 gained, the two `irrelevant` probes in both of
    their sets.
  - Live 80: no request lost a fact or claim line. 4 packets differed in their excerpts only, which is the lexical
    route's run-to-run noise.
  - Acceptance 2 and 3 hold as well: `packet-v18` on this branch gives every probe the same result as on `main`, and
    against `packet-v1` the total is 273 → 319 with no category worse.

## Acceptance criteria

1. The measurement above passes under `packet-v19` itself. Results go in `docs/perf/phase46-related-fill.md`.
2. Under `packet-v18` every probe is identical to `main` before this phase.
3. The `0.1.x` comparison under `packet-v19` has no category worse than `packet-v1`.
