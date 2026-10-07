# Phase 35 — the excerpt anchor, replayed (2026-10-08)

`packet-v15` (ADR 0069) against `packet-v14` on the zero-call replay (AGENTS §7 item 6): every probe of the v0.3.0
bench (`0ace76c`, `extract-v16`, the S0–S6 runs of 2026-10-05/06, databases `nmos_b030_*`) and the exact-quote set
(PHASE-33 Q10 b, `nmos_p33_s3`), each compiled again with `audit.replay`, the query embedded on the evaluation Ollama
(`qwen3-embedding:8b`), three replays per policy, the majority deciding. Zero model calls.

## The bench

| Set | Cases | `packet-v14` | `packet-v15` | Forbidden placed (v14 → v15) |
|---|---:|---|---|---|
| S0main default / all history | 40 / 40 | 34 / 34 | 34 / 34 | 3 / 3 → same |
| S0s2 default / all | 15 / 15 | 15 / 15 | 15 / 15 | 0 → 0 |
| S1 turn 30 / 60 | 25 / 25 | 25 / 25 | 25 / 25 | 0 → 0 |
| S1 turn 120 | 25 | 22 | **23** | 2 → 2 |
| S1 turn 240 | 25 | 23 | 23 | 1 → 1 |
| S2 default / all history | 25 / 25 | 22 / 23 | 22 / 23 | 2 / 1 → same |
| S3; S5 branch; S5 new chat | 6 each | 6 each | 6 each | 0 → 0 |
| S4; S4b | 4; 3 | 3; 3 | 3; 3 | 0 → 0 |
| S6 | 25 | 21 (memory 1 of 3) | **23 (memory 3 of 3)** | 2 → 2 |
| first-cue probes (S0main, S0s2, S2, S6) | 1 each | 0, 1, 1, 1 | same | 0 → 0 |
| **All** | 314 | **286** in every replay | **289** in every replay | 14 → 14 |

Gained: S6 `c120_21_early` and `c120_22_early` (PHASE-35 "Why now"), and S1 turn 120's `c120_21_early` (the same
question on the same story). **No case lost** in any replay. **Q6 met.** S0main and S0s2 are the owner's real chats:
aggregates only; their missed memory cases are not this class (no case changed).

## The quote set

| | `packet-v14` | `packet-v15` |
|---|---|---|
| Replays | 21, 21, 21 / 24 | 21, 21, 20 / 24 (majority 21) |

`q-first-07` ("…처음 … 뭐라고 했어?") failed in one `packet-v15` replay of three: its turn's chunk holds the quote, and
with 처음 no longer an anchor word the excerpt's best sentence moves within the chunk on the lexical route's time slice.

## How the rules were chosen

Measured on the prototype, in order:

1. Q1 and Q2 alone recovered `c120_21_early` (the bread) but not `c120_22_early` (the moon): the moon's vector chunk
   ends one sentence before "그런데 그 달이 붉었다".
2. Q3 by the anchor words first (the whole message when it holds a sentence with more of the question's keywords)
   recovered the moon, but gave up a chunk for a sentence holding the two main characters' names, and the quote set
   lost `q-first-07` in two replays of three.
3. Q3 only when the chunk held none of the tie words lost the moon again: the chunk holds "하늘에 달이 떠 있었다".
4. Q3 by the question's one-syllable nouns first, then the anchor words (ADR 0069 item 3): the numbers above.

## Latency

`packet.anchor_rank` splits a message into sentences and counts words: 0.15 ms for a 6,000-character message,
two calls (the chunk and its message) per vector-chunk excerpt when the question names a one-syllable noun.
