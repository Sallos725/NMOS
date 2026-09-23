# 0013 — Assertion semantics: polarity, modality, source class

Status: proposed, 2026-09-23 (Phase 5, B0). Accepted when `docs/phases/PHASE-5.md` is approved.
Owner decisions behind it: Track B §4 "Owner decisions" (Phase 5 = B1; canon sources in B4) and the
Phase 5 design question of 2026-09-23 (a negation ends the matching current fact).

## Context

An assertion today has `subject`, `predicate`, `object`/`value`, `epistemic` (`stated` / `implied`),
knowledge scope (ADR 0007) and provenance. Everything the extractor returns and validation accepts is
treated as something that happened. Three things are therefore lost or wrong:

- **Negation.** "하나는 지도를 잃어버렸다" or "Alice did not enter" can only be skipped or mis-stored
  as a positive fact. Known issue K9 (a lost item keeps its last holder) is partly this.
- **Non-actual content.** A plan, a condition, a dream or a hypothetical ("If Alice killed Bob…") is
  either dropped by the prompt's "skip speculation" rule or, when the model does not skip it, stored as
  actual.
- **Who says so.** A character's statement in dialogue ("I'm a knight") is stored like narration. A lie
  or a boast overwrites narrated state if it comes later.

The Track B proposal listed a coarse modality set (actual, claimed, hypothetical/intended, dreamed,
unknown) and two or three source classes (narration, character claim, and authored canon if admitted).
The owner put authored canon in B4.

## Decision

1. **Three new assertion fields**, asked for in the extraction prompt and normalized by validation
   (`extract-v5`):
   - `polarity`: `positive` | `negative`. Negative means the story states the relation does not
     hold, or no longer holds ("lost", "gave away", "left", "is not").
   - `modality`: `actual` | `hypothetical` | `dreamed` | `unknown`. `hypothetical` covers conditions,
     intentions and plans that have not happened, and speculation; `dreamed` covers dreams, visions and
     imagination; `unknown` is for when the text does not settle it. Missing or invalid → `unknown`.
   - `source`: `narration` | `character_claim`, plus `asserted_by` (a name) for a claim. Narration is
     the story's own voice, including the user's description of their character's actions (the reply
     still decides what happened, ADR 0008). A character claim is something a character says or
     writes in the story. A missing or invalid `source` becomes `character_claim` when `asserted_by`
     names a speaker and `narration` otherwise; `character_claim` without `asserted_by` becomes
     `pending`.
2. **"Claimed" is a source, not a modality.** The proposal's `claimed` modality and a
   `character_claim` source would encode the same thing twice. A claim is `modality=actual`
   (what the speaker presents as true) with `source=character_claim`. Only narration establishes state.
3. **What forms facts.** Current and historical fact versions (`fact_versions`) are built from
   `modality=actual`, `source=narration` assertions, positive and negative. Everything else is stored,
   counted and shown in the Inspector, and handled as follows in Phase 5:
   - character claims: returned as claims on the fact they concern (Inspector) and rendered in the
     packet as `<Claim by="…">` lines ranked after facts, only when relevant to the query. A claim never
     supersedes a narrated version and never becomes the current fact, even when it is newer;
   - `hypothetical`, `dreamed`, `unknown`: stored and inspectable, never in the packet (Phase 5).
4. **Negation ends the matching current fact** (read-side, like ADR 0011; no verifier). For a version
   key, a negative assertion closes the current positive version **only if it denies the same
   relation**:
   - single-valued predicates (`located_in`, `has_status`, `identity`, per-object `relationship` /
     `feels_toward`): the same object or value. "하나 is not in the station" ends "하나 located in
     station" and leaves "하나 located in home" untouched;
   - holder per item (`possesses`, ADR 0011): the same holder. "하나 lost 지도" ends 하나's holding of
     지도, and the item has no current holder; "카이토 does not have 지도" changes nothing when 하나 holds it;
   - multi-valued predicates: the same subject, object and value.
   A closed version stays in the history with the negative assertion as its end. A negative assertion
   that matches no current version is kept as a negative fact (e.g. "Alice did not enter" is a fact,
   not the absence of one) and rendered with `negated="true"`.
5. **Packet.** `<Fact>` gains `negated="true"` for current negative facts. The packet Note says that a
   negated fact is explicitly not (or no longer) true, and that a `<Claim>` is what a character said,
   not established truth. Legacy facts (step 6) render as today.
6. **Legacy assertions.** Rows from `extract-v4` and older have no new fields (migration defaults:
   `polarity=positive`, `modality=actual`, `source` NULL). They are read as narration, which is how
   they are read today, and the Inspector marks them as legacy. They never become claims.
7. **Prompt rule change.** "Skip speculation" becomes "label it": speculation, plans and dreams are
   extracted with their modality when they are durable story content, so they can later feed threads
   (Track B, B3). Small talk still yields an empty list.

## Consequences

- K9 is fixed for explicit loss and giving-up statements the extractor labels as negative. Implicit
  ends (an item destroyed, eaten, used up, without a statement that the holder no longer has it) still
  need transition rules (Track B, B2, next after Phase 5).
- A lie told in dialogue no longer overwrites narrated state. If the story never narrates the truth,
  the only thing known is the claim, and it is shown as a claim.
- Facts can now disappear from the packet because the extractor labels them non-actual. A model that
  overuses `unknown` or `hypothetical` removes real facts. Phase 5 acceptance therefore includes a
  real-model run that counts how often actual events are mislabeled, and the finer modality set
  (observed, believed, suspected, promised, …) is added only when recorded fixtures show the coarse set
  producing a wrong current state (Track B, B1).
- `epistemic` (`stated` / `implied`) stays as the certainty of an actual assertion and keeps its packet
  attribute.
- `source` has room for `authored_canon` and `user_lock` later (B4, B7); adding one is a new extractor
  or resolver generation, as any change to extraction output is (D20).
- Schema: new columns on `assertion` in one new migration; no rewrite of existing rows beyond
  defaults.
