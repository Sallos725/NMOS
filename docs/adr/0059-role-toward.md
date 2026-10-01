# 0059 — `extract-v15`: a role between two people is its own fact (`role_toward`)

Status: accepted, 2026-10-01. Phase 25 step 2 (`docs/phases/PHASE-25.md` Q1–Q7, approved by the owner; AGE-27 under
AGE-24). Narrows `relationship` (ADR 0038 unchanged in how it folds); amends what counts as how two characters stand
(ADR 0026). No migration, no plugin build, no recall option, no new packet policy.

## Context

The main M0 chat's question "what is character A in the user's house?" has one answer, a tenant, and the ledger states
the tenancy in three turns. Re-extracted with `extract-v14`, one of them gave `A · located_in · <user>'s house` with a
quote that states the tenancy: the model saw the role and kept the place. The registry offered nothing better:
`relationship` read "relationship of subject to object (sibling, rival, lovers…)". A replay passed the case once,
through a vector excerpt of the user's own words rather than a fact.

A role could have widened `relationship`, but a pair has one relationship history for both directions (ADR 0038): a
tenancy and a friendship between the same two people would replace each other.

## Decision

1. **A new predicate `role_toward`** (Q1): character → character, a value, `single` and `per_object` like
   `feels_toward` and `addresses`, so each direction has one current role and its own history. Its description lists
   roles (tenant of, landlord of, employer of, works for, teacher of, student of, master of, servant of, guardian of,
   ward of…) and asks for the subject's side as the value.
2. **`relationship` is personal** (Q1): its description says kin, romance, rivalry, friendship, and points a role such
   as tenant or employer to `role_toward`. Its fold (one history per pair, symmetric values, ADR 0038) is unchanged.
3. **Both are current** (Q2): a pair keeps its relationship and each direction's role at once; a newer role replaces
   the role of its direction only, and the earlier one becomes its history, as any `per_object` fact.
4. **A place and a role both** (Q3): the prompt's `role_toward` line says a role is not a relationship, asks for one
   assertion per direction the turn states, and, when a turn says both where someone lives and the role they hold
   there, for `located_in` and `role_toward` both. Its example uses synthetic names and a role other than the measured
   tenancy ("하나가 하녀로 일하며 지내는 카이토의 저택"), so the evaluation's tenancy case is not answered by the prompt's own
   example.
5. **Read as how two characters stand** (Q4): `role_toward` is in `facts.STANDING`, so it ranks with PRIOR_STANDING
   (ADR 0026), leads the packet's facts, carries what it replaced and how it started (packet-v5, ADR 0038; ADR 0056,
   K42 marks), and is in the Inspector's pair view in a "Role" ("역할") column between Relationship and Feelings, one
   line per direction. Canon facts may state it (`canonfacts.PREDICATES`). `STANDING` is outside the registry, so
   this needs no generation of its own; only rows of `extract-v15` and later carry the predicate, so a recorded request
   replays as it was without an option.
6. `COMPILER_VERSION` is `extract-v15`. The registry fingerprint changes; so does the canon generation's, through the
   registry text only (its prompt and `canon-v1` are unchanged).

## Consequences

- Each chat's recent window (`NMOS_EXTRACT_BACKFILL`, 100 turns) is extracted again once and its canon sources read
  again once (Q5). `0.3.0`'s users move from `extract-v13` to `extract-v15` and pay one re-extraction; the unreleased
  `extract-v14` is replaced before the tag (AGENTS.md §13).
- Older turns keep `extract-v14`'s rows until "Extract all history"; they hold no `role_toward`, so a role stated only
  there is not a fact until then.
- A role the story only implies may still come out as `relationship` from a model that ignores the narrowed
  description; such rows fold as before.
- Roles do not appear in `<Cast>` groups (out of scope).
- Evaluation: `docs/perf/extract-v15.md` (step 3, a bounded paid run before step 2 merges).
