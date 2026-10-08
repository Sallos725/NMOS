# Phase 36 — named facts, replayed (2026-10-08)

`packet-v16` (ADR 0070) against `packet-v15`, zero model calls: the owner's trial chat and S1's live run replayed
request by request (`tools/replay_sequence.py`), and every probe of the v0.3.0 bench and the quote set
(`tools/eval_rp.py`, three replays, the majority deciding; AGENTS §7 item 6). The query embedded on the evaluation
Ollama (`qwen3-embedding:8b`); the trial chat without vectors (its embedder is the owner's).

## Required lines (Q4 b)

| | Requests | Required: share of lines | Required: share of tokens | Supportive: repeat share | Supportive: stale tokens | Lines left out resting | Whole: repeat share |
|---|---:|---:|---:|---:|---:|---:|---:|
| Trial chat, `packet-v15` | 37 | 0.760 | 0.838 | 0.561 | 0.126 | 27 | 0.694 |
| Trial chat, `packet-v16` | 37 | **0.674** | **0.801** | 0.519 | 0.067 | 38 | 0.675 |
| S1, `packet-v15` | 241 | 0.632 | 0.687 | 0.243 | 0.018 | 356 | 0.502 |
| S1, `packet-v16` | 241 | **0.569** | **0.656** | 0.242 | 0.014 | 410 | 0.501 |

The trial chat is the owner's (aggregates only); its replayed packets are smaller than live (no vectors). **Q5 (b) met**:
the required share is lower on both chats and the whole packet repeats no more.

## The bench and the quote set (Q4 c)

| | `packet-v15` | `packet-v16` |
|---|---|---|
| The v0.3.0 bench, every probe of S0–S6 (314) | 288, 289, 289 | **289, 289, 289** |
| Forbidden phrases placed | 14, 14, 14 | 14, 14, 14 |
| The quote set (scored from its source turn) | 21, 21, 21 / 24 | 21, 20, 21 / 24 |

No case lost or gained on the majority of three replays. **Q5 (c) met.**

## How the rule got there (Q1 amended twice on the replay)

1. The rule as first proposed (a name alone: required only for now and standing facts, boundaries and word hits) lost
   one real-chat case in all three replays: a question asking what a character does for work, whose answer is an
   identity fact sharing no word with the question. The fact was placed in the requests before it, no reply used it,
   and it rested.
2. With the question-kind cues (`facts.ASKS`: "무슨 일을 해", 직업, 정체 → identity; 소속 → membership; 성격, 생김새 →
   trait; "무슨 일이 있었어" → event; 알고 있어 → knows) that case came back, and S1's question about the red moon on an
   early night failed in two replays of three: a place's world fact that holds "붉은 달" had backed its excerpt under
   `packet-v15`, and named by the place alone it rested.
3. With a fact holding one of the question's one-syllable nouns also named (`facts.asked_nouns`, PHASE-35's nouns: 달,
   빵), every case holds in every replay: the numbers above.
