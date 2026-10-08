# 0071 — A status window over time (`packet-v17`, status flags)

Status: proposed 2026-10-08 (`docs/phases/PHASE-39.md` Q3–Q5, decided by the owner as proposed; AGE-43). Adds the
policy `packet-v17` on top of `packet-v16`, not the default; adds the owner repair kind `state_dismiss` (migration
0029). No prompt or generation key changes; the parser observations are unchanged (a rule's `watch` does not change
the rules' version).

## Context

Since Phase 1 NMOS reads status windows deterministically (D10) and recalls each key's latest value when its message has
left the prompt. Game-like cards keep a game's numbers in a bar the model rewrites each turn; NMOS kept only the latest
value, so it could not say when something changed, and it never noticed the bar changing what the story did not.

## Decision

1. **One history.** `state.history` reads every value of every key along the head's membership with
   `current_state`'s filters (accepted, active, visible; D8), oldest first, a value the next bar restates folded into
   one entry. The Inspector's lanes, the recall line and the flags all read it.
2. **The Inspector** draws it on the conversation page with PHASE-32's timeline renderer (`timeline.py`): a lane per key,
   keys that never changed folded. The panel asks for it with `status=lazy` and loads `part=status` when its section
   opens; its markup is inside the sanitizer's existing rules.
3. **`packet-v17`** (`packet.STATE_HISTORY_POLICIES`): a message that names a status key (as the bar writes it, or a word
   of its `retrieval.STATUS_WORDS` group) and asks about change (`retrieval.STATE_CHANGE_CUE`) gets, first in
   `<State>`, one `<StateHistory key>` line per key named (at most `STATE_HISTORY_KEYS`, 2): the last
   `STATE_HISTORY_MAX` (6) values with their turns. It is required (ADR 0068's labels): the message asked for it. It
   includes values whose bar is still in the prompt: the line is the sequence. A message without both a key and a cue
   gets the same packet as under `packet-v16`.
4. **Flags** (`statewatch.py`): a rule's `watch` keys are compared bar to bar; an item that appears in or leaves a list,
   or a number that moves while the value's words stay, is flagged when the reply's prose (the reply without what the
   rules read) names neither it, nor the key, nor (for a number) the new value or the difference, Korean amounts
   included; a value back to the one two bars before on a rerolled, swiped or edited reply is flagged unless the prose
   names it. Nothing is stored: a flag is named by what it says (`flag_id`). Its dismissal is an owner repair
   (`state_dismiss`, ADR 0044), which no memory read applies; the Inspector leaves a dismissed flag out, and an undo
   brings it back.

## Consequences

- The replay of the trial install's 67 recorded requests under the rules as saved there changes none
  (`docs/perf/phase39-history.md`); a question about a key's changes costs 40 to 100 tokens for a number and about 400
  for six inventories.
- On the owner's two game-like chats, watching inventory and equipment raised 5 flags in 23 replies, each an item the
  story never named; the first rules raised 7 more that were not changes without a cause, which shaped the rules
  above (`docs/perf/phase39-flags.md`).
- Migration 0029 only widens `owner_repair`'s kind check; an archive made at 0028 restores and is migrated as before.
- Whether `packet-v17` becomes the default, and which keys the owner's install watches, are the owner's choices.
