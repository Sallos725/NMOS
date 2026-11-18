# 0081 — How a feeling feels: strength, sign and a feeling under it (`extract-v18`)

Status: accepted, 2026-11-18, PHASE-58 (owner's Q1–Q4 of 2026-11-18). Amends ADR 0038 item 3 (a feeling per
direction) with its detail and PHASE-57 Q5 (ADR 0078: a release's version change re-extracts the latest turns) for one
pair of compilers. Migration `0035`.

## Context

`feels_toward` holds one feeling per direction of a pair, as a short phrase. The owner wants to follow how strongly a
character feels, and negative feelings with the positive, without a number (PHASE-58 Why). A score estimated by the
model was declined (`IDEA-SURVEY-2026-09-29.md` §5): it has no quote, and it hides "unknown".

## Decision

1. **The extraction weighs the feeling it writes.** `extract-v18` is `extract-v16` with a `feeling` object on
   `feels_toward`: `intensity` (`faint`, `clear`, `strong`), `valence` (`positive`, `negative` or null) and `under` (a
   second feeling the turn shows beneath the first, with its own intensity and valence, or null). The model reads them
   from the TARGET turn it quotes; nothing is inferred or summed afterwards.
2. **One slot, replaced whole.** The direction keeps one current feeling (ADR 0038 item 3). A change of strength, or a
   feeling under it appearing or fading, is a new `feels_toward` with the whole feeling, which supersedes the older
   version (ADR 0013). A second slot (`multi`) would need its own ending, which the extractor finds unreliably (the role
   endings of PHASE-28).
3. **Stored on the assertion.** `assertion.feeling jsonb`, written by the extraction that wrote the row, so the
   generation that produced it is the row's (D20). Null for every other predicate, every other compiler and a feeling
   the model did not weigh. `normalize` drops an invalid intensity's whole detail, an invalid valence to null and an
   incomplete `under`.
4. **Switching between `extract-v16` and `extract-v18` re-extracts nothing.** `generations.classify` names a change
   whose specs differ only in the compiler and its prompt, between two compilers of `ADDS`, `adds`; activation queues
   for it what a carry-on queues (ADR 0078): turns no generation serves. Older turns keep the facts they have (ADR
   0014), without detail. Every other version change keeps ADR 0078's Q5 policy.
5. **For the owner's eyes only.** The panel and the Inspector show the strength in words, the feeling under it and a
   dot in the sign's colour (mixed when the two have opposite signs; text names the sign too). The packet, the
   author's note, the memory map and recall do not read `feeling`.

## Consequences

- A feeling that the story weakens is visible as a new, fainter version, not as an ending.
- History before the switch has no detail until the owner runs "extract all history" for a chat.
- `extract-v18` is selectable (`NMOS_EXTRACT_COMPILER`); `extract-v16` stays the code default until the owner decides
  at the `1.0.0` tag.
- `extract-v17` (speakers, horizons) is not in `extract-v18`; a later generation that wants both combines them.
