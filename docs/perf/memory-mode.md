# Per-chat memory mode and the default reserve — evidence

Date: 2026-09-27. Phase 10 step 5 (`docs/phases/PHASE-10.md`, ADR 0035). No model calls: the packets are built
by the sidecar's own functions on the restored copy of the owner's database (`extract-v12`, read-only), as in
`docs/perf/packet-v3.md`. Chat text is not quoted.

## 1. Deterministic cases (CI)

`tests/test_scene.py`: the narrator's filter (public, unmarked and own facts; the persona under any name), the
persona shown by the name the host reports in a withheld line, a private claim's marks in the Private section
only, and an end-to-end case through the API: strict mode replaces a secret with a Secret line and no Private
section; a narrator it is kept from gets neither the secret nor a Secret line, and an empty packet when they know
nothing relevant; the persona as narrator, a holder, gets it; the trace records the mode, and a strict request
replays with its own mode after the chat's mode changed.

## 2. The pilot's scenes under each mode (800-token budget)

Lines placed, and lines the mode left out or replaced. The narrator is either the persona or the mother, from
whom the scenes' secrets are kept.

| Scene (cast) | Default | Strict | Narrator: persona | Narrator: mother |
|---|---|---|---|---|
| Breakfast, turn 17 (mother, daughter, persona) | 9 placed, 8 private | 2 facts + 2 Secret lines; 13 withheld | 9 placed; 1 left out | 2 placed; 13 left out |
| Hug request, turn 52 (+ aunt) | 10 placed, 4 private | 8 + 2 Secret lines; 7 withheld | 10 placed; 1 left out | 8 placed; 7 left out |
| Hallway, turn 59 (+ aunt) | 11 placed, 3 private | 8 + 3 Secret lines; 7 withheld | 10 placed; 2 left out | 10 placed; 4 left out |

- **A claim carried the secret.** Before claims were marked private, strict mode on turn 17 still gave the
  daughter's plan word for word as her `<Claim>` (limited, kept from the mother); 133 of the copy's 303 valid
  claims are `limited`, 17 with `hidden_from`. Claims now go through the same rules as facts.
- **Strict mode is costly here.** Almost everything on the breakfast scene is known to the daughter and the
  persona only, so strict mode keeps 2 public facts. That is the pilot's B′, where holders forgot.
- **One Secret line per pair.** The same holders listed in another order ("persona, daughter" and "daughter,
  persona") were two lines until pairs were compared as sets.

## 3. The default reserve

The copy's recorded requests with memory lines (13; 9 from the owner's longest chat, 15 offered lines each)
were compiled again at other budgets, with their own options and extractor, as of their time:

| Budget | Memory lines placed (all 13) | Owner's chat (9 × 15) | Cut for budget |
|---|---:|---:|---:|
| 600 | 106 / 160 (66%) | 81 / 135 (60%) | 54 |
| 800 | 143 / 160 (89%) | 118 / 135 (87%) | 17 |
| 1000 | 159 / 160 (99%) | 134 / 135 (99%) | 1 |
| 1200 | 160 / 160 | 135 / 135 | 0 |

`packet-v3` places the same within one line. Where the room goes, on the owner's 9 requests at 1200 (every line
placed, 856 estimated tokens on average): the Note 183 (the rules for marks, claims, threads and Private), and of
about 700 in memory lines, 354 in tags and attributes. Placed lines repeat a value 24 times, mostly different
facts with the same value (both directions of a feeling); real restatements are fewer (`docs/perf/budget.md`).

The owner raised the default from 600 to 800 (D2 still applies: lower the host's max context by the reserve).
A chat as dense as the owner's places everything at 1000.

## 4. Real host (isolated PocketRisu v1.12.0)

The plugin built from this branch was installed over an earlier one on an isolated PocketRisu with stub models
(chat and extraction). With the budget argument empty, requests carried 800. The Inspector's chat page showed
the Memory mode card with the chat's characters; strict and a narrator saved, survived a refresh, and the next
request's trace recorded both (`strict: true`, the narrator) with the packet's Secret line and the narrator
Note. The card fits a 390 px wide screen.

That run found a gap: strict mode replaced the secret with a Secret line, then placed the chat message that told
the secret as an excerpt. Excerpts that say a withheld line's content are now left out (a case in
`tests/test_scene.py`); on the host the next request placed another excerpt instead and counted two withheld.

## Limits

Layout only; what response models do with each mode is step 7. The copy is one owner's chat, re-extracted once.
An excerpt that tells a withheld secret in other words than the fact's is still placed; so is one from a
scene the narrator was not in, when no withheld line matches it.
