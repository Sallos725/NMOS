# Phase 39 — Status windows NMOS holds

> **Status: approved 2026-10-08 (the owner: the parser rather than a documented limit; the history, the flags and the
> anchor as directions). Step 2 done (the parser and the guide). **In `0.4.0`** (the owner, 2026-10-08: steps 3–5 too);
> Q3–Q5 decided as proposed (the owner, 2026-10-08); steps 2–5 implemented and measured as recorded below; the default policy remains an owner decision. Watch setup approval was reaffirmed by the owner on 2026-10-09; applying it to the trial install is pending, not its approval.** A
> phase the owner pulled in (R7 allows owner exceptions): NMOS's deterministic state (Phase 1, D10) exists but is barely
> used.

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
| Q3 | History (step 3) | **Decided as proposed (the owner, 2026-10-08)**, in two parts. **3a (Inspector):** a "status window" section on the conversation page, drawn by the Phase 32 timeline renderer: one lane per key, a bar per value held, the value now beside it, keys that never changed folded; the panel shows it as it shows the timeline. From the observations NMOS keeps per revision, through the head's membership (D8), so a swipe or an edit shows the values of the path taken. **3b (recall):** a question naming a status key with a "when / how much / since" cue gets one `<StateHistory>` line of that key's last changes (turn → value, at most 6). 3b changes the packet: `packet-v17`, the default only after the owner sees its replay. Details below. |
| Q4 | Changes without a cause (step 4) | **Decided as proposed (the owner, 2026-10-08)**; measured and refined (details below): deterministic (no model call): a rule lists `watch` keys. Between two consecutive accepted bars, (i) an item added to or dropped from a list value (fields split on `/` or `,`), or (ii) a number in a watched value that changes, is flagged when the reply's prose outside the bar names neither the item nor the key; (iii) a watched value that goes back to an earlier value right after a reroll, a swipe or an edit is flagged too. Flags go to "Needs attention" with both bars and the turn; the owner dismisses them as other entries. Off until measured: false alarms counted read-only on the owner's two game-like chats (23 and 6 replies) and shown before it is on. |
| Q5 | The anchor (step 5) | **Decided: no packet change (the owner, 2026-10-08, as proposed).** Found 2026-10-08: mostly already the case. State lines are required lines, placed only when their message is no longer in the prompt (`retrieval.py`: `host_logical_id not in in_context`), and a reply waiting for the next turn is not state yet, so a reroll or a swipe already starts from the previous accepted bar. Read only, the host's request log of the owner's install shows both game-like cards keep their bars in the prompt the model receives (10 and 6 bars in recent requests; no display-only stripping). Step 5 is this record; 3b is the only packet change. |

## Steps 3–4 in detail

**One history for all three uses.** `state.history` reads every value of every key along the head's membership with
`current_state`'s filters (accepted, not disabled, after the last `allBefore`), in story order, and folds a value the
next bar restates into one entry (a bar repeats every field each turn). The Inspector draws it (3a), recall takes the
last changes of one key from it (3b), and the flags compare its neighbouring entries (4).

**3a, the Inspector.** The conversation page gets a "status window" section: one lane per key, a bar per value held
(from the turn its bar first said it to the turn before it changed), the value now beside the key, keys that never
changed folded under one line. Drawn by `timeline.py` in both forms; the panel's form uses only the markup its
sanitizer already keeps (no plugin change). Nothing here is read by recall.

**3b, recall (`packet-v17`).** A message that names a status key and asks about change (`HISTORY_CUE`, or 언제,
얼마나, 부터, 동안, 바뀌, 변화, 올랐, 늘었, 줄었, 떨어졌, when, since, how much, changed) gets, inside `<State>` and
before its items, one `<StateHistory key="…">` line per key it names (at most 2): that key's last changes, at most 6,
oldest first, each as its turn and value. A key is named as the bar writes it (two characters or more, case and
spacing aside, where a word starts: 마나 is not the 마나 of 얼마나), or by a word of its group in `STATUS_WORDS`: a
card's bar is often in English while its chat is in Korean ("Level", "레벨 언제 올랐어?"). The line is required, as
`<State>`'s items are (`packet-v14` labels): the message asked for it. It lists changes whose bar is still in the
prompt too: the line is the sequence, which the prompt shows only scattered across replies. A key named without such a
cue, or a chat without rules, changes nothing. Traced as its own kind (`state_history`). **Replayed 2026-10-08**
(`docs/perf/phase39-history.md`), read only: none of the 67 recorded requests changes; probes on both chats place the
line (40 to 100 tokens for a number, ≈400 for six inventories). The default moves only on the owner's word.

**4, the flags.** A rule may list `watch` keys (they do not change the rules' version: nothing is read again).
Between two neighbouring entries of a watched key's history, NMOS flags (i) an item added to or dropped from a list
value (split on `/`, `,` or `·`; "없음" is no item) that the reply's prose (the reply without what the rules read) does
not name; (ii) a number that changes, the value's words staying the same, where the prose names neither the key, nor
the new number (in digits or Korean words: "삼십만 원"), nor the difference; (iii) on a reply that was rerolled, swiped
or edited (its message holds swipes, as a reroll leaves it (H4), or has more than one revision), a value that goes back
to the one two bars before while the single bar between said otherwise, unless the prose names the key or the value.
A flag names the key, both values, the turn and the reason, in "Needs attention", with one action: dismiss
(`owner_repair` kind `state_dismiss`, migration 0029; undone like other repairs). A rule without `watch` flags
nothing. **Measured 2026-10-08** (`docs/perf/phase39-flags.md`), read only, every key watched: the first rules flagged
15 on the owner's two chats, 7 of them no change without a cause (a place's numbers, money in words, a revert the reply
names); as merged, card A's inventory and equipment keys raise 5 flags in 23 replies, each an item the story never
names, and its resources one borderline flag in 66 changes. The owner reaffirmed approval to set up `watch` on
2026-10-09; the trial snapshot still lacks it, so application remains pending.

**Found by the pre-0.4.0 audit (2026-10-08), fixed here:** a `block` rule whose start matches empty text looped
forever (refused now, and every block search moves forward); a restored chat got no state when the install already had
some (the next start reads message revisions with no current-rule state observation); a chat whose character name arrived
after its messages was not read by card-bound rules (read again when the name changes).
The 2026-10-09 follow-up found that normalized text could commit before parsing, or be filled by a worker, so its
presence was not a durable signal that parsing had finished. `state.sync_rules` now visits message revisions without
current-rule observations in 500-row keyset batches. It preserves positive observations and the caller's transaction;
no-match messages are visited once per startup because no parse-completion marker exists in this schema.

## Acceptance criteria (steps 3–4)

4. The history folds a restated value, follows a swipe or an edit through the head's membership, and leaves out a
   reply waiting for the next turn (tests).
5. The conversation page and the panel draw one lane per changed key and fold the rest; the panel's markup passes the
   plugin's sanitizer unchanged (tests).
6. Under `packet-v17` a question naming a key with a change cue gets one `<StateHistory>` line of at most 6 changes;
   without the cue, or under `packet-v16`, the packet is unchanged (tests); on the replay of the trial install no
   request without such a question changes (done 2026-10-08: 0 of 67).
7. Each flag (i)–(iii) fires on a synthetic bar and stays quiet when the prose names the change; a dismissed flag
   stays dismissed and comes back on undo; an archive made at schema `0028` restores into `0029` (tests). The false
   alarms on the owner's two chats are counted and shown before `watch` is set there (done 2026-10-08).

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
- Making `packet-v17` the default before the owner sees its replay; setting `watch` on the owner's install before the
  owner sees the count (watch setup was subsequently confirmed approved on 2026-10-09).

## Steps

1. This spec.
2. The parser options, their tests, the guide. **Done 2026-10-08.**
3. History (Q3): 3a the Inspector, 3b `packet-v17`: **done 2026-10-08**, opt-in.
4. Flags (Q4): **done 2026-10-08**. The owner reaffirmed watch setup approval on 2026-10-09. A read-only dump of the
   6113 trial install at 12:40 KST found neither of its two saved rules had a `watch` field; setup is not yet applied
   in that snapshot. This check did not change the running install.
5. The anchor (Q5): **done by record**
   (2026-10-08), no packet change.

## Acceptance criteria (step 2)

1. A one-line bar is read field by field with either separator form; a story's own bracket window is not read; a
   value with brackets inside stays whole (tests).
2. A card-bound rule reads only that card's chats, as bodies arrive and in a rebuild (test).
3. On the owner's trial install, read only and in memory: every status bar of the two game-like chats is read whole
   (23 of 23 replies with all 23 fields; 6 of 6 with all 9), and no key from the story's windows. Measured 2026-10-08
   with the guide's rule (`☆ \[` … `\]\s*$`, `separator` `|`).

## Risk

Low for step 2: a new optional rule field each; existing rules read as before (their tests unchanged), and a rule
change rewrites the observations as it always did (the rules' version changes). **High for steps 3–4:** step 4 adds a
migration (a repair kind; an older archive must still restore), 3b changes what recall places (a new policy, not the
default), and 3a adds markup to the panel (inside the sanitizer's existing rules).
