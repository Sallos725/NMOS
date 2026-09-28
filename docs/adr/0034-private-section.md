# 0034 — packet-v3: what only some of the scene know goes in a Private section

Status: accepted, 2026-09-27. Phase 10 (`docs/phases/PHASE-10.md`), step 4. New default packet policy
`packet-v3`; no migration, no new extractor generation. Follows ADR 0033 (secrets) and ADR 0027 (policies).

## Context

In the Stage 4 pilot (`docs/perf/stage4-leak-pilot.md`) the same facts, laid out so that lines only some
characters know sat apart with a rule for them (the pilot's A), kept a secret unsaid in front of the character
it was kept from, while its holder still remembered it, once the fact said whom it was kept from (A′: 3 of 3
with Opus 5.5). Withholding the content instead (B′) stopped leaks by making the holder forget. ADR 0033 made
the marks say whom a fact is kept from.

## Decision

1. **Scene cast** (`scene.cast`), from what the request already read: the characters the two turns before the
   current one are about (subjects, objects, typed participants), every character named in the user's message
   or the previous reply (a known entity, or a name in knowledge marks: someone a secret is kept from may be
   named only there), and the persona. Characters compare by entity; every name the persona goes by, and a full
   name ending with one ("아오키 타쿠미"), is the persona.
2. **Private.** A `limited` fact or open promise is private in this scene when someone in the cast is not among
   the characters shown to know it (`known_by`). Public, unknown and unmarked facts never are; with nobody in the
   cast, nothing is. Claims are unchanged.
3. **`packet-v3`** is `packet-v2` with private lines emitted in a `<Private>` section after `<Facts>`, as the
   same `<Fact>` / `<Thread>` lines with their marks, and a rule added to the Note once: "Private: only its
   holders (known_by) know it. Others must not mention, hint at or act on it; holders keep it from those in
   hidden_from unless the story reveals it." It is the pilot's rule, shortened from 88 to 47 estimated tokens:
   the first private line paid for the rule and took a quarter of a 600-token packet. Budget order and ranking
   are `packet-v2`'s; a private line costs the Private header instead of its section's. The ledger marks it
   `private`, and the trace records the cast (`scene_cast`). Earlier policies ignore the mark, so recorded
   traces replay as before.
4. **Ranking.** A mentioned fact hidden from someone in the cast gains 0.8 (`PRIOR_HIDDEN_PRESENT`): above how
   the cast stand (0.5), below a mention in the user's message rather than the previous reply (1.0) and the
   hidden character being addressed (2.5). The scene is where a secret can leak and where its holder needs it.
5. **Default.** `packet-v3`, in the code and both compose files (which set `NMOS_PACKET_POLICY` explicitly).
   `packet-v2` stays available.

Not here: strict mode and first-person narrators (Phase 10 step 5); the response-model tier (step 7).

## Evidence

`docs/perf/packet-v3.md`.

## Consequences

- A 600-token Korean packet holds less once a Private section opens (the rule costs 47 estimated tokens). On the
  owner's chat a secret the scene needed was cut by the budget in one of three pilot scenes.
- A fact whose `known_by` names only who was present when it happened is private when someone else joins the
  scene. That is the intent (they did not see it), and it also moves ordinary knowledge into Private.
- A secret whose reveal the extraction missed (ADR 0033) stays private and marked hidden.
