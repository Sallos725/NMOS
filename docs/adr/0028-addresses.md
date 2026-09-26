# 0028 — How characters speak to and call each other is its own fact

Status: accepted, 2026-09-26. The owner decided the proposal `docs/proposals/SPEECH-AND-ADDRESS.md` with
the recommended answer to every question (Q1 a, Q2 a, Q3 a, Q4 a). Owner report, not a phase feature.
Follows ADR 0026. New extractor generation `extract-v10`; no migration. Amends D6 (registry) and D37
(`STANDING`).

## Context

A character who agreed to speak 반말 went back to 존댓말 (ADR 0026). ADR 0026 fixed the ranking. The
storage side still had gaps:

- `extract-v9` records the change as a `major` event. An event is a thing that happened: it does not say
  that the agreement still holds, it competes with every other event of the cast (at most 3 per packet),
  and a later change cannot replace it.
- Sometimes the change lands in `relationship` ("반말하는 사이"). There it shares one value per pair with
  "누나", "연인" and so on, so the next relationship replaces it. In the owner's chat that row was gone
  after the turn was re-extracted.

## Decision

1. **Predicate `addresses`** (subject character, object character, value text; `single` per (subject,
   object); world): how the subject now speaks to and calls the object, as the story settles it. The value
   holds the speech level and the form of address in the chat's language, e.g. "반말, '유우마'라고 부름".
   One row per direction (Q2): speech level is often asymmetric.
2. **Only what the story settles.** The prompt asks for `addresses` when the target turn settles it: an
   agreement or decision to speak informally or formally, a form of address asked for or allowed, a new
   form of address used for the first time and taken up. It is narration although the evidence is dialogue.
   A reply that merely uses a speech level, with nobody deciding, asking or remarking on it, is not a change
   ("a slip is not a change"). Otherwise a slip by the response model would be stored and then injected,
   and would reinforce itself. A change back is a new `addresses`; the turning point is also recorded as an
   event.
3. **Read side.** `addresses` joins `STANDING` (ADR 0026): among equal mentions it ranks with relationships,
   and it takes the packet budget before threads. Like every single-valued predicate, a newer value replaces
   the older one per direction, and the older one stays as history in the Inspector. The packet line is
   `<Fact kind="addresses" …>라디아 addresses {{user}}: 반말, '유우마'라고 부름</Fact>`.
4. **Generation.** `extract-v10`: the registry and prompt fingerprints change (D20). Activation re-extracts
   each chat's recent window (`NMOS_EXTRACT_BACKFILL`); older turns keep `extract-v9` facts until "Extract
   all history" (ADR 0014).
5. **Budget unchanged (Q4).** The default memory budget stays 600 tokens. The budget reserves host context
   (D2), so a larger default would shrink every user's history. The docs say when to raise it.

## Evidence

`docs/perf/extract-v10.md`. On the owner's model (`gemma4:31b-cloud`) and on `deepseek-v4.1-flash:cloud`,
7 new synthetic scenes passed 21/21 each: agreements in both directions, a form of address taken up, a
change back, and three controls (a slip, speech settled earlier, routine). On the owner's chat (read-only),
the six turns where speech or address was settled gave `addresses` in 18 of 18 runs. The turn where 라디아
slipped into 존댓말 gave none in 3 of 3, and routine turns gave none in 12 of 12. In an isolated real host
the packet opened its facts with both directions of `addresses`, ahead of eight `knows` facts.

## Consequences

- The owner's upgrade re-extracts the recent window of each chat once, at the provider's cost.
- Whether a turn is major can shift. On the owner's chat the six turns kept the same total of runs with a
  major event (12 of 18 with each prompt), but two turns lost it and one gained it. The speech-level
  information itself moved into `addresses`, which ranks above events.
- The value is free text: how the speech level is phrased varies ("반말" or "해요체", with or without the
  form of address). The response model reads it; nothing parses it.
- A slip that the story later accepts (the characters keep speaking the new way without remarking on it) is
  not recorded until a turn settles it.
