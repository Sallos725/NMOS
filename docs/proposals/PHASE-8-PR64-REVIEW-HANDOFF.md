# Phase 8 PR #64 Review Handoff

> Status: review handoff only, 2026-09-24. This document does not authorize Phase 8 or any code,
> schema, extractor or resolver change. `docs/phases/PHASE-8.md` remains a draft until the owner
> approves Q1–Q5 and the phase gate is updated.

## Purpose

PR #64 (`phase8-spec-draft`) adds the draft Phase 8 specification for typed event/fact participants.
The second commit resolves most of the first document review: typed `{name, type}` participants,
the measured predicate boundary, exclusion of `fulfilled`, stricter controls, and an explicit rule
that participants do not become KNOWN ENTITIES hint candidates.

Three review items remain before the draft is ready for an owner decision:

1. make the claimed KNOWN ENTITIES stability true by construction, not only by candidate filtering;
2. commit the evidence used to justify Q1 and Q3 before asking the owner to approve them;
3. update the PR description so it describes the current head rather than the first commit.

CI for PR #64 was green at review time (`sidecar`, `plugin`). The findings below concern the proposed
contract and its audit trail, not a failing test.

## 1. KNOWN ENTITIES is not yet guaranteed to stay unchanged

### Observed evidence

Current `entity_hints()` (`apps/sidecar/src/nmos_sidecar/extraction.py`) does not copy every entity
from `Resolution`. It builds recency and eligibility from subject and object mentions only, then
serializes the chosen entity's `name`, `type` and aliases from the resolver:

```text
subject/object mentions -> last[entity id] -> resolver entity -> KNOWN ENTITIES line
```

Current `Resolution` (`apps/sidecar/src/nmos_sidecar/entities.py`) chooses an entity's display name
and name order from the first mention it sees. Phase 8 proposes adding participants to that mention
set under `resolve-v2`.

The draft therefore contains two statements that do not yet imply each other:

- participant-only entities are not hint **candidates** because `entity_hints` still orders candidates
  from subjects and objects;
- adding participants leaves the emitted hint list unchanged.

Candidate filtering proves the first statement only. A participant mention that precedes a later
subject/object mention of the same entity can still change the resolver's representative spelling or
alias order. `entity_hints` may then emit different text for an otherwise identical candidate. The
draft itself acknowledges that an entity first mentioned as a participant may show that spelling.

### Current architectural rule

ADR 0012 says KNOWN ENTITIES contains resolved entities mentioned before the target turn, newest
first, bounded by `NMOS_EXTRACT_HINTS`, and that the exact hint list is stored with the extraction.
Hints affect model input and can cause a false merge. A change to hint eligibility or serialization is
therefore an extraction-input behavior change, not merely an Inspector display detail.

### Why the draft is blocked

The deterministic acceptance case currently requires the hint list with participants to equal the
one without them, while the proposed resolver ordering permits a representative spelling to change.
An implementer cannot satisfy both without an additional canonical-name rule or a separate hint view.

### Recommended smallest decision

Keep Phase 8's extraction input byte-for-byte stable with respect to participants:

- participants join entity identity, recall and Inspector display;
- only subject/object mentions establish hint eligibility and recency;
- participant mentions have lower representative-name priority than every name source already used by
  `resolve-v1` (subject, object and evidenced alias names), regardless of transcript position;
- a participant-only entity may use its participant spelling for its Inspector page, but it has no
  hint candidate and cannot change the serialized name or alias order of an existing hint candidate.

Record this as an ADR 0012 amendment in the eventual Phase 8 implementation ADR. The deterministic
test must include the hard case: a participant alias occurs before the subject/object and before the
alias-establishing assertion, yet the KNOWN ENTITIES block remains identical to beta.14.

Alternative: allow participant mentions to change hints. If chosen, remove the equality claim and
the “hints unchanged” acceptance case, state the extraction-input change, and measure token growth,
40-entry crowd-out and false merges. Existing Phase 5 evidence shows a full 40-entity list costs about
350 prompt tokens; the list is bounded, but acceptable Phase 8 cost or behavior has not been measured.

## 2. The approval evidence must be committed before approval

### Observed evidence

The draft bases its boundary on exact claims from 280 recorded model runs:

- 51 of 223 `event` assertions;
- 12 of 25 `destroyed` assertions;
- 10 of 35 `goal` assertions;
- 10 of 19 `knows` assertions;
- 83 usable assertions after excluding `fulfilled`;
- 0 of 18 beta.14 selections when only the second participant is addressed.

The raw Phase 5–7 run files exist, but PR #64 does not include the manual classification that maps
those assertions to participant names or a runnable form of the 0-of-18 check. The draft currently
defers both artifacts to Phase 8 acceptance.

### Current architectural rule

The phase gate requires evidence before a phase is authorized. Measurements and scenario results
may not be fabricated or treated as complete optimistically. Q1 and Q3 ask the owner to choose a
scope specifically because these counts show the measured gap.

### Why the draft is blocked

Deferring the audit until implementation asks the owner to approve the implementation boundary using
evidence that is not yet inspectable. This reverses the gate: the scope evidence must support the
decision, not be produced after it.

### Required handoff artifacts

Add these to the documentation PR, before owner approval:

1. `fixtures/model/phase8/scope-audit.json`
   - one entry per counted assertion;
   - source fixture path, scene, run, assertion index and predicate;
   - subject, object, value and manually identified participant names/types;
   - whether the participant appears only in `value`;
   - whether the assertion is usable in Phase 8 and, if not, the exclusion reason.
2. A standard-library-only audit/check script, or an equivalent deterministic test, that:
   - reads the audit and referenced run files;
   - verifies that every referenced assertion still matches its recorded fields;
   - derives the per-predicate numerator and denominator printed in the draft;
   - fails on a stale reference, duplicate audit entry or total mismatch.
3. A committed beta.14 0-of-18 reproduction:
   - three fixed events whose second participant is absent from subject/object;
   - major and unlabeled forms of each event;
   - three fixed queries addressing only that participant;
   - the released `relevant_facts` behavior, with all 18 outcomes asserted.

The audit may label Korean synthetic scenes and manual semantic judgments explicitly. It does not
need to pretend participant identification is fully automatable; it must make every judgment
inspectable and totals reproducible.

After these artifacts land, change the Phase 8 text from future tense (“is committed beside the
result”) to a direct link to the committed audit and command.

## 3. PR description is stale

PR #64's description still summarizes the first commit:

- Q2 is described as an untyped `with` field;
- Q3 says every value-bearing assertion carries participants;
- it reports 85 cases without explaining why the two `fulfilled` cases are excluded from the usable
  Phase 8 scope.

The current head instead recommends typed `{name, type}` JSON, limits Q3 to `event`, `goal`, `knows`
and `destroyed`, and treats 83 cases as usable.

Update the PR description before requesting owner approval. Its Q1–Q5 summary should match the table
in `docs/phases/PHASE-8.md`, and its evidence paragraph should link the committed scope audit and
0-of-18 reproduction.

## Recommended execution order

1. Decide the resolver representative-name rule. Recommended: preserve hint serialization by giving
   all `resolve-v1` name sources priority over participant mentions.
2. Amend the Phase 8 draft's Resolution, Upgrade and cost, deterministic evaluation and acceptance
   sections to state that rule precisely.
3. Commit the scope audit and reproducible checks; update the evidence section with their paths and
   command.
4. Update the PR description to the current Q2/Q3 recommendations and evidence totals.
5. Run `git diff --check`, the new audit check, sidecar tests and plugin tests.
6. Re-review the complete diff. Only then ask the owner to answer Q1–Q5.

## Done for this handoff

The review follow-up is complete when:

- the participant/hint interaction has one implementable rule with no contradictory acceptance case;
- ADR 0012 amendment is named as a Phase 8 documentation requirement;
- all scope counts and the 0-of-18 result are reproducible from committed artifacts;
- the PR description matches the current draft;
- CI is green;
- Phase 8 is still explicitly draft and not authorized.

Do not create migration 0017, `extract-v8`, `resolve-v2`, participant recall or Inspector behavior as
part of this review follow-up. Those remain gated Phase 8 implementation.
