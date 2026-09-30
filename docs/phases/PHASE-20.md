# Phase 20 — A name join shown before it is made, and an undo that restores what it changed

> **Status: proposed (2026-10-01), awaiting the owner's approval.** Stage 6 of `docs/ROADMAP-1.0.md`, remaining
> items ("edit aliases"; the entity merge and split of the original §20): C7 of
> `docs/proposals/IDEA-SURVEY-2026-09-29.md`, which the survey's recommended order puts with Stage 6's remaining items
> (owner, 2026-09-29). Tracked as AGE-3. No release; it ships with the Stage 6 milestone.

## Questions and proposed answers

| # | Question | Proposed answer | Alternatives |
|---|---|---|---|
| Q1 | What does the preview show? | **What the join changes in this chat's memory, from the chat's own rows:** the entity after the join (its names, the name shown, which of the two ids it keeps); facts about both names that would replace one another (a single-valued fact such as a place or a condition: which version becomes current, by the story's order, and which is superseded), that would merge into one (the same value), and item timelines that would merge (and a dispute that would appear, ADR 0017); a relationship, promise or thread between the two names (it becomes one character's with itself); secrets kept from one name and held or told by the other; owner repairs and locks whose match changes (one that applies now and would match nothing, or a lock that would start holding off statements about the other name); a join with the persona; canon names that would join as well. Each line with its turn. **"Nothing changes"** when the names are one entity already or one is not mentioned on the head. | Counts only; the entity after the join only. |
| Q2 | Which actions get a preview? | **Every one that changes who is who: a join, a split (ADR 0044), and the undo of either.** The split and the undo are the join read the other way; one computation serves all three. | The join only. |
| Q3 | How is it computed? | **Read only, on the owner's click:** the chat's memory as it is and as it would be with the join (or without it), both read as every request reads them (`memory_view`), and the difference. No model call, nothing stored, nothing on the request path. A read of the owner's longest chat takes about 15 ms (147 messages, restored copy), so a preview is two of them. | A stored plan table. |
| Q4 | What if memory changes between the preview and the click? | **The preview carries a fingerprint of what it read** (the head commit, the owner links and repairs in force, the extractor and canon generation). The join, split and undo accept it; when it no longer matches, the sidecar answers 409 and the panel shows a fresh preview. Requests without it (the API as today) still work. | No check (the join is undoable anyway); a lock on the chat. |
| Q5 | Does the owner choose a side for each conflicting fact? | **No. The story's order decides, as it does today, and the preview says which version wins.** A wrong winner is fixed afterwards with Phase 13's repairs (retract or correct), linked from the preview's line; the join stays one undoable row. | A side per fact, written as repairs in the same action (several rows for one click, and undo must remove them together). |
| Q6 | A relationship, promise or thread between the two joined names? | **Shown as a warning in the preview; memory keeps it as today.** None of the owner's seven joins made one (below). A rule that drops them waits for a case. | The fold leaves out a relation between an entity and itself (a resolver change, `resolve-v6`). |
| Q7 | What does "an undo that restores the exact state" need? | **Undo already restores everything read from the ledger:** a join is resolved at read time (ADR 0025), so removing it gives back the same entities, facts, threads, secrets and repair matches. **Except the turns extracted while the join was in force:** extraction lists the joined names as one entity (ADR 0025 item 5), so those turns' facts were written with the joined names. The undo's preview counts them, and the panel offers to re-extract just those turns (their extractions discarded, as a rebuild does, and the turns queued; model calls at the owner's provider, off by default). | Count only, with the chat's full rebuild (today's button) as the remedy. |
| Q8 | A backup before a join? | **None.** A join, a split and an undo delete nothing: each is an owner row with `created_at` and `removed_at`, and the re-extraction of Q7 discards derived rows only (invariant 2). | Download an archive (Phase 16) before each join. |
| Q9 | Where? | **The panel's Inspector tab,** where the join, split and undo buttons are (ADR 0025, 0044): a click shows the preview in place with "Join" / "Split" / "Undo" and "Cancel". The browser Inspector stays read-only (H15). | A separate merge page. |
| Q10 | How is it measured? | **Deterministic cases** for every line kind of Q1 (each case also checks that the preview equals the difference after the action); **the owner's seven joins on the restored copies** (undone and redone on the copy, the preview against the result, counts only); a real-host smoke on an isolated PocketRisu (a join previewed and made, then undone); no migration, so no upgrade case beyond the existing ones; request-path latency unchanged (the request path changes in nothing). | Deterministic cases only. |

## Goal

Joining two names changes what memory says about both, at once and without a word: a fact of one replaces a fact of
the other, a secret kept from one is now kept from someone who knows it. After this phase the owner sees that before
the click, and an undo gives back what the join changed, including the turns extracted while it held.

## Evidence behind the scope

On the restored copies of the owner's two measured chats (`extract-v14` evaluation copies, read-only, 2026-10-01,
counts only), each of the owner's seven joins read with and without it:

- **Four of seven changed none of the counts** (entities, facts, threads, secrets, conflicts): the names were one
  entity already, or not both mentioned on the head. The owner could not tell; a preview would have said "nothing changes".
- **Three joined two entities into one.** Two of them left one current fact fewer: two statements about the two names
  now share one version, and one replaces the other without a line anywhere. None made a relationship or thread of a
  character with itself; thread, secret and conflict counts did not change.
- **72 turns** (52 and 20, two joins) were extracted with the two names listed as one entity. Removing those joins
  today would bring back two entities, but those turns' facts would keep the names as the extractor wrote them under
  the join.
- A memory read of the longest chat (147 messages) takes about 15 ms (median of seven), so a preview of two reads is
  well within a click.
- The copies have no owner repairs or splits; the repair and lock lines of Q1 are covered by deterministic cases.

## In scope (Phase 20)

1. **The preview (Q1–Q4).** A pure difference of two memory views; endpoints for a join, a split and an undo, each
   returning the lines of Q1 and a fingerprint; the fingerprint checked by the join, split and undo endpoints (409).
2. **Re-extracting the turns extracted under a join (Q7).** The turns found from their extraction's stored hints (the
   two names listed as one entity); an endpoint that discards those extractions and queues the turns, after the
   owner's click; the undo preview's count.
3. **Panel (Q9).** The preview in place of today's immediate join, split and undo; strings in both languages; a new
   plugin build.
4. **Evaluation (Q10)** and docs: an ADR, `ARCHITECTURE.md` (a decision; D36 still says there is no owner split),
   README, the Korean guide, KNOWN-ISSUES (K8), CHANGELOG.

## Out of scope (Phase 20)

- Choosing a side per fact in the join (Q5), and dropping self-relations (Q6).
- Joins suggested by NMOS, joins of more than two names in one action, joins across chats.
- Any change to extraction, resolution rules, the packet or the request path.
- Writing from the browser Inspector (H15).

## Acceptance criteria

- [ ] Every existing test and memory-evaluation case passes; recorded packets replay as they were.
- [ ] Deterministic cases for each line kind of Q1, for a join, a split and an undo; in each, the preview equals the
      difference read after the action, and "nothing changes" is shown when nothing does.
- [ ] A stale fingerprint gets 409 and changes nothing; a request without one behaves as today.
- [ ] Undo of a join followed by re-extraction of the turns it covered gives the same memory as a chat that never had
      the join (deterministic, stub model).
- [ ] On the restored copies, for each of the owner's seven joins: the preview matches the result of undoing and
      redoing it on the copy.
- [ ] Real-host smoke on an isolated PocketRisu: a join previewed and made in the panel, then undone.
- [ ] A preview of the longest measured chat within 200 ms.
- [ ] The change marked high risk where it touches identity (AGENTS.md §14: the join, split and undo endpoints) and
      extraction (the re-extraction), in the report and the PR.
- [ ] ADR, `ARCHITECTURE.md`, README, the Korean guide, KNOWN-ISSUES, CHANGELOG.

## Steps (one pull request each)

1. This document, approved; AGENTS §2 and STATUS name Phase 20 current.
2. The preview and the fingerprint check (sidecar), with the deterministic cases.
3. Re-extracting the turns extracted under a join (Q7).
4. The panel, the plugin build and the real-host smoke.
5. The restored copies, latency, docs; Phase 20 complete.

Every merge reaches the owner's `:edge`; no tag (AGENTS.md §13).

## Stop conditions

Stop and ask the owner when:

- a preview does not match the result of its action on a restored copy, and the difference is not a defect of the
  preview;
- finding the turns extracted under a join from their stored hints misses turns or finds others (then the undo shows
  a count only, Q7's alternative);
- re-extracting single turns needs a migration or a new extractor generation;
- a preview of the longest chat takes more than the criterion.
