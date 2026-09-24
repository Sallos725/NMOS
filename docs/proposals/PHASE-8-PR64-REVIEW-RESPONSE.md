# Phase 8 PR #64 Review Response

> Status: response to `docs/proposals/PHASE-8-PR64-REVIEW-HANDOFF.md`, 2026-09-24. Like the handoff,
> it authorizes nothing: `docs/phases/PHASE-8.md` stays a draft until the owner answers Q1–Q5. No
> migration, extractor, resolver, recall or Inspector code was written.

## Summary

The handoff's three items are correct, and all three are addressed in PR #64. Checking them turned up
problems the handoff did not name. The most important is that the scope counts the handoff restated
(85 and 83) were themselves wrong. It also asks for one artifact, the 0-of-18 check pinned to released
behavior, in a form that would break after Phase 8; it is committed in a form that does not.

| Handoff item | Verdict | Where it is addressed |
|---|---|---|
| 1. KNOWN ENTITIES stable by construction | Agreed | `PHASE-8.md` In scope item 3, Upgrade and cost, the "hints unchanged" case, acceptance (ADR 0012 amendment) |
| 2. Commit the approval evidence first | Agreed; the counts it quotes are withdrawn | `fixtures/model/phase8/scope-audit.json`, `tools/check_phase8_scope_audit.py`, `apps/sidecar/tests/test_participant_scope.py` |
| 2.3 A 0-of-18 check of "the released behavior" | Partly disputed | `test_participant_scope.py` (see below) |
| 3. Stale PR description | Agreed | PR #64 description |

## 1. KNOWN ENTITIES: agreed, fixed

The handoff is right that candidate filtering alone did not make the hint list stable. `Resolution`
takes an entity's representative spelling and name order from the first mention it sees
(`entities.py`, `first.setdefault`). A participant mention before the first subject/object mention
could therefore change the serialized hint of an entity that stays a candidate. The previous draft
both allowed that and asserted equality, as the handoff says. An earlier review message on this PR also
called the effect negligible; that was wrong.

`PHASE-8.md` now takes the handoff's recommended rule and states how it holds by construction. The
resolver reads participant mentions in a second pass, after every `resolve-v1` name source (subjects,
objects, evidenced alias names). Every `resolve-v1` node keeps its first-seen order and every root stays
the same, so an entity `resolve-v1` knows keeps its name, alias order and grouping. Only
participant-only entities take a participant spelling, and they are not hint candidates. The
deterministic "hints unchanged" case now requires a byte-for-byte equal KNOWN ENTITIES block, including
the hard case the handoff names: a participant spelling occurs before the first subject/object mention
and before the `also_called`. The acceptance criteria name the ADR 0012 amendment.

One consequence the handoff did not state: because the roots do not move, the only thing that changes
existing entity ids is the `RESOLVER_VERSION` string. The bump that ADR 0012 requires still changes
every Inspector entity URL once. The draft now says so. Keeping the version string would avoid it, but
it would break ADR 0012's rule that a resolver change is a new version, so the draft keeps the bump.

## 2. Evidence before approval: agreed, and the counts were wrong

Agreed without reservation: the owner cannot be asked to approve a boundary on numbers no one can
inspect. The artifacts are committed:

- `fixtures/model/phase8/scope-audit.json`, with one entry per candidate assertion:
  - every valid `event`, `destroyed`, `goal`, `knows` and `fulfilled` assertion in the Phase 5–7 runs
    (308);
  - the source file, line, assertion index, scene, variant, run and the stored fields;
  - the recall route (fact, claim, or not in the packet), the participants as `{name, type, kind}`,
    and whether the entry is usable or why not.
- `tools/check_phase8_scope_audit.py`, standard library only. It verifies:
  - every entry against its run file;
  - completeness: every candidate in the run files is in the audit;
  - no duplicates;
  - that every derived field follows the audit's rules.

  It prints the per-predicate counts, and CI runs it through `test_participant_scope.py`, which also
  asserts the totals.

Doing the audit the way the handoff asks, by reading each value rather than matching a name list,
showed that the numbers the handoff quotes, and PR #64 claimed, came from the first draft's fixed name
list (하나, 카이토, 유이, `{{user}}`, 미나토, 하루). That method was wrong in both directions:

- **It counted the persona.** 12 of the 85 had `{{user}}` as the only other person: a confession, a
  walk and a meal with the user, and a promise to meet the user. Recall never treats the persona as a
  mention (Q4, ADR 0019), so participants cannot help them.
- **It counted a self-alias.** `미나토 하루카 goal: 하루라고 불리기` matched "하루".
- **It missed groups and unlisted people:** 산적들, 경비병들, 선배 기사들, 왕, 부단장, 보건실 선생님.
- **It ignored the recall route.** 4 `goal` assertions are hypothetical and never reach the packet,
  and 14 of the usable ones are character claims, which `relevant_facts` selects too. Q4 did not say
  whether participants count for claims.

The audit's result: 78 usable assertions (event 51, destroyed 12, knows 10, goal 5). The event number
is the same 51 as before by coincidence; the sets differ. The handoff's "83 usable" is withdrawn along
with the draft's.

The handoff also left out how thin the evidence is outside `event`. The assertion counts come from
repeated runs: three per scene, and the Phase 5 scenes appear twice, in two fixture directories. By
distinct scene, the usable evidence is 18 scenes: event 15, knows 3, destroyed 2, goal 2. `PHASE-8.md`
Q3 now gives both numbers. It keeps the four-predicate recommendation, because the real-model tier adds
a scene for each, and it leaves `event` only as alternative (b) with its scene count.

### 2.3 The 0-of-18 check: partly disputed

The handoff asks for a check of "the released `relevant_facts` behavior, with all 18 outcomes
asserted". Pinned to released behavior, that test must fail the day Phase 8 lands, because making such
facts recallable is the point of Phase 8. `test_participant_scope.py` instead asserts the rule that is
true now and stays true afterwards: a fact without participant data is selected only through its subject
and object. Under Q5 that is exactly how turns of older generations behave after Phase 8. The 18
outcomes are asserted (3 events × major/unlabeled × 3 queries), and so is the positive control
(addressing the subject selects the fact).

The check also no longer uses the draft's example of 하나 confessing to 카이토. That event was written
for the in-session check and was never produced by the model: the recorded confession is to `{{user}}`.
The three events are now recorded ones: `유이 → 카이토`, `산적들 → 카이토`, `카이토 → 유이` (the betrayal).
The Goal section's example changed accordingly.

## 3. PR description: agreed, fixed

The PR #64 description now matches the current draft: typed participants, the four predicates, 78
usable assertions in 18 scenes, the withdrawn fixed-list counts, the hint rule, and links to the audit,
the check and the test.

## Kept from the owner's commit

Commit `74dec5f` added the owner-reported case "taking part is not knowing" and its deterministic,
real-model and acceptance entries. This response leaves them unchanged. They are consistent with it:
participants never change knowledge marks, and the audit's `possessor` kind (`카이토 knows: 하나의
비밀`) is a participant, never a knower.

## Checks run

- `python3 tools/check_phase8_scope_audit.py`: no problems; 78 usable in 18 scenes.
- `cd apps/sidecar && uv run pytest -q`: see the PR's CI.
- `git diff --check`: clean.

Phase 8 remains a draft and is not authorized.
