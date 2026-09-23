# 0011 — One current holder per item

Status: accepted, 2026-09-23 (owner: continue Track A). Track A, A4. Changes how `possesses` facts are
read; no schema change, no new extractor generation.

## Context

`possesses` is multi-valued per subject (D6 registry): `Yujin possesses map` and later `Hana possesses
map` are different facts, so both stayed current after the map changed hands. The per-turn extraction
comparison found exactly this (`docs/perf/turn-extraction.md`: `유진 possesses 해안 지도` stayed current
after the map was returned), independently of the extraction unit.

Track A offered three options: an item-centric predicate, an explicit termination assertion, or
deferral to Track B. The recommended one was a new item-centric predicate (`held_by`). Two facts
changed that recommendation:

- The extractor generation fingerprints `repr(REGISTRY)` (D20). A new predicate, or a changed
  cardinality on `possesses`, is a new generation: every user's covered history is queued for
  re-extraction, which costs LLM calls (≈3.1k tokens per turn with the model in
  `turn-extraction.md`).
- Stored `possesses` assertions already carry what an item-centric reading needs: the item (object),
  the holder (subject) and the position.

## Decision

1. **Read `possesses` per item.** The version key of a `possesses` assertion is the item
   (`(predicate, normalized object)`), not the holder. The current fact is the item's latest assertion;
   earlier holders are its history. A holder with several items still has one fact per item.
2. **Outside the registry.** The rule lives in `predicates.HOLDER_PER_ITEM`, not in `Predicate` fields,
   because it changes only how stored assertions are read. Extraction output, the prompt and the
   generation key are unchanged; the fact projection is computed at read time, so the change applies
   to existing data at once and needs no rebuild.
3. **History shows holders.** Fact history entries now include `subject`.
4. **Explicit termination is not added.** An item that is lost or destroyed without a new holder still
   shows its last holder. That needs transition semantics (Track B, B2).

## Consequences

- A → B → C shows C as the current holder and A, B in the history
  (`tests/test_extraction.py::test_an_item_has_one_current_holder_and_keeps_its_history`).
- Item names are free text: "해안 지도" and "지도" are different items, so a transfer the
  extractor names differently still leaves two holders. Stable entity identity is Track B, B1.
- Two different items with the same name in one chat collapse into one; the same limitation applies
  to every text-keyed fact today.
- `located_in` for items remains a separate fact; an item can show a holder and a place from
  different turns.
