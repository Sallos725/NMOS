# 0064 — A role ended as listed (`extract-v16`), and a full name with its given name (`given_name_join`)

Status: **proposed**, 2026-10-03 (Phase 28 step 2, `docs/phases/PHASE-28.md` Q1–Q4; under AGE-24). Both are behind
settings that are off by default: `NMOS_EXTRACT_COMPILER=extract-v16` and `NMOS_GIVEN_NAME_JOIN=1`. Making either the
default is the owner's decision on the measurement of PHASE-28 Q5; until then this ADR is not accepted. No migration,
no plugin build; one recorded recall option added. ADR 0013's matching rule and ADR 0012's resolution are unchanged when
the settings are off.

## Context

The owner's live run on `e13dee7` found two state defects in its traces (PHASE-28 Goal):

1. **A role outlives its ending.** A stay that ended was extracted as a negative `located_in`, which cannot end
   `role_toward`; an employment's ending was extracted in other words than the role, so ADR 0013 item 4 (a negative of a
   per-object single-valued predicate must deny the same normalized value) left the role current beside it.
2. **One person, two entities.** A character written in full (백이안) and by the given name alone (이안) resolves to two
   entities: the story never says "이안, that is 백이안", so no `also_called` joins them (ADR 0012), and Phase 24 gives the
   given name to no one because it already names an entity of its own (ADR 0058 item 3). The extraction hints then list
   both, so the split persists.

## Decision

1. **`extract-v16`: CURRENT ROLES** (Q1, Q2). The extractor is shown the roles in force before the target turn, as
   OPEN PROMISES, OPEN THREADS and OPEN SECRETS are shown (`extraction.role_hints`, `roles_block`): the current,
   narrated, actual, positive `role_toward` facts of the generation's own earlier extractions, folded as the read side
   folds them, newest first: those whose party other than the persona the prompt names, then the persona's own, at most
   `OPEN_ROLES` (8). A rule after the role rule (`ROLE_ENDINGS`) asks, when the TARGET turn ends a listed role, for
   `role_toward` with `"negative"` and subject, object and value exactly as listed; not for a temporary absence or an
   unlisted role; a new role toward the same person replaces the listed one by itself (single per direction, ADR 0059).
   ADR 0013 is unchanged: the copied value is what lets the negative close exactly that role. The list is stored with
   the extraction's hints (`roles`).
2. **Selected by a setting, the default unchanged** (Q3). `NMOS_EXTRACT_COMPILER` selects one of
   `extraction.COMPILERS` (`extract-v15`, the default when empty, or `extract-v16`; anything else is refused at
   startup). `extraction.PROMPTS["extract-v15"]` is `SYSTEM_PROMPT` and its generation key is the one on `main` before
   Phase 28 (pinned); `extract-v16`'s differs by compiler and prompt only. A generation's own rows record its compiler.
3. **`given_name_join`: a recorded recall option, off unless asked for** (Q4). With it the request's resolution
   (`entities._given_joins`, after the story's aliases and the owner's links) joins a character written as a
   three-syllable Hangul name with a common family name (`variants.given`) to the character named by its given name
   alone when: both are mentioned in each of at least `GIVEN_JOIN_TURNS` (2) turns; no single assertion names both; no
   turn gives them different values of one single-valued predicate; no other character's full name has that given name;
   neither is the persona and the given name is not the persona's; neither name is ambiguous; and the owner has not split
   them (ADR 0044). The join is listed among the entity's aliases (`given_name: true`). `NMOS_GIVEN_NAME_JOIN=1` turns it
   on for new requests; `tools/eval_rp.py --given-name-join [--show-joins]` replays recorded requests with it and lists
   every join. The Inspector and the owner's previews read without it.
4. **Replay.** The option is recorded with the other recall options; a trace without it replays with it off
   (`audit.replay`), as `name_variants` (ADR 0058 item 6). `RESOLVER_VERSION` is unchanged: it only seeds entity ids, and
   a replay restores recorded options, not a resolver.

## Consequences

- With neither setting, nothing changes: the extractor key, every prompt, every packet and every replay are as before.
- Selecting `extract-v16` re-extracts every chat once (a new generation, ADR 0006). On a first connection, live and
  first-sight work runs newest first (`extraction.claim`), so a turn that ends a role can be extracted before the turn
  that set it up and then lists nothing: the role stays current. A generation's backfill runs oldest first, so an
  existing chat switched to `extract-v16` lists in story order. `OPEN PROMISES` has the same limit. Both pinned in
  `test_extract_v16.py`; PHASE-28 Q5 (c) measures first connection and backfill apart.
- **`given_name_join`'s conditions do not prove identity.** Two people, one written in full and one only by the same
  given name, mentioned in separate assertions of the same turns ("백이안이 들어왔다. 이안이 앉았다."), read exactly as
  one person called both ways and are joined (pinned in `test_given_name_join.py`). A wrong join mixes two characters'
  current facts and their knowledge marks. Hence a comparison candidate: never the default without the owner's decision,
  and withdrawn if any measured chat shows a false join (PHASE-28 Q4); identity would then go to the extractor's alias
  guidance instead.
- Under a join, what is kept from one spelling is kept from the joined character (`test_given_name_join.py`).
- `given_name_join` reads three-syllable Hangul names only. An English story's split ("Elena Vance" called "Elena" or
  "Vance") is not covered: there a story calls one person by either part and writes names in either order, so the
  namesake risk is wider; extending it waits for the measurement on Hangul names (PHASE-28 Q6). `extract-v16` is
  language-independent.
- Each request with the option reads its rows once more for the join's conditions; latency is measured before any
  default (PHASE-28 acceptance criteria).
- Evaluation: `tools/eval_extract_sample.py --compiler extract-v16` (role endings as listed and others counted apart),
  `tools/eval_rp.py --given-name-join --show-joins`.
