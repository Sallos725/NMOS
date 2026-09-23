# 0008 — Extraction per turn, history backfill and memory rebuild

Status: accepted, 2026-09-23 (owner). Revises D7 and D17; adds D22.

## Context

Up to beta.7 every accepted message was extracted on its own (D7): the target message plus the
previous `K = 6` active messages. That has three costs:

- **Two calls per exchange.** A user message and the reply to it are two jobs. Each sends the same
  previous six messages, so context tokens overlap heavily.
- **User messages are compiled before their outcome.** A user message is accepted as soon as it
  arrives, so "I pick up the sword" is compiled before the reply says whether that happened. A
  refused or failed action can become a fact.
- **Windows don't follow the story.** A six-message window can start in the middle of an exchange.

In PocketRisu, role-play is an alternation of user input and character reply. The unit the owner
reasons about is the **turn**, not the message.

Two related gaps came up in the same review:

- Only the latest `NMOS_EXTRACT_BACKFILL` messages of a chat are extracted when NMOS first sees it.
  Raising the setting later did nothing until the sidecar restarted, and there was no way to ask for
  the rest of one chat.
- There was no way to redo a chat's semantic memory ("reboot") after a bad extraction run or a large
  manual cleanup of the chat.

## Decision

### 1. Turns

A **turn** is a maximal run of user messages followed by the maximal run of non-user messages that
answers it. It is computed over head membership, in order, from these members only:

- not a comment (`isComment`);
- not disabled (`disabled` is `true` / `"true"`);
- after the last `allBefore` cut. The cut message and everything before it are inactive (D15), so
  they can't be part of any turn or context.

Messages before the first user message (the greeting) form turn 0. The **anchor** of a turn is its
last non-user message. A turn with no reply yet (the chat's tail user message) has no anchor, and
nothing is extracted from it.

`active_membership` stores `turn` (index in the head, `NULL` for non-members) and `turn_hash`
(anchor rows only): SHA-256 over the revision hashes of the turn's members and the members of the
previous `K` turns (`NMOS_EXTRACT_TURNS`, default 3). The per-message `window_hash` stays as it was,
so facts of generations compiled before this change stay readable while such a generation is still
active (e.g. extraction switched off).

### 2. One extraction per turn

- A turn is extracted **once**, when its anchor is accepted: when the user continues from the reply
  (D5 unchanged). Rerolls and swipes still cost nothing until then.
- Job and extraction are keyed by `(anchor revision, turn_hash, extractor generation)`, reusing the
  `window_hash` column of `extraction` and the job payload. Assertions point at the anchor revision.
  The extraction row records the member revision ids of the turn (`extraction.members`), so
  provenance still reaches every source revision (invariant 10).
- The model sees the previous `K` turns as CONTEXT and all messages of the turn as TARGET, each
  message capped as before (6,000 target / 2,000 context normalized chars). The prompt says that
  when the reply contradicts, refuses or changes what the user message attempts or claims, the reply
  decides what happened.
- Invalidation (D8) is the same mechanism at turn granularity. An edit, delete, swipe or disable
  inside turn `t` changes the hashes of turns `t … t+K`. Those extractions stop matching immediately
  and are re-queued. When a second reply is appended to the last turn, that turn's anchor moves to
  the new message. The membership rows of the last turn are rewritten in place (append path), since
  membership is derived.
- A fact's `turn` in the packet and Inspector is the turn index. Ordering and supersession still use
  the anchor's position.
- The extractor generation spec gains `unit: "turn"` and `context_turns`, and drops the message
  `window`. `COMPILER_VERSION` becomes `extract-v4`. Upgrading therefore activates a new generation.
  Under the ADR 0006 coverage policy, the latest backfill of each chat is re-extracted first, then
  every older turn that an earlier generation had covered. Until then the Inspector shows partial
  coverage.

### 3. Backfill counts turns, and applies without a restart

- `NMOS_EXTRACT_BACKFILL` (panel: "처음 연결 시 처리할 턴 수") counts **turns**. The default stays
  100, which is about 200 messages for the same number of calls as before.
- Saving a different extraction or embedding backfill in the panel schedules the missing work at
  once. The coverage policy is idempotent, so a restart is no longer needed.

### 4. Per-chat actions (D22)

Two actions per conversation, sidecar API plus buttons in the panel's Inspector tab. The standalone
browser Inspector stays read-only.

- **Extract all history** — `POST /v1/conversations/{id}/extract-history`. Queues every turn of
  the head that the active extractor generation has not compiled, and every message that the active
  embedding projection has not embedded, regardless of backfill. It runs at background priority, so
  live turns go first.
- **Rebuild memory** — `POST /v1/conversations/{id}/rebuild`. Marks this chat's extractions of the
  active generation as discarded (`extraction.discarded_at`; the rows stay for audit), then
  re-queues every turn of the head, the recent backfill first. Facts disappear until they are
  re-extracted. The Inspector shows partial coverage meanwhile. Embeddings depend on content only
  and are not redone. Raw evidence, state observations and membership are untouched (invariant 1).

Both actions exist only for chats NMOS has already seen. **NMOS never ingests a chat by itself.** A
chat enters the ledger only when the user generates in it with the plugin enabled. Chats that were
never opened after installation are not read. This is cheaper, it matches consent, and it avoids
PocketRisu's lazily loaded chat content, which can produce empty or partial snapshots
(HOST-FACTS §3-7).

### 5. Mass deletion

No new mechanism. Deleting any number of messages ("delete all below") is a reconciliation that
removes members from the head. Facts and recall read head membership only, so the deleted range's
facts are gone from the next packet (invariant 7). Earlier fact versions become current again.
Deleting the tail needs no re-extraction. Deleting in the middle re-extracts the next `K` turns.
Deleted revisions stay in the ledger. If they come back (for example, a later full snapshot that
contains them again), their extractions match again and are reused without model calls. A truncated
snapshot is therefore recoverable, and NMOS doesn't try to tell it apart from a real deletion:
ignoring a real deletion would violate invariant 7. The Inspector lists each commit's changes by kind
and count (for example `delete ×12`).

## Consequences

- Measured on one synthetic Korean chat with a reasoning model (`docs/perf/turn-extraction.md`):
  41 % fewer calls, 37 % fewer prompt tokens, 19 % more completion tokens, 9 % fewer tokens overall.
  The per-message run kept two false facts from refused user actions; the per-turn run did not.
- Sync path: up to about 7 % slower at 5,000 messages (`docs/perf/scale.md`).
- Facts are only as fresh as the last accepted turn, as they already were for replies. A user
  message's facts wait for the reply and the next user message.
- Upgrading re-extracts previously covered history once, at the provider's cost, as any generation
  change does (ADR 0006).
- `NMOS_EXTRACT_WINDOW` affects only the per-message window hash that pre-turn generations read. It
  no longer changes what is extracted.
