# 0080 — Needs attention in bulk, and a conflict corrected where it is shown

Status: accepted, 2026-11-08, PHASE-57 B1 and B2 (owner's Q2 and Q3 of 2026-11-08) and the spec's amendment 1.
Amends ADR 0044 (owner repairs: one at a time) and ADR 0047 item 3 (a canon conflict's choices). Migration `0034`.

## Context

Each row of **Needs attention** had its own repair button, and `POST /v1/conversations/{id}/repairs` took one repair:
a chat with forty dropped facts after a re-extraction took forty presses. A conflict could be locked, retracted or
undone, but not corrected: `fact_correct` was offered in the facts list only, and refused a canon fact the story had
superseded.

## Decision

1. **Each row says what Apply and Retract send.** `inspector._bulk` marks a row with `data-bulk`: its kind (`g`), the
   kind's label, and the request each action sends, a repair or `{"undo": id}`. Apply is the row's offered action (a
   stale thread closed with its kind's default ending, a dropped fact or a held role ending restored, a canon conflict
   kept as canon's, a status flag dismissed); Retract retracts the row's fact (a role ending applied automatically, the
   story's side of a story conflict or the undo of the owner's correction there, canon's side of a canon conflict, the
   undo of a repair that matches nothing). The panel reads the marks; it decides nothing about them.
2. **One batch, all or none.** `POST /v1/conversations/{id}/repairs/batch` (`items`, `undo`, `preview`; at most 200
   each) plans every item with `repairs.plan` against one read of the chat's memory (`repair_view`), and writes them in
   one transaction with one `batch_id`, or, with any item refused, writes nothing and answers 422 with each item's
   error. A preview returns the same plan and writes nothing. The same repair twice is refused.
3. **What needs its preview stays one at a time.** A name split, a "not a character" and their undos, and a held
   alias's join (an entity link that re-extracts the joined turns) are never in a batch: their rows carry no mark and
   the batch refuses them.
4. **Undone together or alone.** `POST .../repairs/batch/{batch_id}/remove` takes back every repair of the batch still
   in force; the repairs table shows each batch as one line with **Undo all**, and each repair keeps its own undo.
5. **A conflict's statements are corrected from their row.** Both statements of a conflict get **Correct** for each
   field `_corrections` allows. The story's is an ordinary `fact_correct`. Canon's is a `fact_correct` of the canon fact
   with `lock: true`: the correction and a lock on it in one transaction, so the corrected canon stays current against
   the story's later statement. Without the lock the story's statement would supersede the correction at once and the
   row would leave while the two still disagreed. `_plan_fact` now finds a superseded canon fact for a correction too.

## Consequences

- A queue of the same kind is settled in two presses (select all, apply) and a confirmation of the preview.
- A batch is ordinary repairs: rebuilds, new generations and replays treat them as they treat one repair (ADR 0044).
- A held alias still needs one press and its preview per row.
- Correcting canon's side of a conflict is "keep canon's, as corrected"; keeping the story's is still a retraction of
  canon's statement, and correcting the story's statement to agree takes the row away.
