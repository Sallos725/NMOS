# 0021 — Typed participants

Status: accepted, 2026-09-24. Phase 8 (`docs/phases/PHASE-8.md`, owner answers Q1–Q5). Amends ADR 0012
(entity identity): participants are mentions, read after every `resolve-v1` name source. Steps 1–2:
the field, migration 0017, `resolve-v2` and recall. `extract-v8` (step 3) asks the model for them.

## Context

An `event`, `goal`, `knows` or `destroyed` value often names a second person: `카이토 event: 유이를
경비병들에게 넘겨주었다`. Fact recall counted only the subject and object as mentions, so addressing 유이
never brought the fact back: 0 of 18 in the recorded-event check. The scope audit counts 78 usable
assertions in 18 scenes (`fixtures/model/phase8/scope-audit.json`, `tools/check_phase8_scope_audit.py`).

## Decision

1. **Typed field (Q2, Q3).** The extractor lists participants as `with: [{name, type}]`, type
   `character` or `group`. `predicates.participants()` keeps them only on `event`, `goal`, `knows` and
   `destroyed`. It drops an entry without a name of at most 60 characters or of another type, drops the
   subject, the object and a repeated `(type, normalized name)`, and keeps at most 6. Stored in
   `assertion.participants` (migration 0017; a JSON array or NULL). Nothing is inferred from the value
   text, for any generation.
2. **Resolution (`resolve-v2`, amends ADR 0012).** A participant is a typed mention and resolves like a
   subject or object of its type. The resolver reads participant mentions in a second pass, after every
   subject, object and evidenced alias name. So an entity `resolve-v1` knows keeps its representative
   spelling, name order, aliases and grouping, and only `RESOLVER_VERSION` changes its id. Participants
   never create alias edges, so they never merge or split entities. Different types stay apart, and an
   ambiguous alias links nobody. A participant never named as a subject or object is an entity of its
   own (Inspector).
3. **Hints unchanged.** KNOWN ENTITIES candidates still come from subject and object mentions only
   (ADR 0012, item 5). With the second pass, the serialized block is byte-for-byte the one without
   participants, even when a participant spelling comes before the entity's first subject/object mention
   and before the `also_called` that joins its aliases.
4. **Recall (Q4).** A resolved participant's names join the fact's `names`, so it counts as a mention
   like the subject: 2.0 in the user's message, 1.0 in the previous reply. This holds for facts and
   character claims (the same selection). The persona is never added, since it is in every chat.
   Participation changes no knowledge mark (D19), no version key and no thread. The event cap and
   salience rules (ADR 0020) are unchanged.
5. **Older generations (Q5).** Rows without participants recall through subject and object only, as
   before, until they are re-extracted.

## Amendment (2026-09-25, ADR 0024)

Since `extract-v9` KNOWN ENTITIES (and the new UNNAMED CHARACTERS list) take typed participants as
mentions, after the subject and object of the same row: a character first shown without a name is often
only a participant, and a later turn can link its name only if it is listed. Participants still never
create alias edges or change an entity that subjects and objects define.

## Consequences

- An event reaches the packet when the person it happened to is addressed (`tests/test_participants.py`;
  memory evaluation "addressed participant"; `tests/test_participant_scope.py` keeps the no-participant
  rule).
- The `resolve-v2` bump changes every Inspector entity URL once, as any resolver change does.
- Cost:
  - participants are fetched as text, and each distinct stored list is parsed once and cached (the
    driver's jsonb decoding of every row cost ≈10 ms at 10,000 messages);
  - `entities.node()` is cached, and only rows with participants are processed;
  - the Inspector alone resolves participants for display.

  Fact read at 10,000 messages: +7 ms median (`docs/perf/phase8-extraction.md`).
- Entity mention counts in the Inspector include participant mentions.
