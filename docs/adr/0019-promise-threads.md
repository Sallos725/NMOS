# 0019 — Promise threads

Status: accepted, 2026-09-24. Phase 7 step 2 (`docs/phases/PHASE-7.md`, owner answers Q2, Q3, Q5).
Read-side only: no schema change and no new extractor generation. `fulfilled` (the "kept" resolution)
comes with `extract-v7` in step 3; until then only a negative `promised` closes a thread.

## Context

A promise is made in dialogue, so extraction records it as a character claim (ADR 0013). In the
Phase 5 real-model tier all 6 runs of "plan to meet" did so, and 3 of 6 labeled it `hypothetical`,
which keeps it out of the packet. `promised` is multi-valued: nothing ever marks a promise as kept, so
as a fact it would stay current forever. Among a main character's many newer facts it also lost every
packet slot (PHASE-7, "Evidence").

## Decision

1. **Opening (Q2).** A `promised` assertion opens a thread when the narration states it (legacy rows
   without a source count as narration, as everywhere) or it is a claim whose speaker resolves to its
   subject (the maker), with modality `actual` or `hypothetical`. Saying a promise makes it, and its
   content is in the future by nature. Reported, dreamed and unknown promises keep their earlier
   routes (claims, other).
2. **Closing (Q3).** `fulfilled` closes a thread as `kept`, and a negative `promised` as `broken`
   (broken, withdrawn or released). Only if the resolution is `actual` and the narration, the maker or
   the recipient states it. A bystander's claim or a plan to break it closes nothing.
3. **Matching by text.** A resolution names its promise by text, not by id: an id would point at an
   assertion that a later generation's re-extraction of the opening turn replaces (ADR 0014). It
   matches the open threads of the same maker entity (ADR 0012), and of the same recipient when it
   names one. Equal normalized text wins. Otherwise the most similar thread by the overlap coefficient
   of character trigrams (|A∩B| / min(|A|, |B|): a resolution often shortens the promise) must reach
   0.6 and lead the next by 0.15. No match, or a tie, closes nothing, and the resolution is listed as
   unmatched.
4. **Restating.** A new promise restates an open one of the same maker and recipient only when one
   text contains the other (at least 4 characters, and only one such thread): "등대 앞에서 만나기로"
   restates "비가 그치면 내일 아침 등대 앞에서 만나기로 함". Two promises of one maker often share words
   ("등대 앞에서 만나기", "등대 앞에서 기다리기"), so the resolution bar would merge them. Similarity would
   also compare every new promise with every open one of its maker: the first version (0.9 similarity)
   took ≈85 ms per fold for 500 synthetic promises made by 4 characters. A restatement is recorded on the thread;
   after a thread closes, the same words open a new one.
5. **Consumed assertions.** The assertions a thread opened, restated or closed, and unmatched
   resolutions, are not facts, claims or other assertions as well. A promise appears once.
6. **Packet (Q5).** Open threads whose maker or recipient is mentioned in the user's message
   (first) or the previous reply, newest first, at most `threads_limit` (default 3; 0 turns them
   off). The persona's names never count as a mention: the persona is in every chat. A thread whose
   opening message is still in the prompt is left out (D3). They go in a `<Threads>` section after
   `<State>` and before `<Facts>`, with the opening turn's knowledge marks (D19). The Note gains one
   sentence only when a thread line is kept.
7. **Nothing is stored.** Threads are a fold over the head's served assertions in position order, then
   extraction order within a turn. An edit, delete or reroll changes the next read, and a rebuild
   reproduces them.

## Consequences

- A spoken promise reaches the packet whenever its maker comes up, however far back it was made
  (`tests/test_threads.py`; memory evaluation "promise recalled", "reported promise", "broken promise",
  "edit removes the break", "delete removes the promise"; `docs/perf/eval-baseline.md`).
- Older turns (`extract-v6` and earlier) open threads at once. They close only by a negative
  `promised`, because they have no `fulfilled`. Step 3 adds `fulfilled` and shows the extractor the open
  promises.
- A promise the story forgets stays open. Closing on age would state something the story did not
  (PHASE-7 stop condition). Owner repair is Track B, B7.
- Cost: the fold runs on every fact read, over the `promised` and `fulfilled` assertions only. Text
  matching compares a resolution with its maker's open threads, and trigrams are computed only when
  the text is not equal (`docs/perf/phase7-extraction.md`).
- The thresholds are set on the deterministic cases. The real-model tier (step 6) checks them on model
  output and may move them; a change is a new entry here.
