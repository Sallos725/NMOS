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

## Step 4 — facts and names (2026-09-28)

8. **Facts.** A fact repair's target is the assertion's turn, the turn's hash, its predicate, source, subject and
   object (as entities) and its line. It is applied to the head's assertions before the folds, in the order repairs
   were made, and matched against the same assertions the API checked it against (`assertions` in the memory view),
   so a target the API accepted is never silently ambiguous.
   - `fact_retract`: the assertion is left out, whatever generation extracts it again, so the version before it is
     current again; that version's packet line names the repair.
   - `fact_correct` (a new object, a new value, or both): an owner's version of the fact. At the fact's own turn, or
     for a fact that accumulates (a trait, an event), it replaces the assertion in place, with its position and turn
     hash, so the turn's other repairs (a secret found out) still find it. From a later turn it is a version at the end
     of that turn, which supersedes the fact from there, and a later statement of the story supersedes it (Q4). Its
     entities are resolved again. The API refuses a new object from a later turn when it changes what the fact is about
     (a relationship's pair, an item's whereabouts): both would stay current; the owner corrects it at its own turn or
     retracts it. An owner's version cannot itself be repaired: the owner takes the repair back.
9. **Names (K8).** `name_split` says two names of one type are not one entity. Resolution drops the story's aliases
   that join them directly. When they are still one entity — the owner's own join through another name, or aliases
   resolution accepts — the repair lists the names that still join them, over exactly the joins resolution made. Of an
   owner join (ADR 0025) and a split of the same two names, the newer holds. Extraction's entity hints use the splits,
   as they use the joins.

The step's Codex review found seven defects, all confirmed and fixed before merge: corrections cleared the turn hash a
secret repair needed, kept the old object's entities, took an earlier turn's position, could leave two pairs current,
were validated against other candidates than the read used; a split's explanation could name a join resolution had
refused; a retraction's restored version did not name the repair.

## Step 6 — measured (2026-09-28)

10. **Cost.** A read applies the fact repairs to the rows of their turns only and builds the result once, and fetches
    its conversation, the repairs in force and its last turn in one query (`docs/perf/repair.md`). With 100 fact repairs
    at 10,000 messages a retrieve is +7.0 ms p50 over Phase 12 `main` (+1.7 with none); the criterion was +5, and the
    owner accepted the miss.
11. **The secret gate** judges a scene by the owner's decisions: the words of a secret the character found out by the
    scene (in the story or by a repair) are told, not forbidden (owner, 2026-09-28; `tools/eval_secret_gate.py`).

## Consequences

- One repair fixes an item for good: through edits elsewhere in the chat, rebuilds and new generations, with no model
  call. The owner's lists on the restored copy can be applied as repairs and measured (step 6).
- A repair can match nothing: after an edit of its turn, or a generation that words the item past the thread match.
  It is listed, not lost, and the owner can make it again on the new item.
- A closed thread leaves the threads section and `<Cast>`; the raw turn that states it can still come back as an
  excerpt (invariant 1: raw text is evidence, never repaired).
- The owner can close a thread that is not over, or mark a secret found out that is not. Each repair is visible,
  undoable and audited; nothing is deleted.

## Amendment (2026-10-01, Phase 20, ADR 0055)

A name split and its undo are previewed like a join (ADR 0055); `expect` on the split and on its removal checks the
preview's fingerprint. Other repair kinds have no preview.
