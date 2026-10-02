# Phase 28 — Identity, role endings and answer selection after the AGE-24 live run

> **Status: draft, 2026-10-03; no implementation or paid evaluation authorized.** Proposed correction under
> AGE-24, not roadmap Stage 7 or 8. The owner asked whether the problems recorded in
> [PR #249](https://github.com/Sallos725/NMOS/pull/249) can be fixed. This document makes the proposed scope
> reviewable; it does not treat that question as approval of new identity or reconciliation rules.

## Goal and baseline

Recover the failed S1/S2 current-state, S3 book-title and S4b edited-birthday cases while retaining the real-chat
recall gains. Identity evidence, a role's ending, and the selection of an answer are separate problems and must
be measured separately before combining changes.

The baseline is PR #249 at `536947980e4a22402078148eb9aa3fa1ec42987c`, reporting the live run on `e13dee7`:
S1 final 19/25 (historical 21/25), S2 full history 20/25 (22/25), S3 5/6 (6/6), S4b 2/3 (3/3).
S0main full-history memory cases passed 8/10, 10/10 and 8/10. Preserve all 24 result sets and their original
rubric. These are packet/input evidence scores, not generated-answer accuracy or an isolated #247 A/B test.

## Additional investigation on 2026-10-03

Code inspected at `c603356`. The preserved evaluation databases were opened with PostgreSQL
`default_transaction_read_only=on`, bounded by the recorded request's position and time on the preserved current
head. This inventory is not an exact packet replay and does not replace PR #249's baseline scores.

- S4b trace `01a0fbfc-b7df-70d3-a702-848ae6d8230c`: 472 served assertions, one served alias; no active-generation
  `also_called` row for 하람 / 윤하람. The two spellings occur separately within turns 2, 33 and 99.
- S2 trace `01a0fc1a-aabe-7b61-94f8-2fcab9967e06`: 1,115 served assertions, two served aliases. The active
  generation has two valid and three pending aliases; none concerns 도윤 / 서도윤, 이안 / 백이안 or 하람 / 윤하람.
  The introductory turns contain full names and narrative references using the given names. In the inspected
  introductions (turns 0, 2 and 7), each source message is under the extractor's 6,000-character target limit.
  This rules out simple target-length truncation there; it does not prove that every cooccurrence establishes identity.
- S2's guest role is assertion 517, turn 1. Room departures are negative `located_in` rows 901 and 908, turns 86
  and 87. They cannot themselves end a `role_toward` fact.
- S2's positive role 103, turn 222, says `항해사: 무진의 배에서 일함`; negative 45, turn 233, says
  `항해사: 청새치호에서 일했음`. With the subject names linked, `facts.version_key` agrees but `facts.relation`
  differs. A pure reconstruction using these fields confirms that both stay current; an identical-value negative
  ends the positive, while an unrelated-role negative leaves it current. These are three controlled checks,
  not new live scenario results.
- Seven existing pure tests passed: stated aliases, ambiguous aliases, occupied given names, secret marking under
  a variant, matching negation, holder-specific negation, and bounded excerpt growth. No product code changed.

Local diagnostic script and detailed inventory: `/tmp/nmos-pr249-investigation/inventory.py` and `inventory.json`.
They read the isolated `nmos_age24_e13dee7_s2_1` and `nmos_age24_e13dee7_s4b_1` databases. No links were saved,
no extraction was discarded or rerun, and no model/embedding call was made. Temporary files are not durable fixtures;
a subsequent experiment must record its inputs, script hashes and aggregate results alongside its report.

## Proposed scope and decisions for approval

| Slice | Proposed change or experiment | Required boundary |
|---|---|---|
| 1. Evidenced identity | Compare the missing aliases against their full source turns and stored hints. Test extractor guidance to preserve full/given-name identity when the narration establishes it, using the existing `also_called` provenance path. | No suffix-only merge, no bypass of occupied-name exclusions, no automatic owner links. Ambiguous people stay separate. A prompt change gets a new extractor generation. |
| 2. Role endings | Separate a missing role-end assertion from an extracted negative that cannot match its positive. Compare stable role values and evidence-backed matching of an explicit ending to an earlier role on isolated data. Select the smallest candidate that passes the controls below. | Keep the existing one-current-role-per-direction contract. Do not let any departure end every role or drop value matching for all negatives. Adoption of a changed matching rule requires an explicit ADR decision and a defined replay/older-generation strategy before runtime changes. |
| 3. Current versus historical evidence | After correcting identity/state, replay S1/S2 with fixed candidates. Test whether provenance can distinguish an obsolete state passage from useful old evidence on current-state questions. | No age-only filtering; preserve early one-off facts and before/first/why answers. If the evidence cannot establish obsolescence, do not invent it. |
| 4. Answer-bearing text | For S3, compare content-keyword sentence scoring, adjacent-sentence selection and question-specific fact selection independently. | No book-title-specific rule. Keep candidates and budget fixed when isolating selection; evaluate paraphrases and held-out questions before combining changes. Preserve v11's ordinary excerpt limit/four-sentence rule and its why/contents 320-character cap unless the owner approves a specific alternative. |

The first implementation candidate is slice 1 after its evidence inventory, with positive and collision controls.
Role matching and selection candidates are not settled merely by approving this scope: record their exact rule,
version/replay treatment and controlled comparison before proposing adoption. Existing owner previews can diagnose
confirmed pairs; saving links to the owner's conversations is not part of this phase.

Prompt/registry edits must be grouped into one proposed new generation before adoption, with the existing
recent-window and older-generation fallback behavior made explicit. Do not rewrite `extract-v15` rows or silently
re-extract the benchmark baseline. A packet or ranking change must be recorded/versioned so earlier requests retain
their original behavior. Do not choose a new generation or packet policy as the default before its evidence gate.

## Acceptance criteria (proposed; none met by the investigation above)

- [ ] Identity: the affected pairs have source-backed identity or remain explicitly unresolved; same-given-name
      people, owner splits, persona classification and secret boundaries retain their intended behavior. Editing,
      deleting, disabling or rerolling the alias source removes its influence on the next packet.
- [ ] Roles: the observed guest and employment failures no longer appear as obsolete current facts when their
      endings are established. Controls cover another role's negation, temporary absence, changes of workplace,
      repeated descriptions, reverse-direction roles and past questions. No simultaneous-role feature is added.
- [ ] Selection: S3's title and S4b's edited birthday reach their unchanged questions without the obsolete answer;
      S1/S2 current-state questions exclude the demonstrated obsolete current assertions. History and negated old
      terms are classified separately without changing the raw score after the fact.
- [ ] Replay controls: reproduce the original ledger/text before claiming any fixed-candidate counterfactual.
      Freeze query, previous reply, visible context, membership, known-at time, policy and budget. Otherwise report
      only an inventory or memory-view diagnostic. Recorded older requests keep their original results.
- [ ] Fresh-extraction controls, if needed: isolated copies, fixed inputs, repeated outputs, per-turn alias/end
      provenance, false joins/false terminations, missing facts and token usage. Mixed old/new generations are tested.
      Review an exact call/token estimate and obtain its approval before any paid/model evaluation.
- [ ] Final live gate: propose at least the historical scores on the four regressed sets (21/25, 22/25, 6/6, 3/3),
      retain other sets' latest gains, and retain S0main's at-least-8/10 memory target across three repetitions.
      Report all 24 sets and original forbidden-pattern counts; do not trade a case loss for an aggregate gain.
      If the raw forbidden rubric rejects valid history/negation, present that conflict for an owner decision.
- [ ] The full sidecar suite and memory evaluation pass. A changed request path is measured at 10,000 messages
      with alternating baseline/candidate rounds, p50/p95 and packet sizes; latency must remain within measured
      baseline variation. Fail-open and the 4,000-token reserve remain intact.
- [ ] Diff-scoped self-review names the guarantees at risk; docs, STATUS and applicable ADRs reflect the adopted
      behavior and actual evidence. AGE-24 stays open until its full gate passes or the owner changes the criterion.

## Steps and stop conditions

1. Review this draft and approve the correction scope; update AGENTS §2 and STATUS only after approval.
2. Freeze the baseline and source evidence inventory; add focused regression expectations for one slice at a time.
3. Implement and compare bounded candidates on isolated data. Review each changed semantic rule before adoption;
   keep unmeasured behavior off the production default. Request a concrete model-run budget only when prepared.
4. Run the full controls, then the explicitly budgeted live benchmark. Record failures as failures and stop at the
   evidence boundary. No release/tag or production rebuild is included.

Stop for an invariant/ADR conflict, a needed schema or runtime-dependency change, altered old replay, a new false
identity/role termination or secret leak, a missed acceptance bar, an unavailable baseline, or a paid run exceeding
its approved budget. Do not replace real host/model evidence with synthetic unit results.

**High risk (AGENTS §14):** identity and provenance; current versus historical state; stored extraction generations;
knowledge boundaries; retrieval/injection selection and fail-open behavior. This draft changes none of those paths.
