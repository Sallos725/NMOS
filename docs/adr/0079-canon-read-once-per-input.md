# 0079 — Canon read once per input, copied into each chat

Status: accepted, 2026-11-08, PHASE-57 A1 (owner, 2026-11-08: a cache; a rebuild re-reads its own chat only).
Amends ADR 0045's consequence ("a card shared by several chats is kept once per chat": still kept per chat, now read
once) and ADR 0047 item 1 (a read's jobs and a rebuild). Migration `0033`.

## Context

Canon is kept per conversation (ADR 0045), and `canonfacts.process` called the model for every part of every canon
revision a chat's extractions did not cover. A new chat with a bot already played paid for its card, persona and
always-active lorebook entries again, though the model saw the same input.

## Decision

1. **The input's fingerprint.** Each canon extraction records `coverage.input`: the fingerprint of the source line
   (`describe`: the text's kind, an entry's comment and keys), the part number and count, the part's text with the
   macros replaced, and the card's and the persona's names only when the text uses the macros (`wtag` is not `plain`).
   The generation key covers the rest of the call (version, prompt, predicates, normalizer, model settings, part size).
   `build_prompt` writes both names into every message; a chat already keeps a `plain` text's read when its persona is
   renamed (ADR 0047), so another chat's `plain` read is the same read.
2. **A match is copied.** Before a part is sent, the newest non-discarded extraction of the same canon generation with
   the same `input` on another revision (`reusable`, the index of migration `0033`) is copied into this revision: the
   same window, its assertions with their statuses, `raw` and `coverage.reused_from` naming the read it came from (the
   first read, for a copy of a copy), `usage` zero calls, written under the same job guard as a model answer.
   Copying keeps every chat's rows its own: repairs, locks, retractions, rebuilds and audit stay per chat.
3. **Only what recorded its input is a source.** Extractions from before migration `0033` recorded no input, and the
   normalizer may have changed since, so their fingerprint is not computed afterwards.
4. **A rebuild reads its own chat again.** Its canon jobs carry `fresh: true` (a revived job takes the new payload) and
   skip the lookup; no other chat's rows change, and later chats may copy the fresh read as the newest match.

## Consequences

- A second chat of one bot with the same persona makes no canon call for what the first read after the upgrade; one
  with another persona reads again the texts that use the name macros, and copies the rest.
- The same text under another description (a lorebook entry's keys or comment) is read again: its prompt differs.
- A read that was wrong stays in every chat that copied it until each is rebuilt.
- The Inspector's canon coverage counts copied parts (`reused`); model usage counts no call for them.
