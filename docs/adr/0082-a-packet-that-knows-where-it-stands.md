# 0082 — A packet that knows where it stands: who is gone, who came back, what just ended (`packet-v20`)

Status: accepted, 2026-11-23, PHASE-60 (S2.1, S3, S4). Builds on ADR 0043 (`<Cast>`), ADR 0019 and 0039 (threads),
ADR 0068 (labels and rest). No migration.

## Context

`packet-v19` selects memory by what the message and the scene name. Three things nobody names are therefore missing:
that a character is dead or gone (so a reply brings them back), that a character has just returned after a long
absence, and that a promise was broken a turn ago (its thread closed, so it left the packet). The packet also never
says how far extraction has got, so a reply may trust memory over a newer message.

## Decision

1. **Every rule is a read of what is stored.** No model call, nothing written. All of it is under `packet-v20`;
   `packet-v19` and earlier compile as they did, fresh or replayed (D39).
2. **Gone is read from the current status, narrowly.** A character's current, narrated, positive, undisputed
   `has_status` matched against a closed word list, minus a recovered list, minus negations and near misses.
   `located_in` counts only for a whole place name on a short list of non-places. A word inside a longer place name
   never counts. A character present in the scene by rows of a later turn is not pinned: the story's later word wins
   over the list. The rule errs toward not pinning; a missed pin is today's behaviour, a wrong pin silences a living
   character.
3. **A gone line is the fact itself, marked.** `gone="true"` on the status line, first in `<Facts>` or inside the
   character's `<Cast>` group, `required`, at most 8 and 10 % of the budget. Privacy, strict and narrator rules apply
   to it as to any fact: a death kept secret is not announced to the scene.
4. **An absence is counted in turns that were read.** The return gap counts only turns an extraction serves; turns
   nobody extracted are unknown, never an absence (invariant 4). It is an attribute of the `<Character>` tag
   (`back_after`), shown for the first 5 turns of the return.
5. **A closed thread lingers briefly, as support.** Up to 3 threads closed within 15 turns, the broken before the
   kept, `supportive`, so they rest when no reply uses them (ADR 0068) and never crowd out open threads.
6. **The Note says how far memory has got** when a replied turn is newer than the last served one.
7. **New lines keep shapes the normalizer already drops.** Marks are attributes of `<Fact>`, `<Thread>` and
   `<Character>`; no new line tag carries story content. An echo of any of them is dropped by `clean-v3` (K27), so no
   new normalizer and no re-derivation.

## Consequences

- A status the story words unusually ("그는 이제 없다") is not recognised; the owner's pin (ADR 0087) or a status
  correction covers it.
- The word lists are read-side constants of `packet-v20`: a change to them is a new policy, so traces replay.
- Each rule is checked on a copy of production before a deployment: every pin and annotation is read (PHASE-60 C2).
