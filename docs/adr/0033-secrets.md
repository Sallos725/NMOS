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
   content because a shared head alone ("루카 goal:") made two different secrets look alike. No match ends
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

## Amendment 1 (2026-09-27, Phase 10 step 7): who found out knows it

Item 6 kept the fact's `known_by` as extracted. With the Private section (ADR 0034) and the memory mode (ADR
0035) reading `known_by`, a character who had found out a secret still counted as not knowing it: the fact
went to Private with its rule telling them not to act on it, strict mode withheld it from them, and as a
narrator they were not given it. The synthetic case "a reveal ends it" (`tests/memeval.py`) placed it in
Private. Now the read side also adds the character to `known_by` from the revealing turn on; deleting that
turn takes them out again. Packets recorded before this that placed a revealed fact may not reproduce on
replay (on `:edge` only, never released).

## Amendment 2 (2026-09-27, audit G1–G2): an edited turn and a missed reveal

The 2026-09-27 audit (`docs/proposals/ORIGINAL-VISION-TO-STABLE-2026-09-27.md`) found two faults in item 5
and K29.

- **G1: rule 1 outlived an edit.** Linking by turn is meant for the same turn extracted again in other words.
  It also held after the owner edited that turn into a different secret: Noel, who had found out Luca's plan
  to watch a lecture, counted as knowing the new plan to steal a diamond. The worker now stores, with the
  OPEN SECRETS it lists (`extraction.hints`, not shown to the model), the hash of each listed turn
  (`listed_hash` on the reveal as read). Rule 1 considers only secrets whose turn hash on the head (their
  served extraction's) equals it; any other secret of that turn can end only by rule 2 (content), and a reveal
  matching nothing is reported unmatched while the secret stays kept. A reveal extracted before this has no
  hash and keeps rule 1. The fact read carries the two hashes only on reveals and marked facts; at 10,000
  messages it stays at ≈57 ms p50 (a first version that compared them in SQL doubled it).
- **G2: "Extract all history" could not recover K29.** It queued only turns not yet extracted, and the turn
  that missed the reveal had been. It now also extracts again each turn whose extraction was written before
  any extraction holding an earlier turn's current secret existed (so its OPEN SECRETS could not list it):
  that extraction is discarded (kept for audit) and the turn is queued, oldest first. A turn that saw an
  earlier wording of the secret, in any generation, is left alone. In play, where turns are extracted one at
  a time, nothing qualifies.

Consequences: an edit of a secret's turn that keeps its content ends the secret only when the new wording
reaches the content match; a far rewording is reported as unrevealed until the revealing turn is extracted
again (Rebuild). While a re-extraction is queued, that turn's facts come from an older generation or are
missing. Two workers can still extract neighbouring turns at once; another "Extract all history" then fixes it.

## Amendment 3 (2026-10-01, Phase 22, ADR 0057): a reveal check instead of a re-extraction

G2's fix extracted such a turn again, and the new model call dropped facts the turn had (AGE-25: on the owner's M0
main chat 34 narrated facts left the chat's memory after one press). "Extract all history" now keeps the turn's
extraction and asks a reveal check: the same OPEN SECRETS, CONTEXT and TARGET, answered with `secrets` only, its
`learned` rows served with the turn while the extraction it checked serves it (ADR 0057). Which turns qualify is
unchanged, except that a check counts as having looked. Rebuild is unchanged.
