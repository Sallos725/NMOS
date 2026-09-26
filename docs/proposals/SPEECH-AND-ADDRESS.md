# Proposal — Speech level and forms of address as their own fact

> Status: decided 2026-09-26: the owner chose the recommended answer to every question (Q1 a, Q2 a, Q3 a,
> Q4 a). Implemented as ADR 0028, `extract-v10`; evidence `docs/perf/extract-v10.md`.

## Problem

Owner report (2026-09-26): a character who agreed to speak 반말 went back to 존댓말. ADR 0026 reproduced
it on the owner's chat and fixed the ranking. The storage side still has these gaps:

- **No slot.** `extract-v9` records the change as a `major` event ("라디아 event: 유우마에게 말을 놓기
  시작함", "{{user}} event: 라디아를 '누나'라고 부르기 시작함"). An event is something that happened;
  nothing marks it as the rule that holds from then on. Events compete with every other event of the cast
  (at most 3 per packet), and in a crowded scene the budget cuts them (ADR 0026: it fit at 1,200 tokens,
  not at 600).
- **Wrong slot.** Sometimes the change lands in `relationship` ("라디아 relationship {{user}}: 반말하는
  사이"). There it shares one value per pair with "누나", "연인" and so on, so a later relationship replaces
  it. In the owner's chat, that relationship row was extracted once and was gone after the turn was
  re-extracted.
- **No history.** A move back to 존댓말, or a new form of address, cannot supersede an event, so both stay
  current side by side.

## Proposal

1. **Predicate `addresses`** (subject: character, object: character, value: text; `single` per
   (subject, object), world). Value: how the subject speaks to or calls the object, in the chat's
   language, for example "반말, '유우마'라고 부름" or "존댓말(해요체), '유우마 씨'라고 부름". Extract it only
   when the target turn shows or settles it: an agreement, a first use, or a change back. Do not extract
   it for every line of dialogue.
2. **Read side.** `addresses` joins `STANDING` (ADR 0026): among equal mentions it is ranked with
   relationships, and it takes the budget before threads. A newer value replaces the older one per
   direction, so a change back is current and the earlier value is history (Inspector).
3. **The event stays.** The change is still an event with salience by what it changes (D35), so its
   story value is kept. `addresses` records the rule that follows from it.
4. **Generation.** `extract-v10`. As with every new generation, the recent window
   (`NMOS_EXTRACT_BACKFILL`) is re-extracted at the provider's cost, and older turns keep `extract-v9`
   facts until "Extract all history" is run (ADR 0014).

## Questions for the owner (recommended answer first)

- **Q1 — Add `addresses`?** (a) Yes, as above. (b) No: keep the ADR 0026 ranking and raise the budget.
  (c) Put it into `relationship` with a stricter prompt; this keeps the one-value-per-pair conflict.
- **Q2 — Both directions?** (a) One row per direction (라디아 → 유우마 and 유우마 → 라디아 are separate facts),
  because speech level is often asymmetric. (b) One symmetric row.
- **Q3 — Evidence before release.** (a) A real-model tier like `docs/perf/extract-v9.md`: the owner's
  model on turns 12–15, 39, 42 and 46 of the owner's chat (read-only copies), plus a synthetic change
  back to 존댓말. (b) Synthetic cases only.
- **Q4 — Default budget.** (a) Leave 600 and document raising it; the budget reserves host context (D2),
  and a larger default shrinks everyone's history. (b) Raise the default to 1,000.

## Out of scope

Deriving speech level from the text of replies (for example, counting sentence endings) is out of scope:
facts come from the extraction model with evidence (D6), never from string heuristics.
