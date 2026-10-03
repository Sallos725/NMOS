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
   *Amended again on the owner's run of `4a7c11c`* (the same turns, 22 calls before the stop condition): the numbered
   endings carried the listed value, the employment ending closed 3 of 3 and the move 2 of 3 (the third quoted the
   previous turn and was rightly dropped), but on the eve of the move, still packing, the model ended the stay 3 of 3
   on a sentence about the next day. Each ending now states `when`: "now" when it is over by the end of the TARGET
   turn, "planned" when the turn only plans, arranges, announces or prepares it; only "now" is written, and a missing
   or other `when` closes nothing. The evidence must quote the TARGET turn, never CONTEXT.
   *And on the run of `37af724`* (9 calls): the eve kept the stay 3/3 ("planned") and the resignation ended 3/3, but the
   move closed 0/3: the model named the stay and "now" and quoted a sentence of the previous turn and one of the target
   joined by "...", which missed the bar as a whole (0.64–0.67 against 0.7). The rule now asks for one passage of the
   TARGET turn as it is; and `quoted_in` reads a quote joined by an ellipsis by its passages: the first of
   `EVIDENCE_MIN_CHARS` or more found in the turn at the same bar is the evidence kept, a passage from CONTEXT is never
   counted or kept. The bar is unchanged.
   *And on `2e4ccfd`* (9 calls): the move ended 3/3 and the resignation 3/3, each on one TARGET passage, but the eve
   was ended "now" once in three, on the same TARGET sentence about the next day (similarity 0.975). A quote that
   places the change later (`LATER`: 내일, 다음 날/주/달, 예정, tomorrow, next week, will, going to, …) now closes
   nothing whatever `when` says, and the rule says a sentence about tomorrow or later is never "now". This is a cue list
   in the K39 manner: it can miss an ending told with such a word (a stale role) and grows only by measurement; a
   premature ending (a wrong current state) is the worse error.
   *And on `162b515`* (9 calls): `LATER` held the eve 3/3 (it blocked one "now"), the resignation ended 3/3, but the
   move closed 1/3: twice the model named the stay "now" and quoted only the previous turn's room assignment (the
   reason for the move, not the move). The rule now asks for the TARGET turn's own words for what happens there that
   ends the role (they carry their bags out, hand back the key, say they quit), and says a reason, an arrangement or a
   plan in CONTEXT is not evidence; the closing line asks to quote the text after "TARGET turn N:". The quote check is
   unchanged.
   *And on `c582343`* (76 calls before stopping): the three earlier role checks passed 3/3 each, but S2 turn 74
   ended the protagonist's mentorship in 2/3 runs on taking another job, although the context explicitly kept the
   lessons. The prompt now distinguishes a relationship between two people from a job title or workplace: context
   may establish continuity, while an ending still needs the TARGET to end that relationship. The parser and
   reconciliation rule are unchanged. A bounded 27-call remeasurement kept the mentorship 3/3 and the earlier
   three checks 3/3 each; this does not establish the full comparison or worker/backfill acceptance. See
   `docs/perf/extract-v16-role-continuity.md`.
   *And on `073b7a1`* (the aliases now kept, item 2): the four core checks held 12/12, but at S2 turn 99, a promotion
   at the bakery, the model ended the listed role toward the inn's owner ("now", R5, a TARGET quote about the
   promotion) in 2 of 3 runs; the parser had refused the same wrong ending earlier only for its malformed reference.
   The rule now says a new role, job or promotion toward someone else never ends a listed role toward a different
   person, the evidence having to show the listed role's own two people parting; the closing line asks whether the
   turn ends each role "between its own two people (a new role or promotion toward someone else does not)". Parser
   unchanged.
   *And on `ed10842`* (41 calls before stopping): the unrelated bakery promotion still ended the inn employment
   in 2/3 runs. `ended_roles` now also requires the listed counterpart's name or an unambiguous KNOWN ENTITIES alias
   in the bounded, shown TARGET. For a role toward the persona, the check uses the other party (the existing
   resolver's persona-name rule). CONTEXT, hints alone, text beyond the shown target, another entity type and a
   shared alias do not supply that mention. The name can be outside the quote: the PR comment's quote-only proposal
   would reject all 31 preserved correct move/resignation endings. Replaying the implemented guard keeps those 31
   and drops eight known wrong endings; the fresh 90-call S2 probe passes 15/15 core role checks and 6/6 name joins.
   The model still proposes a wrong ending once at turn 99, blocked by the guard. This is a conservative prerequisite,
   not semantic proof: a pronoun-only counterpart may leave a stale role, and an incidental name in the turn can
   still accompany a wrong model judgment. Three additional endings at turn 219 require sequential state review;
   fixed v15 hints do not establish their ending time. No default change or Q5 completion follows from this result.
   See `docs/perf/extract-v16-role-target.md`.
   *And on `f747f4f`* (507 successful samples before stopping): a shop's closure ended a continuing residence
   in 3/3 runs despite the resident keeping access. The system rule and closing reminder now distinguish
   closing a business or retiring from ending a residence or mentorship, and check continued access at the
   TARGET's end. System-only wording still failed 2/3; the final 24-call check keeps this role 3/3 and passes
   all six role cases (18/18) and name joins (6/6). Parser unchanged; this is a prompt mitigation requiring a
   new generation and full measurement, not a semantic guarantee. See `docs/perf/extract-v16-role-closure.md`.
   *And on `7dbef46`* (739 samples): S1's resignation (turn 233) was named correctly ("now", both directions, a
   TARGET quote), but the turn called the listed 강무진 by the given name 무진 alone and the fixed hints did not link
   them, so the counterpart check refused all six endings (S1 15/18). The check now also counts the counterpart's
   given name alone (`name_parts`, as NAME PAIRS reads it), written apart, when no other known full name shares it
   and it is not the persona's. A namesake known only by the given name still counts: the check stays a
   prerequisite, not proof of identity. Not yet measured with a model; the owner's offline counterfactual with the
   alias supplied closed 3/3.
   The same review found that `LATER`'s 내주 and 내달 (next week, next month) also matched the verbs 내주다 (hand
   over: "열쇠를 내주고") and 내달리다 (dash), so a done ending quoted with them closed nothing; they now count only as
   the nouns (followed by a space, a particle such as 에, 의 or 부터, or the end). No model call measured this.
2. **A name and a part of it** (Q4). The `also_called` rule (`ALIAS_PARTS`, in place of `extract-v15`'s `V15_ALIAS`)
   also asks for an alias when the TARGET turn writes a character by a full name and, for the same character, by part
   of it: the given name alone, or in a story in English the first or the last name alone; subject the full name, value
   the part. Not when the two could be different people: they speak to or act on each other, are named side by side as
   two, or the story has another character with that name. Provenance is ADR 0012's: the alias lives as long as its
   turn, and a name linked to two others is ambiguous and joins neither. The turn check is stricter for this case
   (`alias_evidenced(..., apart=True)`, `PARTS_APART`): when one name is part of the other, the turn must write the
   full name, and the part on its own, not only inside the full name; a full name known only from earlier turns
   (KNOWN ENTITIES, ADR 0024) does not stand in, since a part alone may be someone else's name.
   *Amended on the owner's run of `27c7658`:* on all 27 S2 turns that write a known full name and its part apart (two
   pairs, 7 and 20 turns, 3 runs each, 81 calls) the model gave no `also_called` at all, in the raw answer; the hints
   listed the full name and the part as two KNOWN ENTITIES. As with the roles, the choice is now made for the model to
   answer by number: **NAME PAIRS** (`extraction.name_pairs`, `pairs_block`, at most `NAME_PAIRS`, 8) lists each full
   name of a named character in KNOWN ENTITIES whose part (`name_parts`: the given name of a Hangul name of three or
   four syllables; the first or the last word of a Latin name of two words or more) the TARGET turn writes apart as
   `alias_evidenced(apart=True)` checks it, as N1, N2, …; not a pair the hints already show as one entity, a part two
   known full names share (a namesake), or a name of the persona (PHASE-28 Q6). The rule and a closing line ask the
   model to report in `same_names` each pair the turn uses for one character, with a quote of the TARGET turn;
   `extraction.same_names` writes the `also_called` (subject the listed full name, value the part) when the quote is
   in the turn (`quoted_in`), and drops a free `also_called` the model wrote between a listed pair's names. The pairs
   are stored with the extraction's hints (`names`). Identity is still the model's judgment, now asked of it pair by
   pair; ADR 0012's turn check, provenance and ambiguity rule are unchanged, and a name whose full name is not yet
   known (a first introduction) is left to the free rule above.
   *And on `0abb2fd`* (90 calls; roles 12/12): NAME PAIRS were listed on 21 of the 27 turns, and on 46 of their 63
   answers the model confirmed a pair by its names (`"pair": "윤하람 / 하람"`) instead of its number, which the parser
   refused (17 gave none); no alias was kept, none wrong. The rule now says `pair` is the number as listed, never the
   names, and the closing line shows the answer for N1 with its names (`for N1, 윤하람 / 하람: {"pair": "N1", …}`). The
   parser is unchanged: a pair named by its names is still refused.
   *And on `073b7a1`* (81 calls): every `same_names` entry used the number; 49 aliases were kept (9 refused by the quote
   check), only the two target pairs, and both pairs resolved as one entity in each run (윤하람/하람 2/2/2 turns, 백이안/
   이안 15/14/14).
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
