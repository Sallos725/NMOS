# Phase 26 — A repair whose item is gone suggests where it belongs now

> **Status: approved (2026-10-01): every answer as proposed, and an exception to R7; current, alongside Phase 23.**
> Stage 6 (owner repair, ADR 0044), the remaining
> part of AGE-23 before `0.3.0`: the owner chose on 2026-10-01 to make a repair that matches nothing after a new
> extractor generation easy to re-apply, rather than only rewording Stage 6's done criterion ("quality before time").
> R7 (2026-10-01) keeps new phases to Stage 7 until 1.0, urgent fixes excepted; the owner granted this phase an
> exception (2026-10-01), as Phase 23 had. No release in this phase; `0.3.0` (AGE-7) follows it.

## Questions and answers

| # | Question | Answer | Not chosen |
|---|---|---|---|
| Q1 | Which repairs get suggestions? | **Every repair that matches nothing now and names an item:** thread close and reopen, secret found out and kept, fact retract and correct, and a lock on a canon fact. Not a name split (it names two names, not an item), not a restore (its fact is gone by definition, ADR 0057), and not a lock on the owner's correction (it names that correction's repair, not an item: it moves with the correction, Q3). A repair whose target turn was edited or deleted gets none either: the story changed there, so the owner decides afresh (ADR 0044 item 3). | Threads only (the measured case; secrets and facts orphan the same way). |
| Q2 | What is a candidate? | **An item of the same head, in the state the repair would change, that no applied repair holds:** for a thread close, an open thread of the same kind and maker (and counterpart for a promise or a debt); for a reopen, a closed one; for a secret found out, a kept secret of the same predicate and subject (and object); for a keep, an ended one; for a fact retract or correct, a current story fact (not canon, not the owner's) of the same predicate, source and subject (and object); for a lock, a canon fact of that head not locked. A candidate must also allow the repair: a secret still kept from (found out) or over for (keep) the repair's character. At most three, in a total order: first those whose quote shares a run of 12 characters with the repair target's stored quote (`target.evidence`, ADR 0044 amendment 2), then the higher text similarity to the target's text (`threads.similarity`), then the nearer turn to the target's turn, then the earlier turn, then the item's text in code-point order (all of which a rebuild of the same rows keeps). No minimum similarity: the owner judges, and a wrong suggestion costs a glance. | A similarity floor (on the measured copy most real candidates sit below 0.2, so a floor would hide them); candidates from other heads (another character's thread is never the same thread). |
| Q3 | What does the owner do with one? | **"Apply here": one action that moves the repair** — the old repair is removed and the same repair (kind, outcome, character or new value, note) is planned for the candidate exactly as a new repair is (`repairs.plan`, with every check it makes) and stored with the old one's id as `moved_from`, in one transaction. The effective turn stays the old one's when the candidate allows it, and otherwise becomes the earliest the candidate allows (its turn, or the story's close or reveal the repair undoes), never past the chat's last turn. A lock on a moved correction moves with it in the same transaction (removed, and stored again naming the new correction, with its own `moved_from`). Previewed first (`POST …/repairs/{id}/move/preview` with `item`: the difference and its fingerprint, as Phase 20's previews) and refused when memory changed since (`expect`). Undoing the moved repair removes it like any repair; the one it moved from stays removed (both stay in the Repairs history), so nothing applies twice. "None of these" leaves the repair as it is. | Two clicks with today's buttons (apply the repair to the candidate, then undo the old one: no plugin build, but two audit rows that do not say they belong together, and a window where both are stored); applying the best candidate automatically (a wrong match closes a thread the story still has open: the worse failure). |
| Q4 | Where? | **In "Needs attention"**, on the row of the repair that matches nothing: up to three candidate lines under it, each with its turn, its text and "Apply here". The browser Inspector stays read-only (H15). | A separate page. |
| Q5 | What does it change? | **A migration for `owner_repair.moved_from` (nullable, referencing `owner_repair`); `POST …/repairs/{id}/move/preview` with `item`, and `POST …/repairs/{id}/move` with `item` and `expect`; a new plugin build** (the panel's repair actions are a closed list, `inspector.ts` `REPAIR`). No extractor, packet policy or recall option: a moved repair is a repair, read as of its `created_at` and `removed_at`, so recorded requests replay as they were (ADR 0027). Archives carry the column (ADR 0050). | — |
| Q6 | How is it measured? | **On the production copy re-extracted with `extract-v15` (`nmos_p26_v15`, read-only apart from its repairs), with the owner's 68 Phase 13 repairs:** the 28 that match nothing — 9 have no item of their head in the state they change (no candidate), 19 have some. The owner opens each of the 19 in the copy's panel and says whether its item is among the candidates or truly gone; for every one the owner names, "Apply here" makes it current as the repair says, and nothing else changes (the preview's difference). Deterministic cases in CI for every kind of Q1, the ranking, the move's audit, undo, `expect`, an archive round trip with a moved repair, an upgrade from `main`. No model call. | A labelled set without the owner (only the owner knows which thread a repair meant). |
| Q7 | Is this high risk (AGENTS.md §14)? | **Yes:** it changes stored owner input (a migration and a move of repairs) and what is current through them. | — |
| Q8 | And Stage 6's done criterion? | **Reworded once this phase holds:** "every repair survives a rebuild and a new extractor generation, or, when the generation no longer states its item, is listed with the items it may now mean and moved by the owner in one action." Then Stage 6 is complete and AGE-23 closes. | The wording alone, without this phase (the owner's option 1). |

## Evidence behind the scope

The owner's 68 Phase 13 repairs (made on `extract-v13` copies) on the production copy re-extracted with `extract-v15`
(2026-10-01, `~/nmos-eval/stage6-v15/`, counts only): 40 apply (as on `extract-v14`), none missed where the item is
still stated with the repair's quote. Of the 28 that match nothing, 9 have no item of the same head in the state the
repair changes (what was repaired is gone); 19 have one to six such items, of which five reach a text similarity of
0.2 or more (one secret at 0.4 or more within five turns) — repairs whose error may have come back reworded, which
today the owner must find and repair again by hand after every new generation. The same holds within a generation:
a rebuild of `extract-v14` restated 22 % of threads and 28 % of facts without the earlier quote (AGE-23, measure 2).

## Goal

After a new extractor generation, a repair whose item the story no longer states the same way shows the items it may
now mean, and the owner moves it to the right one in one action, or leaves it.

## In scope (Phase 26)

1. Candidates (Q1, Q2) computed on read for repairs that match nothing, in `repairs.py`, beside the matcher.
2. The move (Q3, Q5): migration `0029`, `moved_from`; `POST /v1/conversations/{id}/repairs/{repair_id}/move` and its
   preview; the Repairs history names a move.
3. The Inspector's "Needs attention" rows and the character page (Q4), both languages; the panel's "Apply here" with
   its preview (a new plugin build).
4. Tests (Q6), ADR 0060, ARCHITECTURE (D70), STATUS, CHANGELOG, README and the Korean guide; the owner's review on the
   copy; Stage 6's done criterion reworded (Q8).

## Out of scope (Phase 26)

- Applying a suggestion without the owner; a similarity floor or model calls to rank candidates.
- Suggestions for a name split, a restore or a lock on the owner's correction; moving a repair across chats.
- The release (`0.3.0`, AGE-7) and the production deploy (the owner's).

## Acceptance criteria

- [ ] Every existing test passes; deterministic cases for every kind of Q1: a repair that matches nothing lists the
      candidates of Q2 in their order, none held by an applied repair; "Apply here" moves it in one transaction with
      `moved_from`, with the checks and effective turn of Q3, its preview equals the change, `expect` refuses a stale
      move, a lock on a moved correction moves with it, and undo behaves as Q3 says.
- [ ] A recorded request replays as it was across a move; an archive with a moved repair restores with it.
- [ ] On `nmos_p26_v15`, every one of the 19 repairs with candidates shows them; for every repair the owner says is
      among its candidates, "Apply here" makes the repair apply again and changes nothing else.
- [ ] The Inspector page of the copy's longest chat reads no more than 5 ms slower (median of ten reads).
- [ ] Review per AGENTS.md §14 (high risk; the self-review, a Codex review only on the owner's request).

## Steps (one pull request each)

1. This document, approved; AGENTS §2 and STATUS name Phase 26 current.
2. Candidates, the move, the migration, the API, the Inspector rows and the plugin build, with their tests (ADR 0060).
3. The owner's review on the copy; latency; documentation; Stage 6's criterion reworded; Phase 26 complete. Then,
   outside this phase: AGE-23 closes, the owner deploys `:edge` and installs the plugin, `0.3.0` (AGE-7) with the
   owner's OK for the tag.

Every merge reaches the owner's `:edge`; no tag (AGENTS.md §13).

## Stop conditions

Stop and ask the owner when:

- a candidate list would need another head than Q2's to hold the owner's item (a design question, not a tuning one);
- the move cannot be one transaction with the current schema, or undo needs a second migration;
- the Inspector page reads more than 5 ms slower.
