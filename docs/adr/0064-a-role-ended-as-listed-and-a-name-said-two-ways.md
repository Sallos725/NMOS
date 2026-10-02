# 0064 — `extract-v16`: a role ended as listed, and a name said two ways

Status: **proposed**, 2026-10-03 (Phase 28 step 2, `docs/phases/PHASE-28.md` Q1–Q4; under AGE-24). Behind
`NMOS_EXTRACT_COMPILER=extract-v16`, off by default. Making it the default is the owner's decision on the measurement of
PHASE-28 Q5; until then this ADR is not accepted. No migration, no plugin build, no recall option. ADR 0012's
resolution and ADR 0013's matching rule are unchanged. **Amended the same day:** the read-side join first proposed for
Q4 (`given_name_join`) was measured, joined nothing, and is withdrawn (below); Q4 is the extractor's alias rule instead.

## Context

The owner's live run on `e13dee7` found two state defects in its traces (PHASE-28 Goal):

1. **A role outlives its ending.** A stay that ended was extracted as a negative `located_in`, which cannot end
   `role_toward`; an employment's ending was extracted in other words than the role, so ADR 0013 item 4 (a negative of a
   per-object single-valued predicate must deny the same normalized value) left the role current beside it.
2. **One person, two entities.** A character written in full (윤하나) and by the given name alone (하나) resolves to two
   entities. `extract-v15` links two names only when "the TARGET turn itself gives both names for the same entity"
   ("하나(Hana)"), which narration that simply calls a character both ways never does; and Phase 24 gives the given name
   to no one because it already names an entity of its own (ADR 0058 item 3). The extraction hints then list both, so
   the split persists.

## Decision

1. **CURRENT ROLES** (Q1, Q2). The extractor is shown the roles in force before the target turn, as OPEN PROMISES,
   OPEN THREADS and OPEN SECRETS are shown (`extraction.role_hints`, `roles_block`): the current, narrated, actual,
   positive `role_toward` facts of the generation's own earlier extractions, folded as the read side folds them, newest
   first: those whose party other than the persona the prompt names, then the persona's own, at most `OPEN_ROLES` (8).
   The roles are numbered (R1, R2, …), as OPEN SECRETS are (S1, …). A rule after the role rule (`ROLE_ENDINGS`) asks
   the model to report in `roles_ended` each listed role the TARGET turn ends, with a quote of the turn; not a temporary
   absence; not to write the ending as a `role_toward` itself; a new role toward the same person replaces the listed one
   by itself (single per direction, ADR 0059). `extraction.ended_roles` writes each ending as a negative `role_toward`
   with the listed subject, object and value (an unknown number or a quote not in the turn gives nothing), and drops a
   negative `role_toward` the model wrote itself between a listed role's two parties. ADR 0013 is unchanged: the
   listed value is what lets the negative close exactly that role. The list is stored with the extraction's hints
   (`roles`).
   *Amended 2026-10-03 on the owner's run of `a5c888a`:* the first rule asked the model to write the negative with the
   listed value copied. On the S2 role-ending turns (13 turns, 3 runs each, 39 calls, `gemma4:31b`), it closed 0 of 6:
   the endings it gave carried the role's name without the description the list showed, in the raw answer, so they
   matched nothing; the stay's ending was missed in 2 of 3 runs. Naming the listed role by number takes the copy away
   from the model.
2. **A name and a part of it** (Q4). The `also_called` rule (`ALIAS_PARTS`, in place of `extract-v15`'s `V15_ALIAS`)
   also asks for an alias when the TARGET turn writes a character by a full name and, for the same character, by part
   of it: the given name alone, or in a story in English the first or the last name alone; subject the full name, value
   the part. Not when the two could be different people: they speak to or act on each other, are named side by side as
   two, or the story has another character with that name. Provenance is ADR 0012's: the alias lives as long as its
   turn, and a name linked to two others is ambiguous and joins neither. The turn check is stricter for this case
   (`alias_evidenced(..., apart=True)`, `PARTS_APART`): when one name is part of the other, the turn must write the
   full name, and the part on its own, not only inside the full name; a full name known only from earlier turns
   (KNOWN ENTITIES, ADR 0024) does not stand in, since a part alone may be someone else's name.
3. **Selected by a setting, the default unchanged** (Q3). `NMOS_EXTRACT_COMPILER` selects one of
   `extraction.COMPILERS` (`extract-v15`, the default when empty, or `extract-v16`; anything else is refused at
   startup). `extraction.PROMPTS["extract-v15"]` is `SYSTEM_PROMPT` and its generation key is the one on `main` before
   Phase 28 (pinned); `extract-v16`'s differs by compiler and prompt only. A generation's own rows record its compiler.
   `extract-v15`'s alias check is as it was.

## Withdrawn: `given_name_join`

The first step 2 proposed a recorded recall option that joined, at read time, a three-syllable Hangul name and its
given name when the stored assertions mentioned both in the same turns (at least two) and nothing said they were two
people. The owner's read-only measurement on #251's head (`5e3032f`; nine preserved databases, 837 reads at their
recorded positions and times; no model call): **no join on any read**, the S4b and S2 replays without vectors unchanged
(2/3 and 22/25), the S4b edited birthday still missing on the original ledger with fixed candidates. Cause: the target
pairs occur together in the text of 3 (S4b) and 20 (S2) turns, but in the subject, object or participants of the same
turn's assertions in none, so the evidence the option read was never there. Co-occurrence in the text would not prove
identity either (two people so named read the same), so the owner chose the extractor's alias rule (item 2), which the
same paid `extract-v16` run measures. The option, its setting and its tool flags were removed before merge.

## Consequences

- Without the setting, nothing changes: the extractor key, every prompt, every packet and every replay are as before.
- Selecting `extract-v16` re-extracts every chat once (a new generation, ADR 0006). On a first connection, live and
  first-sight work runs newest first (`extraction.claim`), so a turn that ends a role can be extracted before the turn
  that set it up and then lists nothing: the role stays current. A generation's backfill runs oldest first, so an
  existing chat switched to `extract-v16` lists in story order. `OPEN PROMISES` has the same limit. Pinned in
  `test_extract_v16.py`; PHASE-28 Q5 (c) measures first connection and backfill apart.
- The alias rule asks the model to judge identity from the narration. A wrong alias joins two characters' facts and
  knowledge marks; the turn check, the ambiguity rule and the owner's split (ADR 0044) are the guards, and the Q5 (c)
  evaluation counts every alias the model gives. It covers names in Latin script as well.
- Evaluation: `tools/eval_extract_sample.py --compiler extract-v16` (role endings as listed and others counted apart;
  the alias check as the worker applies it).
