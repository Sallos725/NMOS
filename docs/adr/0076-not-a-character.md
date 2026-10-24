# 0076 — Not a character: the owner leaves a name out of the cast or out of memory

Status: accepted, 2026-10-24, PHASE-47 (owner's Q1–Q3 of 2026-10-14; implementation approved by R8 on 2026-10-23).

## Context

Extraction files whatever the text uses like a person as a `character` (ADR 0012): a monster the party fights, or the
name of a simulation-style bot card that narrates the game. Both then sit in the people list and in relationship
pairs. They are different cases: facts about the monster are the story (who killed it, what it dropped), while what
the bot "says" is not. The repairs of ADR 0044 work on one fact or thread at a time, and entities are derived from
facts, so the owner had no way to say "this is not a character" short of retracting every fact that names it.

## Decision

A new owner repair, `entity_exclude` (migration `0031`), with two scopes:
- **`cast`** (the default, "캐릭터 아님"): the entity leaves the people, every relationship pair (the Inspector, the
  panel's memory and person screens, the author's note's address lines) and the packet's `<Cast>` groups, and is not
  offered as a narrator. Every fact stays: the memory view, the packet's fact lines and recall read it as before.
- **`memory`** (a second, explicit choice, "기억에서도 제외"): also its own facts (subject) and the standing it is one
  end of (`relationship`, `role_toward`, `feels_toward`, `addresses`) leave the memory view, before the secret and
  thread folds. A row that names it only as a participant, or as another subject's object, stays.

It is owner input like every repair: it stores the name the owner saw (the panel names the entity by its id; the
sidecar stores its name), every read resolves that name, so a name the story joins to it follows and a split name does
not; a rebuild or a new extractor generation keeps it; a replay reads only the exclusions in force at its time
(ADR 0027); undo sets `removed_at`. Nothing is deleted. The persona, the chat's own character (the host's), a name the
chat never mentions and an entity already left out are refused (422).

A preview (as for a split, ADR 0055) counts both scopes, the relationship pairs and the facts that would leave; the
action carries the fingerprint of the scope it was previewed for. Undo is previewed the same way.

## Why read time, and why two scopes

Raw text and derived rows are never edited (invariants 1 and 2). A read-time exclusion keeps every row, follows the
resolution's joins and splits, and replays. One all-or-nothing exclusion would either keep the bot's noise or erase the
monster's history, so `cast` keeps every fact and is the default.

## Consequences

- `scene.cast` (who is in the scene, which decides what a scene may know) is unchanged; only the `<Cast>` groups skip
  an excluded entity. `quotes.character_names`, `variants.aliases` and the extractor's hints are unchanged, so recall
  matches and attributes as before.
- The cost of a read is unchanged within measurement: resolving 100 exclusions and filtering a 1,021-row view takes
  0.19 ms either way (PHASE-47 evidence).
- Telling the extractor not to extract such a name is a new generation and out of scope.
