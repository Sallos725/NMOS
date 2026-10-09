# 0072 — Explicit questions about the persona (`packet-v18`)

Status: implementation scope accepted by the owner, 2026-10-09 (AGE-18,
PHASE-40); zero-call replay and synthetic latency measured, reduced live check and
default decision pending. See [evidence](../perf/phase40-persona-questions.md). Amends ADR 0023 decision 4
only for the question route below. Resolution, extraction generations and ordinary
persona-name mentions are unchanged.

## Context

Ignoring every persona name as a mention prevents its numerous facts from taking
other characters' slots whenever a user narrates in the third person. It also omits
the persona's own answers to explicit third-person questions (K32). Phase 24's
unrestricted first-person-equivalent boost caused regressions and was rejected.
The original sample-2 questions include a Korean given name; the company answer
is an attributed identity claim, not a narrated fact.

## Decision

- Add opt-in `packet-v18`, inheriting every v17 capability. The repository default
  remains v16 and existing v16/v17 traces keep their rules.
- Require an explicit question whose subject is the resolved persona in the same
  clause. Recognize bounded Korean/English forms for the person's identity/work,
  membership, traits, knowledge, location, possessions and past events. Indirect
  narration and ambiguous subjects abstain. This is not unrestricted language understanding.
- Accept resolved names and an unshared Korean given name derived by the existing
  `variants.given` rule. Check other entities' names and derived given names. These
  question-only names never enter ordinary mention matching, Cast or thread ranking.
- Consider only facts or claims with that resolved subject and a predicate/content
  cue the question asks for. A company-name question can target either membership
  or identity: the extractor can record employment as either. Keep a character's
  assertion as a Claim with its speaker and provenance.
- Let at most two matching targets compete in normal fact/claim ranking, sharing
  the cap across both routes. Their mention score is 1.5, below a current-query name
  (2.0) and above a name in the previous reply (1.0). Merely appending to spare slots
  failed the real first-gate question because previous-reply events filled its quota.
  Existing event and token budgets still apply. No extra DB or provider read is introduced.
- Reuse history, context, minor-event, risky, rest and mode rules. Explicitly asked
  matching facts are named (required); this does not bypass secret filtering or
  make an inactive source eligible. Old traces do not silently gain first-cue behavior.

## Consequences and evidence boundary

This can recover an explicitly asked fact without granting all persona facts a
mention bonus. A full candidate pool, a tight token budget, unsupported question
grammar or missing extracted evidence may still prevent an answer. A synthetic
success alone is insufficient: PHASE-40 requires original K32 improvement and
three-round replay without a new failed or forbidden case, followed by the relevant
live check. No extraction repair, default promotion or release completion is claimed
by this decision record.
