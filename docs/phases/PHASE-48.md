# Phase 48 — Replies only: a per-chat switch that leaves the user's messages out of memory

Status: **draft**, 2026-10-15 (AGE-87). An owner request, not a roadmap stage. Not approved for implementation.
**Q1–Q5 answered (owner, 2026-10-15): Q1 as recommended, Q2 per chat (not as recommended), Q3 decided by the
switch's purpose, Q4 under the rules after 1.0.0, Q5 approved. Q6 (raised by Q2) answered (owner, 2026-10-15): (a), with
the choice the owner's.** Approval to implement is
a separate decision and has not been given.
**After 1.0.0** (R7; the two quiet weeks on the trial install run from 2026-10-13 to at least 2026-10-27): nothing of
this phase lands on the trial install or in a `0.4.x` release. The release that carries it is decided after 1.0.0; a
minor release (`1.1.0`) is proposed, since a migration, a panel control and a generation variant are not a patch.
**Implementation design added 2026-10-15** (below, before the steps), with step 4's read-only count
(`docs/perf/phase48-user-messages.md`).

The owner asked (2026-10-15) for a switch: when it is on, memory comes from the AI's replies only. Asked whether that
meant leaving out only some user messages (out-of-character lines, instructions to the model) or all of them, the
owner chose all of them, behind a toggle. The switch is for **full impersonation**: chats where the AI writes the
persona's lines and actions too (`{{user}}는 "그래, 그렇게 하자." 라고 말하며…`), so the user's own message is mostly a
direction to the model and what happened is in the reply.

**High risk if built** (`AGENTS.md §14`):
- a change to what memory reads select (user messages leave every recall route of a chat with the switch on);
- an extractor generation variant chosen per chat, and a narrower generation fallback for those chats (S3, Q6);
- a migration on stored owner input (the per-chat flag);
- the off path must stay byte-identical, or every install changes without anyone turning anything on.

## Why

1. **In full impersonation a user message is not story.** It carries directions to the model ("길게 써줘",
   "다음 장면으로", "{{user}}가 거절하게"), out-of-character lines and wishes a reroll replaced. The reply is where the
   persona's words and actions are written. Today the directions become facts and excerpts like any other text.
2. **Where user messages enter memory today** (read from the code, 2026-10-15):
   - **Extraction.** The TARGET turn is every member of the turn, the user's message and the reply
     (`extraction.load_context`, `members`). extract-v14's evidence check looks for the quote in what the model saw
     of the TARGET (`shown_target`), so a quote from the user's message passes. Facts are stored against the turn's
     anchor revision, the reply (`assertion.source_revision_id`), so **a read cannot tell which message a fact came
     from**: facts cannot be filtered by role after extraction.
   - **Older turns.** A generation change re-extracts only each chat's recent window (`extract_backfill`, default
     100 turns); older turns are served by the newest earlier generation that has them (ADR 0014 §2).
   - **Summaries** (Phase 12). Scene summaries read the turns with their speakers (`summaries._speaker`).
   - **Recall candidates.** The lexical, keyword, vector and quote routes share the eligibility predicates (not
     disabled, not a comment) in `retrieval.py` and `vectors.vector_candidates`. Each candidate row already carries
     `sr.metadata->>'role'`.
   - **Embeddings.** Every eligible message is embedded.
   - **The active extractor is one key for the install** (`rt["active_extractor"]`, about 18 reads in `api.py`); every
     read already takes the key as a parameter (`facts.served_assertions`).
3. **What the switch does not touch.** Gating still recognizes a main generation by the user's latest input in the
   prompt (ADR 0001), and recall still searches for what the user's latest message asks. The switch decides what is
   remembered, not what is asked. Raw messages are never edited or dropped (invariants 1, 2), and the Inspector still
   shows every message.

## Proposal

S1. **A per-chat flag** (Q2), `conversation.replies_only boolean NOT NULL DEFAULT false`, set through the API like the
memory mode (ADR 0035: `memory_strict`, `memory_narrator`, migration `0021`). Migration `0030` is reserved by the held
Phase 45 and Phase 47 takes the next free number when it is built; this phase takes the next one after. The panel's
**This chat** card (Status tab, ADR 0048) gets a toggle, **AI 답장만 기억 / Remember AI replies only**. Turning it on asks
first, with the recent window's turn count and that it re-extracts them at the provider's cost, and the Q6 choice: the recent window only, or the whole history too, each with its turn count.
Turning it off says that the chat's earlier memory comes back at once (S3). Korean first, English beside it
(`i18n.ts`). The plugin stays light (`nmos-plugin-stays-light`): the counts are the sidecar's.

S2. **Recall (read side).** For a chat with the flag on, a user message is not a candidate on any route (lexical,
keyword, vector, quote): one predicate beside the existing eligibility predicates. Embeddings are still made for every
message, so the projection key does not change and switching never re-embeds. For a chat with the flag off, every read
is the same as on `main`.

S3. **Extraction (write side).**
- **A variant key.** The extractor generation's spec gets a field (`members: "replies"`). `generations.make` hashes the
  spec, so this is a distinct key with the same compiler; the default key does not change.
- **Chosen per chat.** Every read that now takes `rt["active_extractor"]` takes the chat's key instead: the variant
  for a chat with the flag on, the default otherwise. The worker extracts a flagged chat's turns under the variant
  (its jobs carry the variant key) beside the default generation's jobs for every other chat.
- **The TARGET holds the turn's reply only**, and the user's message is not shown to the extractor (Q3). The evidence
  check, which already looks for the quote in the TARGET, refuses anything quoted from the user's message.
  What reads the turn's text (`MIN_CONTENT_CHARS`, `name_pairs`, `revealed`, `normalize`, `coverage_of`) reads the
  reply. A turn with no reply yet extracts nothing.
- **Turning it on** queues the chat's recent window under the variant, at the provider's cost.
- **Older turns** of a flagged chat are never served by a generation that read the user's messages (Q6): ADR 0014's
  fallback, for that chat, considers only replies-only generations. Until the owner extracts them, those turns have no
  facts; their raw replies still come back as excerpts.
- **Turning it off** serves the default generation again at once: its extractions are kept (ADR 0015 keeps superseded
  LLM extractions), so nothing is re-extracted. The variant's rows are kept too, so turning it on again re-extracts only
  turns added or changed since.

S4. **Summaries.** For a flagged chat, a scene summary reads the replies only, under a summary generation variant with
the same spec field, so summaries made from both sides are not served for it.

S5. **Export and restore.** The flag is a column of `conversation`, so a NMOS Archive (ADR 0050) carries it with the
chat; step 2 checks that it round-trips. A restore into a build without the migration is refused as for any newer
schema.

## Out of scope

- Leaving out only some user messages (out-of-character detection, a per-message mark). The owner chose all of them.
- One switch for the whole install (Q2).
- Changing the recall query or gating.
- Deleting or altering raw messages, or their embeddings.
- A translation plugin's markup inside replies (AGE-79): a normalizer change with its own spec.

## Questions for the owner

- **Q1 — which layers the switch governs. Answered (owner, 2026-10-15): (a), all of them.** Recall, extraction and
  summaries, built in that order (steps 2–3).
- **Q2 — one switch or one per chat. Answered (owner, 2026-10-15): per chat** (recommended was one for the install).
  This is what makes S3's per-chat key, the worker's two generations at once, Q6 and the migration part of the phase.
  It also makes turning the switch off free (S3).
- **Q3 — what the extractor sees of the user's message. Decided by the switch's purpose (owner, 2026-10-15): (b),
  nothing of it.** The owner asked for the difference to be settled for full impersonation:
  - (a) *Shown as context, not a source.* Helps only when the reply leans on words it does not repeat ("그 제안",
    "아까 말한 대로"). Costs: every turn's input grows by the user's message; and the direction is in front of the
    model, so a direction the reply did not follow (the reply went elsewhere, or a reroll replaced it) can still shape
    a fact. The evidence check refuses a quote from the message, but not a value read from it beside a quote from the
    reply.
  - (b) *Not shown.* The reply is the only record of what happened, which is what full impersonation means: the reply
    already writes the persona's words and actions. Cost: a reply that only makes sense with the message loses that
    context. In full impersonation that is the rarer case.
  - Step 4 checks the choice on the same turns: (b), and (a) beside it as a comparison only, counting the reply-stated
    facts (a) finds that (b) misses. If (b) misses any, stop and report before going on.
- **Q4 — the one-generation-per-milestone rule. Answered (owner, 2026-10-15): this is after 1.0.0, so it follows the
  release rules in force then.** `AGENTS.md §13` defines the cadence before 1.0.0 only. The variant is opt-in per chat
  and leaves the default key unchanged, so no other chat re-extracts; it is built on the compiler current when it is
  implemented (if `extract-v17`, Phase 45, lands first, the variant follows it).
- **Q5 — the gate. Answered (owner, 2026-10-15): approved as recommended.** The recall part: a zero-call replay with
  the flag off (identical to `main`, three rounds) and on (which probes change). The extraction part: a reduced paid
  run instead of the full live gate, on one gate chat's copy with the flag on, its probes scored; the cost estimated and
  approved before the run (with Q3's comparison arm in the estimate).
- **Q6 — older turns of a flagged chat (raised by Q2). Answered (owner, 2026-10-15): (a), as long as the owner has
  the choice.** Turning the switch on asks: the recent window only, or the whole history too, each with its turn
  count; the owner can also extract the history later from the Inspector. Beyond the recent window, ADR 0014 serves a turn from
  the default generation, which read the user's messages, so the directions would stay in the chat's older memory.
  - (a) **Recommended:** no fallback to a generation that read the user's messages. A flagged chat's older turns have
    no facts until they are extracted under the variant; turning the switch on offers **"전체 기록도 다시 추출"**
    (the existing extract-all-history, `POST /v1/conversations/{id}/extract-history`) with its turn count. Raw replies
    still come back as excerpts meanwhile. Clean, and the owner decides the cost per chat.
  - (b) Fallback as now, the older facts marked in the Inspector as made from both sides. Nothing lost and nothing
    paid, but the old directions keep reaching the packet until the history is extracted.
  - (c) Turning it on always queues the whole history. Clean at once, but a long chat's cost is paid without a choice.

## Implementation design (2026-10-15)

Written before approval, so the build after 1.0.0 starts from known edits. It does not authorize them. Paths are as
of `main` `7d89a39`; the build re-checks them.

**Measured first** (`docs/perf/phase48-user-messages.md`, read only, the trial install's 10 chats): 4 of 632 served
facts (0.6 %) have evidence found only in a user message; 210 of 817 recorded excerpts (26 %) are user messages, in 88
of 109 packets with excerpts (81 %). On this data the switch shows on the read side. Whether these chats are full
impersonation was not checked, so the paid run uses a chat the owner names as one.

D1. **The flag.** Migration (next free number when built; `0030` is reserved by Phase 45 and Phase 47 takes the next):
`ALTER TABLE conversation ADD COLUMN replies_only boolean NOT NULL DEFAULT false`. No backfill, no rewrite. Archives
already export `conversation` rows (`archive.py` `Table("conversation", …)`); step 2 proves the column round-trips.

D2. **The API.** `GET /v1/conversations/{id}/replies-only` → `{on, recent_turns, history_turns}` (the counts the
confirm shows: turns the recent window would re-extract, and the rest of the head). `PUT` with `{on, history}` where
`history` is `"recent"` or `"all"` (Q6). Its own endpoint, not a field of the memory mode (ADR 0035), so memory-mode
clients are unchanged. The PUT is one transaction: set the flag, then queue (D6). A 409 when fact extraction is off and
the flag is turned on: the read side alone would serve the default generation's facts, the case Q6 rules out.

D3. **One eligibility clause for recall.** Every recall SQL that now repeats the eligibility predicates (`disabled`,
`isComment`) gets the same clause, `AND NOT (%(replies)s AND sr.metadata->>'role' = 'user')`:
- `retrieval._MATCHES_HEAD` (lexical; its users `_MATCHES` and the count beside it);
- the keyword route's query (`holds`, near the end of `retrieval.py`);
- `retrieval._turn_messages` and `retrieval._first_met` (the source-turn quotes and "at first", PHASE-21/33);
- `vectors.vector_candidates`.
`RecallOptions` gets `replies_only`, set per request where the memory mode is already set
(`dataclasses.replace(options, strict=conv.memory_strict, …)` in the retrieve path). The parameter is a plain boolean,
so the plans stay the same when it is false; step 2's latency check covers the true case.

D4. **The per-chat extractor key.**
- The variant is `generations.make(...)` with the default extractor's spec plus `members: "replies"`, built beside
  `extraction.extractor(settings)` and kept in the runtime as `rt["extractor_replies"]`.
- **A trap to close first:** `projection_generation.activated_at` defaults to `now()` (migration `0008`), so merely
  registering the variant (`generations.ensure`) would make it the most recently activated generation, and
  `generations.active(conn, "extract")` would return it for the whole install. `active()` and every "most recently
  activated" ordering must leave out generations whose spec has `members` (`spec->>'members' IS NULL`); the variant is
  registered with `ensure` and never `activate`d. A test pins it: after the variant is registered, the active key and
  every unflagged chat's packet are unchanged.
- A helper `extractor_key(conn, conv)` returns the variant key for a flagged chat and the active key otherwise. The
  reads that now take `rt["active_extractor"]` (about 18 in `api.py`: memory view, Inspector pages, held aliases,
  dropped facts, coverage, preview) take it, and so does the retrieve path's `RecallOptions.extractor_key`.
- **Fallback (Q6).** The fact read (`facts.ACTIVE_ASSERTIONS_TEMPLATE`, window `w`) and the serving read
  (`extraction.SERVING_EXTRACTIONS`) choose per turn among all generations. Both get
  `AND (g.spec->>'members' = 'replies') = %(replies)s`: a flagged chat sees only replies-only generations (of any
  compiler, so a later compiler's variant can still fall back to an earlier variant), and an unflagged chat never sees
  a variant's rows. Coverage counts the same way, so a flagged chat's not-yet-extracted history shows as not covered.

D5. **The extractor's input** (Q3 (b)). `load_context` loads members and context as now; for the variant,
`members` keeps the turn's `char` messages and `context` keeps the earlier turns' `char` messages only. Leaving the
earlier turns' user messages in CONTEXT would bring the directions back one turn later, which Q3 rules out. Everything
that reads the turn text (`turn_text`, `shown_target`, `MIN_CONTENT_CHARS`, `name_pairs`, `revealed`, `normalize`,
`coverage_of`) then reads the replies without further change. The extraction row's `members` still lists the whole
turn (provenance), and its `coverage` records that the user's message was left out. A turn with no reply returns no
call. The prompt text is unchanged; only its input is, which is why the spec field, not a compiler bump, makes the key.

D6. **Queueing.** `extraction.schedule_generation(conn, key, backfill, conv, history=…)` already queues one chat:
turning the flag on calls it with the variant key and `history=(history == "all")`. Every other place that queues a
chat's extraction (first sight and live turns after a sync, `extract-history`, the per-chat rebuild) takes
`extractor_key(conn, conv)`. Turning the flag off queues nothing: the default generation's kept rows serve at once
(ADR 0015), and the variant's rows stay for the next time.

D7. **The worker.** `claim` already matches `kind || '|' || generation` against a list. `worker.handlers` becomes a
map keyed by `(kind, key)` with the variant's extract handler beside the default one, both on the same model client;
`run_once` dispatches by the job's kind and generation. A job of a key no handler has still waits, as now.

D8. **Summaries and reveal checks.** The summary generation (`summaries.summarizer`) and the reveal-check generation
(`reveals.generation`) read turns too: each gets the same spec field and its own variant, scheduled per chat the same
way, with replies-only turn input, and the same rule as D4 keeps each variant out of
`generations.active` and out of an unflagged chat's reads. Canon facts read the lorebook, not turns, and are unchanged.

D9. **The panel.** The **This chat** card (ADR 0048, `ui.ts`) gets the toggle. Turning it on opens a confirm with
the two counts from D2 and two choices, **최근 N턴만 다시 추출** and **전체 기록까지 다시 추출 (N턴)**, and the cost note.
Turning it off says the earlier memory is back at once. Strings in `i18n.ts`, Korean first. The plugin only calls the
two endpoints; counts and queueing are the sidecar's.

D10. **What is not touched.** Embeddings and their projection key; the recall query and gating; the packet policy;
raw rows; the Inspector's message list (it still shows the user's messages, with no "used" mark in this phase).

**Test list by step.**
- Step 2 (D1–D3, D9): the flag defaults off and round-trips through an archive; with it off, every route returns what
  `main` returns on the same synthetic chat; with it on, no `user` revision on any of the five routes; another chat in
  the same database unchanged; no embedding job queued by either switch; the confirm's counts.
- Step 3 (D4–D8): the activation trap (above); the per-chat key in the retrieve path and the API reads; fallback both
  ways (a flagged chat never serves a default row; an unflagged chat never serves a variant row, including after the
  flag is turned off); the stub extractor's quote from a user message refused and from the reply kept; CONTEXT without
  user messages; on → off → on queues the window, nothing, then only new or changed turns; summaries and reveal
  checks under their variants; the worker running both extract keys.

## Steps

1. This spec, and the owner's answers.
2. **The flag and recall.** The migration, the API (read and set, like the memory mode), the read-side predicate on
   every route, the This chat toggle and its confirm, the archive round-trip and tests:
   - with the flag off, every route and packet is identical to `main`;
   - with it on, no user-message revision is a candidate or an excerpt on any route of that chat, other chats are
     unchanged, and the query and gating are unchanged;
   - switching does not queue embedding jobs.
3. **Extraction and summaries.** The spec field, the per-chat key in every read, the worker's jobs under two
   generations, the TARGET without the user's message, Q6's fallback rule, the summary input and tests with the stub
   extractor:
   - a fact quoted only from the user's message is not recorded; a fact quoted from the reply is;
   - the default extractor and summary keys are unchanged; the variant's keys differ;
   - flag on → off → on: what each switch queues (on: the recent window, then only new turns; off: nothing);
   - another chat's facts, coverage and jobs are unchanged by one chat's switch;
   - a flagged chat's older turns follow Q6.
4. **Measurement.**
   - A read-only count: of the current facts, how many have evidence found only in a user message (the size of what
     the switch drops). Numbers only. **Done 2026-10-15 on the trial install's database, read only**
     (`docs/perf/phase48-user-messages.md`): 4 of 632 facts; 210 of 817 excerpts. Repeated on the paid run's chat.
   - The zero-call replay of Q5.
   - The reduced paid run of Q5 with Q3's comparison arm, after the owner approves its estimate.
5. **Docs.** An ADR (next free number), `docs/KNOWN-ISSUES.md` (a reply that leans on the user's message loses that
   context; Q6's older turns), the README and `docs/guide.ko.md`, `docs/STATUS.md`.

## Acceptance criteria

1. With every flag off, a replay of every gate probe is identical to `main` before this phase (three rounds), and the
   extractor, embedding and summary keys are unchanged.
2. With the flag on, on a synthetic chat, no packet excerpt or quote comes from a user message, the recall query and
   the gating decision are the same as with it off, and a second chat without the flag is unchanged.
3. With the flag on, the stub extractor's fact quoted from the user's message is refused and its fact quoted from the
   reply is kept.
4. Switching on queues the chat's recent window, and the whole history only when the owner chooses it (Q6); a
   flagged chat's older turns never show a fact from a generation that read the user's messages; switching off queues nothing and
   serves the default generation at once; neither queues an embedding job.
5. A retrieve at 10,000 messages costs at most +5 ms p50 over `main` with the flag on.
6. Step 4's count of facts the switch drops, and Q3's comparison, are reported before the switch is offered in a
   release.
7. Export → restore round-trips the flag.

## Stop conditions

- The off path changes any packet, or any default generation key. Stop and diagnose.
- The variant cannot be made without changing the default key. Stop and ask.
- With the flag on, a fact quoted from the reply is lost in the stub tests, or Q3's comparison finds reply-stated
  facts that (b) misses. Stop and report.
- One chat's switch changes another chat's facts, coverage or jobs. Stop and diagnose.
- The paid run's cost passes its approved estimate by more than half. Stop and report.

## Evidence rules

The repository is public. Tests and fixtures use synthetic names and invented chats only. Measurements on copies of
the owner's data report numbers, never chat content.
