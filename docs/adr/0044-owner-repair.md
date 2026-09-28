# 0044 — The owner repairs memory: owner input found by what it says

Status: accepted, 2026-09-28; revised the same day after the step's Codex review (AGENTS.md §14): repairs became
events of their turn in the folds, matching compares counterparts and a secret's head, and every kind stores its turn.
Phase 13 step 3 (`docs/phases/PHASE-13.md`, Q1–Q5, Q7). Migration 0024. Threads and
secrets in this step; facts and names follow in step 4 under the same rules. Amends ADR 0019 and ADR 0039 (a thread
can be closed or reopened by the owner), ADR 0033 (a secret can be marked found out, or kept, by the owner) and ADR
0027 (a line a repair changed names the repair in its provenance).

## Context

Memory can be wrong in ways the story never fixes. On the owner's longest chat 50 of 59 open threads ended in the
story without a turn saying so in words extraction matched (K23), and every one of the 40 M0 packets carried at least
one of them. Six secrets were found out in the story with no reveal matching them (the K29 family), and they kept
`<Story>` out of every secret-gate scene (`docs/perf/repair.md`). Until now the owner could join two names (ADR 0025),
extract history again, rebuild or delete.

Two constraints shape a fix. Raw evidence and derived rows are never edited (invariants 1, 2): a fix must be input,
applied at read time, like the owner's name joins. And an assertion id is not stable: a rebuild or a new extractor
generation makes new rows for the same turn, often in other words, so a fix keyed by id would be lost.

## Decision

1. **Owner input.** Table `owner_repair` (migration 0024): the chat, the kind, the target, the value, an optional note,
   `created_at` and `removed_at`. Kinds: `thread_close`, `thread_reopen`, `secret_found_out`, `secret_keep` (this
   step), and `fact_retract`, `fact_correct`, `name_split` (step 4; the API refuses them until then). A rebuild keeps
   it; undo sets `removed_at` and keeps the row; deleting the chat deletes it (ADR 0009).
2. **A target is what the item says.** For a thread: its turn, the turn's hash (ADR 0008), its kind, maker,
   counterpart and text. For a secret: its turn, the turn's hash, its head (subject, predicate and object), its
   holders and its text. The read applies a repair to the one item of the same turn, while that turn's hash is unchanged, of the
   same kind and maker (the same entity, ADR 0012) — for a promise or a debt the same counterpart too, as a
   restatement must have — or, for a secret, of the same head, whose text is closest and at least as close as a thread
   match (`MATCH_MIN`, ADR 0019). Two items equally close match nothing, and the API refuses a repair of an item it
   cannot tell apart from another. A new generation that words the item differently still matches it; an edit of the
   turn does not (as reveals after ADR 0033 amendment 2). A repair that matches nothing does nothing and is shown as
   such.
   - The assertion query now carries every row's turn hash, not only a possible secret's.
3. **What each does.**
   - `thread_close`: the thread's status becomes the outcome the owner chose (a promise `kept` or `broken`; otherwise
     one of the `resolved` outcomes, ADR 0039), closed at a turn, with the owner as its closer.
   - `thread_reopen`: a thread the story closed, by a wrong match or too early, is open again.
   - `secret_found_out`: the secret ends for that character at a turn, as a reveal would (ADR 0033): the fact no longer
     lists them in `hidden_from`, and counts them as knowing it for the scene, strict mode, a narrator and summaries.
   - `secret_keep`: a reveal the story made by mistake no longer ends the secret for that character.
4. **The owner wins, until the story says something new** (Q4). A repair takes effect at a turn (by default the chat's
   last turn when it was made; never before the item's turn, or before the story's close or reveal it undoes). It is an
   event of the thread or secret fold after every row of that turn, so later rows see it: the same aim stated again
   after an owner's close opens a new thread, a close after an owner's reopen closes it, and a reveal after an owner's
   keep ends the secret. A read of the head as of an earlier turn does not apply it. Repairs of one turn apply in the
   order they were made.
5. **Replays** (ADR 0027): a read as of an earlier time sees only the repairs in force then, so a recorded packet
   replays as it was. A packet line a repair changed — a thread, or a fact, claim or thread of a secret the owner
   marked — carries it in its ledger provenance (`ref.repair`), as a line carries its assertion.
6. **API.** `GET /v1/conversations/{id}/threads` and `…/secrets` list the items with the `id` a repair names.
   `POST /v1/conversations/{id}/repairs` takes `kind`, `item` (that id), and `outcome`, `character`, `turn`, `note` as
   the kind needs; it checks the item against the current memory and answers 422 with the reason when the repair
   cannot be made (no such item, already closed, not kept from that character, a turn outside the item's turn and the
   chat's last turn). The repair stores the target, not the id. `GET …/repairs` lists every repair, newest first, with
   the item each in force applies to now; `POST …/repairs/{repair}/remove` takes one back.
7. **Inspector.** A "Repairs" section per chat (each repair, what it targets, what it sets, when, and whether it is
   applied, matches nothing now, or was taken back); threads the owner closed and secrets the owner marked say so. The
   buttons are the panel's, in step 5; the Inspector HTML stays read-only (H15).

## Consequences

- One repair fixes an item for good: through edits elsewhere in the chat, rebuilds and new generations, with no model
  call. The owner's lists on the restored copy can be applied as repairs and measured (step 6).
- A repair can match nothing: after an edit of its turn, or a generation that words the item past the thread match.
  It is listed, not lost, and the owner can make it again on the new item.
- A closed thread leaves the threads section and `<Cast>`; the raw turn that states it can still come back as an
  excerpt (invariant 1: raw text is evidence, never repaired).
- The owner can close a thread that is not over, or mark a secret found out that is not. Each repair is visible,
  undoable and audited; nothing is deleted.
