# Phase 48 — Replies only: an owner switch that leaves the user's messages out of memory

Status: **draft**, 2026-10-15. An owner request, not a roadmap stage. Not approved for implementation.
**After 1.0** (R7; the two quiet weeks on the trial install run from 2026-10-13 to at least 2026-10-27): nothing of
this phase lands on the trial install or in a `0.4.x` release before that gate closes.

The owner asked (2026-10-15) for a switch: when it is on, memory comes from the AI's replies only. Asked whether that
meant leaving out only some user messages (out-of-character lines, instructions to the model) or all of them, the
owner chose all of them, behind a toggle.

**High risk if built** (`AGENTS.md §14`):
- a change to what memory reads select (user messages leave every recall route while the switch is on);
- an extractor generation variant: the switch changes what the extractor may record, and turning it on re-extracts;
- the off path must stay byte-identical, or every install changes without anyone turning anything on.

## Why

1. **A user message is not always story.** It carries out-of-character lines, directions to the model ("길게 써줘",
   "다음 장면으로"), wishes a reroll replaced and drafts the reply rewrites. Some owners treat only the reply as what
   happened. Today such text becomes facts and excerpts like any other.
2. **Where user messages enter memory today** (read from the code, 2026-10-15):
   - **Extraction.** The TARGET turn is every member of the turn, the user's message and the reply
     (`extraction.load_context`, `members`). extract-v14's evidence check looks for the quote in what the model saw
     of the TARGET (`shown_target`), so a quote from the user's message passes. Facts are stored against the turn's
     anchor revision, the reply (`assertion.source_revision_id`), so **a read cannot tell which message a fact came
     from**: facts cannot be filtered by role after extraction.
   - **Summaries** (Phase 12). Scene summaries read the turns with their speakers (`summaries._speaker`).
   - **Recall candidates.** The lexical, keyword, vector and quote routes share the eligibility predicates (not
     disabled, not a comment) in `retrieval.py` and `vectors.vector_candidates`. Each candidate row already carries
     `sr.metadata->>'role'`.
   - **Embeddings.** Every eligible message is embedded.
3. **What the switch does not touch.** Gating still recognizes a main generation by the user's latest input in the
   prompt (ADR 0001), and recall still searches for what the user's latest message asks. The switch decides what is
   remembered, not what is asked. Raw messages are never edited or dropped (invariants 1, 2), and the Inspector still
   shows every message.

## Proposal

S1. **A setting, `replies_only`** (boolean, default off), editable at runtime (`runtime.EDITABLE`), one value for the
whole install (Q2). The panel's settings get a toggle, **AI 답장만 기억 / Remember AI replies only**, with two
lines under it: the persona's own actions and words are then remembered only when a reply states them, and turning
it on re-extracts each chat's recent window at the provider's cost (S3).

S2. **Recall (read side).** With the switch on, a user message is not a candidate on any route (lexical, keyword,
vector, quote): one predicate beside the existing eligibility predicates. Embeddings are still made for every
message, so the projection key does not change and switching is instant both ways, with no re-embedding. With the
switch off, every read is the same as on `main`.

S3. **Extraction (write side).** With the switch on, the extractor generation's spec gets a field
(`members: "replies"`). `generations.make` hashes the spec, so this is a distinct key with the same compiler; the
default key does not change.
- The TARGET holds the turn's reply only. The user's message is shown before it as context, labelled as what the
  reply answers and not a source of facts (Q3). The evidence check, which already looks for the quote in the TARGET,
  then refuses a quote from the user's message without asking the model to behave.
- What reads the turn's text (`MIN_CONTENT_CHARS`, `name_pairs`, `revealed`, `normalize`, `coverage_of`) reads the
  reply. A turn with no reply yet extracts nothing.
- Turning the switch on activates the variant: each chat's recent window (`extract_backfill`) is re-extracted at the
  provider's cost, as for any new generation (ADR 0006). Turning it off reactivates the default generation. Step 3
  checks whether that generation's kept rows are served again without re-extraction (ADR 0015) and reports either way.

S4. **Summaries.** With the switch on, a scene summary reads the replies only. The summary generation's spec gets
the same field, so summaries made from both sides are not served as replies-only ones.

S5. **Export and restore.** Step 2 checks whether a NMOS Archive (ADR 0050) carries runtime settings. If it does, the
switch round-trips; if not, a restored install starts with it off, and the README says so.

## Out of scope

- Leaving out only some user messages (out-of-character detection, a per-message mark). The owner chose all of them.
- A switch per chat, unless Q2 says otherwise.
- Changing the recall query or gating.
- Deleting or altering raw messages, or their embeddings.
- A translation plugin's markup inside replies (AGE-79): a normalizer change with its own spec.

## Questions for the owner

- **Q1 — which layers the switch governs.**
  - (a) **Recommended:** recall, extraction and summaries, built in that order (steps 2–3). Only this does what was
    asked: without the extraction side, what a user message said still becomes facts.
  - (b) Recall only. No re-extraction and nothing paid, but facts from user messages stay.
  - (c) Extraction and summaries only. The user's messages still come back as excerpts.
- **Q2 — one switch or one per chat.** Recommended: one for the install. Writing out-of-character lines is a habit of
  the owner, not of a chat, and a per-chat switch would re-extract chat by chat with a cost each owner has to follow.
- **Q3 — what the extractor sees of the user's message when the switch is on.**
  - (a) **Recommended:** the message as context, labelled not a source. A reply like "그래, 그렇게 하자" only makes
    sense with what it answers, and the evidence check keeps the message's own words out of the facts.
  - (b) Nothing of it. The model may then misread who did what in the reply.
- **Q4 — the one-generation-per-milestone rule (`AGENTS.md §13`).** Recommended: the variant is opt-in and leaves the
  default key unchanged, so it does not count as the release's generation; an owner who turns it on pays one
  recent-window re-extraction. It is built on the compiler current when it is implemented: if `extract-v17`
  (Phase 45, held) lands first, the variant follows it.
- **Q5 — the gate.** The recall part is recall-only (`AGENTS.md §7.6`): a zero-call replay with the switch off
  (identical to `main`, three rounds) and on (which probes change). The extraction part is an extraction change,
  which calls for the full live gate. Recommended: since the default path does not change, a reduced paid run instead:
  one gate chat's copy re-extracted with the switch on, its probes scored, the cost estimated and approved before
  the run. Say if the owner wants the full live gate.

## Steps

1. This spec, and the owner's answers.
2. **Setting and recall.** `replies_only` in `runtime.EDITABLE`, the read-side predicate on every route, the panel
   toggle (Korean first, English beside it, `i18n.ts`), the archive check (S5) and tests:
   - with the switch off, every route and packet is identical to `main`;
   - with it on, no user-message revision is a candidate or an excerpt on any route, and the query and gating are
     unchanged;
   - switching does not queue embedding jobs.
3. **Extraction and summaries.** The spec field, the TARGET split, the summary input and tests with the stub
   extractor:
   - a fact quoted only from the user's message is not recorded; a fact quoted from the reply is;
   - the default extractor and summary keys are unchanged; the variant's keys differ;
   - on → off → on: what each switch queues, and whether kept rows are served again.
4. **Measurement.**
   - A read-only count on a copy: of the current facts, how many have evidence found only in a user message (the
     size of what the switch drops). Numbers only.
   - The zero-call replay of Q5.
   - The reduced paid run of Q5, after the owner approves its estimate.
5. **Docs.** An ADR (next free number), `docs/KNOWN-ISSUES.md` (the persona's actions need a reply to state them),
   the README's settings section and `docs/guide.ko.md`, `docs/STATUS.md`.

## Acceptance criteria

1. With the switch off, a replay of every gate probe is identical to `main` before this phase (three rounds), and
   the extractor, embedding and summary keys are unchanged.
2. With the switch on, on a synthetic chat, no packet excerpt or quote comes from a user message, and the recall
   query and the gating decision are the same as with it off.
3. With the switch on, the stub extractor's fact quoted from the user's message is refused and its fact quoted from
   the reply is kept.
4. Switching on and off queues no embedding job. What extraction re-runs on each switch is measured and reported.
5. A retrieve at 10,000 messages costs at most +5 ms p50 over `main` with the switch on.
6. Step 4's count of facts the switch drops is reported before the paid run.

## Stop conditions

- The off path changes any packet, or any default generation key. Stop and diagnose.
- The variant cannot be made without changing the default key. Stop and ask.
- With the switch on, a fact quoted from the reply is lost in the stub tests. Stop and report.
- The paid run's cost passes its approved estimate by more than half. Stop and report.

## Evidence rules

The repository is public. Tests and fixtures use synthetic names and invented chats only. Measurements on copies of
the owner's data report numbers, never chat content.
