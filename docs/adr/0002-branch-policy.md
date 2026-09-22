# 0002 — Cross-chat branch policy (resolves O4)

Status: accepted by owner, 2026-09-22.

## Context

Branching (H5, HOST-FACTS Q4) creates a new chat, reissues every message id, and appends
`{{specialcomment::branchedfrom::<origin chat.id>::<origin name>::<branch-point chatId>::}}`
as a disabled comment message.

## Decision

A branch is a **new conversation**. On its first reconciliation the sidecar parses the marker
and records:

- `branched_from_host_chat_ref` — origin `chat.id` (always, even if NMOS never saw the origin);
- `branched_from_conversation_id` — the NMOS conversation for that chat id, if one exists;
- `branched_from_message_ref` — the origin branch-point message `chatId`.

The branch gets its own ledger; its copied prefix is ingested as ordinary revisions. No
cross-conversation revision linking is performed.

## Consequences

- Recall inside a branch covers only the branch's own ledger (which already contains the copied
  prefix), so nothing from the origin's post-branch history can leak in.
- Duplicate storage of the copied prefix is accepted.
- Linking prefixes to origin revisions stays possible later from the recorded refs.
