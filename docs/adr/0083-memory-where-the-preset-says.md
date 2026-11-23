# 0083 — Memory where the preset says, and old dialogue left out in steps (plugin)

Status: accepted, 2026-11-23, PHASE-60 (S1, S2.2, S2.3). Amends D2 ("trimming host history from inside the plugin is a
later, opt-in feature": this is it), D3 (what counts as in context) and ADR 0001 (placement). No migration.

## Context

The plugin places the packet before the latest user turn, or at the end. `end` lands after a prefill and breaks it.
A preset or lorebook author cannot choose the place. And a long chat sends dialogue memory already holds; a cut that
moves every turn would also defeat the provider's prompt cache, which keys on the prompt's prefix.

## Decision

1. **A marker names the place.** `[NMOS.memory]` in any outgoing message is replaced, first occurrence only, by the
   packet; every other occurrence is removed. Removal happens on every path out of `beforeRequest`, including
   failure and requests memory skips, because a leaked marker is worse than no memory. It is a pure function of the
   prompt and the packet.
2. **Idempotence is by content, not by role.** `hasPacket` recognises only a system message (a reply quoting the tag
   must not stop memory). A marker may sit in a message of any role, so a retry (H2) is recognised by the prompt
   already holding the exact packet text being placed.
3. **Analysis reads the host's prompt; only the returned copy changes.** Canon observation, the turn index and the
   in-context ids are computed on the prompt as the host sent it.
4. **`end` means before a trailing prefill.** And whenever the packet lands after the user's turn, one fixed line
   after the packet says the turn already happened and outranks background memory; the plugin lowers the budget it
   asks for by that line's reserve, so D2 holds for the whole message.
5. **The sidecar decides the cut; the plugin only applies it.** The plugin has no turn numbers and no knowledge of
   coverage. It sends `keep_recent_turns` and `step`; the sidecar answers with the first message to keep, moved down
   to what extraction **and** a scene summary cover, quantized to `step` so the prefix is stable for `step` turns.
6. **Recall is told the truth about the prompt.** The sidecar removes the cut messages from the in-context set before
   recall and records the effective set, so their evidence can be excerpted and a replay is exact. If the plugin
   then cannot apply the cut safely it drops nothing; the cost is some text sent twice, never text lost.
7. **Dropping is conservative.** Only whole prompt messages that each carry one host message, in one contiguous run
   before the boundary, of role `user` or `assistant`; never the latest user turn or after. Anything else is `format`:
   nothing dropped, reason shown. The host chat is never written (`setChatToIndex` stays forbidden).

## Consequences

- A preset that merges the chat into one message gets no trimming.
- Trimming needs summaries on; without them nothing is cut (`no_summaries`).
- The kept window swings between `keep_recent_turns` and `keep_recent_turns + step − 1` turns: the price of a prefix
  that holds still.
- The marker in a lorebook entry is canon text like the rest of the entry; the normalizer is unchanged, so no
  generation moves.
