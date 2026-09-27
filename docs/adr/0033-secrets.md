# 0033 — Secrets: kept from, not absent; a reveal ends one

Status: accepted, 2026-09-27. Phase 10 (`docs/phases/PHASE-10.md`), steps 2 and 3; owner answers Q1 a, Q4 a.
New extractor generation `extract-v12`; no migration. Revises ADR 0007 (knowledge scope) and D19; amends D6
(registry).

## Context

The Stage 4 pilot (`docs/perf/stage4-leak-pilot.md`) found that the packet keeps a secret unsaid, and its holder
still remembers it, once the fact says whom it is kept from; the knowledge marks rarely said so. In the owner's
chat `limited` mostly recorded who was present, `hidden_from` was missing on real secrets and set on trivia
(someone who was only absent), and a secret the story revealed at turn 21 was still marked hidden from that
character at turn 59.

ADR 0007 asked for `hidden_from` on "something done while others were away", which reads as absence.

## Decision

1. **Kept from, not absent.** `known_by` lists who is shown to know a fact: they did it, saw or heard it, or were
   told. `hidden_from` lists only characters it is deliberately kept from: a secret, a lie told to them, a
   surprise or a plan they must not learn, a hidden identity, something done behind their back. Someone who was
   simply not there is left out (unknown, as ADR 0007 says for everyone not listed). A feeling or thought nobody
   else is shown knowing is `limited` with its holder alone in `known_by`.
2. **A secret** is a valid assertion with `knowledge = limited` and a non-empty `hidden_from`, not dreamed. It is
   read, not stored (`secrets.fold`), like a promise thread (ADR 0019).
3. **OPEN SECRETS.** The extraction prompt lists the open secrets before the target turn whose holders or those
   they are kept from the prompt names, newest first, at most 8, numbered: `S1. <subject> <predicate>: <content>
   (known by: …; kept from: …; turn N)`. They are recorded with the extraction (`hints.secrets`).
4. **A numbered check, not a predicate the model writes.** The answer gains `secrets`: `{"secret": "S1",
   "found_out_by": [...], "evidence": "..."}` for each listed secret a character it is kept from finds out in the
   target turn (told, overhearing, seeing it happen, catching the holders at it, plainly working it out); a hint,
   a related remark, a suspicion or a guess is not. A reminder at the end of the prompt asks for the check. The
   worker turns each entry into `learned` (subject: that character; value: `[turn N] <the listed line>`), only
   for names the secret was kept from, a listed number, and evidence found in the target turn (trigram
   containment ≥ 0.7). `learned` stays in the registry for stored rows but is not offered to the model
   (`DERIVED`). A first version asked the model for `learned` with the listed text copied out: on the owner's
   chat it wrote `knows` instead (0 of 3 on the reveal turn), and with a reminder it named one of several copies
   or over-fired on related turns (`docs/perf/extract-v12.md`).
5. **A reveal ends the secret for that character only, from its turn on** (Q1 a). It ends the open secret of
   the listed turn with the same head (subject and predicate, trigram overlap ≥ 0.8) whose content is closest,
   however that turn is worded now; and every other open secret kept from the character whose head matches and
   whose content is equal or reaches the thread match (overlap ≥ 0.6, ADR 0019). Linking by turn keeps a reveal
   when the listed turn is extracted again in other words: a generation switch extracts the newest turns first,
   so the list a turn saw may come from the previous generation's facts. A head is compared apart from the
   content because a shared head alone ("엘피 goal:") made two different secrets look alike. No match ends
   nothing and is reported (`unrevealed`).
6. **Read side.** `memory_view` drops the revealed character from the fact's `hidden_from`, adds `revealed`
   (to whom, by which turn) and returns the secrets. `learned` is never a fact, claim or other assertion itself.
   Because nothing is stored, editing or deleting the revealing turn restores the secret on the next read
   (invariant 7), and as-of reads (ADR 0027) see the secret as it was at the request.
7. **Generation.** `extract-v12`: the prompt and registry fingerprints change (D20). Activation re-extracts each
   chat's recent window (`NMOS_EXTRACT_BACKFILL`); older turns keep their marks until "Extract all history".

Not decided here: how the packet shows private facts, strict mode and first person (Phase 10, later steps).

## Evidence

`docs/perf/extract-v12.md`.

## Consequences

- A secret revealed before `extract-v12` stays marked until its turns are extracted again with it: the reveal
  needs the OPEN SECRETS list.
- A reveal ends a secret only when it names it closely enough. A reveal worded far from the listed text ends
  nothing and is shown as unrevealed in the facts view; the owner cannot yet end one by hand (Stage 6).
- A character who learns part of a secret ends all of it for them.
