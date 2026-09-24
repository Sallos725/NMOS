# 0016 — One whereabouts per item

Status: accepted, 2026-09-24. Phase 6 step 1 (`docs/phases/PHASE-6.md`, owner answer Q2). Decision
D30. Known issue K10. Read-side only: no schema change and no new extractor generation.

## Context

ADR 0011 gave each item one current holder: the version key of `possesses` is the item. An item's
place (`located_in` with an item subject) was still its own version key. "Hana has the map", then
"Hana puts the map on the table" left both facts current: the map was on the table and in Hana's
hands at once. The reverse case did the same: the map is on the table, then Kaito takes it (K10).

## Decision

1. **One version key per item for holder and place.** `possesses` (keyed by its object) and
   `located_in` of an item (keyed by its subject) share the key `("whereabouts", item)`. The item is
   the resolved entity where the resolver links it (ADR 0012), otherwise its normalized name.
   `located_in` of characters and groups is unchanged. The rule is `predicates.whereabouts()`,
   outside the registry for the reason `HOLDER_PER_ITEM` is (ADR 0011 item 2): it changes only how
   stored assertions are read.
2. **Two slots, folded in order.** The fold keeps a holder slot and a place slot. Each slot follows
   the existing rules: a positive assertion becomes current, and a negation ends the slot's current
   version only if it denies the same holder or place (ADR 0013). A positive holder or place closes
   the other slot unless both come from the same turn. "Hana holds the map in the library" keeps both;
   a later "the map is on the table" keeps only the table. A negation says where the item is not, so
   it closes nothing in the other slot.
3. **Turns, not messages.** Two assertions share a turn when their `turn` is equal. Rows without a
   turn (per-message extractions of older generations) each count alone, as in `ACTIVE_ASSERTIONS`.
4. **History names the predicate.** A whereabouts fact's history mixes holders and places, so each
   entry carries `predicate`.

## Consequences

- Put down / picked up / moved: the newer statement decides (`tests/test_transitions.py`, memory
  evaluation cases "put down", "picked up", "holder and place in one turn", "a character's place is not
  an item's"; `docs/perf/eval-baseline.md`). The earlier code fails the first two with a stale fact.
- A held item's place is not derived from its holder's location: that would state something the story
  did not (PHASE-6 stop condition).
- The change applies to existing data at once, on the next read.
- Items that stop existing (K9 remainder) need `destroyed` (Phase 6 step 2).
