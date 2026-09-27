# `extract-v12`: secrets kept from someone, and when they end — evidence

Date: 2026-09-27. Phase 10 steps 2–3 (`docs/phases/PHASE-10.md`, ADR 0033). Model: `gemma4:31b-cloud` (the
owner's extraction model) through Ollama at `http://127.0.0.1:11434/v1`, temperature 0.

## What changed

- `hidden_from` is only for what is deliberately kept from a character; absence is not a secret.
- OPEN SECRETS (S1…S8) in the prompt, a numbered `secrets` check in the answer, and `learned` filled by the
  worker as `[turn N] <listed line>`; a reveal ends the listed turn's secret of the same head and every copy
  whose head and content match.
- A generation's backfill is claimed oldest first (live and first-sight work stays newest first).

## 1. Synthetic scenes (`tools/eval_v12_model.py`, fixtures `fixtures/model/v12/2026-09-27-gemma4-31b`)

13 Korean scenes, 3 runs each. Kept, absent and private scenes also run with the `extract-v11` prompt.

| Category (scenes) | `extract-v11` | `extract-v12` |
|---|---:|---:|
| Kept from someone: a surprise, a lie, a hidden identity (3) | 9/9 | 9/9 |
| Absent, not hidden: away, asleep, elsewhere (3) | 8/9 | 9/9 |
| Private feeling or hope, not hidden (2) | 6/6 | 6/6 |
| Reveal of a listed secret: sees it, confronted, overhears (3) | — | 9/9 |
| Control: the holders whisper, the other only suspects (2) | — | 6/6 |

`extract-v11` once marked a character who was asleep as `hidden_from`. The synthetic scenes are easier than the
owner's chat: the separation of absence from secrecy is measured on it below.

## 2. The owner's chat, re-extracted on a copy

The 2026-09-27 backup of the owner's database was restored into a scratch database (production untouched); the
longest chat (73 turns) was re-extracted there with `extract-v12` through the worker, as a generation switch
does. Chat text is not quoted here.

| | `extract-v10` (as served) | `extract-v12` |
|---|---:|---:|
| Valid assertions | 343 | 372 |
| `limited` | 90 | 116 |
| With `hidden_from` | 12 | 13 |
| `learned` | — | 6 |
| Secrets at the head: still kept / ended | 12 / 0 | 7 / 6 |

- **The pilot's stale secret ends.** The mother found out the daughter's plan to watch her lecture at turn 21.
  `extract-v10` still marked the plan hidden from her at the head. With `extract-v12` all five copies of it
  (turns 6, 7 ×3, 19) end at turn 21; one more copy (turn 20, an event) stays marked.
- **A surprise ends when it is given.** The hidden cookie (turn 7) ends at turn 12, when the daughter hands it
  to her mother.
- **The pilot's missing mark is set.** The daughter's promise to hug her mother (turn 9) is now `hidden_from` the
  mother; `extract-v10` had no mark on it, which is why the pilot's A needed A′.
- **Absence noise is gone** where `extract-v10` had it (a trembling hand marked hidden from someone who was not
  there). One questionable mark stays in both (a greenhouse's heat marked hidden from the mother), and one
  plan's kept-from character varies between runs.
- **One reveal is missed.** At turn 52 the user's character tells the mother about the hug promise; the check
  reported it in 1 of 3 probe runs and not in the full run, so the promise stays marked at the head.

## 3. How the reveal check was chosen (probes on the copy, 3 runs per turn)

| Design | Reveal turns caught | Turns without a reveal, false reveals |
|---|---|---|
| Model writes `learned` with the listed text | turn 21: 0/3 (it wrote `knows`) | — |
| Same, with an end-of-prompt reminder | turn 21: 3/3, but one copy of several | turns 10–17: many (up to 7 secrets at once) |
| Reminder tightened | turn 21: 0/3 | turn 16: 3/3 |
| **Numbered `secrets` check (adopted)** | turns 12, 21, 30: 3/3 each; turn 52: 1/3 | turns 10, 13, 14, 17: 0/3; turn 16: 2/3 |

Turn 16 is a conversation about the daughter's worry for her mother, close to the hug promise's reason.

**Order matters.** The first full run claimed turns newest first, as before: turn 21 then saw OPEN SECRETS from
the previous generation's facts, and after the earlier turns were extracted again in other words 5 reveals
matched nothing (3 secrets ended). Linking a reveal to its listed turn, and claiming a generation's backfill
oldest first, gave the table above (6 ended, 1 repeated reveal of an ended secret, no mismatch).

## Cost

About 600 calls to `gemma4:31b-cloud` on the owner's Ollama account (synthetic runs, probes and five 73-turn
re-extractions of the copy); no paid API.

## Limits

One extraction model, one real chat. The reveal check depends on the model: it misses a plainly told secret in
some runs and fires on a related conversation in others. A missed reveal leaves a secret marked until "Extract
all history" or a later turn reports it; there is no owner repair yet (Stage 6).
