# 0035 — Per-chat memory mode: strict and first-person narrator

Status: accepted, 2026-09-27. Phase 10 (`docs/phases/PHASE-10.md`), step 5; owner answers Q2 and Q3. Migration
0021; no new extractor generation or packet policy. Amends ADR 0034 (claims) and D2 (the default reserve).

## Context

`packet-v3` (ADR 0034) gives the model what only some of the scene know, with a rule not to voice it. In the
Stage 4 pilot (`docs/perf/stage4-leak-pilot.md`) that kept secrets unsaid while their holders remembered them.
Withholding the content instead (the pilot's B′) stopped every leak and every recollection. Some chats want
that anyway, and a chat told in one character's first person should not be handed what the narrator cannot
know (the pilot's C). Neither can be read from the host: presets name their POV toggles differently (Q3).

## Decision

1. **Stored per chat** (migration 0021): `conversation.memory_strict` (off) and `conversation.memory_narrator`
   (none; at most 60 characters). `GET /v1/conversations/<id>/memory-mode` returns both and the chat's
   characters (non-persona character entities); `PUT` sets both. Owner input, not a source entry: it is
   read by every request of the chat from then on and recorded in each trace's recall options (`strict`,
   `narrator`), so a replay compiles with the mode the request had, whatever the chat's mode is now.
2. **Narrator.** A line stays when it is public or unmarked, or `limited` with the narrator among `known_by`
   (compared by entity; `{{user}}` is the persona under any name). Other lines are left out, and the Note adds
   "The story is told in the first person by X: only what they know is listed." What the narrator knows and
   someone else in the scene does not stays private (`packet-v3`).
3. **Strict.** A line private in this scene (ADR 0034) is replaced by
   `<Secret holders="…" not_known_by="…" turn="N">Something known to …, not known to ….</Secret>`: its
   holders and the characters in the scene not shown to know it, one line per such pair of sets. A Secret
   line is not itself private: its content is withheld, so it needs no Private rule (47 tokens saved), only
   its own Note text ("… its content is withheld. Holders may act as people keeping a secret; nobody states or
   hints at it."). The ledger keeps the withheld line's provenance and marks `not_known_by`.
4. **Both** apply in that order: the narrator's filter, then strict. An excerpt that says what either left
   out (half of a withheld line's content spans, `REPEATS`) is left out too: on the real host, strict mode
   replaced a secret with a Secret line and then placed the chat message that told it. The trace counts
   withheld lines and excerpts (`memory_mode_withheld`).
5. **Claims** (ADR 0013) are marked private like facts. A private claim in the Private section shows who
   knows it (`known_by`, `hidden_from`); elsewhere, and in earlier policies, a claim shows no marks as
   before. In the pilot's first scene on the owner's chat, strict mode still gave a secret word for word as a
   claim before this. The ledger marks a claim's `hidden_from` too, so an echo of it counts as a possible leak.
6. **Panel.** The Inspector's page for a chat, where its other actions are, has a "Memory mode" card: a strict
   checkbox and a narrator list (none, the user's character, the chat's characters).
7. **Default reserve 800** (was 600; owner, 2026-09-27). On the owner's recorded requests a 600-token packet
   placed 66% of the memory lines retrieval offered, 800 placed 89%, 1000 all of them
   (`docs/perf/memory-mode.md`). D2 still holds: the user lowers the host's max context by the reserve.

## Evidence

`docs/perf/memory-mode.md`.

## Consequences

- Strict mode costs recollection: on the pilot's first scene it withheld 13 of 15 lines. It is for chats that
  prefer a forgetful holder to a leak.
- The narrator filter trusts `known_by`. A fact the narrator saw but extraction did not list them for is left
  out; an unmarked fact is kept.
- `packet-v3` changes for private claims. Its traces recorded before this change (on `:edge` only, never
  released) may not reproduce on replay.
- The mode lives in NMOS, not in the host: exporting the chat does not carry it (Stage 6 export).
