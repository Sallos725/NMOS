# Phase 35 — The excerpt lands on what was asked, not on when (`packet-v15`)

> **Status: proposed 2026-10-08, a correction phase (AGENTS §7 item 5) found by Phase 33's S6 diagnosis.** Under
> AGE-10, beside Phase 34 (Stage 7 part 2); `0.4.0` waits for it (the owner, 2026-10-08: fix S6 before the release).
> Recall only: no extraction prompt, generation key, stored row or migration changes.

## Why now

Phase 33 explained S6's missed memory cases (one of three while NMOS catches up on a 120-turn chat) by the turns
extraction has not reached, and gave those turns raw-evidence excerpts (Q5). The zero-call replay showed Q5 at work on
S6 and every S6 packet the same as `packet-v12`'s (`docs/perf/phase33-replay.md`, corrected 2026-10-08), and the
owner dropped the live run (PHASE-33 Q10 d). The two missed cases were read on the bench database (`nmos_b030_s6_1`,
synthetic chat):

| Case | Question | Where the answer is | Where the excerpt landed |
|---|---|---|---|
| `c120_21_early` | 하람이가 처음 권해 준 빵이 뭐였어? | turn 2, "소금버터 꽈배기요." | "손님, 그렇게 물어보시는 분 **처음** 봤어요." |
| `c120_22_early` | 도윤이 윤슬포에 온 지 얼마 안 됐을 때 밤하늘에 떴던 달 기억나? | turn 8, "붉은 달" | "윤슬포에 **온 지** 사흘, 부딪히는 것마다 벽이었다." |

**The right message is found and placed both times**; its excerpt anchors on the wrong sentence:

- **The question's "when" words anchor it.** 처음 is a keyword (`keywords.keywords`), so the sentence with 처음 wins
  (`packet.grown_excerpt` ranks sentences by the question's keywords first). 처음 says when the thing happened, not what
  it was.
- **One-syllable function words break the tie.** packet-v12's tie-break on the question's one-character words
  (PHASE-31 Q3, meant for 책, 집, 돈) also counts 온, 지, 안, 때 ("온 지 얼마 안 됐을 때"), so the sentence "윤슬포에 온 지
  사흘" wins two ties against the one sentence holding 달.
- **The vector chunk holds the wrong part of the message.** A word hit whose vector meets the bar is excerpted within
  its 700-character chunk (packet-v11, ADR 0063); here the best chunk is the fog at the start of the turn, and the red
  moon is in a later chunk.

## Questions and proposed answers

| # | Question | Proposed answer | Alternatives considered |
|---|---|---|---|
| Q1 | What do a history cue's words do? | **They leave the anchor words and only break a tie.** A keyword matching `HISTORY_CUE` (처음, 첫날, 예전, 원래, …) no longer picks the best sentence; it counts among the tie words, and a first cue adds both 처음 and 첫 (the story says "첫 빵" where the question says "처음"). The keyword route (which messages are found) is unchanged. | Drop cue words from the keywords altogether (the keyword route then loses its anchor for "처음 만났을 때"); a model call (C8). |
| Q2 | Which one-syllable words break a tie? | **Only those that can name something.** A fixed list of one-syllable function words (`FUNCTION_SYLLABLES`: verb and ending pieces such as 온, 준, 한; dependent nouns such as 지, 때, 것, 게; 안, 못, 더; pronouns and determiners) no longer counts; 책, 집, 돈, 빵, 달 still do (PHASE-31 Q3 unchanged for them). | A part-of-speech tagger (a dependency, AGENTS §4); keep every one-syllable word (S6 22 stays missed). |
| Q3 | When does the whole message replace the chunk? | **When the question names a one-syllable noun (달, 빵) and the whole message holds a sentence with more of those nouns, then of the anchor words, than any sentence of the chunk** (`packet.anchor_rank`). Otherwise the chunk stays (packet-v11's rule: the chunk is the part of the message the meaning found). Measured on the prototype: comparing by the anchor words first gave the chunk up for a sentence holding the two main characters' names and lost a quote-set case (q-first-07); the cue words (처음, 첫) do not count here either. | Always the whole message for a word hit (undoes ADR 0063's measured gain); the anchor words first (the names every scene holds win); a second excerpt from the same message (one more slot per message). |
| Q4 | How does it ship? | **`packet-v15` behind `NMOS_PACKET_POLICY`**, on top of `packet-v14`; `packet-v14` and earlier unchanged and selectable. The default is the owner's decision on the measurement. | A recall option per rule. |
| Q5 | How is it measured? | **(a)** Deterministic cases for each rule. **(b)** The zero-call replay of every probe of the v0.3.0 bench (S0–S6, 20 sets) and the quote set under `packet-v14` and `packet-v15`, three replays, the majority deciding (AGENTS §7 item 6). **(c)** No live run proposed: the extraction is unchanged, and Phase 33's S6 replay showed a live run on fresh extraction would mostly measure the extractor's variance (the owner, 2026-10-08); the owner may ask for S6 once (123 extraction calls, about $0.22). | The full live gate (an extraction change only). |
| Q6 | What is the bar? | On (b): S6 memory cases at least two of three; every set no worse than `packet-v14` by any case; forbidden totals not higher; the quote set at least 20 of 24. | No worse by one case (Phase 33's bar; this change is small enough to hold every case). |

## In scope

1. `packet-v15`: Q1–Q3 in `retrieval.gather` and `packet` (`anchor_words`, `FUNCTION_SYLLABLES`, `anchor_rank`).
2. Deterministic tests; the replay (Q5 b) and its report in `docs/perf/`.
3. An ADR (0069) and an ARCHITECTURE decision; README, guide and CHANGELOG lines.

## Out of scope

The keyword route and lexical recall (which messages are found); extraction; a model call; S6's state case
(`c120_01_state`) and irrelevant case (`c120_24_irrelevant`), which fail for other reasons on every policy.

## Steps

1. This document, approved.
2. `packet-v15` with deterministic tests, the ADR, and the replay (Q5 b).
3. The owner's decision on the default; then `0.4.0`.

## Stop conditions

Stop and ask the owner when: a replayed set loses a case under `packet-v15`; a forbidden total rises; the change needs
a stored row, a migration or a dependency.
