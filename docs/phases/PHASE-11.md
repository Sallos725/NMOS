# Phase 11 — Narrative Engine, part 1 (Stage 5)

> **Status: approved 2026-09-28 (owner), in progress.** Stage 5 of `docs/ROADMAP-1.0.md` (original §24–26,
> §31–37; Track B, B3 remainder), part 1 of 2. The owner chose Stage 5 next, with the M0 evaluation first, once
> G1–G3 were fixed (R1), and answered every question below with the recommended answer, except Q0's release:
> none is planned yet.

## Questions and answers

| # | Question | Answer | Alternatives not taken |
|---|---|---|---|
| Q0 | One phase or two? | **Two phases.** Phase 11: M0, relationships, threads, explicit links (one extractor generation). Phase 12: summaries and character state (a summary projection, no extractor change; its own spec). **No release decided** (owner: on hold). | One phase for all of Stage 5; `0.3.0` after both. |
| Q1 | M0: where do the real-chat questions come from? | **A restored copy of one of the owner's `pg_dump` backups** (`nmos-backups/`), in the test Postgres, read-only. Questions and gold answers are written with the owner and stay outside the repository, like the Phase 10 cases; reports carry numbers only. | Only synthetic cases. |
| Q2 | Which open threads (R3)? | **Goal, question (a mystery or an unanswered question), threat, debt**, beside the existing promise. A meeting stays a promise with a time; a missing item stays item whereabouts (Phase 6). | All nine types of §34; goals only. |
| Q3 | How does a thread end? | **Like a promise (ADR 0019):** the prompt lists OPEN THREADS; a new `resolved` predicate names one by its text with an outcome (achieved, abandoned, failed, answered, averted, paid). Text matching, restatement and "matching nothing" as in ADR 0019; promise handling does not change. (Recommended; the owner raised no objection.) | By age; by hand only (Stage 6). |
| Q4 | Which links between events? | **Only explicit ones:** a resolution links the resolving turn to the opening turn (fulfills, resolves, breaks, reveals); a stated cause (`because`, as the text gives it) on `event`, `feels_toward`, `relationship`, `has_status` and `goal`, resolved at read time to the most similar earlier event of the same participants, else kept as text. No inferred causality. | Model-inferred links marked as estimates. |
| Q5 | Relationships (K24)? | **Read side, no extractor change:** one history per pair; a declared set of symmetric relationships (friends, lovers, siblings, classmates, rivals, colleagues, partners…) ends the older one in both directions; `feels_toward` stays per direction and is shown with its turn next to the pair's newer relationship, never silently closed. ADR with the symmetric table. | A relationship change also ends the pair's earlier feelings. |
| Q6 | Story time (R4)? | **After 1.0.** Turns stay the time axis; "three days later" is text. | In this stage. |
| Q7 | Which extraction models measure it? | **`gemma4:31b-cloud` (the owner's) and `deepseek-v4.1-flash`**, both through the local Ollama, 3 runs per synthetic Korean scene, 2 workers (429s). | `gemma4` only. |
| Q8 | Summaries (Phase 12) | **Direction accepted with Q0:** scene summaries of fixed windows and a rolling "story so far", as a rebuildable projection with its own generation, in a `<Story>` section with its own budget share. Detailed in `PHASE-12.md`. | Episodes and arcs too. |
| — | The persona's full name (found by M0) | **Both:** the owner joins the names by hand in production now (ADR 0025), and step 3 adds a resolver rule: a character name that ends with the persona's name, as a separate word, is the persona. Read side (`resolve-v5`), no re-extraction. | By hand only; the rule only. |
| — | Rolling out `extract-v13` | **The owner is told the re-extraction's size before step 4 merges** and pulls `:edge` themselves; the backup is taken first. | Hold every step off production until the end. |

Release: none decided (owner, 2026-09-28).

## Goal

The memory follows the story's open business and its reasons, not only its latest facts: what each character
is still after, what is still unanswered or threatened or owed, what ended it, and why someone feels or stands
as they do. Relationships read as one history per pair.

## Evidence behind the scope

From the owner's production database, aggregates only (read-only, 2026-09-28; 7 chats; current extractor
generation):

- **Goals pile up.** 115 valid `goal` assertions against 26 `promised`. `goal` is multi-valued and nothing ends
  one, so every goal ever stated stays current: one character holds 40, the median subject 3. Promises have a
  lifecycle (8 `fulfilled`); goals do not.
- **Relationships are split.** `feels_toward` 71 over 14 pairs, 5 of them recorded in both directions;
  `relationship` only 8, and 2 pairs carry both predicates. This is K24's surface (Phase 8 measured the stale
  outcome in 2 of 9 runs).
- **Events are many and unlinked.** 216 `event` assertions, 75 major, with participants (Phase 8) but no link to
  what they caused or resolved; a "why" question can only be answered by excerpt search.

## In scope (Phase 11)

1. **M0 — RP evaluation on real chats.** A tool that restores nothing itself: given a database URL (a restored
   backup, Q1) and a case directory outside the repository, it builds the packet each question's request would
   get (the Phase 9 replay path) and scores whether the gold facts are placed, whether forbidden or stale ones
   are, and how many tokens they took. Categories: current and past state, promises, goals and other threads,
   relationships now and before, speech level, secrets, "why" questions, irrelevant old events kept out. Numbers
   for `main` before any Phase 11 change are the baseline. Public synthetic cases for each new category join the
   deterministic memory evaluation in CI.
2. **Relationship history per pair (Q5, read side), and the persona's full name.** ADR with the symmetric table; the Inspector and the packet
   show one block per pair with the current relationship, feelings per direction with their turns, and the
   earlier relationship. Closes K24's direction case; the predicate case is shown with turns and measured. A
   character name ending with the persona's name as a separate word resolves to the persona (`resolve-v5`; M0 found
   the owner's chat split in two, `docs/perf/m0-baseline.md`).
3. **`extract-v13` (one generation).** OPEN THREADS (goal, question, threat, debt) listed like OPEN PROMISES;
   `resolved` (value: the listed text; outcome); new predicates `question`, `threat`, `owes` (subject, object,
   value); an optional `because` on the predicates of Q4. The registry, prompt and generation change once; the
   recent window is re-extracted at the provider's cost (ADR 0014), older turns keep their facts until "Extract
   all history".
4. **Threads at read time (Q2, Q3).** `threads.py` generalized from promises to the five types, pure and
   as-of aware; a goal the story achieves or abandons stops being current; history kept; edits and deletes
   restore (invariant 7). The packet's `<Threads>` section holds open threads of the scene cast first, the thread
   the user's message is about first of all (ADR 0019 amendment 1).
5. **Explicit links (Q4).** Resolutions and stated causes become links at read time, never stored as truth; the
   packet can place the cause next to a feeling or relationship when the budget allows; the Inspector shows a
   fact's cause and a thread's opening and end.
6. **Inspector.** Threads by type with their state, outcome and turns; unmatched resolutions; the pair view.
7. **Evaluation.** M0 before and after; the extraction tier (Q7); latency; a real-host smoke; an upgrade from a
   `v0.1.0-beta.21` database and from the Phase 10 `main`.

## Out of scope (Phase 11)

- Summaries, scenes, episodes, arcs and the per-character state block (Phase 12, Q0, Q8).
- Inferred causality, a causal graph store, graph queries.
- Story time (Q6, R4); style and procedural memory (after 1.0).
- Owner repair of threads or links by hand (Stage 6).
- Any release (none decided, Q0).

## Acceptance criteria

- [ ] Every existing test and memory-evaluation case passes; no stale memory in any mode; `packet-v4` traces
      still replay.
- [x] M0 exists, with its baseline on `main` recorded before step 3 (numbers only in the repository):
      `docs/perf/m0-baseline.md`, 5 of 12 owner-confirmed cases.
- [ ] Synthetic cases in CI for each thread type (opened, resolved, deleted, edited back), a "why" question
      answered from a stated cause, a relationship changed in the other direction (K24), and an irrelevant old
      event kept out.
- [ ] Extraction tier, both models (Q7), 3 runs per scene: threads opened for stated goals, questions, threats
      and debts and not for passing wishes; resolutions matched to their listed thread; causes quoted only when
      the text states them. Every miss listed; any scene below 2 of 3 shown to the owner before the phase closes.
- [ ] M0 on a restored backup re-extracted with `extract-v13`: no category worse than the baseline; goals no
      longer pile up (the character with 40 current goals has only open ones); K24 cases in the owner's chats read
      as one history.
- [ ] Retrieve latency at 10,000 messages within +10 ms p50 of Phase 10 `main`.
- [ ] Real-host smoke on an isolated PocketRisu: a thread opened and resolved in play reaches the packet and the
      Inspector.
- [ ] Upgrade from a `v0.1.0-beta.21` database and from Phase 10 `main` (`tests/test_upgrade.py`).
- [ ] `ARCHITECTURE.md` (decisions), ADRs, README, the Korean guide, KNOWN-ISSUES (K23, K24 rewritten), CHANGELOG.

## Steps (one pull request each)

1. This document, approved.
2. M0: the evaluation tool, the public synthetic categories, the baseline.
3. Relationship history per pair and the persona's full name (ADR, read side).
4. `extract-v13`: OPEN THREADS, `resolved`, the new predicates, `because` (ADR).
5. Threads at read time and the packet's thread section.
6. Explicit links at read time, packet and Inspector.
7. Inspector views.
8. Evaluation tiers (each paid run approved first), real-host smoke, upgrade, documentation.

Every merge reaches the owner's `:edge`; no tag (AGENTS.md §13). Step 4 re-extracts each chat's recent window
when production pulls it: the owner is told its size before it merges, and pulls it themselves after a backup.

## Stop conditions

Stop and ask the owner when:

- the extraction models cannot tell a goal from a passing wish (below 2 of 3 on most scenes);
- a thread type needs a schema change beyond what the read side can derive;
- M0 shows a category worse than its baseline and no fix inside the phase recovers it;
- a paid run would exceed its agreed budget;
- M0 would need production data beyond a restored backup the owner provided.
