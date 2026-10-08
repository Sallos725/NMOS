# Phase 39 — Status windows NMOS holds

> **Status: approved 2026-10-08 (the owner: the parser rather than a documented limit; the history, the flags and the
> anchor as directions). Step 2 done (the parser and the guide); steps 3–5 each get their questions answered before
> they start. **In `0.4.0`** (the owner, 2026-10-08: steps 3–5 too).** A phase the owner pulled in (R7 allows owner exceptions):
> NMOS's deterministic state (Phase 1, D10) exists but is barely used.

## Why now

Game-like cards end every reply with a status bar the model writes: level, points, items, money, place. The model
recomputes it each turn and gets it wrong in ways a ledger can see. NMOS has read status windows since Phase 1, but:

- **It cannot read the common form.** A `block` rule reads one `key: value` per line; a bar is one line of fields
  between a start and an end mark, split by `|`. A `regex` rule over the whole reply also reads the story's own
  bracket windows (messages, appraisals), which such cards use too.
- **It cannot be bound to a card.** Rules are one set for the install; a rule's `character` compares the message's
  internal speaker id, not a name a user can write.
- **Nothing uses what it reads beyond the latest value.** On the owner's trial install no rule was set and nothing was
  read; the latest bar is already in the prompt, so injecting it again adds little.

## Questions and answers

| | Question | Answer |
|---|---|---|
| Q1 | How are bars read? | **Decided: the parser, documented.** A `block` rule takes `separator`; the text between start and end is split by it and each field read as `key: value` or `key=value`, each cleaned on its own (a long bar keeps every field). A rule ending at `\]\s*$` keeps brackets inside a value. Detecting rules automatically is not done: cards differ (the owner); the guide shows how. |
| Q2 | How is a rule bound to a card? | **Decided: `card`, the chat's character name** (`conversation.host_character_name`, the name PocketRisu shows), exactly; without it a rule reads every chat. `character` is unchanged. |
| Q3 | History (step 3) | Proposed, in two parts. **3a (Inspector):** a "status window" section on the conversation page, drawn by the Phase 32 timeline renderer: one lane per key, a bar per value held, the value now beside it, keys that never changed folded; the panel shows it as it shows the timeline. From the observations NMOS keeps per revision, through the head's membership (D8), so a swipe or an edit shows the values of the path taken. **3b (recall):** a question naming a status key with a "when / how much / since" cue gets one `<StateHistory>` line of that key's last changes (turn → value, at most 6). 3b changes the packet (a new policy), so it goes with Q5's measurement. |
| Q4 | Changes without a cause (step 4) | Proposed, deterministic (no model call): a rule lists `watch` keys. Between two consecutive accepted bars, (i) an item added to or dropped from a list value (fields split on `/` or `,`), or (ii) a number in a watched value that changes, is flagged when the reply's prose outside the bar names neither the item nor the key; (iii) a watched value that goes back to an earlier value right after a reroll, a swipe or an edit is flagged too. Flags go to "Needs attention" with both bars and the turn; the owner dismisses them as other entries. Off until measured: false alarms counted read-only on the owner's two game-like chats (23 and 6 replies) and shown before it is on. |
| Q5 | The anchor (step 5) | **Found 2026-10-08: mostly already the case.** State lines are required lines, placed only when their message is no longer in the prompt (`retrieval.py`: `host_logical_id not in in_context`), and a reply waiting for the next turn is not state yet, so a reroll or a swipe already starts from the previous accepted bar. Read only, the host's request log of the owner's install shows both game-like cards keep their bars in the prompt the model receives (10 and 6 bars in recent requests; no display-only stripping). Proposed: no packet change for the anchor; record this, and add only 3b. |

## In scope (step 2)

- `apps/sidecar/src/nmos_sidecar/parsers.py`: `separator` on `block` rules, `card` on every rule, both checked.
- `apps/sidecar/src/nmos_sidecar/state.py`: the chat's character name for card rules, as each body is stored and in a
  rebuild.
- Tests (synthetic bars): field by field, both separators, a story bracket window left alone, a long bar, nested
  brackets, card binding through sync and a rebuild.
- `docs/guide.ko.md` ("한 줄짜리 상태창"), `config/parsers.example.json` (`status-bar`), CHANGELOG.

## Out of scope

- Detecting a card's rule automatically (Q1).
- Computing a game's numbers, or writing anything into PocketRisu (D1).
- Steps 3–5 until their questions are answered.

## Steps

1. This spec.
2. The parser options, their tests, the guide. **Done 2026-10-08.**
3. History (Q3). 4. Flags (Q4). 5. The anchor (Q5).

## Acceptance criteria (step 2)

1. A one-line bar is read field by field with either separator form; a story's own bracket window is not read; a
   value with brackets inside stays whole (tests).
2. A card-bound rule reads only that card's chats, as bodies arrive and in a rebuild (test).
3. On the owner's trial install, read only and in memory: every status bar of the two game-like chats is read whole
   (23 of 23 replies with all 23 fields; 6 of 6 with all 9), and no key from the story's windows. Measured 2026-10-08
   with the guide's rule (`☆ \[` … `\]\s*$`, `separator` `|`).

## Risk

Low for step 2: a new optional rule field each; existing rules read as before (their tests unchanged), and a rule
change rewrites the observations as it always did (the rules' version changes). Steps 3–5 are judged when specified
(step 4 writes to "Needs attention"; step 5 changes the packet).
