# Phase 28 — A role that ends, and a name said two ways, after the AGE-24 live run

> **Status: approved 2026-10-03 (the owner, every proposed answer below), current as a correction phase (AGENTS §7
> item 5); step 2 in review (#251).** A correction found by measurement under AGE-24, not roadmap Stage 7 or 8. Scope narrowed on
> review of the first draft (#250): the role-ending and identity defects first, each behind a setting that is off by
> default; excerpt and ranking changes only after they are re-measured on the corrected state (Q6).

## Questions and proposed answers

| # | Question | Proposed answer (approved) | Alternatives considered |
|---|---|---|---|
| Q1 | How does a role end when the story ends it? | **The extractor is shown the roles in force, numbered, and names the one the story ends** (`extract-v16`). As `OPEN PROMISES`, `OPEN THREADS` and `OPEN SECRETS` already do, a `CURRENT ROLES` block lists the current `role_toward` facts before the target turn (R1, R2, …); when the TARGET turn ends one (a stay ends and they move out, someone quits or is dismissed, the arrangement is called off) the model reports it in `roles_ended` with a quote of the turn, and the worker writes the negative `role_toward` with the listed subject, object and value (a free negative between a listed role's parties is dropped). ADR 0013's matching rule (`facts.relation`: a negative must deny the same value) is unchanged, so the listed value closes the listed role and nothing else. *Amended on the owner's run of `a5c888a`* (39 calls on S2's role-ending turns): asking the model to copy the value closed 0 of 6, since it gave the role's name without its description; by number, nothing is copied. *Amended again on the re-run of `4a7c11c`* (22 calls): the values held and the employment ended 3/3, but the stay was ended on the eve of the move 3/3, on a sentence about the next day; each ending now states `when` ("now" over in the TARGET turn, "planned" only planned or prepared), and only "now" closes the role. *And on `37af724`* (9 calls): eve kept 3/3, resignation ended 3/3, the move 0/3 — the quote joined a CONTEXT sentence and a TARGET sentence with "..."; the rule now asks for one TARGET passage, and a joined quote counts by its passage found in the TARGET turn at the same bar (CONTEXT never counts). *And on `2e4ccfd`* (9 calls): move 3/3, resignation 3/3, eve kept 2/3 — once "now" on the TARGET sentence about the next day; a quote with a time word placing the change later (`LATER`) now closes nothing whatever `when` says. *And on `162b515`* (9 calls): eve 3/3, resignation 3/3, move 1/3 — twice the quote was the previous turn's room assignment (the reason, not the move); the rule now asks for the TARGET turn's own words for what happens there. A new role toward the same person still replaces the old one by itself (`role_toward` is single per direction, ADR 0059). | Loosen `facts.relation` for roles (match the role's head word, or tie an ending to a proven earlier role): changes ADR 0013's reconciliation rule and older replays, and can end the wrong role of a pair. Infer an ending from a departure (`located_in` negative): a departure is not an ending in general. |
| Q2 | Which roles are listed, and what about a first connection? | **Current, narrated, actual, positive `role_toward` facts before the target turn**, read from the generation's own earlier extractions like the other blocks: those whose party other than the persona the prompt names first, then the persona's own (the persona is in every scene), newest first, at most 8 (`OPEN_ROLES`). Live and first-sight work runs newest first (`extraction.claim`), so on a first connection a later turn can be extracted before the turn that set up its role and its list is empty or partial; a generation's backfill runs oldest first, so switching an existing chat to `extract-v16` lists in story order. `OPEN PROMISES` has the same limit today. Measured, not changed, here: the evaluation reports first-connection and backfill runs apart. | Hold a first connection's later turns until earlier ones are extracted (changes the worker's order for every generation; out of scope). |
| Q3 | How does `extract-v16` ship? | **Behind a setting, off by default.** `NMOS_EXTRACT_COMPILER` selects `extract-v15` (the default) or `extract-v16`; `extract-v15`'s generation key does not change, so no chat re-extracts on the upgrade. The owner selects `extract-v16` on isolated copies for the evaluation (Q5); making it the default is a later decision on its results. A prompt or registry change is a new generation (ADR 0006): `extract-v15` rows are never rewritten. | Replace `extract-v15` outright (Phase 25's way): every chat re-extracts on the merge that reaches `:edge`, before anything is measured. |
| Q4 | How are a full name and its given name joined? | **The extractor's alias rule, in `extract-v16` (decided by the owner 2026-10-03 on the measurement of the first answer).** The `also_called` rule also asks for an alias when the TARGET turn writes a character by a full name and, for the same character, by part of it (the given name alone; in a story in English the first or the last name alone): subject the full name, value the part; not when the two could be different people (they speak to or act on each other, are named side by side as two, or the story has another character with that name). ADR 0012's provenance and ambiguity rule apply as for any alias; when one name is part of the other, the turn check wants both written in that turn, the part on its own, not only inside the full name. It rides Q1's generation, so Q5 (c)'s paid run measures both. **The first answer, withdrawn:** a recorded recall option `given_name_join` joining the two at read time when the stored assertions mentioned both in the same turns. The owner's read-only measurement on #251's head (nine preserved databases, 837 reads; no model call) found **no join on any read**: the target pairs occur together in the text of 3 (S4b) and 20 (S2) turns but in the same turn's assertions in none, so S4b (2/3) and S2 (22/25) replays and the edited birthday were unchanged; and co-occurrence would not prove identity anyway. | The read-side join (withdrawn, above); the same join on the text's co-occurrence (a text read per request, and still no proof of identity); a suffix match alone (joins namesakes); saving owner links on the owner's chats (not this phase). |
| Q5 | How is it measured? | **Deterministic cases in CI, then the owner's measurement with every individual result reported.** (a) Per-defect replays on the preserved copies, read-only: the guest role current after its stay ended, the employment role and its differently worded ending both current, and the two split full/given-name histories; each reproduces the original ledger first. (b) Measured and withdrawn: the read-side join (Q4). (c) `extract-v16` against `extract-v15` on isolated copies with fixed inputs (`tools/eval_extract_sample.py --compiler extract-v16`): role endings found, endings that matched nothing, roles ended wrongly, the aliases given (each checked by the owner: a wrong one fails), the split pairs joined, token use; first connection and backfill apart; an exact call and token estimate approved by the owner before any paid call. (d) Then the live runs: the four regressed scenarios and S0main, three times each, reported as medians **and** every run. | Single runs against the historical lane (the first draft): one stochastic run each, no variance estimate; S3 and S4b also miss under `packet-v10` on the same extraction, so a single-run gate can fail a correct fix or pass a wrong one by chance. |
| Q6 | What is not in this phase? | Excerpt, sentence-anchor, fact-ranking or packet-policy changes (the first draft's slices 3 and 4: current-state questions selecting old passages, an answer-bearing sentence left out of its excerpt), re-scoped after Q5 (a) and (c) re-measure them on the corrected state; a fix for a name split that involves the persona (Q4 excludes it, the persona guard stays); a read-side name join of any script (withdrawn, Q4); simultaneous roles; automatic owner links; any change to the worker's order, the schema, or a default before its evidence; a release. | — |

Q1 measurement amendment (2026-10-03, `c582343`): the first three role checks passed, but the wider run stopped
at 76 calls when a new job incorrectly ended a continuing mentorship in 2/3 runs. The prompt now says that a
job, workplace or rank change does not itself end the relationship between the listed people; context can
establish continuity, while an ending still needs the TARGET. The bounded correction check passed 12/12
reconciliation checks over 27 calls. This does not complete Q5 (c); see `docs/perf/extract-v16-role-continuity.md`.

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
2. **The alias rule** (Q4), in `extract-v16`: a full name and a part of it, with the part checked on its own in the
   turn; ADR 0064 (proposed).
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
- [ ] **Identity (deterministic).** Under `extract-v16` an alias of a full name and a part of it joins the two as one
      character; the part only inside the full name links nothing; `extract-v15`'s check is as it was.
- [x] **The read-side join (Q5 b)**, measured by the owner on #251's head: no join on any of 837 reads; S4b 2/3 and S2
      22/25 replays unchanged; the edited birthday still missing. Not met: withdrawn (Q4).
- [ ] **`extract-v16` evaluation** (Q5 c, after the owner approves its estimate): the guest and employment endings
      close their roles on the isolated copies, no role is ended wrongly, the split pairs are linked and no alias joins
      two people, first connection and backfill reported apart, and token use within the approved estimate.
- [ ] **Live gate** (Q5 d, after a decision to switch defaults): the four regressed scenarios reach at least their
      historical scores at the median of three runs (21/25, 22/25, 6/6, 3/3); S0main keeps at least 8/10 in every run;
      the other sets keep their latest gains; all 24 sets and the raw forbidden-pattern counts reported for every run. A
      false join, a wrong role ending or a secret leak in any run fails the gate whatever the median.
- [ ] Latency: requests at 10,000 messages (`tools/bench_story.py`) on an `extract-v16` copy within the baseline's
      variation; fail-open and the memory budget intact.
- [ ] Diff-scoped self-review naming the guarantees at risk; STATUS, ADR 0064 and the ADR index reflect the adopted
      behaviour. AGE-24 stays open until its gate passes or the owner changes the criterion.

## Steps (one pull request each)

1. This document, approved; AGENTS §1/§2 and STATUS name Phase 28.
2. `extract-v16` (roles and the alias rule), off by default; deterministic cases; ADR 0064 (proposed); the tool's
   flag; the owner's measurement commands and the call estimate in the pull request. Not merged before the owner
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
