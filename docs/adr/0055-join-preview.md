# 0055 — A join, a split or an undo is shown before it is made

Status: accepted, 2026-10-01 (Phase 20, `docs/phases/PHASE-20.md`; C7 of `docs/proposals/IDEA-SURVEY-2026-09-29.md`).
Amends ADR 0025 (a join applied at once) and ADR 0044 item 9 (a split applied at once).

## Context

The owner joins two names (ADR 0025) and splits two names the story joined (ADR 0044). Both are read-time: they
change nothing stored, and every read resolves the chat with the links and splits in force. But a join changes what
memory says about both names, and it did so without a word. On the restored copies of the owner's two measured chats
(PHASE-20, "Evidence"), four of the owner's seven joins changed none of the counts and two left one current fact fewer:
a fact of one name replaced by a fact of the other, in the story's order, shown nowhere.

## Decision

1. **The preview is a difference of two reads.** `memory_view(..., what_if=...)` reads the chat as it would be with
   a link or a split added (a row as it would be stored, `created_at` now) or one taken back; `preview.diff` compares
   it with the read as it is. Nothing is written, no model is called, the request path is untouched.
2. **What it lists (PHASE-20 Q1).** The entities of the two names before and after; current facts that stop being
   current (`fact_replaced` by a different value of the same version, `fact_merged` into the same value,
   `fact_ended` with no successor) or start being current (`fact_back`, with the version it takes over); a
   relationship or promise whose two sides become one entity (`self_relation`, `self_thread`; kept, Q6) or stop
   being one (`…_gone`); threads that change status, become another thread's restatement (`thread_merged`) or come
   back; secrets whose holders, kept-from or open names change (`secret`, flagged `kept_from_holder` when a
   character it is kept from now holds it, `kept_from_holder_gone` when no longer), merge or come back; repairs in
   force whose match changes; conflicts (disputed whereabouts, canon, locked) that appear or go; a join with the
   persona and its undo (`persona`, `persona_gone`); canon aliases that come or go with it. Every kind has its mirror,
   so an undo's preview is the join's read backwards. `changes` is false when the entities and every list are
   unchanged.
3. **Endpoints.** `POST /v1/conversations/{id}/entity-links/preview` (a join, the body of the join),
   `POST …/entity-links/{link}/remove/preview`, `POST …/repairs/preview` (`name_split` only; other kinds 422) and
   `POST …/repairs/{repair}/remove/preview` (a split's). Each answers `{action, changes, before, after, lines, counts,
   fingerprint}`, with the checks of the action itself (422, 404).
4. **The fingerprint (Q4).** A hash of the head, the owner links and repairs in force, the extractor and canon
   generations, the canon manifest the read used, and the preview's entities and lines. The join, a split and both
   removes accept it as `expect`; in the action's transaction the sidecar locks the chat's row (`FOR UPDATE`, as a
   sync does), reads the head under the lock, computes the preview again and answers 409 with the fresh preview when
   it differs, writing nothing. Without `expect` the endpoints behave as before.
5. **Re-extracting the turns a join covered (Q7).** `POST …/entity-links/{link}/reextract`, after the join is taken
   back (422 while it holds, or while the two names are one entity through the story or another link; 409 with
   extraction off): the head's turns whose serving extraction (the active generation first, then the most recently
   activated, as every read chooses) was made since the link's `created_at` and listed the two names as one entity in
   KNOWN ENTITIES (`extraction.hints`). No upper bound at the undo: a job the model was still answering stores its
   row later, and the next call finds it. Their extractions of every generation are discarded (kept for audit) and
   just those turns queued, as a rebuild does for a whole chat (D22); the undo's preview carries their count
   (`reextract.turns`). A second call finds nothing.
7. **A job made obsolete while the model answers stores nothing.** Before its row is written the worker locks its
   job and checks that it is still running under its own claim (`locked_at`); a rebuild, a re-extraction or a claim
   taken back after 10 minutes makes it store nothing, and `finish` ends only the claim that ran it. This closes the
   same gap for a whole-chat rebuild.
6. **No side is chosen (Q5).** The story's order decides which version holds, as it did; the preview says which.
   A wrong winner is repaired with ADR 0044's retraction or correction.

## Consequences

- A preview costs two memory reads (about 15 ms each on the 147-message restored chat).
- The fingerprint refuses an action after any new turn or extraction that changes the difference, and after any new
  head at all; the panel shows the fresh preview it gets with the 409.
- A sync, a join or a repair of the same chat waits for the checked action; the extraction worker does not take the
  chat's lock, so an extraction committed within the few milliseconds between the check and the write is not
  refused. Its rows are read at the next read like any other.
- A re-extraction is a new model call: it reads the names apart and the chat as it is now (so a turn may list
  entities its first extraction had not seen yet), and a real model may word its facts differently. Later turns keep
  their extractions, whose hints were built from the earlier rows (PHASE-20 Q7, kept by the owner); the chat's full
  rebuild re-reads everything.
