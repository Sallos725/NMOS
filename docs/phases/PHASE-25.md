# Phase 25 — `extract-v15`: a role between two people is a relationship

> **Status: draft, awaiting the owner's approval.** Not a roadmap stage: a correction found by measurement, tracked as
> AGE-27 under AGE-24. The owner decided on 2026-10-01 that `0.3.0` waits for AGE-24's fixes and that `extract-v15`
> replaces the unreleased `extract-v14` before the tag (`docs/STATUS.md`, Decisions; AGENTS.md §13). Phase 23 is
> current in another session. No release in this phase; `0.3.0` follows it (the production rebuild, Stage 6's
> repair-survival check on it, AGE-23, AGE-7).

## Questions and proposed answers

| # | Question | Proposed answer | Alternatives |
|---|---|---|---|
| Q1 | Where does a role between two people go (tenant and landlord, employer and employee, teacher and student, master and servant, guardian and ward)? | **`relationship`, by its description:** "relationship of subject to object: kin, romance, rivalry, friendship, or a role between them (tenant of, landlord of, employer of, works for, teacher of, student of…)", value as the subject's side ("tenant: rents a room in the object's house"). One prompt example, synthetic (타쿠미 / Takumi and names the tests already use). No new predicate, no change to recall, the packet, the Inspector or the plugin: a role is printed, ranked (standing facts, ADR 0026) and shown per pair as a relationship already is. | **A new predicate `role_toward`** (directional, one current value per pair): a role and a personal relationship stay apart, but it touches the registry, the pair history key, standing facts, the Inspector's pair view, canon facts and both languages' labels — more than this phase's day. |
| Q2 | A pair that already has a relationship? | **The role becomes the pair's current relationship and the earlier one its history** (one history per pair, ADR 0038): "friends" then "tenant" reads as tenant, before: friends. Measured (Q5): how often a role row replaces a personal one in the sampled turns and the M0 chats; if more than one pair in ten loses a still-true personal relationship that way, stop (Stop conditions) and take Q1's alternative. | Keep both current (a relationship becomes multi-valued: ADR 0038's pair history changes, rejected). |
| Q3 | Does `located_in` still apply? | **Yes, both:** where someone lives is still a place; the role is said once more as a relationship. The prompt's line asks for both when a sentence says both. | The role only. |
| Q4 | What does the new generation cost to adopt? | **What a new generation re-extracts today:** each chat's recent window (100 turns, D20); older turns keep `extract-v14`'s rows until "Extract all history". Canon sources are read once more (the registry's descriptions are in canon prompts, `canonfacts.py`; Phase 19 recorded about 7 calls on production). `0.3.0`'s users move from `extract-v13` to `extract-v15` and pay one re-extraction (AGENTS.md §13). The owner rebuilds production once more (the decision of 2026-10-01). | — |
| Q5 | How is it measured? | **A bounded paid run from the implementation branch, after the owner's OK for its estimate, before it merges** (as Phase 19), `gemma4:31b` through the provider's API, two workers (429s): (a) the three AGE-27 evidence turns of the main M0 chat × 3 runs (9 calls); (b) Phase 19's sampled turns — the synthetic chat's 91 ledger turns and the main M0 chat's 20 — × 3 runs (333 calls), against Phase 19's stored `extract-v14` runs (no new baseline spend); (c) the two M0 chats re-extracted (73 + 34 turns, 107 calls) and evaluated at `packet-v10`, 4,000, vectors off and on, against `extract-v14`. **Estimate: about 450 calls, ≈3.8M input and ≈0.4M output tokens** (v14's ≈8.4k input a call). | `deepseek-v4.1-flash` too (Phase 19's second model; doubles (c), K41 says its M0 counts are noisy). |
| Q6 | Is this high risk (AGENTS.md §14)? | **Yes:** a new extractor generation changes what every chat stores after re-extraction. | — |

## Evidence behind the scope

The main M0 chat's question "what is character A in the user's house?" (the answer: a tenant). Its ledger states the
tenancy in three turns. Re-extracted with `extract-v14` (`gemma4:31b`, 2026-10-01, the three turns once): one turn gave
`A · located_in · <user>'s house` with a quote that states the tenancy — the model saw it and kept the place only; the other two gave feelings and events, no relationship. The registry's `relationship` lists "sibling,
rival, lovers…" only. A replay passed the case once through a vector excerpt of the user's own words, not through a
fact (excerpt luck; AGE-27).

## Goal

A role between two people — who rents from whom, who works for whom, who teaches whom — is extracted as the pair's
relationship, so a question about it finds a fact rather than an excerpt by chance.

## In scope (Phase 25)

1. `extract-v15`: the `relationship` description (Q1), one synthetic prompt example and the prompt's line on a place
   and a role (Q3); the compiler version and the generation's fingerprint change accordingly (D20); the canon
   generation changes through the description only.
2. Tests: the description and example in the prompt, synthetic names only; the generation keys change; a role row is
   a relationship and replaces a pair's earlier one as history (ADR 0038, unchanged code).
3. The paid evaluation (Q5) and `docs/perf/extract-v15.md`; ADR 0059; ARCHITECTURE (a decision); STATUS (the queue
   emptied); CHANGELOG; README and the Korean guide where they name `extract-v14` as the current generation.

## Out of scope (Phase 25)

- A new predicate (Q1's alternative); recall, the packet, the Inspector, the plugin.
- Re-extracting older turns; deploying to production and the rebuild (the owner's, after this phase); the release.

## Acceptance criteria

- [ ] Every existing test passes; the deterministic cases of In scope 2.
- [ ] (a) A relationship row with a role (tenant or renting) for the AGE-27 pair in at least two of the three runs.
- [ ] (b) Sampled turns, three runs: ledger facts found among valid rows, mean not below the lowest of `extract-v14`'s
      runs; the evidence check parks at most 10 % of valid rows (Phase 19's bar); input tokens within 5 % of
      `extract-v14`'s.
- [ ] (c) The M0 chats at `packet-v10`, 4,000, vectors off and on: cases passed and needing memory not lower than
      `extract-v14`'s by more than one per run; forbidden phrases placed not higher in total; the AGE-27 case passes
      with vectors off.
- [ ] Q2: a role row replaces a still-true personal relationship for at most one pair in ten among the pairs whose
      relationship changed in (b) and (c).
- [ ] Review per AGENTS.md §14 (high risk; the self-review, a Codex review only on the owner's request).

## Steps (one pull request each)

1. This document, approved; AGENTS §2 and STATUS name Phase 25 current.
2. `extract-v15` and its tests, the self-review. **Not merged until step 3's criteria hold.**
3. The paid evaluation from step 2's branch after the owner's OK for its estimate; `docs/perf/extract-v15.md`; then
   step 2 merges.
4. Documentation; Phase 25 complete. Then, outside this phase: the owner deploys `:edge`, rebuilds production with
   `extract-v15` and dumps it; Stage 6's repair-survival check runs on that dump
   (`~/nmos-eval/stage6-v14-repairs/check2.py`); AGE-23; `0.3.0` (AGE-7) with the owner's OK for the tag.

Every merge reaches the owner's `:edge`; no tag (AGENTS.md §13).

## Stop conditions

Stop and ask the owner when:

- a role row replaces a still-true personal relationship for more than one pair in ten (Q2): take Q1's alternative or
  accept it;
- any criterion of (b) or (c) is missed;
- a paid run would go beyond its estimate by more than a quarter;
- a schema change or a change to recall looks necessary.
