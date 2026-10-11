# Phase 44 step 1 — would a recall tool have answered the misses? (2026-10-12)

Zero model calls. Base: `main` at `48a693a`, `packet-v18`, with today's options (`keyword_particles` and
`source_clock` on, as Phase 42's gate ran).

Cases: every probe of the v0.3.0 bench (314; databases `nmos_b030_*`) and the exact-quote set (24; `nmos_p33_s3`).
- Each case was replayed with `audit.replay` and scored by `tools/eval_rp.py`'s `score`.
- Three separate processes were run; the majority decides each case.
- Queries were embedded on the evaluation Ollama (`qwen3-embedding:8b`). Vector search ran on every replay.
- S0main and S0s2 are the owner's real chats: counts only.

## What was measured

The tool's result was taken to be what the same question recalls with **1,200 more tokens** (Q5 a) or **2,000 more**
(Q5 c).
- The request is replayed a second time with its budget raised, and the lines it places that the default packet did
  not are the tool's delivery.
- A case passes "with the tool" when the default packet plus that delivery hold every gold phrase and no forbidden
  one.

So the tool's query is the probe as the user asked it, and its delivery uses the compiler's own rules (anchors, quote
route, memory mode). This is **the upper bound of a tool that asks the question verbatim**.

By construction, it cannot tell a tool apart from a larger default budget. The column "larger budget alone" (the
raised replay by itself) is reported for that reason. A model that rewords its question is not measured here (no
model calls). The diagnostic below bounds that part.

## Result: A1 not met — 4 of 27 misses answered; the gain is the budget's

The default replay reproduced the recorded result: 291/314 recall, and 20/24 quotes. The record says 21/24; the
difference is `q-first-07`, which is known to change from run to run under every policy (it loses a 0.001 tie).

So this run's miss set is 23 + 4 = **27 cases**, and A1 needs 14.

| Set | Cases | Default | Default + tool (+1,200) | Default + tool (+2,000) | Larger budget alone (+2,000) | Forbidden placed (default) |
|---|---:|---:|---:|---:|---:|---:|
| S0main (default, all history, first cue) | 81 | 70 | 72 | 72 | 72 | 6 |
| S0s2 (default, all history, first cue) | 31 | 31 | 31 | 31 | 31 | 0 |
| S1 (turn 30, 60, 120, 240) | 100 | 96 | 96 | 96 | 96 | 3 |
| S2 (default, all history, first cue) | 51 | 46 | 46 | 46 | 46 | 3 |
| S3, S5 branch, S5 new chat | 18 | 18 | 18 | 18 | 18 | 0 |
| S4, S4b | 7 | 6 | 7 | 7 | 7 | 0 |
| S6 (default, first cue) | 26 | 24 | 24 | 24 | 24 | 2 |
| **Bench** | **314** | **291** | **294** | **294** | **294** | **14** |
| Exact-quote set | 24 | 20 | 20 | 21 | 21 | 0 |
| **All** | **338** | **311** | **314** | **315** | **315** | **14** |

**What the tool gains**
- Three bench cases at either size: one S0main question (counted in both of its sets) and `s4_del_brush`.
- One quote case at +2,000: `q-first-07`, the tie case above (20, 21, 21 in the three runs).
- No case passing at default fails with the tool. The tool placed no forbidden phrase that the default had not.

**The gain is the budget's.** In every case, "default + tool" and "larger budget alone" decide the same. Everything
the tool gained, a larger default budget gains too.

**Most requests have budget to spare.**
- On the bench, the median delivery is 0 tokens: the raised replay placed nothing new for most requests, because the
  packet was not full.
- Where something was placed, p95 was 664 tokens (+1,200) and 1,214 tokens (+2,000).
- On the quote set, the median delivery was 388 and 628 tokens.
- Of the cases that already pass at default, 48 % would receive some delivery at +1,200. That is the cost a tool
  pays only on a call and a raised default pays on every turn.

## Why the other 23 misses stay

Each case still missed at +2,000 was read against the chat's own source text before its request. Each gold phrase
the replay did not hold was searched there (read-only, counts only).

| What is missing | Cases | What could fix it |
|---|---:|---:|
| Nothing: every gold phrase is held, but a forbidden phrase is placed | 14 | Not a recall tool: more memory cannot remove what is already placed |
| Gold is in the source text, but recall does not reach it with the question as asked | 9 | Possibly a reworded question (not measured), or recall itself |
| Gold is in neither | 0 | — |

The 9 reachable cases:
- 3 are S0main cases: two questions, one of them counted in two sets;
- 3 are `c240_19_past`, in S1 turn 240 and in S2's default and all-history sets (the same probe in different
  runs);
- 3 are quotes: `q-turn-57`, `q-first-12` and `q-said-44`.

**The bound.** Even if a model reworded all 9 so that recall reached them, the tool would answer 4 + 9 = 13 of 27.
That is still below A1's 14. A1 cannot be met on this evidence, whatever the rewording.

## Reading

- **The measured part of a recall tool's value is a budget raise.** That is a known setting: the 4,000 default
  decided in Phase 15 (`packet-v9`, ADR 0049). A tool would spend it only on a call; the default spends it on every
  turn.
  - 3 of 314 bench cases is too few to reopen that setting on its own.
  - The cost side is a live question: the call rate, and one more main-model request per call.
- **Half of the misses are what the packet places, not what it lacks.** The 14 forbidden-only cases are stale or
  irrelevant lines placed as current. They are packet-policy work. A tool cannot help them.
- **The remaining room is recall's reach for 9 questions.** That is ordinary recall work (wording, anchors, the
  quote route). A tool would depend on the model to reword them.

## Reproduction

- Scripts and per-case JSON (names and counts only, mode 0600) are in `~/nmos-eval/phase44/` on the owner's
  machine: `zero_call.py`, `summarize.py` and `diag.py`.
- They import `eval_rp` and `nmos_sidecar` from the worktree and open every database with
  `default_transaction_read_only=on`.
- No product code changed for this step.
