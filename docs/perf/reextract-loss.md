# What a re-extraction keeps — measurements (Phase 22)

Phase 22 (`docs/phases/PHASE-22.md`, ADR 0057 and its amendment 1, ADR 0044 amendment 3, D66), AGE-25. Measured
2026-10-01 on local copies of the owner's chats (the three-plugin bench's M0 chats and restored production copies, on the
test PostgreSQL; never production), counts only: no chat text, names or ids leave the copies. Scripts outside the
repository (`~/nmos-eval/phase22/`), run with the Phase 22 step 3 code; `tools/reextract_loss.py` is the read-only tool.

## Dropped facts (Q5, Q8)

`tools/reextract_loss.py`, on each copy's head as it is now. *Same generation*: the turns whose serving extraction of the
active generation replaced a discarded one of that generation — what "Needs attention" lists. *Across generations*: the
turns an older generation's live extraction also covers, measured only.

| Copy | Same generation: turns | Facts | Stated again | Lost by the turn | **Dropped** (listed) | Across generations: turns, facts, lost |
|---|---:|---:|---:|---:|---:|---|
| Owner's M0 main chat, after its "Extract all history" (K29, 2026-09-30) | 68 | 236 | 142 | 94 | **31** | — |
| Owner's second M0 chat (same bench) | 33 | 132 | 93 | 39 | **24** | — |
| The bench's S2 set | 75 | 238 | 54 | 184 | **95** | — |
| Restored production copy (`extract-v13` active) | 0 | — | — | — | **0** | 128 turns, 538 facts, 159 lost (7 chats) |
| The same copy re-extracted with `extract-v14` (three chats re-extracted by evaluations) | 128 | 530 | 373 | 157 | **66** (33, 23, 10) | 21 turns, 121 facts, 32 lost |

- **The spec's production figure was wrong.** PHASE-22's evidence counted every re-extraction a copy holds; production's
  were made under generations that no longer serve (its active `extract-v13` generation never re-extracted a turn), so
  "Needs attention" lists none there, not 106. Its losses across generations (159 of 538 facts) are an upgrade's, by
  design not listed (Q5).
- On the M0 main chat 31 facts are listed (the spec's text comparison counted 34; names compared as entities match more,
  as the spec expected). AGE-25's occupation is one of them.
- Most dropped facts are places and belongings (`located_in`, `possesses`), then events, goals and knowledge.

## AGE-25 end to end, no model call

On a copy of the M0 main chat as it is (damaged by its press of "Extract all history"), with the functions the API calls:

| Step | M0 case "A는 무슨 일을 해?" | Listed |
|---|---|---:|
| Before | failed | 31 (A's occupation among them) |
| Restore A's occupation (`fact_restore`) | **passed** | 30 |
| Undo | failed | 31 |

## The reveal checks instead of the re-extractions (Q8, one paid run)

The M0 main copy put back as it was before its press (the 68 re-extracted turns' first extractions live again), then the
new "Extract all history": only reveal checks were queued and only the reveal handler ran, with `gemma4:31b-cloud`
through the evaluation Ollama (the copy's extractor), two workers. The owner approved the estimate (68 calls, about 276k
input tokens).

| | The press's 68 re-extractions (recorded) | 68 reveal checks |
|---|---:|---:|
| Extractions discarded | 68 | **0** |
| Input tokens | 727,232 | **323,967** (−55 %) |
| Output tokens | 85,306 | **1,491** (−98 %) |
| Model time | 324 s | **50 s** (26 s wall) |
| M0 main, all cases / cases that need memory / forbidden placed | 35/40 · 6/10 · 1 | **36/40 · 6/10 · 0** (as before the press) |
| AGE-25's case | failed | **passed** |

The estimate (calibrated on the recorded re-extractions' tokens per character) was 17 % low.

**Reveals.** Read as memory reads them (secrets ended, by the secret's turn and the character):

| Secret (turn) | The press's re-extractions | The checks |
|---|---|---|
| 6 | found out | found out (a turn earlier) |
| 7 | found out | found out |
| 8 | open | found out |
| 62 | — (the re-extraction stated no such secret) | found out |
| 9 | found out at turn 52 | **open**: the turn-52 check listed it and answered no |
| 18, 19 | found out | — (secrets only the re-extraction stated; the kept extractions have none) |

- Of the secrets both read the same way, the checks found every reveal the press found but one (turn 9), and two more.
- The one: the secret is a character's plan to comfort another *as if by chance*; turn 52 carries the plan out. The
  other character sees the act, not the plan, so by the prompt's rule ("a hint … is not finding out") the check's *no*
  reads as right and the press's reveal as a false positive. The acceptance criterion ("at least the reveals the 68
  re-extractions found") is therefore **not met as written**; the owner decides.

## Request path

`tools/bench_scale.py 10000` (fact read at 10,000 messages), Phase 22's spec commit (`40bdf9b`, before step 2) against
step 3:

| At 10,000 messages | Before (`40bdf9b`) | After (step 3) |
|---|---:|---:|
| Fact read, p50 / p95 | 105.2 / 140.0 ms | 105.9 / 134.6 ms |
| Fact read with two generations, p50 | 104.3 ms | 106.4 ms |
| Lexical recall, p50 | 21.3 ms | 19.8 ms |
| Warm append, p50 | 177.9 ms | 167.2 ms |

Unchanged within noise (the same 5,014 assertions; the read probes a turn's checks in the same join). A chat without
restores runs no extra query; one with restores, one small query for the restored turns.
