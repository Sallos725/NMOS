# Memory evaluation baseline (2026-09-23, Track A, A5; Phase 5 and Phase 6 cases 2026-09-24)

Deterministic tier of the RP memory evaluation. It gates CI (`apps/sidecar/tests/test_memory_eval.py`)
and prints this table (`tools/eval_memory.py`).

## Method

- **Synthetic cases**, written for this evaluation (`apps/sidecar/tests/memeval.py`). They are not
  host evidence and not a user's chat. Each case is a sequence of host actions (send, edit, delete,
  reroll, swipe, branch) driven through the real sidecar API, syncing after each one as the plugin
  would, then one question.
- **Stub extractor and embedder.** Rules map fixed sentence shapes to assertions ("X is in the Y." →
  `located_in`, "X has the Y." → `possesses`, "X keeps a secret from Y: …" → `knows` with
  `hidden_from`; since Phase 5 also negation — "X lost / does not have the Y.", "X did not enter / is not
  in the Y." —, a hypothetical "If X goes to the Y,", a dream "X dreamed she was in the Y.", narrated
  identity "X is a Y." and a claim 'X says: "I am a Y."'; since Phase 6 an item's place — "The Y is
  on the Z.", "X puts the Y on the Z." — and a holder and place in one sentence "X has the Y in the
  Z."; an item's end "X burns / eats the Y." → `destroyed`, and no rule for damage); the embedder is a concept bag with weak
  hashed words. Results therefore measure
  reconciliation, invalidation, retrieval and packet compilation, not model quality.
- **Measured on the packet**, never on a generated answer, so no judge model is involved:
  - *gold*: text that must reach the model (a fact line or an excerpt);
  - *stale*: text that must never reach it: edited, deleted, rerolled or unselected-swipe content,
    another branch's later story, or a superseded fact line;
  - *irrelevant*: the packet for a question nothing in the chat relates to must be empty.
- **Modes.** `recent`: no memory, only the last 6 messages the host prompt still holds (the question
  itself excluded). `lexical`: raw lexical recall (no extractor, no embeddings). `hybrid`: lexical +
  vectors. `full`: hybrid + facts. The last 6 messages are sent as `in_context_ids`, so memory must
  bring what is older.

Gold for the state cases is a fact line (e.g. `Hinata located in harbor`), which only `full` can
produce; `lexical` and `hybrid` can still bring the original sentence as an excerpt.

## Results

| Case | Category | recent | lexical | hybrid | full |
|---|---|---|---|---|---|
| current state after moves | current state | **no** | **no** | **no** | yes |
| history of a move | historical state | **no** | yes | yes | yes |
| item changes hands | current state | **no** | **no** | **no** | yes |
| edited message | edit invalidation | **no** | **no** | **no** | yes |
| deleted turn | delete invalidation | — | — | — | — |
| rerolled reply | reroll invalidation | **no** | **no** | **no** | yes |
| swipe back | swipe invalidation | **no** | **no** | **no** | yes |
| branch does not see the origin's later story | branch isolation | **no** | **no** | **no** | yes |
| exact quote | exact quote | **no** | yes | yes | yes |
| Korean paraphrase | paraphrase recall | **no** | **no** | yes | yes |
| secret kept from someone | soft knowledge | **no** | **no** | **no** | yes |
| lost item | negation | **no** | **no** | **no** | yes |
| negated entry | negation | **no** | **no** | **no** | yes |
| negation of another place | negation | **no** | **no** | **no** | yes |
| denial by a non-holder | negation | **no** | **no** | **no** | yes |
| hypothetical and dream | modality | **no** | **no** | **no** | yes |
| lie in dialogue | source | **no** | **no** | **no** | yes |
| put down | item whereabouts | **no** | **no** | **no** | yes |
| picked up | item whereabouts | **no** | **no** | **no** | yes |
| holder and place in one turn | item whereabouts | **no** | **no** | **no** | yes |
| a character's place is not an item's | item whereabouts | **no** | **no** | **no** | yes |
| destroyed | item end | **no** | **no** | **no** | yes |
| eaten | item end | **no** | **no** | **no** | yes |
| damaged, not destroyed | item end | **no** | **no** | **no** | yes |
| edit removes the end | item end | **no** | **no** | **no** | yes |
| use after end | conflict | **no** | **no** | **no** | yes |
| unrelated question | irrelevant-memory suppression | — | empty | empty | empty |

| Mode | gold reached | cases with stale memory | irrelevant packets | mean packet tokens |
|---|---:|---:|---:|---:|
| recent | 0/25 | 0 | — | 0 |
| lexical | 2/25 | 0 | 0/1 | 120 |
| hybrid | 3/25 | 0 | 0/1 | 146 |
| full | 25/25 | 0 | 0/1 | 178 |

Before Phase 6 step 1 (ADR 0016), `full` had stale memory in "put down" (`Hana possesses map`) and
"picked up" (`map located in table`).

"—": the case has no gold (the deleted turn only checks that nothing of it comes back).

## What CI enforces

- No stale or other-branch text in any memory mode.
- `full` reaches every gold.
- Irrelevant questions get an empty packet in every memory mode.
- `recent` reaches none of the gold (the cases really need memory).

## Not covered here

- **Model tier.** Extraction quality (e.g. a refused user action recorded as done) depends on the
  model; it is reported separately with model, endpoint, prompt generation and run count
  (`docs/perf/turn-extraction.md`), never gated.
- Latency tiers: `docs/perf/scale.md`.
- Broad-query abstention: `apps/sidecar/tests/test_normalized_text.py` and `docs/perf/scale.md`
  (a case here would need more than 200 matching messages).
