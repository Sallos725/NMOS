# 0060 — A repair whose item is gone suggests where it belongs now, and moves in one action

Status: accepted, 2026-10-01. Phase 26 step 2 (`docs/phases/PHASE-26.md` Q1–Q8, approved by the owner with an exception
to R7; AGE-23). Extends ADR 0044 (owner repair) and its amendment 2 (a repair finds a new generation's item by its
quote). Migration 0029; a new plugin build. No extractor, packet policy or recall option.

## Context

A repair stores what its item said, not its row id, and finds it again on every read by its turn, head and text, or by
its quote (ADR 0044 item 3, amendment 2). On the production copy re-extracted with `extract-v15`, 40 of the owner's 68
Phase 13 repairs apply and none is missed where its item is still quoted; 28 match nothing, and 19 of those have items
of the same head in the state the repair changes — some of them the repaired error, worded anew by the new generation.
Until now such a repair was only listed under "Needs attention" with its undo, and the owner had to find the item and
repair it again by hand after every new generation.

## Decision

1. **Candidates** (`repairs.candidates`, Q1, Q2). For a repair that matches nothing now, is not on an edited target
   turn and names an item — a thread close or reopen, a secret found out or kept, a fact retract or correct, a lock on
   a canon fact — the items of its head in the state it changes that no applied repair holds: open threads for a close,
   closed for a reopen (same kind and maker, and counterpart for a promise or a debt); secrets still kept from the
   repair's character for found out, over for keep (same predicate, subject and object); current story facts for a
   retract or correct, unlocked canon facts for a lock (same predicate, source and subject, and object where the object
   is part of the fact's slot: a per-object or multi-valued predicate). At most three, in a total order: a quote sharing
   a 12-character run with the target's stored quote first, then the higher text similarity, the nearer turn, the
   earlier turn and the text. No floor: the owner judges.
2. **Edited turns.** A memory read marks a repair that matches nothing on a turn whose hash differs from the target's
   (`edited`); it gets no candidates (ADR 0044 item 3). The extra lookup runs only when such a repair exists.
3. **The move** (Q3, Q5). `POST /v1/conversations/{id}/repairs/{repair_id}/move/preview` with `item` returns the
   difference (Phase 20's preview, `what_if` dropping the old repair and adding the moved one) and its fingerprint;
   `POST …/move` with `item` and `expect` checks the fingerprint under the chat's lock, plans the repair for the item as
   a new repair is planned (`repairs.plan_move` → `plan`, every check), takes the old repair back and stores the new one
   with `owner_repair.moved_from` naming it, in one transaction. Only a candidate can be the item. The effective turn
   stays the old one's when the item allows it, else becomes the earliest the item allows; never past the last turn.
   A lock on a moved correction is taken back and stored again naming the new correction, with its own `moved_from`.
   Undoing the moved repair takes it back like any repair; the one it moved from stays removed.
4. **Where** (Q4). The Inspector's "Needs attention" lists the candidates under the repair's row, each with
   "Apply here" (`data-repair="repair_move:<repair>:<item>"`); the panel previews and moves (a new plugin build; the
   panel's repair actions are a closed list). A preview that names no entity says "Memory stays as it is" when nothing
   changes.

## Consequences

- After a new extractor generation the owner moves an orphaned repair in two clicks (preview, confirm) instead of
  finding its item and repairing it again; nothing moves without the owner.
- `owner_repair` gains a nullable `moved_from`; archives carry it as any column (ADR 0050); a recorded request replays
  as it was across a move (a moved repair is a repair, read as of its `created_at` and `removed_at`).
- Found while testing: amendment 2's quote match takes the one item of the head whose quote shares a 12-character run
  with the target's. Two goals of one character whose quotes begin the same way (a stub's "Hana wants to …") share such
  a run, so a repair whose own goal lost its quote matched the other goal. Real prose rarely repeats twelve characters
  across two items of one head, and the match needs exactly one; it is recorded here, not changed in this phase.
- The owner's review of the 19 repairs with candidates on the copy, and the Inspector's latency, are step 3.
