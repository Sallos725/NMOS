# 0017 — An item's end: `destroyed` and `extract-v6`

Status: accepted, 2026-09-24. Phase 6 step 2 (`docs/phases/PHASE-6.md`, owner answer Q3). D30
amended. Known issue K9.

## Context

A new holder ends an item's previous holder (ADR 0011), and so does a statement that the holder lost
it (ADR 0013). An item that is burned, eaten or used up with neither kept its last holder: the story
said the letter was ash, and memory still said Hana had it (K9). No registry predicate can say that an
item is gone. `has_status` is for characters, and a status would not say that nothing holds the item
any more.

## Decision

1. **Registry predicate `destroyed`.** Subject type `item`, no object, value required (how, in the
   chat's language), single-valued, world. Registry description: "the item no longer exists or can no
   longer be held or used". Prompt rule: only when the TARGET turn ends an item's existence or use
   (burned, torn to pieces, eaten, drunk, used up, shattered beyond use). Not when it is only damaged,
   hidden, dropped or lost. A loss stays `possesses` with `negative`.
2. **Part of the whereabouts (ADR 0016).** `destroyed` is a third slot in the item's whereabouts. A
   positive `destroyed` closes the holder and the place, including those of its own turn, in either
   extraction order ("Hana burns the letter she holds"). It is a current fact itself
   (`letter destroyed: burned`). A negative one ("the letter did not burn") is a negative fact and ends
   nothing else.
3. **New extractor generation `extract-v6`.** The registry change alone would change the generation
   key (D20). `COMPILER_VERSION` names it. Activation re-extracts the recent window only; older turns
   stay on `extract-v5` until "extract all history" (ADR 0014). Older generations never produce
   `destroyed`, so an item they left with a holder keeps it until a v6 turn ends it.
4. **Until step 3:** a later turn that holds or places the item again is the newer statement and
   closes the end. Phase 6 step 3 makes this a conflict (owner answer Q4).

## Consequences

- Burned, eaten and used-up items lose their holder and place once the turn is extracted by v6. The
  memory evaluation cases "destroyed", "eaten", "damaged, not destroyed" and "edit removes the end"
  cover this (`docs/perf/eval-baseline.md`), with fold cases in `tests/test_transitions.py`.
- Upgrading costs one re-extraction of each chat's recent window, as for any generation change. The
  prompt grows by one registry line and one rule. Tokens per turn are measured in the real-model tier
  (Phase 6 step 5).
- Whether real models apply the rule (and leave damaged items alone) is measured in the real-model
  tier, not here.
