# Phase 25 — `extract-v15`: a role between two people is a relationship

> **Status: approved (2026-10-01): Q1 the alternative, a new predicate `role_toward` ("quality before time", owner);
> the rest as proposed — Q2 restated for that choice, the draft's Q4–Q6 now Q5–Q7, and Q4 (what reads the new
> predicate) added as that choice's consequence; current, alongside Phase 23.** Not a roadmap stage: a correction found
> by measurement, tracked as AGE-27 under AGE-24. The owner decided on 2026-10-01 that `0.3.0` waits for AGE-24's
> fixes and that `extract-v15` replaces the unreleased `extract-v14` before the tag (`docs/STATUS.md`, Decisions;
> AGENTS.md §13). No release in this phase; `0.3.0` follows it (the production rebuild, Stage 6's repair-survival
> check on it, AGE-23, AGE-7).

## Questions and answers

| # | Question | Answer | Not chosen |
|---|---|---|---|
| Q1 | Where does a role between two people go (tenant and landlord, employer and employee, teacher and student, master and servant, guardian and ward)? | **A new predicate `role_toward`** (owner, 2026-10-01): character → character, a value, one current value per (subject, object) and direction (`per_object`, as `feels_toward` and `addresses`): "the subject's role toward the object: tenant of, landlord of, employer of, works for, teacher of, student of, master of, servant of, guardian of, ward of…", value as the subject's side ("tenant: rents a room in the object's house"). `relationship`'s description says personal (kin, romance, rivalry, friendship) and points roles to `role_toward`. One synthetic prompt example (타쿠미 / Takumi and names the tests already use). | Widening `relationship`'s description (the draft's proposal): a role and a personal relationship would replace each other in one pair history (ADR 0038). |
| Q2 | A pair that has both? | **Both are current, each with its own history:** the pair's relationship (one history for both directions, ADR 0038, unchanged) and each direction's role. A role that changes (tenant → owner of the house) makes the earlier role its history, as any `per_object` fact. | — |
| Q3 | Does `located_in` still apply? | **Yes, both:** where someone lives is still a place; the role is its own fact. The prompt's line asks for both when a sentence says both. | The role only. |
| Q4 | What reads `role_toward`? | **Everything that reads how two characters stand** (`facts.STANDING`): ranking (PRIOR_STANDING, ADR 0026), the packet's lead lines, the first cue's history (ADR 0056), history under its marks (K42), and the Inspector's pair view, which gains a "Role" column (both languages). Canon facts may state it (`canonfacts.PREDICATES`). Only rows of `extract-v15` and later carry it, so a recorded request replays as it was: no recall option, no packet policy. No migration (the store has no list of predicates), no plugin build. | A recall option (nothing to switch: older generations have no such rows). |
| Q5 | What does the new generation cost to adopt? | **What a new generation re-extracts today:** each chat's recent window (100 turns, D20); older turns keep `extract-v14`'s rows until "Extract all history". Canon sources are read once more (the registry's descriptions are in canon prompts; Phase 19 recorded about 7 calls on production). `0.3.0`'s users move from `extract-v13` to `extract-v15` and pay one re-extraction (AGENTS.md §13). The owner rebuilds production once more. | — |
| Q6 | How is it measured? | **A bounded paid run from the implementation branch, after the owner's OK for its estimate, before it merges** (as Phase 19), `gemma4:31b` through the provider's API, two workers (429s): (a) the three AGE-27 evidence turns of the main M0 chat × 3 runs (9 calls); (b) Phase 19's sampled turns — the synthetic chat's 91 ledger turns and the main M0 chat's 20 — × 3 runs (333 calls), against Phase 19's stored `extract-v14` runs (no new baseline spend); (c) the two M0 chats re-extracted (73 + 34 turns, 107 calls) and evaluated at `packet-v10`, 4,000, vectors off and on, against `extract-v14`. **Estimate: about 450 calls, ≈3.8M input and ≈0.4M output tokens** (v14's ≈8.4k input a call; the registry line adds a few dozen tokens). | `deepseek-v4.1-flash` too (doubles (c); K41 says its M0 counts are noisy). |
| Q7 | Is this high risk (AGENTS.md §14)? | **Yes:** a new extractor generation changes what every chat stores, and the read side ranks a new kind of fact. | — |

## Evidence behind the scope

The main M0 chat's question "what is character A in the user's house?" (the answer: a tenant). Its ledger states the
tenancy in three turns. Re-extracted with `extract-v14` (`gemma4:31b`, 2026-10-01, the three turns once): one turn gave
`A · located_in · <user>'s house` with a quote that states the tenancy — the model saw it and kept the place only; the other two gave feelings and events, no relationship. The registry's `relationship` lists "sibling,
rival, lovers…" only. A replay passed the case once through a vector excerpt of the user's own words, not through a
fact (excerpt luck; AGE-27).

## Goal

A role between two people — who rents from whom, who works for whom, who teaches whom — is extracted as its own fact
next to their relationship, so a question about it finds a fact rather than an excerpt by chance.

## In scope (Phase 25)

1. `extract-v15`: `role_toward` in the registry, `relationship`'s description narrowed to personal ties (Q1), one
   synthetic prompt example and the prompt's line on a place and a role (Q3); the compiler version and the generation's
   fingerprint change accordingly (D20); the canon generation changes through the registry text only.
2. The read side (Q4): `role_toward` in `facts.STANDING` and `canonfacts.PREDICATES`; the Inspector's pair view gains
   its column (Korean and English labels).
3. Tests: the registry entry and the prompt (synthetic names only); the generation keys change; a role row is current
   per direction and its earlier value becomes history; a pair keeps its relationship and its roles at once; a role
   ranks as a standing fact and appears in the packet's lead lines and the Inspector's pair view; a recorded request
   of an earlier generation replays as it was.
4. The paid evaluation (Q6) and `docs/perf/extract-v15.md`; ADR 0059; ARCHITECTURE (D69); STATUS (the queue emptied);
   CHANGELOG; README and the Korean guide where they name `extract-v14` as the current generation.

## Out of scope (Phase 25)

- A relationship with more than one current value (ADR 0038 unchanged); roles in `<Cast>` groups.
- Re-extracting older turns; deploying to production and the rebuild (the owner's, after this phase); the release.

## Acceptance criteria

- [ ] Every existing test passes; the deterministic cases of In scope 3.
- [ ] (a) A `role_toward` row with the tenancy for the AGE-27 pair in at least two of the three runs.
- [ ] (b) Sampled turns, three runs: ledger facts found among valid rows, mean not below the lowest of `extract-v14`'s
      runs; `relationship` rows found not fewer than `extract-v14`'s lowest run (roles do not take relationships'
      place); the evidence check parks at most 10 % of valid rows (Phase 19's bar); input tokens within 5 % of
      `extract-v14`'s.
- [ ] (c) The M0 chats at `packet-v10`, 4,000, vectors off and on: cases passed and needing memory not lower than
      `extract-v14`'s by more than one per run; forbidden phrases placed not higher in total; the AGE-27 case passes
      with vectors off.
- [ ] Review per AGENTS.md §14 (high risk; the self-review, a Codex review only on the owner's request).

## Steps (one pull request each)

1. This document, approved; AGENTS §2 and STATUS name Phase 25 current.
2. `extract-v15`, the read side and their tests, the self-review (ADR 0059). **Not merged until step 3's criteria
   hold.**
3. The paid evaluation from step 2's branch after the owner's OK for its estimate; `docs/perf/extract-v15.md`; then
   step 2 merges.
4. Documentation; Phase 25 complete. Then, outside this phase: the owner deploys `:edge`, rebuilds production with
   `extract-v15` and dumps it; Stage 6's repair-survival check runs on that dump
   (`~/nmos-eval/stage6-v14-repairs/check2.py`); AGE-23; `0.3.0` (AGE-7) with the owner's OK for the tag.

Every merge reaches the owner's `:edge`; no tag (AGENTS.md §13).

## Stop conditions

Stop and ask the owner when:

- `role_toward` rows take the place of `relationship` rows (criterion (b)), or any criterion of (b) or (c) is missed;
- a paid run would go beyond its estimate by more than a quarter;
- a schema change, a recall option or a plugin change looks necessary.
