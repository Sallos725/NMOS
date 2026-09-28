# Phase 12 — Narrative Engine, part 2 (Stage 5)

> **Status: approved 2026-09-28 (owner), in progress.** Stage 5 of `docs/ROADMAP-1.0.md` (original §26, §32,
> §36–37), part 2 of 2, after PHASE-11 Q0 and Q8: summaries and character state, with a summary projection and no
> extractor change. The owner asked for this spec after accepting Phase 11 and answered every question below with the
> recommended answer (2026-09-28). Amended the same day after review: the story prompt lists secrets too, a summary
> written before a secret it must keep is written again, `packet-v7` went to the turn-numbering fix (ADR 0041) so this
> phase's policy is `packet-v8`, and a secret gate is required before summaries reach a packet.

## Questions and answers

| # | Question | Answer | Alternatives not taken |
|---|---|---|---|
| Q1 | What is summarized, in what units? | **Scenes of a fixed window of 8 turns** (about 25,000 characters on the owner's chats), summarized once each, in the order of the story. A window is summarized when it is complete and older than the prompt's own last messages. | 4 or 16 turns; scenes detected by the model; episodes and arcs (§36) too. |
| Q2 | How does the packet speak for the whole chat? | **A "story so far"**: one call over every current scene summary, redone when a window completes or a scene summary changes. It is one level above scenes, order-independent, and rebuilt from them. | An incremental chain (each window updates the last "so far"); scene summaries only. |
| Q3 | Secrets (Phase 10) in summaries? | **Left out, and checked.** The prompt lists the window's OPEN SECRETS and says to leave their content out ("X keeps something from Y" at most). The story-so-far prompt lists them too. A summary whose text repeats a secret's content (trigram overlap, as ADR 0033 matches reveals) is not used, and the Inspector shows it as held back; that check is lexical and catches a copied secret, not a reworded one, so the prompt is the guard and summaries reach a packet only through the secret gate below. A summary written before a secret it must keep was extracted is held and written again. In narrator mode (ADR 0035) the packet has no `<Story>`: summaries have no per-character knowledge. Strict mode uses the same check. | A summary with a secret goes to `<Private>`; per-character summaries (a call per character). |
| Q4 | Character state (§32)? | **A `<Cast>` block from facts, at read time (no model):** for each character in the scene cast (Phase 10), up to four characters, their place, condition (`has_status`), feeling toward the persona or the addressed character, open goals (at most 2, ADR 0039) and what they carry (at most 3). These lines leave `<Facts>`, so nothing is said twice. A new packet policy `packet-v8` (`packet-v7` numbers excerpts by turn, ADR 0041). | No block: facts rank as now (ADR 0026); character summaries written by the model. |
| Q5 | Budget? | **`<Story>` takes at most 30% of the budget inside the frame**: the story so far first, then the one scene summary most related to the message. The default reserve stays 800. What `<Story>` does not use goes to the other sections. **Superseded 2026-09-28 (owner):** the default reserve is 2,000; at 800 the story so far (285 tokens) did not fit its share of 204. | A higher default reserve (1,000); a fixed token count. |
| Q6 | Which model writes them, and when is it on? | **The extraction model and endpoint** (the same settings), as its own projection generation (`summarize`: model, endpoint, prompt version, window). It is on when extraction is on; a panel switch turns it off. | A separate summary model setting; off by default. |
| Q7 | Rolling it out? | **All complete windows of each chat, newest chats first, at background priority.** The owner is told the size before the merge that turns it on, and pulls `:edge` themselves after a backup. | Only windows completed after the upgrade. |
| Q8 | How is it measured? | **M0 with new owner-confirmed cases whose answers lie outside the prompt window** (Phase 11 lesson: only 9 of 28 needed memory). About 12 cases: early events, "what has happened so far", and a character's current state. Also a real-model tier on both models (Phase 11 Q7) and deterministic cases in CI. | The 28 cases only. |
| Q9 | Release? | **The owner's call when Phase 12 is done.** That completes Stage 5, which the roadmap maps to `0.3.0`. Stage 4's `0.2.0` is not released yet either. | Decide now. |

## Goal

The packet speaks for the whole chat, not only for the facts retrieval found. An old scene comes back in a few
lines when the message is about it. The model always has a short account of the story so far, and each character
in the scene arrives with their current state.

## Evidence behind the scope

From the restored copy of the owner's backup (Phase 11 Q1; read-only, 2026-09-28):

- **The chats are long in characters, not in turns.** The longest has 74 turns and 147 messages, about 3,100
  characters per turn after cleaning (231,000 in all). The next has 35 turns. The prompt's own last messages hold
  about 5–6 turns (M0, `docs/perf/m0-baseline.md`), so about 90% of the longest chat is outside the prompt.
- **Memory answers little of what lies outside the window.** In M0, 9 of 28 cases need memory, and 7 of those pass
  after Phase 11. The two that fail ask about something no current fact holds: an old goal outranked by newer ones,
  and why a status that later ones replaced was so.
- **The packet cannot say what happened in general.** It carries facts, threads and excerpts that match the
  message. "What have we been through?" gets excerpts that share its words, or nothing.
- **Cost.** Extraction already reads each turn with its 3 context turns (`NMOS_EXTRACT_TURNS`), about 4 turns of
  text per call. Summaries of 8-turn windows read each turn once more. For the longest chat that is about 9 calls
  of about 25,000 characters, plus a small "so far" call each time a window completes.

## In scope (Phase 12)

1. **M0, extended (Q8).** About 12 new cases written with the owner, answers outside the prompt window, kept
   outside the repository. Numbers for `main` before any Phase 12 change are the baseline.
2. **The summary projection (Q1, Q2, Q6).** A new projection kind `summarize` with its own generation (ADR).
   - A scene summary is keyed by its window's turn hashes (ADR 0008). An edit, delete, swipe or disable inside the
     window stops it matching: it is masked at once and redone (invariant 7). Branches that share the window share
     it.
   - The story so far is keyed by the scene summaries it was made from.
   - Both are stored as derived rows with provenance: window, generation, prompt fingerprint (invariants 2 and 10).
     Raw text is never replaced in storage (invariant 1).
   - Jobs run in the worker like extraction, with the same retry and failure accounting (G3).
3. **Secrets (Q3).** The window's OPEN SECRETS go into the scene and story prompts; a deterministic check runs when
   a summary is read; a summary written before a secret it must keep is held and written again; narrator mode leaves
   `<Story>` out.
4. **Packet (Q4, Q5), `packet-v8`.** A `<Story>` section (the story so far; the scene summary most related to the
   message, from lexical and, when on, vector search over summaries) within its share. A `<Cast>` block from facts
   for the scene cast. Earlier policies render as before; recorded packets replay under their own policy (ADR 0027).
5. **Inspector.** Summaries per chat, with their windows, generation and state (current, masked, held back for a
   secret, failed); the story so far; a character's state block on the character page.
6. **Evaluation.** M0 before and after; the real-model tier; latency; a real-host smoke; an upgrade from Phase 11
   `main`.

## Out of scope (Phase 12)

- Episodes, arcs and long-term relationship summaries (§36): scenes and the story so far only (Q1, Q2).
- Summaries that replace facts or excerpts. They are added context: facts still decide what is current.
- Closing threads by hand or from summaries (K23; Stage 6).
- Story time (R4, after 1.0); style and procedural memory (after 1.0).
- Any new extractor generation: `extract-v13` stays.

## Acceptance criteria

- [ ] Every existing test and memory-evaluation case passes; no stale memory in any mode; `packet-v6` traces still
      replay.
- [ ] Deterministic cases in CI:
  - an old scene placed for a message about it;
  - an edit inside a window replaces its summary, with no stale text in the packet;
  - a branch sees only its own summaries;
  - a secret's content never reaches `<Story>`, with the one it is kept from in the scene or in strict mode;
  - narrator mode has no `<Story>`;
  - `<Story>` stays within its share;
  - `<Cast>` lines are not repeated in `<Facts>`;
  - a secret stated after a summary was written holds that summary until it is written again;
  - with facts and threads off, a summary is still checked against the chat's secrets.
- [ ] Real-model tier, both models (Phase 11 Q7), 3 runs per synthetic Korean window:
  - the summary names the window's key events (gold phrases) and invents none (forbidden phrases);
  - it leaves a listed secret's content out;
  - it stays within its token cap.
  - Every miss is listed; any scene below 2 of 3 is shown to the owner.
- [ ] M0 on a restored backup: no category worse than the baseline, and the new cases improve. On the owner's
      longest chat, the packet's `<Story>` covers every complete window older than the prompt within the budget.
- [ ] **Secret gate (required before summaries reach a packet):** on the restored copy, every scene in which a
      character is present that a secret is kept from gets a `<Story>` without that secret's words (a list of
      forbidden words per secret, confirmed with the owner), under both models' summaries.
- [ ] Retrieve latency at 10,000 messages within +10 ms p50 of Phase 11 `main`.
- [ ] Real-host smoke on an isolated PocketRisu: a window completed in play gets a summary that reaches the packet
      and the Inspector.
- [ ] Upgrade from Phase 11 `main` (`tests/test_upgrade.py`).
- [ ] `ARCHITECTURE.md` (decisions), ADRs, README, the Korean guide, KNOWN-ISSUES, CHANGELOG.

## Steps (one pull request each)

1. This document, approved. **Done** (2026-09-28).
2. M0: the new cases with the owner, and their baseline on `main`. **Done**: 12 owner-confirmed cases, every answer
   outside the prompt window; 2 of 12 on `main` after Phase 11 (`docs/perf/m0-baseline.md`).
3. The summary projection: schema, generation, jobs, invalidation, the Inspector list (ADR). Off in the packet.
   **Done** (ADR 0042, migration 0023): off by default (`NMOS_SUMMARIES`).
4. The summary prompt and secrets, measured on both models (the real-model tier), before anything reaches a packet.
   **Done** (ADR 0042 amendment 1, `docs/perf/summaries.md`): `gemma4` 18/24, `deepseek` 24/24. Two scenes below 2 of
   3, shown to the owner: `gemma4` named the forged letter (not the forgery) 3 of 3, and wrote a kiss that was the
   whole scene 2 of 3, both copies the read-time check holds. (A first record, 21/24, used names from a real chat in one
   scene; it was replaced.) The owner accepted the letter miss (2026-09-28); the kiss, found when the record was
   redone, is shown to the owner with that change. The owner approved step 5 with the backfill size given (11 scene and 2 story calls on
   the restored copy, about 275,000 characters).
5. `packet-v8`: `<Story>` and `<Cast>`, the budget share, narrator and strict handling (ADR). Merged only after the
   secret gate and M0 (no category worse) pass. Before it merges, the
   owner is told the backfill size (Q7). **Done** (ADR 0043, ADR 0042 amendment 2), gates pending. The stories did not fit 30 % of
   800 tokens (a stop condition); the owner chose a default budget of 2,000 (2026-09-28). A summary that restated a
   secret stated after it (another stop condition); the owner chose to write such summaries again. M0 with `gemma4`
   extraction: 2 → 5 of the 12 new cases, 26 of 28 kept (`docs/perf/summaries.md`).
6. Inspector views (summaries, story so far, character state).
7. Evaluation, real-host smoke, upgrade, latency, documentation.

Every merge reaches the owner's `:edge`; no tag (AGENTS.md §13).

## Stop conditions

Stop and ask the owner when:

- a summary leaks a secret's content in the real-model tier and the prompt cannot stop it;
- either model invents events in more than 1 of 3 runs on most scenes;
- M0 shows a category worse than its baseline and no fix inside the phase recovers it;
- `<Story>` needs more than its share to cover the longest chat, so the default reserve would have to change;
- the backfill would cost more than the owner agreed (Q7), or a paid run would exceed its budget.
