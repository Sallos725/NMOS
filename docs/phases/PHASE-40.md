# Phase 40 — Questions about the persona in the third person

Status: approved for implementation and measurement, 2026-10-09. After reviewing
the question-limited proposal and briefly deferring it, the owner explicitly brought
AGE-18 / K32 back into 0.4.0, before the two-week real-use period. Implementation and zero-call replay are done; see
[measurement](../perf/phase40-persona-questions.md). The reduced live check remains open;
default promotion is not approved. Phase 39 remains current.
This is a recall correction beside it, not a roadmap stage.

## Evidence and cause

At `c170266`, `facts.relevant_facts` removes the resolved persona's names from mention
scoring. Only the existing first-person detector adds the persona-specific bonus.
This implements ADR 0023 decision 4; it is not the identity split fixed by AGE-58.
Lexical, excerpt and summary routes can still return persona information. K32 is not
a claim that every third-person request loses all persona memory.

A synthetic, pure-function reproduction on 2026-10-09 used two facts, stored under
`{{user}}` and resolved with host persona name `타쿠미`: identity `천문학자` and location
`북쪽 관측소`. With the current named-by-words rule:

| Query | Selected fact predicates |
|---|---|
| `타쿠미는 무슨 일을 해?` | none |
| `내 직업은 뭐였지?` | located_in, identity |
| `타쿠미는 지금 어디 있어?` | none |
| `타쿠미는 고개를 끄덕인다.` | none |

These are constructed inputs, not host evidence or measured answer-quality scores.
The current persona, hidden-ledger/audit and name-variant suites passed 66 tests;
the part-alias suite passed 12, including the persona/shared-name regression.

Phase 24 Q4 previously rejected two wider rules: treating the persona's name as a
first-person request gained one sample-2 case but lost another and two synthetic
cases, introducing stale values; lexical-only restriction gave no net gain.
See `docs/perf/name-variants.md` and `docs/KNOWN-ISSUES.md` K32.

## Approved correction scope

A bounded third-person question route amends ADR 0023 decision 4 only
for explicit questions about the resolved persona. Ordinary narration still gives
no persona-name bonus. Do not simply substitute the persona name with `my`/`내`.

1. Require an unambiguous, already resolved persona name and an explicit question
   cue in the same clause. Reuse existing predicate-question cues where applicable;
   specify and test location/possession and historical-question cues before coding.
   A name in narration or a question about a different character is insufficient.
2. Consider only facts whose subject resolves to that persona and whose predicate
   or content answers the question. Do not boost every persona fact, every event
   involving the persona, or facts naming it only in a knowledge mark.
3. Rank at most two question-specific matching targets within the existing fact/event and
   token budgets. Apply current/history selection, inactive-source filtering,
   knowledge gates, risky ordering and rest/required classification consistently.
   The cap is a proposed measurement parameter, not an established optimum.
4. Implement behind a new `packet-v18`, based on v17. Keep v16/v17 and old-trace
   replay unchanged. Neither the global default nor the 6113 policy changes merely
   because the experimental implementation exists.

### Evidence-guided details (before candidate replay)

The original sample-2 questions use the persona's given name, absent from the
resolver's stored aliases, and the company answer is a character claim. The route
therefore also accepts the existing `variants.given` spelling of a resolved
three-syllable Korean persona name only when no other entity holds or derives that
spelling. This is local to the explicit-question route: no entity join, ordinary
mention, Cast or thread-name expansion changes. Claims use the same route and
share the two-target cap with narrated facts; they remain attributed claims.
Question cues include identity/work, membership/company, traits, knowledge,
location, possession and explicitly asked past events. Specific content words can
select a matching persona fact/claim when its predicate alone does not encode the
question's noun. Uncertain subjects and indirect questions in narration abstain.

Owner decision: correct K32 for 0.4.0, superseding the earlier deferral.
The recommended route avoids the demonstrated broad boost, but improvement and
absence of displacement are hypotheses until replayed.

### Ranking correction found on the real replay

The first implementation only appended answers to spare slots. On the remaining
sample-2 question with current options, three events mentioned only by the previous
reply filled the event quota; the asked persona event was recognized but could not
enter. The total fact pool had spare capacity. Keep the two-row cap but let those
explicit targets compete in normal ranking: question-target mention 1.5, between
an ordinary current-query name (2.0) and a previous-reply name (1.0). Existing event
quota, minor-event rule, first-cue ordering and token budget remain authoritative.
This targets the question's facts, not all persona facts. Old trace flags stay intact.

## Scope and acceptance

- Read-side selection only: no schema, entity merges, extraction prompt/generation,
  provider calls, dependencies or host mutation. No change to first-person parsing.
- Synthetic regressions: explicit identity/location/history questions, narration,
  another character's question with persona narration, aliases and shared names,
  private/hidden facts, inactive sources, current versus ended facts and tight budgets.
- On available copied gate databases, run all existing probes three times per
  baseline/candidate with cached embeddings only. Require no newly failed probe by
  majority, no new forbidden case, and no quote regression. Report aggregate scores
  as well as per-case differences. Never treat a higher total as covering a lost case.
- Identify reproducible K32 probes before tuning; require a previously missed real
  persona question to improve. If the old sample-2 database/probes are unavailable,
  record that boundary rather than replacing their result with synthetic success.
- Check latency using the existing recall benchmark. After replay succeeds, the
  relevant reduced live check follows AGENTS section 7.6; new paid calls need a
  separate estimate and authorization. The earlier 65 Voyage queries are not a
  reusable allowance for additional calls.
- Lead diff review must check high-risk guarantees: selection/isolation, provenance,
  stale-state exclusion, bounded budget and replay compatibility. Update the ADR,
  STATUS and K32 only with the actual outcome.

Stop if a baseline probe regresses, a forbidden value newly appears, the route
requires an unapproved semantic/host inference, or essential real evidence is absent.
The owner includes this correction in 0.4.0. Default policy and deployment depend on
the measured candidate; approval to implement does not mean its gate has passed.
