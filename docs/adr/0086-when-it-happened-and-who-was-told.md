# 0086 — When it happened, and who was told (`extract-v19`)

Status: accepted, 2026-11-23, PHASE-60 (S7, S8). Builds on ADR 0081 (`extract-v18`, `adds`), ADR 0006 (generation
keys), ADR 0071 and 0074 (status windows and their clock). Amends D6 (the registry) for one compiler. Migration `0037`.

## Context

An assertion has one time: the turn that told it. A flashback, or yesterday's event mentioned today, is therefore
dated at its telling. And NMOS records what a character knows (`knows`, knowledge marks, reveals) but not that one
character passed something on to another. Both need the extraction to say more, which is a new generation — and
production must not pay to re-extract history for it (ADR 0081 item 4).

## Decision

1. **`extract-v19` is `extract-v18` plus two rules and one predicate.** `feeling`, roles and name pairs are kept.
2. **`when_happened` is a phrase, not a timestamp.** On `event` and `promised`, only when the turn places it at
   another time than the turn. The story's own wording, resolved against the story clock when the prompt shows one.
   NMOS computes no date and orders nothing by it: it is shown beside the turn of telling.
3. **The clock is a recorded input.** The literal clock of a tracked status window as of the target turn is a prompt
   line and is stored on the extraction row (`story_clock`). Like the hints (ADR 0012) it comes from beyond the
   window, is recorded, and is not part of validity.
4. **`told` is its own predicate and changes no knowledge.** Character → character, what was passed on. It is
   evidence of a telling with its quote; knowledge marks and reveals stay what the extraction and the reveal check
   say (ADR 0033). Deriving "the hearer now knows" would be inference without a quote.
5. **The new predicate stays out of `REGISTRY`.** Every extractor key hashes `repr(REGISTRY)`: adding a row would
   change the keys of `extract-v15…v18` and re-extract every install. `told` lives in a per-compiler extension;
   readers and validators see `REGISTRY` plus the extensions, the fingerprint sees `REGISTRY` alone, and the
   extension's definition is hashed into `extract-v19`'s `prompt` fingerprint (D20 still holds: what changes output
   changes the key).
6. **`extract-v19` joins `ADDS`.** With the spec's fields equal to `extract-v18`'s, a change among `extract-v16`,
   `-v18` and `-v19` differs in `compiler` and `prompt` only and is `adds`: nothing already served is queued, in either
   direction. A test pins the earlier keys to their values before this phase.
7. **Older rows are read as they are.** No `when_happened`, no `told`; "extract all history" is the owner's manual
   fill, per chat.

## Consequences

- A turn extracted before the switch keeps its telling turn as its only time.
- `told` rows exist only from `extract-v19`; a switch back keeps them stored and unread for turns another compiler
  serves.
- The prompt grows; the phase reports the growth against `extract-v18` (at most 15 %).
- A switch back from `extract-v19` queues nothing only on code that knows `extract-v19` (its `ADDS`); an image from
  before this phase reads it as a version change. A rollback therefore changes the compiler before it changes the
  image (PHASE-60 C3).

## Amendment (2026-11-25, PHASE-65 S1, audit G2): the clock line

Item 3's clock strips a `<prefix>.` from a key, reads 현재 시간 / 현재 시각 / 일차 / day / 요일 / 계절 as their own
categories, and never shows a field more than one turn older than the newest one, so a date of one turn and a time
of another are no longer stitched into one clock. It stays a recorded input, not part of validity or of the key, so
rows of one generation written before and after differ in the clock they were shown.
