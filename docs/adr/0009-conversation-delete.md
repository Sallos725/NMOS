# 0009 — Deleting a conversation

Status: accepted, 2026-09-23 (owner). Amends invariant 1; adds D23.

## Context

A chat can be deleted in PocketRisu, but NMOS kept everything it had recorded for that chat and
listed it in the Inspector forever. NMOS cannot notice the deletion itself: no plugin hook fires on
delete (H10), and NMOS never reads chats on its own (D22).

Invariant 1 says raw evidence is never destroyed, and migration 0001 enforces it: a trigger refuses
every `DELETE` on `source_revision`. The owner was offered two options:

- **Hide.** Keep the data, drop it from the list. The invariant stays as it is. Nothing is freed,
  and generating in that chat again brings it back.
- **Delete.** Remove everything recorded for the chat. It cannot be undone.

The owner chose delete.

## Decision

1. **Invariant 1 is amended.** NMOS itself never destroys raw evidence: not reconciliation, compilation,
   retention or any automatic process. Only the owner can delete one whole conversation, and only
   through an explicit request.
2. **One action, whole conversation.** `POST /v1/conversations/{id}/delete` deletes the
   conversation and every row that belongs to it in one transaction: host observations, source
   objects and revisions, commits, membership, normalized text, state observations, extractions and
   assertions (discarded ones included), embeddings, retrieval traces and jobs. The response counts
   the deleted rows. Single messages or ranges are not deletable. Removing them from the chat in the
   host already takes them out of every packet (invariant 7, ADR 0008 §5).
3. **The guard stays in the database.** Migration 0012 lets the `source_revision` delete trigger
   pass only for rows of the conversation named by `nmos.delete_conversation`. The delete sets this
   with `set_config(..., true)`, so it lasts only for its own transaction. Any other `DELETE` is
   refused as before.
4. **Concurrency.** The delete locks the conversation row first, as sync does. A sync that arrives
   during the delete waits, then records the chat as new. A worker whose model call is in flight
   fails on its first write (the revision is gone), and the failure is not retried because its job
   row is gone.
5. **Branches keep their origin refs.** A branch's `branched_from_conversation_id` is cleared. Its
   `branched_from_host_chat_ref` and message ref stay, like a branch whose origin NMOS never saw
   (D14).
6. **If the host chat still exists**, the next generation in it syncs it as a new chat: an import
   commit, first-sight backfill only (D22). Older turns can be extracted again with "extract all
   history".
7. **UI.** A **대화 삭제 / Delete conversation** button on a conversation page in the panel's Inspector
   tab. It takes two clicks, like rebuild, and the button turns red. After the delete the panel returns
   to the list. The standalone browser Inspector stays read-only.
8. **The plugin forgets cached packets** after any successful panel action other than a read. Its
   packet cache (10 min, keyed by exact chat state) would otherwise serve the deleted chat's memory
   to a reroll of an unchanged chat. The same applied to a rebuild or a settings save before this ADR.

## Consequences

- A delete cannot be undone. The panel says so before the second click.
- Deleting runs a foreign-key check for every row it removes. Migration 0012 adds indexes on the
  referencing columns that had none (extraction by revision, assertion by extraction, membership by
  revision, state by revision, lineage parent, commit by observation, trace by commit). Measured on
  one machine with a second chat of the same size in the database (`docs/perf/scale.md`): 25,000
  messages delete in 1.8 s instead of growing quadratically (5,000 messages took 5.3 s without the
  indexes). Sync-path timings at 10,000 messages are within run-to-run noise.
- Checked in the real UI (PocketRisu v1.12.0, isolated instance, 2026-09-23), with the plugin routing
  directly and through the PocketRisu server: the button needs two clicks, and one armed button
  disarms the other. The sidecar deleted 15 and then 17 messages' rows. The panel returned to an
  empty list, and the next message in the same chat recorded it again as a new conversation (an
  import commit).
- Nothing records that a delete happened except the sidecar log line (`deleted conversation=…
  rows=…`), which has no content.
- O5 (retention of abandoned worldlines, observations and old generations) stays open. This ADR only
  covers the owner deleting one conversation.
