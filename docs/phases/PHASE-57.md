# Phase 57 — Pay once: canon read once per input, a model change carries on, and the Inspector's queue in bulk

Status: **approved**, 2026-11-08; PR A (steps 2–3) built 2026-11-08 (ADR 0078, ADR 0079, migration `0033`); PR B (step 4) built 2026-11-08 (ADR 0080, migration `0034`, amendment 1) (an owner request, not a roadmap stage; after `1.0.0`). The owner chose the shape in
the design conversation of 2026-11-08: canon read once for every chat that sends the model the same input, a rebuild
re-reading only its own chat; ADR 0014's fallback for summaries too; canon's re-read on a model change made a choice;
a "carry on" option when the model changes; and in the Inspector's **Needs attention**, a bulk apply and retract, and a
correction on a conflicting fact. Q1–Q5 answered as recommended and the spec approved for implementation (owner, 2026-11-08: "승인, 구현 시작"). Linear: to be filed.

**High risk if built** (`AGENTS.md §14`):
- **memory selection across generations:** summaries are served from an earlier generation (A2), and a model change
  queues nothing by default (A3), so a packet holds more text an earlier model wrote;
- **canonical memory copied between chats:** a canon extraction is copied from another conversation's (A1), so one
  chat's memory comes from a model call another chat paid for;
- **owner repairs in bulk:** one action writes many repairs (B1), and a correction now reaches a canon fact from the
  conflict row (B2);
- **two migrations** (A1's lookup index, B1's batch id).

Invariants it touches (`AGENTS.md §3`): **derived rows carry their generation and members** (a copied extraction is a
row of this chat's revision with the source it was copied from, A1); **raw text is never replaced**; **owner repairs
store what the item says and survive rebuilds** (ADR 0044; a batch is a set of ordinary repairs, B1).

## Why

Read from the code (`main` at `a70b022`).

1. **Canon is read again for every chat.** Canon is per conversation (ADR 0045, "a card shared by several chats is kept
   once per chat"): each chat's card fields, persona, author's note and lorebook entries are its own revisions, and
   `canonfacts.process` calls the model for every part of every revision no extraction of the chat's covers. A new chat
   with a bot already played pays for its card again (on sample 2: the card, the persona and 45 always-active entries,
   ADR 0047's consequences), though the model sees the same input.
2. **A model change re-pays summaries and canon in full.** The extraction, summary, canon and reveal generations all
   hash `llm_url` and `llm_model` (`generations.make`), so changing the model changes all four. `api.activate` then:
   - queues the latest `extract_backfill` (100) turns of every chat for the new extractor, older turns served by the
     earlier generation (ADR 0014);
   - queues **every** due window of every chat for the new summarizer (`summaries.schedule_all`), and a summary is read
     from the active generation only (`summaries._scenes`, `_story`: `generation = key`), so until the worker catches up
     a chat has no scene summaries and no story so far;
   - queues **every** chat's canon in force for the new canon generation (`canonfacts.schedule`), although canon facts
     are already served by the most recently activated generation that read a revision (`canonfacts.ROWS`, `chosen`).
   An owner who changes the model because the old one ran out of quota (the case that started this phase) pays most
   when they can least.
3. **The Inspector's queue is one row at a time.** Each row of **Needs attention** (`inspector._attention`) has its own
   repair button and `POST /v1/conversations/{id}/repairs` takes one repair. A chat with forty dropped facts after a
   re-extraction takes forty presses.
4. **A conflict can be retracted or locked, not corrected.** `fact_correct` exists (ADR 0044 item 8) and the facts list
   offers it (`inspector._corrections`), but a conflict row offers only *keep canon's* (`fact_lock`), *keep the
   story's* (`fact_retract` of canon's statement) or *retract* / *undo*. When both statements are a little wrong, the
   owner leaves the row, finds the fact in the list and corrects it there.

## Goal

A chat started with a bot NMOS already read costs no canon call for what it sends the same way; changing the model
re-pays nothing unless the owner asks; and the owner can settle **Needs attention** many rows at a time, correcting a
conflicting statement where the conflict is shown.

## Scope

### Part A — pay once (PR A)

A1. **Canon read once per input.** Before a part of a canon revision is sent to the model, `canonfacts.process` looks
for an extraction that answered the same call:
- **The same call** is the canon generation key (it hashes the version, prompt, predicates, normalizer, model settings
  and part size, ADR 0047 item 1) and, of the part's user message, what a chat's own rows already treat as the input
  (the window's `wtag`, ADR 0047 item 1): the source line (`describe`: the text's kind, an entry's comment and keys),
  the part number and count, and the part's text after the macros are replaced; the `CHARACTER` and `USER` lines
  **only when the text uses the name macros** (`wtag` is the names tag, not `plain`). `build_prompt` writes both names
  into every message, but a chat already keeps a `plain` text's read when its persona is renamed (ADR 0047), so a
  `plain` text read for another persona's chat is the same read. The fingerprint (`generations.fingerprint` of those
  fields, in that order) is recorded in the extraction's `coverage` as `input`.
- **A match** is a canon extraction of any conversation with that generation key and that `input`, not discarded, the
  newest first. The part is then not sent: the extraction is **copied** into this chat's revision (same window, the
  matched assertions with their statuses, `usage` zero calls, `raw` = `{"reused_from": <extraction id>}`), in the same
  transaction and with the same job guard as a model answer. Copying, not sharing, keeps each chat's rows its own:
  its repairs, locks and retractions (ADR 0044, per conversation), its rebuild and its audit are unchanged.
- **Only what recorded its input is a source.** Extractions made before this phase did not record the message they
  sent, and the normalizer may have changed since, so their fingerprint is not computed after the fact: the first chat
  after the upgrade reads its canon once more, and the chats after it reuse that read.
- **A rebuild reads its own chat again** (owner, 2026-11-08). "Rebuild memory" discards the chat's canon extractions
  (ADR 0047 item 1) and queues its canon with `fresh: true`: those jobs skip the lookup and call the model. No other
  chat's rows change; a later chat may reuse the fresh read, as the newest match. A copy is the copying chat's own
  row, so a read that was wrong in the chat it came from stays in every chat that copied it until each is rebuilt.
- The Inspector's canon coverage counts copied parts apart from called ones ("reused from another chat").

A2. **Summaries served from an earlier generation (ADR 0014 for summaries).** Per due window, the scene summary is the
active summarizer's for the window's key, else the one of the most recently activated earlier `summarize` generation
for the same key, not discarded; one generation per window. The story so far is the newest story whose members are all
among the served scene summaries, the active generation's first. The read-side checks (`held`, `leaks`, the secrets
listed) apply to a served summary whatever made it. The Inspector's summary coverage shows windows by the active
generation, by an earlier one (named) and none, as extraction's does. A story is queued only when no served story is
made from every served scene, so a switch with every window served queues no story.

A3. **What a model change queues: the owner's choice** (Q1, owner 2026-11-08: chosen when the model is changed, carry
on by default).
- **A model change** is a new generation whose spec differs from the active one's only in `model` or `endpoint`
  (`generations.make` keeps them apart from the version, prompt and settings). A change of version or prompt, which a
  release brings, keeps its own policy (Q5). A change is found against the active generation the database records
  (`generations.active`), at startup as on a save: today startup calls `activate` with no previous keys and so queues
  the backfill, every summary window and every chat's canon again for the active generations on each start.
- **The panel asks** when **Save** changes the extraction model or endpoint: **이어쓰기 / Carry on** (selected) or
  **최근 N턴 다시 / Redo the latest N turns** (N = `extract_backfill`), and a checkbox **원전도 새 모델로 다시 읽기 /
  Read the setting again with the new model**, off. Under the choice, the number of jobs each would queue, counted
  before saving (`POST /v1/config/preview`, no model call).
- **Carry on** queues only what no generation covers: a recent-window turn no extraction of any generation serves, a
  due window no generation summarized, a canon text no canon generation read. New turns are extracted, summarized and
  read by the new model as they come. Everything else is served by the generation that made it (ADR 0014, A2,
  `canonfacts.ROWS`).
- **Redo the latest N turns** queues today's extraction backfill and the due windows those turns fall in.
- **The canon checkbox** queues every chat's canon in force, as today.
- **Only the save that chose them redoes anything.** The jobs that save queues stay in the queue across restarts. Every
  other scheduler queues only what no generation serves (no extraction, summary or canon read of any non-discarded
  generation): startup with no generation change, a sync (an edit, a swipe or a delete runs `summaries.schedule` over
  every window, which today looks for the active key's summaries only), a manifest applied or a lorebook entry held for
  the first time (`canonfacts.schedule`, which today queues every text of the chat the active canon generation has not
  read). Explicit actions keep queuing for the active generation: "extract all history", "rebuild memory", the
  re-extraction of joined turns, and raising `extract_backfill` in the settings.
- `PUT /v1/config` takes the choice as `on_model_change: {"mode": "continue" | "recent", "canon": bool}`, used for that
  save and not stored. A model change that does not come with a choice (an environment variable at startup, an older
  plugin, a script) is **carry on** without the canon.
- Switching back to a model used before needs nothing new: its generation becomes active again with what it made.
- "Extract all history" (per chat) also queues that chat's windows an earlier summarizer serves, as the explicit way to
  bring a chat to the new model.

Embeddings keep D20 (re-embed everything on an embedding change; vector spaces do not mix, ADR 0014 item 5).

### Part B — the queue in bulk (PR B)

B1. **Select, then apply or retract** (Q2, owner 2026-11-08: checkboxes and a selection). In the panel's **Needs
attention**:
- Each row with an action has a checkbox, and each kind's heading a **전부 선택 / Select all**. Under the list, **선택
  적용 (n) / Apply selected** and **선택 철회 (n) / Retract selected**.
- **Apply** is the row's offered action: a stale thread is closed with its kind's default ending, a dropped fact or a
  held role ending restored, a held alias joined, a canon conflict kept as canon's (lock), a status flag dismissed.
  **Retract** retracts the row's fact: a role ending applied automatically, the story's side of a story conflict (or the
  undo of the owner's correction there), canon's side of a canon conflict (the story's kept), the undo of a repair that
  matches nothing.
- A selected row that has no such action is skipped. Before anything is written the panel shows what will happen
  ("12 restored, 3 locked, 2 skipped") and the owner confirms.
- `POST /v1/conversations/{id}/repairs/batch` (`{"items": [RepairRequest, ...], "preview": bool}`, at most 200 items)
  plans every item with `repairs.plan` against one read of the chat's memory, in one transaction: all are written or,
  if one cannot be planned, none, with each item's error. The repairs written share a `batch_id`. The repairs table
  shows a batch as one line with **일괄 되돌리기 / Undo all**, which removes its repairs together; each stays undoable
  on its own.
- The browser tab stays without repair buttons (H15); the bulk controls are the panel's. The plugin holds the
  selection and sends the list; what each row's action is, the planning and the preview are the sidecar's
  (`nmos-plugin-stays-light`).

B2. **Correct a conflicting fact where it is shown** (Q3, owner 2026-11-08: both sides). A conflict row of **Needs
attention** and of the **Conflicts** section offers **정정 / Correct** for each statement, with the fields
`inspector._corrections` allows (object, value): the story's statement and the other side, canon's or the story's.
Correcting canon's statement is a `fact_correct` of the canon fact, in this chat only, as a lock or a retraction is
(ADR 0047 item 4). A correction that makes the two statements agree takes the row away; one that does not leaves it,
with the owner's version on its side.

## Out of scope

- Sharing canon facts between chats as one set of rows, or a card-level memory (A1 copies per chat).
- Reusing message extractions between chats (AGE-84's content-fingerprint experiment, `exp/age84-85-copy-basis`, stays
  an experiment).
- A different extraction model per chat, or a model for summaries apart from extraction's.
- Embedding generations (D20 stays).
- Bulk correction (a correction needs the owner's words per item), bulk actions in the browser tab, bulk across chats.
- Any extraction prompt, generation key, predicate or packet policy change.

## Questions and proposed answers

- **Q1 — what a model change queues. Answered (owner, 2026-11-08): (a).** (a) Chosen at the change, carry on by default
  (A3). (b) Chosen at the change, the latest 100 turns by default. (c) Always carry on.
- **Q2 — bulk shape. Answered (owner, 2026-11-08): (a).** (a) A checkbox per row, select all per kind, apply or retract
  the selection after a preview (B1). (b) One "all" button per kind.
- **Q3 — what a conflict correction reaches. Answered (owner, 2026-11-08): (a).** (a) Both statements, canon's in this
  chat only (B2). (b) The story's only.
- **Q4 — documents and pull requests. Answered (owner, 2026-11-08): (a).** (a) One phase, two pull requests (A and B,
  independent). (b) Two phases. (c) One pull request.
- **Q5 — a release's generation change (a new version or prompt, not a model). Answered (owner, 2026-11-08): (a).** Today: the latest 100 turns, every
  summary window, every chat's canon. **(a) Recommended:** facts unchanged (the latest `extract_backfill` turns),
  summaries the due windows those turns fall in (A2 serves the rest), canon unchanged (every chat's canon, since a new
  canon prompt is why a release changes it). (b) Everything as today, A2's fallback only serving while the backfill
  runs. (c) As a model change: the owner's choice, carry on by default.

## Amendment 1 (2026-11-08, from the code, before PR B): what a batch leaves out, and canon's correction locks

- **One at a time stays one at a time.** A held alias's join is an entity link (ADR 0025) that re-extracts the joined
  turns and is made from its preview; a name split, a "not a character" and their undos are made from theirs too
  (PHASE-20 Q4, PHASE-47 S4). B1's Apply does not join a held alias: such rows carry no checkbox, and the batch refuses
  these kinds. Every other row kind of B1 is in.
- **Correcting canon's statement keeps it.** A correction of a canon fact is an owner's version at the canon's turn;
  the story's later statement would supersede it at once, and the row would leave while the two still disagree. B2's
  correction of canon's side is therefore the correction and a lock on it, in one transaction (`lock: true`): canon's
  statement, as corrected, stays current. Correcting the story's statement is an ordinary correction.

## Steps

1. This spec (docs only), for the owner's approval.
2. **PR A, summaries and the model change.** ADR 0078 (amends ADR 0014 and ADR 0042): A2's read and coverage, A3's
   classification, the three queues, `on_model_change` and `POST /v1/config/preview`, Q5's policy; the panel's choice
   and counts (plugin, `dist/` rebuilt). Tests: a window served by an earlier generation, one generation per window,
   a story from mixed scenes, `held` on a served older summary, carry on queues nothing on a fully covered chat and the
   uncovered rows on a partial one, redo queues the window's turns and windows, the canon checkbox, a version change
   keeps Q5's policy, switching back, a config save without a choice, an older plugin's save byte-identical; after
   carry on, a restart queues nothing, a new message queues its own turn and window only, a swipe or an edit queues the
   windows it changed only, a card edit queues the changed text only; the explicit actions still queue for the active
   generation.
3. **PR A, canon read once.** ADR 0079 (amends ADR 0045's consequence and ADR 0047 item 1); migration `0033`: an index on
   canon extractions' `(extractor_key, coverage->>'input')`. A1's fingerprint, lookup, copy and `fresh`; coverage's
   "reused" count. Tests: a second chat with the same card makes no call and gets the same assertions; a different
   persona name re-reads the texts that use the name macros and copies the plain ones (the names tag `wtag` holds both names, as within a chat, ADR 0047); another description of the same text re-reads it; a
   discarded source is not used; a rebuild calls the model for its chat only and leaves the other chat's rows; a repair
   in one chat does not reach the other; a stopped read goes on with the parts it lacks.
4. **PR B, bulk and correction.** ADR 0080 (amends ADR 0044); migration `0034`: `owner_repair.batch_id`. B1's endpoint,
   preview and undo; the rows' checkboxes and actions as data the panel reads; B2's correction buttons; the panel's
   selection, bar and confirmation (plugin, `dist/` rebuilt). Tests: every row kind's apply and retract, a skipped row,
   all-or-nothing on one bad item, the cap, undo all, undo one of a batch, correcting canon's side, correcting the
   story's side to agree removes the row, the single-repair route unchanged.
5. **The check** (no paid call, `nmos-api-spend`), on throwaway copies of the test install's chats (test PG :5436, never
   production's database): the canon parts A1 would have copied (fingerprints recomputed on the copy, marked as an
   estimate, since older reads did not record theirs), then measured on fresh reads by the local eval model (:11500) for
   two chats of one bot; the jobs each choice of A3 queues on a model change to a stub endpoint, before any worker runs;
   the summaries A2 serves. The owner checks the panel on the test install (6131/6113).

PR A (steps 2–3) and PR B (step 4) touch different files and may be built side by side; `0033` is A's and `0034` B's,
merged in that order.

## Acceptance criteria

1. Two chats of one bot with the same persona: the second chat's canon read makes **no model call** for the texts the
   first read with this phase, and its canon facts are the first chat's, row for row.
2. "Rebuild memory" on one of them calls the model for its canon and changes no row of the other.
3. After a model change with **carry on**, a chat whose turns, windows and canon are all covered queues **no** job,
   then or after a restart, and its next packet holds the same facts, summaries and canon facts as before the change.
   A message, swipe or edit afterwards queues only the turns and windows it made or changed.
4. While the new summarizer has made nothing, every window an earlier generation summarized is served, with its secrets
   check.
5. **Redo the latest N turns** queues the jobs the preview counted, and the canon checkbox every chat's canon in force.
6. A config save without `on_model_change` (an older plugin) and with no model change behaves as before: same response,
   same queued jobs.
7. Selecting rows and **Apply selected** writes the previewed repairs in one transaction, or none; **Undo all** removes
   them together.
8. **Correct** on either side of a conflict writes a `fact_correct` for that fact in that chat; correcting it to agree
   takes the conflict away.

## Stop conditions

- A copied canon extraction would differ from what the model was asked (a fingerprint that misses part of the input,
  found by a test or the check): stop and fix the fingerprint before anything reuses.
- Serving older summaries puts a held secret into a packet in any test or on the copies: stop; the fallback does not
  ship until the check holds for every generation served.
- A bulk preview and its write disagree on a real chat's queue (the memory moved between them): report it before
  step 5's owner check, instead of writing what the preview did not show.

## Risk and release

High risk (see the top). The off paths stay as they are: a single repair, a config save that changes no model, a canon
read with no match. Built on `main` after the spec's approval; the test install (6131/6113) first; the install the
owner uses only after the `1.0.0` gate's quiet weeks end and `1.0.0` is tagged (a migration and a generation-serving
change are the heavy changes the quiet weeks exclude); released in `1.1.0`.
