# Phase 28 — A role that ends, and a name said two ways, after the AGE-24 live run

> **Status: approved 2026-10-03 (the owner, every proposed answer below), current as a correction phase (AGENTS §7
> item 5); step 2 next.** A correction found by measurement under AGE-24, not roadmap Stage 7 or 8. Scope narrowed on
> review of the first draft (#250): the role-ending and identity defects first, each behind a setting that is off by
> default; excerpt and ranking changes only after they are re-measured on the corrected state (Q6).

## Questions and proposed answers

| # | Question | Proposed answer (approved) | Alternatives considered |
|---|---|---|---|
| Q1 | How does a role end when the story ends it? | **The extractor is shown the roles in force and ends one exactly as listed** (`extract-v16`). As `OPEN PROMISES`, `OPEN THREADS` and `OPEN SECRETS` already do, a `CURRENT ROLES` block lists the current `role_toward` facts before the target turn; when the TARGET turn ends one (a stay ends and they move out, someone quits or is dismissed, the arrangement is called off) the model gives `role_toward` with `"negative"` and subject, object and value **exactly as listed**. ADR 0013's matching rule (`facts.relation`: a negative must deny the same value) is unchanged, so the copied value closes the listed role and nothing else. A new role toward the same person still replaces the old one by itself (`role_toward` is single per direction, ADR 0059). | Loosen `facts.relation` for roles (match the role's head word, or tie an ending to a proven earlier role): changes ADR 0013's reconciliation rule and older replays, and can end the wrong role of a pair. Infer an ending from a departure (`located_in` negative): a departure is not an ending in general. |
| Q2 | Which roles are listed, and what about a first connection? | **Current, narrated, actual, positive `role_toward` facts before the target turn**, read from the generation's own earlier extractions like the other blocks: those whose party other than the persona the prompt names first, then the persona's own (the persona is in every scene), newest first, at most 8 (`OPEN_ROLES`). Live and first-sight work runs newest first (`extraction.claim`), so on a first connection a later turn can be extracted before the turn that set up its role and its list is empty or partial; a generation's backfill runs oldest first, so switching an existing chat to `extract-v16` lists in story order. `OPEN PROMISES` has the same limit today. Measured, not changed, here: the evaluation reports first-connection and backfill runs apart. | Hold a first connection's later turns until earlier ones are extracted (changes the worker's order for every generation; out of scope). |
| Q3 | How does `extract-v16` ship? | **Behind a setting, off by default.** `NMOS_EXTRACT_COMPILER` selects `extract-v15` (the default) or `extract-v16`; `extract-v15`'s generation key does not change, so no chat re-extracts on the upgrade. The owner selects `extract-v16` on isolated copies for the evaluation (Q5); making it the default is a later decision on its results. A prompt or registry change is a new generation (ADR 0006): `extract-v15` rows are never rewritten. | Replace `extract-v15` outright (Phase 25's way): every chat re-extracts on the merge that reaches `:edge`, before anything is measured. |
| Q4 | How are a full name and its given name joined? | **A recorded recall option, `given_name_join`, off by default; a read-only comparison candidate (ADR 0064, proposed).** With it, the request's entity resolution joins a character named by a three-syllable Hangul name (`variants.given`, ADR 0058) to the character named by its given name alone when **all** hold: the two names are mentioned in the same turn in at least `GIVEN_JOIN_TURNS` (2) turns; no single assertion names both (a statement relating the two, or listing both as participants, says they are two people); no other character's full name has the same given name; neither is the persona, nor the persona's given name; neither name is ambiguous; and the owner has not split the two (ADR 0044). Nothing is stored. A trace records the option, and a trace without it replays with it off, as `name_variants` does: `RESOLVER_VERSION` alone does not keep older replays (it only seeds entity ids; `audit.replay` restores recorded options, not a resolver). | Wider `also_called` guidance in the extractor (identity from the narration's coreference): sound provenance, but a full re-extraction and a paid run; kept for after the resolver comparison, in the same generation as Q1 if still needed. A suffix match alone: joins namesakes. Saving owner links on the owner's chats: not this phase. |
| Q5 | How is it measured? | **Deterministic cases in CI, then the owner's measurement with every individual result reported.** (a) Per-defect replays on the preserved copies, read-only: the guest role current after its stay ended, the employment role and its differently worded ending both current, and the two split full/given-name histories; each reproduces the original ledger first. (b) `given_name_join` against off on the same traces (`tools/eval_rp.py --given-name-join`), no model call. (c) `extract-v16` against `extract-v15` on isolated copies with fixed inputs (`tools/eval_extract_sample.py --compiler extract-v16`): role endings found, endings that matched nothing, roles ended wrongly, token use; first connection and backfill apart; an exact call and token estimate approved by the owner before any paid call. (d) Then the live runs: the four regressed scenarios and S0main, three times each, reported as medians **and** every run. | Single runs against the historical lane (the first draft): one stochastic run each, no variance estimate; S3 and S4b also miss under `packet-v10` on the same extraction, so a single-run gate can fail a correct fix or pass a wrong one by chance. |
| Q6 | What is not in this phase? | Excerpt, sentence-anchor, fact-ranking or packet-policy changes (the first draft's slices 3 and 4: current-state questions selecting old passages, an answer-bearing sentence left out of its excerpt), re-scoped after Q5 (a) and (b) re-measure them on the corrected state; a fix for a name split that involves the persona (Q4 excludes it, the persona guard stays); simultaneous roles; automatic owner links; any change to the worker's order, the schema, or a default before its evidence; a release. | — |

## Goal

Two defects confirmed in the stored traces of the owner's live run on `e13dee7` (AGE-24), each a state error rather
than a scoring artefact:

1. **A role outlives its ending.** The protagonist's guest role toward the innkeeper stays current after the story has
   them leave (the leaving was extracted as a negative `located_in`, which cannot end `role_toward`); an employment role
   stays current next to its own ending, which the extractor wrote in other words, so ADR 0013's value match does not
   close it. Both reach current-state questions as current facts.
2. **One person, two entities.** A character written in full and by the given name alone resolves to two entities
   with separate current histories: the given name already names an entity of its own, so Phase 24's one-owner rule
   (ADR 0058 item 3) gives the variant to no one, and the extraction hints then list the given name separately, so the
   split persists. An edited birthday under one spelling misses a question asked with the other; an old form of
   address stays current under one spelling after the other's later change.

## Baseline

The owner's live run on `e13dee7` (packet and input evidence scores, not generated-answer accuracy, and not an
isolated #247 A/B): S0main full-history memory cases 8/10, 10/10 and 8/10 (the real-chat target met); against the
historical NMOS lane, S1 final 21/25 → 19/25, S2 full history 22/25 → 20/25, S3 6/6 → 5/6, S4b 3/3 → 2/3. The result
files, captured requests and databases stay with the owner, outside the repository; this spec cites aggregates only.

## What the investigation established (read-only, 2026-10-03)

- The affected full/given-name pairs have no alias row in the active generation; both spellings occur in the same
  turns, not in a "name (other name)" statement, so `extract-v15`'s `also_called` rule ("the TARGET turn itself gives
  both names") does not apply.
- With the subject names linked, the employment role and its ending share `facts.version_key` but not
  `facts.relation`: both stay current. A controlled reconstruction confirms an identical-value negative ends the role
  and an unrelated-role negative leaves it current.
- The guest role has one history entry; the room departures are negative `located_in` assertions.
- The owner's link preview (PHASE-20) recovers the edited birthday and ends the old address, and leaves both roles
  current: identity and role endings are separate defects.

## In scope (Phase 28)

1. **`extract-v16`** (Q1–Q3): `CURRENT ROLES` in the extraction prompt, the rule to end a listed role exactly as
   listed, the hints stored with the extraction (`roles`), `NMOS_EXTRACT_COMPILER`, and the evaluation tool's
   `--compiler`.
2. **`given_name_join`** (Q4): the recall option, recorded and replayed off for older traces; `NMOS_GIVEN_NAME_JOIN`
   for new requests (off by default); `tools/eval_rp.py --given-name-join`; ADR 0064 (proposed).
3. Deterministic cases for every branch of Q1, Q2 and Q4, and a pin that `extract-v15`'s generation key and every
   default request are unchanged.
4. The owner's measurement (Q5) and the decision it supports.

## Out of scope (Phase 28)

Q6, and: a new predicate; a change to `facts.relation`, `facts.version_key` or ADR 0013; rewriting or re-extracting
`extract-v15` rows or the benchmark baseline; the Inspector's and the owner preview's resolution (they keep the
default); a migration; a plugin build.

## Acceptance criteria

- [ ] **Defaults unchanged.** With no new setting, `extract-v15`'s generation key, its prompt and every request's
      packet are as before; recorded requests replay as they were (full sidecar suite and memory evaluation).
- [ ] **Roles (deterministic).** A listed role ended in the TARGET turn closes exactly that role; an ending of another
      role, a temporary absence, a negative `located_in` and a reverse-direction role leave it current; a new role toward
      the same person replaces it; past questions still see the ended role in its history; an empty list asks for nothing.
- [ ] **Identity (deterministic).** The option joins a full name and its given name under Q4's conditions; it does not
      join when a single assertion names both, when two full names share the given name, for the persona or the
      persona's given name, for an ambiguous name, after an owner split, or below `GIVEN_JOIN_TURNS`; a trace without the
      option replays with it off; secrets kept from one spelling stay kept under the joined entity.
- [ ] **Per-defect replays** (Q5 a, b): with `given_name_join`, the split histories join and the edited birthday and the
      later address are current, with no false join reported on any traced chat; the role defects are reported as they
      stand (the option does not end roles).
- [ ] **`extract-v16` evaluation** (Q5 c, after the owner approves its estimate): the guest and employment endings
      close their roles on the isolated copies, no role is ended wrongly, first connection and backfill reported apart,
      and token use within the approved estimate.
- [ ] **Live gate** (Q5 d, after a decision to switch defaults): the four regressed scenarios reach at least their
      historical scores at the median of three runs (21/25, 22/25, 6/6, 3/3); S0main keeps at least 8/10 in every run;
      the other sets keep their latest gains; all 24 sets and the raw forbidden-pattern counts reported for every run. A
      false join, a wrong role ending or a secret leak in any run fails the gate whatever the median.
- [ ] Latency: a request with `given_name_join` measured at 10,000 messages (`tools/bench_story.py`), within the
      baseline's variation; fail-open and the memory budget intact.
- [ ] Diff-scoped self-review naming the guarantees at risk; STATUS, ADR 0064 and the ADR index reflect the adopted
      behaviour. AGE-24 stays open until its gate passes or the owner changes the criterion.

## Steps (one pull request each)

1. This document, approved; AGENTS §1/§2 and STATUS name Phase 28.
2. `extract-v16` and `given_name_join`, both off by default; deterministic cases; ADR 0064 (proposed); the tools'
   flags; the owner's measurement commands and the call estimate in the pull request. Not merged before the owner
   reviews it.
3. The owner's measurement (Q5 a–c), recorded as aggregates; the decision on each default (ADR 0064 accepted or
   withdrawn).
4. The live runs (Q5 d) on the merged defaults; then the first draft's slices 3 and 4 re-scoped on what remains.

## Stop conditions

Stop and ask the owner when: a default request, `extract-v15`'s key or an older replay changes; a needed schema,
migration or runtime-dependency change; a false join or a wrong role ending on any measured chat; a secret leak; a
paid run would exceed its approved estimate; a baseline is unavailable; an acceptance bar is missed. Never replace the
owner's measurement with synthetic results.

**High risk (AGENTS §14):** identity and provenance (a join changes which facts are one entity's); current versus
historical state (a role's ending); stored extraction generations (`extract-v16`); knowledge boundaries under a joined
entity; replay of recorded requests.
