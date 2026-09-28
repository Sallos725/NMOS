# `packet-v3`: the Private section — evidence

Date: 2026-09-27. Phase 10 step 4 (`docs/phases/PHASE-10.md`, ADR 0034). No model calls: the packets are built
by the sidecar's own functions. Whether response models follow the rule is step 7.

## 1. Deterministic cases (CI)

`tests/test_scene.py`: the cast (last two turns before the current one, characters named now including names
only found in knowledge marks, the persona under every name), the private test, `packet-v3`'s section and rule
(and that it equals `packet-v2` when nothing is private), and an end-to-end case where a secret kept from a
character goes private while that character acts in the last turns and stays in Facts once only its holders
are in the scene. Every existing test and memory-evaluation case passes with `packet-v3` as the default
(405 tests).

## 2. The pilot's scenes on the owner's chat (restored copy, `extract-v12`)

The requests were rebuilt from the chat: the user's message, the previous reply, the host's last ten messages
as in context, a 600-token budget. Chat text is not quoted beyond packet lines' kinds.

| Scene | Cast | `packet-v2` | `packet-v3` |
|---|---|---|---|
| Breakfast, mother and daughter (turn 17) | mother, daughter, user | the lecture plan and the promises kept from the mother in Threads and Facts with their marks | the same lines in `<Private>` with the rule; one public fact takes the freed order slot |
| Daughter asked to hug her mother (turn 52) | mother, daughter, aunt, user | the hug goal (turn 9, kept from the mother) placed | **the hug goal cut by the budget**; a stale copy of the lecture plan (turn 20, not ended, ADR 0033) is placed in Private instead |
| Hallway after the confession (turn 59) | mother, daughter, aunt, user | the lecture plan is not in the packet (ended at turn 21) | same; one feeling known only to the mother goes to Private |

- **The rule's cost.** The first private line pays for the Private header and the rule: 47 estimated tokens for
  the rule after it was shortened from the pilot's wording (88). At 600 tokens that can push one fact line out,
  as on turn 52. A larger memory budget (around 800) avoids it; the default is unchanged (D2: the budget is
  taken from the host's context).
- **The persona is one person.** Extraction writes the persona's full name (family and given name) where the
  host reports the given name; the cast counted two people until a full name ending with a persona name was read
  as the persona (ADR 0034, item 1).

## 3. Latency

`tools/bench_scale.py 10000` (lexical retrieve after an append), alternately against `main` before this step:

| Run | retrieve p50 / p95 ms |
|---|---:|
| branch 1 | 9.49 / 43.1 |
| main 1 | 9.18 / 43.4 |
| branch 2 | 9.38 / 46.3 |
| main 2 | 9.77 / 46.8 |

Within the +5 ms bound (run-to-run noise). That benchmark has no facts; the cast itself, over 15,000 synthetic
facts with 40 characters and knowledge marks on a fifth of them, takes 1.77 ms p50 (one pass over the rows),
plus one indexed query for the current turn.

## Limits

The packets were checked for layout, not for what a model does with them. A secret whose reveal the extraction
missed stays in Private, marked hidden. The cast is read from extracted turns and names: a character present
but neither acting in the last two turns nor named is not in it.
