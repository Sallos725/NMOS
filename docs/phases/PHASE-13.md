# Phase 13 — Verification and Repair, part 1 (Stage 6)

> **Status: approved 2026-09-28 (owner), in progress.** Stage 6 of `docs/ROADMAP-1.0.md` (original §20, §66–67; Track B,
> B7 and the B2 remainder), part 1 of 2: the owner repairs what memory got wrong, and a queue shows what needs a
> look. Canon sources and export/restore are part 2 (Q0). The owner chose Stage 6 next after Phase 12 (2026-09-28)
> and decided no release for now. The owner answered every question below with the recommended answer
> (2026-09-28), and chose to confirm a list NMOS drafts for step 2 rather than mark the threads from scratch.

## Questions and answers

| # | Question | Answer | Alternatives not taken |
|---|---|---|---|
| Q0 | One phase for Stage 6, or two? | **Two.** Phase 13: owner repair and a "needs attention" queue (closes K8 and K23). Phase 14: canon sources (character card, lorebook, persona, author's note), which need host evidence first, and export/restore. | One phase; canon first. |
| Q1 | What can the owner repair? | **Five kinds:** (1) close a thread (goal, question, threat, debt, promise) with an outcome, or reopen one the story closed by a wrong match; (2) retract a fact (it was never true: the earlier version is current again); (3) correct a fact's value from a turn on (a place, a condition, a relationship); (4) mark a secret found out by a character, or keep one the story ended by mistake; (5) split two names the story joined (K8). | Threads and splits only (the K23/K8 minimum); free edits of every field. |
| Q2 | How is a repair stored? | **As owner input, like the owner's name joins (ADR 0025):** a table `owner_repair` with the chat, the kind, the target as the Inspector showed it, the new value or outcome, the turn it takes effect, an optional note, `created_at` and `removed_at`. No assertion or message is ever edited (invariants 1, 2). A rebuild and a new extractor generation keep it; undo sets `removed_at`; deleting the chat deletes it (ADR 0009). | Repairs as assertions with `source = "owner"` (mixes owner input into derived rows); edits of derived rows (lost on rebuild). |
| Q3 | How does a repair find its target after a rebuild or a new generation? | **By what the target says, not by its row id:** the target's turn, the turn's hash while it reads as it did (ADR 0008; as reveals after ADR 0033 amendment 2), its predicate or thread kind, its subject and its text. On read a repair applies to the one current item of that turn whose head matches and whose text is closest, at the thread match (ADR 0019, `MATCH_MIN`). A repair that matches nothing now (its turn was edited or deleted, or a new generation worded the item too differently) stays stored, does nothing, and is listed in the queue (Q6). | Assertion ids (a new generation makes new rows: every repair would be lost); exact text only (lost on rewording). |
| Q4 | Who wins, the owner or the story? | **The owner, for what was repaired, until the story says something new.** A correction is a fact version from its turn on; a later turn that states the fact again supersedes it as usual. A closed thread stays closed; a later turn that opens the same thread again is a new thread. A retraction holds whatever generation extracts the fact again. A lock that no later turn can change is canon lock, Phase 14. | The owner's word is final forever (a lock now). |
| Q5 | Where does the owner repair? | **In the panel's Inspector tab**, as with name joins (ADR 0025): buttons on thread, fact, secret and name rows, a small form for a correction and its turn, undo on each, a per-chat "Repairs" list, and a bulk close for selected threads. The Inspector in a browser tab stays read-only (H15; the token would sit in its URLs, K21). | Forms in the browser Inspector; the API only. |
| Q6 | The conflict queue (roadmap Stage 6)? | **One "Needs attention" section per chat, from what NMOS already detects, each item with its repair:** disputed item whereabouts (ADR 0017); ends that matched no open thread (K23, the closing turn worded differently); repairs that match nothing now; ambiguous names; and threads open for more than 30 turns without a restatement (a suggestion to close, not a change). No new automatic outcomes. | Pending, conflicting and rejected outcomes in extraction (an extractor generation); a model that checks transitions (§57–59). |
| Q7 | Packet? | **No new packet policy.** A repair changes what is current, so the packet follows under `packet-v8`. A line a repair changed carries the repair in its ledger provenance (invariant 10); a replay reads repairs as of the request (their `created_at` and `removed_at`), so a recorded packet replays as it was (ADR 0027). | Mark owner-corrected lines in the packet text (a new policy). |
| Q8 | How is it measured? | **On the owner's longest chat (restored copy, read-only):** the owner marks which of its open threads are over and which secrets were found out, from the Inspector lists (the lists stay outside the repository). With those repairs applied: no closed thread in any packet, M0 no category worse, and the secret gate still 6 of 6. Also deterministic cases in CI, an upgrade from Phase 12 `main`, a real-host smoke, latency, and one Codex review (AGENTS.md §14). No real-model tier: no extraction change. | Synthetic cases only. |
| Q9 | Release? | **None.** The owner decided on 2026-09-28 not to release for now. | — |

## Goal

When memory is wrong, the owner fixes it in a few clicks and the fix holds: through edits elsewhere in the chat,
rebuilds and new extractor generations. Threads the story left open (K23) and names it joined by mistake (K8) stop
reaching the packet, and each chat shows what needs a look.

## Evidence behind the scope

From the restored copy of the owner's backup (Phase 11 Q1; read-only, 2026-09-28, `extract-v13`, counts only):

- **Threads pile up.** The longest chat (74 turns, 147 messages) has 59 open threads: 37 goals, 10 questions and 12
  promises. Nine goals ended in the story; one character holds 15 open goals where the owner counts 2 still under
  way (K23, `docs/perf/extract-v13.md`). An open thread reaches the packet when its owner or counterpart is mentioned
  or the message is about it (at most three), and an open goal reaches `<Cast>` when the message names its character
  (ADR 0043).
- **Ends that match nothing.** Nine turns ended a thread in words that matched no open one (the Inspector lists them
  under "Ends matching no open thread"). Each is a thread the story closed that stays open.
- **Secrets the story already told.** 14 of the chat's 19 secrets are still kept from someone. In the Phase 12 secret
  gate at least one was found out twice in the story, but no reveal matched it, and it kept `<Story>` out of scenes
  with that character (`docs/perf/summaries.md`).
- **Nothing to repair them with.** The owner's tools are a name join (ADR 0025), "Extract all history", rebuild
  and delete. A wrong fact stays until its turn is edited or re-extracted; a wrong automatic alias cannot be undone
  (K8).
- The chat has no item conflicts or ambiguous names today; the queue still shows them where they occur.

## In scope (Phase 13)

1. **The owner's lists (Q8).** On the restored copy: which open threads are over, and which secrets were found out
   and by whom. NMOS drafts the lists with the turns that suggest each answer; the owner confirms or corrects them.
   Kept outside the repository. Numbers on `main` before any Phase 13 change are
   the baseline.
2. **Storage and matching (Q2, Q3; ADR, migration 0024).** `owner_repair` as owner input; a matcher shared by every
   kind (turn, turn hash, head, closest text); every read applies the live repairs; `removed_at` for undo. Deleting
   a chat deletes its repairs. Replays read repairs as of the request.
3. **Threads and secrets (Q1 items 1 and 4).** Close with an outcome and reopen, in the thread fold (ADR 0019, 0039);
   found out and kept, in the secret fold (ADR 0033), per character.
4. **Facts (Q1 items 2 and 3).** Retract and correct in the fact fold: a retraction removes the version and brings the
   previous one back; a correction adds an owner version from its turn, which a later story turn supersedes (Q4).
5. **Names (Q1 item 5, K8).** "Not the same": resolution drops the story's aliases that join the two names directly.
   When they are still joined through a third name, the Inspector names it. An owner join and an owner split of the
   same pair: the newer holds.
6. **API and panel (Q5).** Endpoints to add, list and remove repairs, and the panel's buttons, forms, undo, "Repairs"
   list and bulk close. The plugin build changes; the owner installs it.
7. **The "Needs attention" queue (Q6)** on each chat's Inspector page, each item with its repair.
8. **Evaluation (Q8).** Deterministic cases, the owner's lists on the restored copy, M0 and the secret gate, a
   real-host smoke, an upgrade from Phase 12 `main`, latency, and a Codex review of the fold and API changes.

## Out of scope (Phase 13)

- Canon sources, authority levels and canon lock (Phase 14, host evidence first).
- Export and restore of the ledger, repairs and settings (Phase 14).
- Pending, conflicting and rejected outcomes in extraction, and a semantic verifier (in the roadmap's draft scope for
  Stage 6, not in its done criteria).
- Repairs by the response model or from chat text: only the owner, through the panel or the API.
- Story time (R4, after 1.0); editing messages (the plugin never changes host data); any extractor generation.

## Acceptance criteria

- [ ] Every existing test and memory-evaluation case passes; no stale memory in any mode; recorded packets replay as
      they were.
- [ ] Deterministic cases in CI, for each repair kind:
  - it applies, and undo restores the previous memory;
  - it survives `rebuild_all` and a new extractor generation that rewords its target;
  - it matches nothing, and is listed, once its turn is edited or deleted;
  - a closed thread is in no packet and no `<Cast>`; a reopened one is back;
  - a retracted fact brings back its earlier version; a later turn supersedes a correction;
  - a secret marked found out stops holding `<Private>` lines and summaries for that character;
  - a split separates two names a story alias joined (K8), and names the third name that still joins them;
  - a replay as of a request before a repair gives the packet that request had.
- [ ] On the restored copy, with the owner's lists applied: no thread the owner closed in any recorded request's
      replay; M0 no category worse; the secret gate 6 of 6.
- [ ] K8 and K23 closed, or rewritten to what remains.
- [ ] Real-host smoke on an isolated PocketRisu: a thread closed in the panel leaves the next packet; undo brings it
      back.
- [ ] Upgrade from Phase 12 `main` (`tests/test_upgrade.py`).
- [ ] Retrieve latency at 10,000 messages within +5 ms p50 of Phase 12 `main` with 100 live repairs
      (`tools/bench_story.py`).
- [ ] One Codex review (AGENTS.md §14) of the fold and API changes, with each finding confirmed or rejected.
- [ ] `ARCHITECTURE.md` (decisions), ADRs, README, the Korean guide, KNOWN-ISSUES, CHANGELOG.

## Steps (one pull request each)

1. This document, approved. **Done** (2026-09-28).
2. The owner's lists and the baseline on `main` (M0, secret gate, open threads). **Done** (`docs/perf/repair.md`): the
   owner confirmed the drafted lists (50 of 59 open threads ended, 9 under way; 6 of 14 kept secrets found out, 2 never
   kept). On `main` every one of the 40 M0 packets carries a thread the owner closed (113 lines, 16 threads); M0 26/28 and
   5/12; the secret gate 6 of 6, with `<Story>` held in all six scenes.
3. Storage, matching, threads and secrets: migration 0024, ADR, API, the Inspector's "Repairs" list.
4. Facts and names: retract, correct, split.
5. Panel: buttons, forms, undo, bulk close; the "Needs attention" queue.
6. Evaluation, real-host smoke, upgrade, latency, Codex review, documentation.

Every merge reaches the owner's `:edge`; no tag (AGENTS.md §13).

## Stop conditions

Stop and ask the owner when:

- the matcher cannot keep repairs across a new generation in the deterministic cases, or matches the wrong item;
- applying the owner's lists makes an M0 category worse or fails the secret gate;
- a repair would need to change raw evidence, host data or an invariant;
- latency exceeds the criterion.
