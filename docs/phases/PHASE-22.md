# Phase 22 — A re-extraction that keeps what it found: a reveal check, and the facts a re-extraction dropped

> **Status: approved (2026-10-01) with every proposed answer (Q2–Q8; Q1 is the owner's decision); current.** Not a roadmap stage: an urgent correction found by
> measurement (a local benchmark of the owner's chats, 2026-09-30/10-01), tracked as AGE-25 under AGE-24 (the urgent
> exception of R7, `docs/STATUS.md`). The owner chose the direction on 2026-10-01 (AGE-25): **a reveal check instead of
> a re-extraction for K29, and a report of the narrated facts a re-extraction dropped**; keeping the earlier facts
> automatically is reconsidered after the loss rate is measured, and extracting a new chat oldest first is not done.
> Phase 21 (AGE-26) is a separate draft; this phase does not depend on it.

## Questions and proposed answers

| # | Question | Proposed answer | Alternatives |
|---|---|---|---|
| Q1 | What does "Extract all history" do with a turn extracted before an earlier turn's secret was (K29)? | **Owner's decision (2026-10-01): it keeps the turn's extraction and queues a reveal check** — one small model call that asks only whether a character a listed secret is kept from finds it out in that turn. Nothing is discarded. Which turns: the same rule as today (ADR 0033 amendment 2). | Today: discard the extraction and extract the turn again (a new model call that words every fact anew). Extract a new chat oldest first (owner: not done; recent memory would fill late). |
| Q2 | What does a reveal check see, and what does it answer? | **What the turn's extraction would see now, minus the rest of its work:** the OPEN SECRETS listed from the served memory before the turn (at most 8, as `secret_hints`), the same CONTEXT and TARGET as a turn extraction (the extractor's context settings), and the extraction prompt's rules for `secrets`. The answer is `{"secrets": [...]}` only, checked as a turn extraction's (`revealed`: a listed secret, characters it is kept from, evidence quoted from the turn) → `learned` rows. **No other facts:** a full extraction also records what the character now knows (`knows`); the check does not. A turn with no open secret before it is checked without a call. | The check also asks for `knows`; the whole extraction prompt with an instruction to report secrets only. |
| Q3 | Where is a check stored, and when does it count? | **As canon facts are (ADR 0047): an extraction of its own generation kind, `reveal`** (key: the extractor's endpoint and model, the reveal prompt, the context settings), stored against the turn's anchor revision under the window `reveal:<turn hash>`, its hints naming the extraction it checked. Its `learned` rows are served with that turn **while the extraction it checked is the one serving the turn**: a rebuild or a re-extraction after a join's undo discards that extraction, and a new extractor generation serves the turn with another, so the check stops counting with it (the new extraction lists the secret when it is made after it; when it is not — a rebuild runs recent turns first — "Extract all history" checks it again, Q4). An earlier request replays with only the checks made by its time (ADR 0027). Migration 0028 adds the kind. | Add the `learned` rows to the checked extraction (no read change, but an extraction would change after it was made, and a replay as of an earlier time would see them). |
| Q4 | When is a turn checked again? | **As today's rule says, with a check counting as seeing the secret:** a turn needs a check when its serving extraction of the active generation was made before an earlier turn's secret was shown and no check of that extraction was made since. Checks run at background priority, oldest turn first (`claim`), so a later turn's OPEN SECRETS leave out what an earlier check found. Running "Extract all history" twice queues nothing the second time. Two workers can still check two neighbouring turns at once (K29's remaining limit, unchanged). | — |
| Q5 | What is a "dropped" fact? | **A narrated fact a re-extraction of the same generation lost, and that the chat's memory no longer holds anywhere:** for each turn of the head whose serving extraction replaced a discarded extraction of the same generation and the same turn hash (a rebuild, a re-extraction after a join's undo, and K29 re-extractions made before this phase), each valid assertion of the replaced extraction (the latest discarded before it) that is narration and not `learned`, that the new extraction does not state again, and that no served narrated assertion of the chat has with the same predicate, subject and object. **Stated again** (revised 2026-10-01 after review, owner's choice): the replaced extraction's facts and the new one's are matched **one to one** — a row of the new extraction restates at most one fact — closest first: (1) the same predicate, subject and object (as entities, ADR 0012) and, for a predicate that accumulates (an event, a trait), the same value; (2) the same predicate, subject and object; (3) the same predicate and subject with a quote sharing a run of 12 characters (ADR 0044 amendment 2), the object worded differently. A quote shared with another character's fact never counts: one sentence that states two characters' occupations restates neither for the other, and one that lists two belongings of one character restates only those the new extraction states. **Read at request of the panel or Inspector, nothing stored.** A new extractor generation is not compared (it words facts its own way, by design); its loss is measured only (Q8). | The same predicate with a shared quote alone (the first draft: another character's fact could hide a drop, review 2026-10-01); every fact the turn lost (also those the chat states elsewhere); an accumulating fact held elsewhere only with the same value (M0 main 81, production's longest chat 127); a match on the whole version key only (119, 162). |
| Q6 | How is it shown? | **In "Needs attention" (panel and Inspector): one row per dropped fact** — "dropped by a re-extraction", its turn, the line as the replaced extraction stated it, and a **Restore** button (Q7). The panel's "This chat" card says how many there are. Nothing on the request path, no HUD line. | A count only; a separate Inspector section without a button. |
| Q7 | What does Restore do? | **An owner repair, `fact_restore` (ADR 0044's rules):** its target is the dropped assertion (the turn, the turn's hash, predicate, subject, object, value, quote); a read adds it back as the owner's version of that fact at its turn, after the turn's other rows, while the turn reads the same; a later statement of the story supersedes it (ADR 0044 Q4). When the turn's serving extraction states it again (Q5's rule), the repair applies nothing and says so. Undo as for every repair. **Never automatic** (the owner's option 3, reconsidered after Q8). | No button (the list only); restore every dropped fact of a turn at once. |
| Q8 | How is it measured? | **Counts only, no model call first:** a read-only tool (`tools/reextract_loss.py`) that reports, per database, the re-extractions compared, the facts stated again, the facts the turn lost and the dropped facts (Q5), by predicate, for the same generation and across generations; run on the restored copies below. **Then one small paid run after the owner's OK for its estimate:** on a copy of the owner's M0 main chat put back as it was before its "Extract all history", the new "Extract all history" with `gemma4:31b` (the copy's extractor): no extraction discarded, the reveal checks' tokens against the 68 re-extractions', the reveals they find against the reveals the re-extraction found, and the M0 case of AGE-25. | Deterministic cases only (no evidence that a real model finds a reveal with the short prompt). |

## Goal

"캐릭터 A는 무슨 일을 해?": the answer was in memory until "Extract all history" threw away the turn's first extraction
to look for a secret's reveal, and the new extraction did not state it again. After this phase looking for a reveal
keeps what the turn's extraction found, and a fact a re-extraction drops is shown to the owner, who can put it back.

## Evidence behind the scope

Measured with read-only queries on local copies (counts only), Q5 as revised, on the head as it is now (each serving
extraction against the latest it replaced): what "Needs attention" would list. Names are compared as text here (case and
spacing aside); the read compares entities, so an alias the chat knows matches and the counts can only fall.

| Copy | Turns compared | Narrated facts | Lost by the turn | Dropped (per chat) |
|---|---|---|---|---|
| Owner's M0 main chat (three-plugin bench, `gemma4:31b`); all 68 by one "Extract all history" (K29) | 68 | 237 | 98 (41 %) | 34 |
| Owner's second M0 chat (same bench, one "Extract all history") | 33 | 135 | 44 (33 %) | 28 |
| The bench's S2 set (same) | 75 | 238 | 180 (76 %) | 100 |
| Restored production copy (`extract-v13`): production's own rebuilds and history extractions, 2026-09-23 to 09-26 | 119 | 496 | 188 (38 %) | 123 (106, 11, 6) |
| The same copy re-extracted with `extract-v14` (those and the copy's own) | 140 | 594 | 212 (36 %) | 98 (53, 33, 6, 6) |

- A third or more of a re-extracted turn's narrated facts do not come back; most of them are stated by another turn,
  and the rest (Q5) leave the chat's memory. Production's longest chat would list 106 today.
- The first draft's rule (a shared quote alone) counted 30, 14, 56, 76 and 70: fewer, because another character's
  fact or another belonging quoting the same sentence hid a drop.
- AGE-25's case is one of the M0 main chat's 34: the turn's first extraction (six rows) narrated character A's
  occupation; its re-extraction (four rows) did not, and the chat kept only a character's claim of it, which the
  packet did not place.
- The M0 main chat's 68 re-extractions used 727,232 input and 85,306 output tokens (the copy's recorded usage, Phase 17).
  A reveal check sends the context, the target and the open secrets, without the extraction rules (13,046 characters)
  or the hints, and answers a short list: its cost is measured in Q8's run, not estimated here.
- Most dropped facts are places (`located_in`) and belongings (`possesses`) — what a re-extraction words as an event or
  leaves out — then events, feelings and knowledge.
- Ranking was ruled out first (AGE-24): a ranking bonus for an occupation question changed nothing on any set.

## In scope (Phase 22)

1. **The reveal check (Q1–Q4):** the `reveal` generation (migration 0028), its job and worker handler, its prompt and
   answer check, the served `learned` rows, "Extract all history" queuing checks instead of discarding, its response
   and the chat's coverage counting checks; ADR 0057 (ADR 0056 is Phase 21's), ADR 0033 amendment 3, K29 updated.
2. **Dropped facts (Q5–Q7):** the read of Q5, "Needs attention" rows in the Inspector and the panel, the panel's count,
   `fact_restore` (migration 0028; ADR 0044 amendment 3), the panel's Restore button; a new plugin build.
3. **Deterministic cases:** the K29 test (`test_extract_all_history_recovers_a_reveal_missed_on_first_import`) passing
   with no extraction discarded; a check without an open secret makes no call; a check stops counting after a rebuild,
   a join's undo re-extraction and a new generation; a second "Extract all history" queues nothing; a replay as of an
   earlier time leaves out a later check; a dropped fact listed, one stated again or held elsewhere not listed, a new
   generation not compared; one quote stating two characters' facts restating neither for the other, and one quote
   listing two belongings restating only the one stated again (Q5's one-to-one match); a restore applied, matching nothing after the turn is edited, applying nothing when the
   turn states it again, undone; an archive with checks and a restore round-trips (ADR 0050); **AGE-25's case end to
   end** on a synthetic chat in its damaged state (a turn's narrated occupation dropped by a re-extraction): the drop
   listed in "Needs attention" → Restore → the occupation in the served packet for "what does A do?" → Undo → gone
   again (review 2026-10-01).
4. **Evaluation (Q8)** and docs: `docs/perf/reextract-loss.md`, `ARCHITECTURE.md` (a decision), README and the Korean
   guide (what "Extract all history" does), CHANGELOG.

## Out of scope (Phase 22)

- Keeping a re-extraction's dropped facts automatically (the owner's option 3, after Q8); extracting a new chat oldest
  first (option 2, not done).
- A new extractor generation (AGE-27's predicate descriptions are `extract-v15`'s); AGE-26 (Phase 21), AGE-28.
- Comparing across extractor generations in the panel (Q5); a reveal check outside "Extract all history".

## Acceptance criteria

- [ ] Every existing test and memory-evaluation case passes; recorded requests replay as they were.
- [ ] The deterministic cases of In scope 3.
- [ ] On the restored copies, the tool's counts recorded (Q8); the M0 main chat's dropped facts include AGE-25's case.
- [ ] On a local copy of the owner's M0 main chat as it is (damaged), no model call: AGE-25's occupation listed as
      dropped, restored, the M0 case's packet holding it, and the repair undone (counts and pass/fail only, nothing of
      the chat in the repository).
- [ ] Q8's paid run (after the owner's OK): no extraction discarded by "Extract all history"; the checks find at
      least the reveals the 68 re-extractions found (each reveal by its secret and character); fewer input and output
      tokens than the re-extractions; AGE-25's M0 case answered.
- [ ] Request-path latency at 10,000 messages unchanged within noise (the served read gains the checks' rows).

## Steps (one pull request each)

1. This document, approved; AGENTS §2 and STATUS name Phase 22 current.
2. The reveal check (In scope 1) with its deterministic cases (ADR 0057, migration 0028).
3. Dropped facts and Restore (In scope 2) with theirs (ADR 0044 amendment 3); a new plugin build.
4. The tool, the evaluation and docs; Phase 22 complete.

Every merge reaches the owner's `:edge`; no tag (AGENTS.md §13). A migration on `main` reaches an `:edge` database
before any release: back up before switching production.

## Stop conditions

Stop and ask the owner when:

- a recorded request replays differently;
- the paid run would exceed its estimate, or the checks find fewer reveals than the re-extractions did;
- "Needs attention" lists more dropped facts on a copy than the table above counts for it;
- the check needs the extraction prompt's other rules to find reveals (a new extractor generation).
