# Memory evaluation baseline (2026-09-23, Track A, A5; Phase 5–8 cases 2026-09-24; Phase 9 2026-09-26; `packet-v2` 2026-09-26; Phase 10 2026-09-27; Phase 11 2026-09-28, step 8 the same day)

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
  Z."; an item's end "X burns / eats the Y." → `destroyed`, and no rule for damage; since Phase 7 a
  promise its maker says 'X says to Y: "I promise to …."', one reported by someone else 'Z says: "X
  promised Y to …."', a broken one "X breaks the promise to Y to ….", a kept one "X kept the promise to …." →
  `fulfilled`, minor events "X did chore N." and a major event "X betrayed Y." (since Phase 8 with Y as
  its participant)); the embedder is a concept bag with weak
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
  bring what is older. `full-v0` (since Phase 9): `full` compiled by `packet-v0`, the packet compiler
  before ADR 0027; `full` uses the default, `packet-v7` since ADR 0041 (`packet-v1` to `-v6` before; the
  table's first 35 cases are the same under each). `packet-v7` gives every case of every mode the same outcome as
  `packet-v6`: no gold or stale string depends on an excerpt's turn number (the mean `full` packet is 1 token smaller,
  190 → 189: a turn index has fewer digits than a position).

Gold for the state cases is a fact line (e.g. `Hinata located in harbor`), which only `full` can
produce; `lexical` and `hybrid` can still bring the original sentence as an excerpt.

## Results

| Case | Category | recent | lexical | hybrid | full-v0 | full |
|---|---|---|---|---|---|---|
| current state after moves | current state | **no** | **no** | **no** | yes | yes |
| history of a move | historical state | **no** | yes | yes | yes | yes |
| item changes hands | current state | **no** | **no** | **no** | yes | yes |
| edited message | edit invalidation | **no** | **no** | **no** | yes | yes |
| deleted turn | delete invalidation | — | — | — | — | — |
| rerolled reply | reroll invalidation | **no** | **no** | **no** | yes | yes |
| swipe back | swipe invalidation | **no** | **no** | **no** | yes | yes |
| branch does not see the origin's later story | branch isolation | **no** | **no** | **no** | yes | yes |
| exact quote | exact quote | **no** | yes | yes | yes | yes |
| Korean paraphrase | paraphrase recall | **no** | **no** | yes | yes | yes |
| secret kept from someone | soft knowledge | **no** | **no** | **no** | yes | yes |
| lost item | negation | **no** | **no** | **no** | yes | yes |
| negated entry | negation | **no** | **no** | **no** | yes | yes |
| negation of another place | negation | **no** | **no** | **no** | yes | yes |
| denial by a non-holder | negation | **no** | **no** | **no** | yes | yes |
| hypothetical and dream | modality | **no** | **no** | **no** | yes | yes |
| lie in dialogue | source | **no** | **no** | **no** | yes | yes |
| put down | item whereabouts | **no** | **no** | **no** | yes | yes |
| picked up | item whereabouts | **no** | **no** | **no** | yes | yes |
| holder and place in one turn | item whereabouts | **no** | **no** | **no** | yes | yes |
| a character's place is not an item's | item whereabouts | **no** | **no** | **no** | yes | yes |
| destroyed | item end | **no** | **no** | **no** | yes | yes |
| eaten | item end | **no** | **no** | **no** | yes | yes |
| damaged, not destroyed | item end | **no** | **no** | **no** | yes | yes |
| edit removes the end | item end | **no** | **no** | **no** | yes | yes |
| use after end | conflict | **no** | **no** | **no** | yes | yes |
| promise recalled | open thread | **no** | **no** | **no** | yes | yes |
| reported promise | open thread | **no** | **no** | **no** | yes | yes |
| broken promise | open thread | — | — | — | — | — |
| kept promise | open thread | — | — | — | — | — |
| edit removes the break | open thread | **no** | **no** | **no** | yes | yes |
| delete removes the promise | open thread | — | — | — | — | — |
| events leave room | event salience | **no** | **no** | **no** | yes | yes |
| major event first | event salience | **no** | **no** | **no** | yes | yes |
| addressed participant | event participants | **no** | **no** | **no** | yes | yes |
| speech level in a crowded scene | standing facts | **no** | **no** | **no** | yes | yes |
| speech level changed back | standing facts | **no** | **no** | **no** | yes | yes |
| relationship changed the other way | standing facts | **no** | **no** | **no** | yes | yes |
| what a relationship was before | standing facts | **no** | **no** | **no** | **no** | yes |
| goal recalled | open business | **no** | **no** | **no** | yes | yes |
| achieved goal | open business | — | — | — | — | — |
| edit takes back the end | open business | **no** | **no** | **no** | yes | yes |
| answered question | open business | — | — | — | — | — |
| threat hangs over someone | open business | **no** | **no** | **no** | yes | yes |
| paid debt | open business | — | — | — | — | — |
| delete removes a goal | open business | — | — | — | — | — |
| question recalled | open business | **no** | **no** | **no** | yes | yes |
| delete removes a question | open business | — | — | — | — | — |
| edit takes back an answer | open business | **no** | **no** | **no** | yes | yes |
| averted threat | open business | — | — | — | — | — |
| delete removes a threat | open business | — | — | — | — | — |
| edit takes back an averted threat | open business | **no** | **no** | **no** | yes | yes |
| debt recalled | open business | **no** | **no** | **no** | yes | yes |
| delete removes a debt | open business | — | — | — | — | — |
| edit takes back a payment | open business | **no** | **no** | **no** | yes | yes |
| why someone is angry | causes | **no** | **no** | **no** | **no** | yes |
| quote under a full budget | budget pressure | **no** | **no** | **no** | **no** | yes |
| one line of a long message | budget pressure | **no** | **no** | **no** | **no** | yes |
| a secret in front of the one it is kept from | secrets | n/a | n/a | n/a | **no** | yes |
| away is not kept from | secrets | n/a | n/a | n/a | yes | yes |
| a reveal ends it | secrets | n/a | n/a | n/a | yes | yes |
| an edit restores it | secrets | n/a | n/a | n/a | yes | yes |
| strict mode withholds it | secrets | n/a | n/a | n/a | yes | yes |
| a narrator is not told what they do not know | secrets | n/a | n/a | n/a | yes | yes |
| a narrator who holds it | secrets | n/a | n/a | n/a | yes | yes |
| unrelated question | irrelevant-memory suppression | — | empty | empty | empty | empty |

| Mode | gold reached | cases with stale memory | irrelevant packets | mean packet tokens |
|---|---:|---:|---:|---:|
| recent | 0/46 | 0 | — | 0 |
| lexical | 2/46 | 0 | 0/1 | 90 |
| hybrid | 3/46 | 0 | 0/1 | 113 |
| full-v0 | 48/53 | 0 | 0/1 | 175 |
| full | 53/53 | 0 | 0/1 | 173 |

Phase 11 step 8 added ten open-business cases, so that each kind of thread is opened, ended, deleted and has its
end edited away: a question and a debt recalled as threads after twelve newer events, an averted threat no longer in
the packet, a goal, a question, a threat and a debt whose opening turn is deleted, and an answer, an averted threat
and a payment whose turn is edited away, which opens the thread again. Those with gold answer under `packet-v0` too:
threads are placed the same way by every policy.

Phase 11 step 6 (ADR 0040) added "why someone is angry": a feeling with the cause the story states, asked about with
"why" after a speech-level fact of the same pair. `packet-v6` places the feeling with its cause; `full-v0` does not.

Phase 11 steps 4–5 (ADR 0039, `extract-v13`) added six open-business cases: a goal and a threat recalled as threads
after twelve newer events, an achieved goal, an answered question and a paid debt no longer in the packet, and an
edit that takes back a goal's end. The stub extractor maps "X wants to …", "X wonders …", "Y threatens X with …",
"X owes Y …" and "X's goal is achieved: …" (and the other outcomes).

Phase 11 step 3 (ADR 0038) added two relationship cases: the story makes a pair lovers and extraction records it
in the other direction than their earlier relationship (K24). Before step 3 both were current, and the earlier
one was stale. `packet-v5` names the relationship a standing fact replaced, so "what were they before" is
answered in `full` and not by `packet-v0` (`full-v0`), which CI checks along with the budget-pressure and Private
cases. "speech level changed back" checks the line's own statement, since `packet-v5` names the replaced speech
level after it.

Phase 10 (ADR 0033–0035) added seven secret cases. They need facts, so they run in `full` and `full-v0` only
("n/a" elsewhere): a secret with the one it is kept from in the scene goes to the Private section (`packet-v3`
and later; `full-v0` has none), someone away is not marked `hidden_from`, a reveal ends the secret and an edit
of the revealing turn restores it, strict mode gives a Secret line and no content (neither the fact nor the
excerpt that says it), and a first-person narrator gets only what they are shown to know. The stub extractor
answers the `secrets` check for "X found out that …." against the listed OPEN SECRETS. The two reveal cases
extract after every step, as in play: extracted all at once, newest first, the reveal came before its
secret and matched nothing (K29). Before ADR 0033 amendment 1, "a reveal ends it" placed the fact in Private:
the character who found out still did not count as knowing it.

Phase 9 (ADR 0027) added two budget-pressure cases: ten long Korean traits and two claims of 하나 fill the
600-token budget, and the answer is only in a message's words (a whole short message, or one sentence of
a long one). `packet-v0` spends the budget on the fact lines and drops the excerpt; `packet-v1` keeps
room for it. CI checks that `full-v0` misses exactly these
two and `full` answers every case.

Before Phase 6 step 1 (ADR 0016), `full` had stale memory in "put down" (`Hana possesses map`) and
"picked up" (`map located in table`).
Before Phase 7 step 1, "events leave room" missed its gold: twelve newer events of Hana took every
fact slot. Before step 2, "promise recalled" missed its gold: the promise reached the packet only as a
`<Claim>`, never as an open thread.
Before step 4, "major event first" missed its gold: its minor events, newer and all naming Hana, took the
three event slots.
Before Phase 8 step 2, "addressed participant" missed its gold in every mode: the event names Kaito only
in its value, and recall counted only subjects and objects as mentions.

"—": the case has no gold (the deleted turn only checks that nothing of it comes back).

## What CI enforces

- No stale or other-branch text in any memory mode.
- `full` reaches every gold.
- Irrelevant questions get an empty packet in every memory mode.
- `recent` reaches none of the gold (the cases really need memory).
- `full-v0` misses exactly the budget-pressure cases, so they keep testing the budget (Phase 9), and the
  cases whose gold is the Private section (Phase 10).

## Not covered here

- **Model tier.** Extraction quality (e.g. a refused user action recorded as done) depends on the
  model; it is reported separately with model, endpoint, prompt generation and run count
  (`docs/perf/turn-extraction.md`), never gated.
- Latency tiers: `docs/perf/scale.md`.
- Broad-query abstention: `apps/sidecar/tests/test_normalized_text.py` and `docs/perf/scale.md`
  (a case here would need more than 200 matching messages).
