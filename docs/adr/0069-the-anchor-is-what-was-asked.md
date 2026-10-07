# 0069 — An excerpt anchors on what the question asks, not on when (`packet-v15`)

Status: proposed, 2026-10-08 (`docs/phases/PHASE-35.md` Q1–Q4; AGE-10). Adds the policy `packet-v15` on top of
`packet-v14`; the default is the owner's decision on the replay. No prompt, generation key, stored row or migration
changes.

## Context

S6's two missed early-detail cases (PHASE-35, "Why now") were found and placed but excerpted from the wrong sentence of
the right message. `packet.grown_excerpt` picks the sentence holding most of the question's keywords, then most of its
one-character words (packet-v12, ADR 0066), then most of its trigrams. A question about the first time carries 처음 as
a keyword, so a sentence that says 처음 about something else wins; a question about "when he had just arrived" ("온 지
얼마 안 됐을 때") carries 온, 지, 안 and 때 as one-character words, so a sentence with "온 지" wins the tie against the
one holding 달. And a word hit whose vector meets the bar is excerpted inside its 700-character chunk (ADR 0063), which
can be a part of the message the words do not point at.

## Decision

Under `packet-v15` (`packet.ANCHOR_POLICIES`):

1. **A history cue's words break ties only.** A keyword matching `HISTORY_CUE` leaves the words that pick the best
   sentence and joins the tie words; a first cue adds both 처음 and 첫 to them (`retrieval.anchor_words`). The
   keyword route is unchanged: the cue still helps find the message.
2. **One-syllable function words break no tie.** The question's one-character words count as tie words unless they
   are in `retrieval.FUNCTION_SYLLABLES` (verb and ending pieces, dependent nouns, negations and adverbs, pronouns and
   determiners); nouns such as 책, 집, 돈, 빵, 달 keep packet-v12's tie-break.
3. **The whole message replaces a chunk that says less of what the question names.** When the question has
   one-syllable nouns among its tie words and the whole message holds a sentence with more of them, then of the anchor
   words, than any sentence of the vector chunk (`packet.anchor_rank`), the excerpt is grown from the whole message;
   otherwise from the chunk, as under ADR 0063. Ranking by the anchor words first gave a chunk up for a sentence
   holding the two main characters' names, which every scene holds.

## Consequences

- On the zero-call replay of the v0.3.0 bench (`docs/perf/phase35-replay.md`): S6's memory cases three of three
  (`packet-v14`: one), and the same first-time question on S1 at turn 120 recovered; no set loses a case on the
  majority of three replays; the quote set as `packet-v14`.
- The function-syllable list is fixed and Korean only; a one-syllable noun missing from it, or a function word
  missing from the list, behaves as under `packet-v14`.
- Rejected: dropping cue words from the keywords (the keyword route loses them); always excerpting the whole message
  for a word hit (undoes ADR 0063's measured gain); a second excerpt from the same message (a slot per message).
