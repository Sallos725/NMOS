# Phase 60 — Memory that knows where it stands: who is gone, who came back, what was carried over, when it happened and who was told

Status: **approved**, 2026-11-23 (owner, in the dispatch brief of 2026-11-23: eight items approved together, "breaking
the 1.0 quiet weeks is explicitly authorized", built and then tried on production 6003 as an experiment). An owner
request, not a roadmap stage. The eight items came from the owner's survey of another memory plugin's ideas. That
plugin's licence is source-available and permission-only: **nothing of its code or prompt text is used**; every rule,
prompt line and name below is written for NMOS from the idea alone (clean room).

Parameters marked **(brief)** are the owner's; those marked **(proposal)** are this spec's choice inside the brief and
the owner may amend them. Code defaults do not change: `extract-v16` and `packet-v19` stay the defaults; this phase's
behaviour is selected (`NMOS_EXTRACT_COMPILER=extract-v19`, `NMOS_PACKET_POLICY=packet-v20`, plugin and panel
switches).

**High risk** (`AGENTS.md §14`). Guarantees at risk, each with the check that pins it:

| Guarantee | Risk | Pinned by |
|---|---|---|
| A generation change re-derives nothing by accident (D20, ADR 0078, 0081) | a new predicate, prompt or field changes the key of `extract-v15…v18`, canon, summarize, reveal or embed; or `extract-v18 ↔ v19` is classified `version` | A1, A2, the copy check C1 |
| Recorded requests replay as they were (D39) | a read-side change leaks into `packet-v19` or older | A3 |
| Stored data, migrations, archive, delete (D23, D60) | three migrations; a new table and columns missing from archive, restore, delete or upgrade | A4, A5 |
| Memory selection, isolation, knowledge boundaries (invariants 6, 7; D19, D44, D45) | carried memory, gone pins, `told` lines, owner pins say what a character must not know, or what the story no longer holds | A9–A13 |
| Fail open; the plugin never mutates host data (operational invariants) | trimming, placeholder replacement, the reranker | A14–A18 |
| Secrets and credentials (D60) | a reranker key in an archive, a log or a trace | A8 |
| Deployment compatibility | the old image on the migrated database (rollback) | C3 |

## Why

1. A long chat pays for old dialogue on every request although memory already holds it, and a cut that moves every
   turn breaks the provider's prompt cache.
2. The packet does not say how far memory has got, so a reply can trust an older fact over what the chat just said;
   `end` placement lands after a prefill; a preset or lorebook entry cannot say where memory goes.
3. A dead or departed character walks back into a scene when nothing in the turn names them.
4. A character back after a long absence is written as if never away; a promise broken two turns ago is forgotten the
   moment its thread closes.
5. "응", "그래서?" embeds as almost nothing; the fused order has no second opinion.
6. A new chat that continues another, or restarts the story with one character remembering, starts from nothing.
7. A flashback told at turn 80 reads as if it happened at turn 80.
8. Who told whom is not recorded; the owner cannot say "keep this character in mind".

## What it does

### S1 — Old dialogue left out in steps (opt-in; plugin + `/v1/retrieve`; ADR 0083; amends D2, D3)

- **Request.** The plugin sends `trim: {keep_recent_turns, step}` with `/v1/retrieve` only when the owner turned
  `trimOldTurns` on (off by default **(brief)**; `keepRecentTurns` default 20 **(proposal)**, 4–200; `step =
  keepRecentTurns` **(brief)**). A request without `trim` is served exactly as before.
- **The sidecar decides the boundary** (turn numbers are the sidecar's, ADR 0008; the plugin stays thin). With `now`
  the turn being answered: `cut = floor((now − keep_recent_turns) / step) × step`. A turn is *covered* when an
  extraction serves it (D20) **and** a current, not-held scene summary holds it (D52). `cut` is lowered to the first
  uncovered turn of the prompt's window, rounded down to a multiple of `step`, so the boundary moves only in whole
  steps whatever the worker's progress. No boundary (`keep_from_id: null`, with a `reason`: `off`, `short`,
  `uncovered`, `no_summaries`, `stale`, `empty_packet`) when nothing can be cut, the head is stale, summaries are off,
  or the compiled packet is empty.
- **Recall sees the prompt as it will be.** The ids of messages before the boundary are removed from the request's
  in-context set before recall (D3), so their evidence may be excerpted; the trace records the effective set and the
  decision (`recall_options.trim`), so an as-of replay compiles the same packet without recomputing it.
- **Response.** `trim: {keep_from_id, keep_from_turn, reason}` and, always, `coverage: {recorded_through_turn,
  covered_through_turn}` (additive; older plugins ignore both).
- **The plugin applies it on a copy** of the outgoing messages, in `beforeRequest`, never on the host chat
  (`setChatToIndex` stays forbidden). It maps prompt messages to host messages one to one (the pointer match of
  `inContextIds`) and drops the prompt messages of host messages before `keep_from_id`. It **drops nothing** and
  reports the reason (`format`) unless every dropped message: has role `user` or `assistant`; carries exactly one host
  message and little else (a preset that merges the chat into one block is not matched); lies in one contiguous run
  that ends before the boundary; and is neither the latest user turn nor after it. No sidecar answer, a stale answer,
  a miss or any error: nothing is dropped.
- **Shown.** The Status tab and the HUD say how many messages were left out, the estimated tokens saved and, when
  nothing was, why.
- The cut only removes what the host would send; the packet's reserve (D2) is unchanged.

### S2 — Where memory goes and what it says about itself (plugin + `packet-v20`; ADR 0082, 0083)

1. **How far memory has got.** Under `packet-v20`, when the head has a replied turn after the latest turn an
   extraction serves (as of the request), the Note adds one sentence: memory is recorded through turn N, and where a
   newer message in the chat disagrees, the chat is right. **(proposal: said whenever at least one replied turn is
   newer, which in live use is nearly every request; it is one short sentence.)**
2. **`end` placement before a prefill.** `injectPacket(..., 'end')` inserts before the trailing run of `assistant`
   messages. Whenever the packet lands after the latest user turn (by `end` or by a placeholder), the plugin appends
   one fixed line after `</NarrativeMemory>` in the same system message: the user's latest message already happened
   and outranks this background memory. The plugin asks for `budget − 40` tokens in that case **(proposal)**, so the
   reserve still bounds the whole message (D2).
3. **`[NMOS.memory]`.** A preset or an activated lorebook entry (H19: in the prompt verbatim) may hold the marker.
   The plugin scans every outgoing message (string content and text parts of multipart content); the **first**
   occurrence is replaced by the packet (by nothing when the packet is empty or memory was skipped) and **every other
   occurrence is removed**, on every path out of `beforeRequest` — an auxiliary request, the plugin off, a chat
   switched off, the turn not found, a failure — so the literal marker never reaches a model. With a marker present
   the default placement is not used.
   - **Idempotent under retries (H2).** A second and third call with the prompt the first call returned give the same
     prompt, whatever the role of the message the marker was in: before placing, a prompt that already holds the
     packet text being placed is returned as it is.
   - **Canon.** Canon observation (which entries the prompt holds, ADR 0045) reads the prompt as the host sent it,
     before replacement. The marker inside a canon text is stored as written (raw evidence); `clean_text` and
     `NORMALIZER_VERSION` do not change, so nothing is re-derived. The canon extractor may read the bare marker as
     text; it names no entity and matches no predicate (a test with a stub model pins that the prompt is unchanged
     apart from that literal).

### S3 — A character who is gone stays gone (`packet-v20`; ADR 0082)

A deterministic read-side rule, no model call. A character (not the persona) is **gone** when its current, narrated,
positive, undisputed `has_status` says so — dead, killed, deceased, missing, vanished, departed for good, exiled;
사망, 죽음, 죽었, 전사, 실종, 행방불명, 떠남, 추방 **(brief's list)** — and does not also say recovered, returned,
alive, revived; 회복, 생존, 귀환, 부활, nor a negation or a near miss ("죽지 않", "죽을 뻔", "죽은 척", "not dead",
"nearly died", "presumed"). `located_in` counts only when the place's whole name is one of a short list that is no
place (행방불명, 실종, 저승, 사후세계; "missing", "the afterlife"): a place whose name merely contains a word of the
list ("죽음의 숲") never makes anyone gone. A gone character who is in the scene by rows of a turn after the status's
turn is not pinned (the story brought them back).

At most 8 **(brief)**, newest first, within 10 % of the budget **(proposal)**, as the character's own status line with
`gone="true"`, first in `<Facts>` (in `<Cast>` when the character has a group; never twice), label `required`, whether
or not the turn names them. The Note explains the mark: they do not appear, act or speak now unless the story itself
brings them back. A gone fact kept from someone in the scene follows the private, strict and narrator rules as any
fact does (D44, D45).

### S4 — Back after a long absence; what just ended (`packet-v20`; ADR 0082)

- **Return gap.** For a `<Cast>` character (not the persona): the turns its assertions mention it in (subject, object,
  participant; canon and carried rows excluded) give its current run (appearances at most 5 turns apart, ending at
  the request) and the appearance before it. When at least 40 **(brief: 40 or 60)** *served* turns lie between them in
  which it does not appear, and the run began at most 5 turns ago, its `<Character>` tag carries
  `back_after="~N turns"` (N rounded to ten). Turns no extraction serves are not counted: an absence nobody read is
  unknown, not an absence (invariant 4).
- **Settled lines.** Threads closed in the last 15 turns **(brief: 15–20)** whose maker or recipient is in the scene
  or named: at most 3 **(brief)**, broken, failed or abandoned before kept, achieved, paid, answered or averted, then
  newest, as `<Thread … status="…" closed_turn="…">` lines after the open threads, label `supportive` (they rest like
  any supportive line, ADR 0068), outside `threads_limit`. NMOS records no `partial` outcome, so the brief's `partial`
  has no line. `threads.fold` already opens a similar promise afresh once the earlier one is closed (a restatement
  joins only an *open* thread); a test pins it at a distance of 30 turns.

### S5 — A short message asks with the reply before it; an optional reranker (ADR 0084; amends D18, D70, `AGENTS.md §4`)

- **`sem_query`.** Under `packet-v20`, when the normalized user message is shorter than 40 characters and there is a
  previous reply **(brief)**, the text embedded for the query is the last 400 characters of that reply, a line break,
  and the message **(brief)**. Lexical and keyword recall, fact relevance and excerpt anchors still read the message
  alone. Recorded as `sem_query`; a trace without it replays with it off. The sync-time prefetch (D70) builds the
  same text with the same function from the head's stored reply, so a short message still finds its embedding
  waiting; a mismatch costs only the usual bounded wait.
- **Reranker, strictly opt-in.** `NMOS_RERANK_URL`, `NMOS_RERANK_MODEL`, `NMOS_RERANK_API_KEY`,
  `NMOS_RERANK_TIMEOUT_MS` (default 600 **(proposal)**), `NMOS_RERANK_FORMAT` (`standard`: `POST <url>/rerank` with
  `{model, query, documents, top_n}`, answers with `results[]` or `data[]` of `{index, relevance_score}`), also
  settable in the panel's settings. Unconfigured, no code path calls anything. Configured, the top 30 fused
  candidates **(proposal)**, each cut to 1,000 normalized characters, are sent once per request with the `httpx`
  client the sidecar already has (no new dependency); the answer reorders them, and a timeout, an error, a malformed
  answer or the request's remaining deadline leaves the fused order (fail open). The trace records `rerank_used`,
  `rerank_ms` and each candidate's rerank score; **a replay never calls the reranker**, it applies the recorded
  scores. The key is a credential like the other two: never in a trace, a log or an archive (an archive holding one is
  refused, D60). It sends chat text to the configured endpoint, as the embedder does; the settings say so.
- **`systemone` format.** The brief names a second wire format by an example model id. Its request and response
  shape is not established here; the implementer builds it only from the provider's published documentation, with a
  recorded fixture of that documentation's example. If the shape cannot be established, `standard` ships alone and the
  report says so. Nothing is guessed. **Outcome:** `standard` ships alone in this phase; `systemone` is not built (no
  published request and response shape was established).

### S6 — A chat that carries another chat's memory (migration `0036`; ADR 0085)

- **The link is owner input.** `conversation_carry`: `id`, `target_conversation_id`, `source_conversation_id`,
  `mode` (`continue` | `regression`), `entity_names jsonb` (the characters who remember; `[]` for `continue`),
  `cutoff_commit_id`, `cutoff_position`, `cutoff_turn` (the source's head and its end at link time, or the last
  message of the turn the owner chose: frozen, because an append extends a head commit in place, D4), `created_at`,
  `removed_at`. One link in force per target; a chat never carries itself; a source's own link is not followed (one
  level) **(proposal)**. A link in force keeps its cutoff commit's membership from any pruning.
- **What is carried is read, never copied.** The source is read as of its cutoff with the machinery an as-of replay
  uses (its facts folded with its canon and repairs, its threads, its story so far), by whatever generation serves it.
  Carried rows enter the target's read by **name**, resolved again in the target (entity ids are per conversation,
  D26); the source's persona is the target's persona.
  - `continue`: the source's current facts, aliases, open threads and story so far are from before turn 0, after the
    target's canon, and the target's own story supersedes them from the turn it says something new (as canon facts
    fold, D57). They carry `source="carried"` and no turn; the story so far is a `<Summary scope="earlier chat">`.
    They take no part in the scene cast, the return gap or secrets' reveal lists.
  - `regression`: the story began again and only the named characters remember. Nothing carried is world truth:
    carried facts and threads that involve a named character (subject, object or participant) are offered only as
    lines `timeline="previous" known_by="<the named>"`, at most 6 per packet **(proposal)**, ranked as facts are,
    inside a `<Regression remembered_by="…">` group, and never enter the target's current facts, cast, gone pins or
    open threads. The Note says: only those characters remember the previous timeline; nobody else knows it, and it
    may not hold now. They are limited knowledge and follow strict and narrator modes as private lines do (D45). No
    summary is carried.
- **Not in this phase:** carried excerpts (raw recall stays per chat), carried memory shown to the target's
  extraction (its prompts and hints read the target only), chains of links.
- **Recorded.** A request records the link it read (`recall_options.carry`: link id, source, commit, position, mode,
  names) and its replay reads that one, removed since or not.
- **API.** `GET /v1/conversations/{id}/carry` (the link in force and removed ones), `POST …/carry/preview` (what
  would be carried: counts, the first lines, the source's characters, a fingerprint), `POST …/carry` (with the
  preview's fingerprint: 409 when the source changed since), `DELETE …/carry` (sets `removed_at`). The panel's
  Settings → This chat links a chat in either mode and unlinks it. Nothing touches a host chat.
- **Archive, restore, delete, upgrade.** The table is in every archive with the ledger's owner input; a link is
  written to an archive only when both chats are in it (the manifest counts those left out); a restore keeps ids;
  deleting either chat deletes its links in the same transaction (D23), counted in the answer; the upgrade fixtures
  pass through `0036`.

### S7 — When it happened, apart from when it was told (`extract-v19`, migration `0037`; ADR 0086)

- **`extract-v19` is `extract-v18`** (roles, name pairs and `feeling` kept) with two rules and one predicate (S8).
- **`when_happened`** on an `event` or a `promised` **(proposal: these two)**: only when the TARGET turn puts it at
  another time than the turn itself — a past event told now, a flashback, an appointed day. A short phrase (at most 80
  characters) as the story gives it, resolved against the story clock when one is shown ("어제" with the clock at
  4월 12일 → "4월 11일"); otherwise as written. Null in every other case; `normalize` drops it on another predicate or
  another compiler. Migration `0037`: `assertion.when_happened text`, and `extraction.story_clock text`. It is copied
  wherever an assertion is (`ASSERTION_COLUMNS`, canon copies, reveal checks, archives).
- **The story clock.** When a status window the chat tracks carries a clock or date (Phases 39, 42, 43), its literal
  value **as of the target turn** (not the head) is one line of the turn's prompt and is recorded on the extraction
  row. It is an input from beyond the window like the hints (D7): recorded, never part of validity. No tracked clock,
  no line, and the prompt is `extract-v18`'s plus the rules.
- **Shown.** `packet-v20`: a line with a `when_happened` carries `happened="…"` beside its `turn` (when it was told),
  and the Note says which is which. The Inspector and the panel show `[happened: …; told tN]`.
- **The switch queues nothing.** `extract-v19` joins `generations.ADDS` with `extract-v16` and `extract-v18`: a
  change among the three whose specs differ only in `compiler` and `prompt` is `adds`, in both directions, and queues
  only turns no generation serves (ADR 0081 item 4). For that to hold, `extract-v19`'s spec has exactly
  `extract-v18`'s fields: the new predicate is **not** added to `REGISTRY` (whose fingerprint every extractor key
  hashes); it lives in a per-compiler extension whose definition is hashed into `extract-v19`'s `prompt`
  fingerprint. The keys of `extract-v15…v18` and of the canon, summarize, reveal and embed generations are
  byte-identical before and after this phase.

### S8 — Who told whom; a character the owner pins (`extract-v19`, migration `0038`; ADR 0086, 0087)

- **`told`** (character → character, multi): the subject passed on to the object something that matters later — a
  secret, news of an event, a fact about a third person, a warning, a rumour — that the turn shows the object did not
  have. Ordinary conversation is not `told`. The value is what was passed on; `with` may name whom it is about. It
  needs its quote like every row (invariant 10). Only `extract-v19` asks for it and only its rows are read; canon
  never states it. It changes no knowledge mark by itself: nothing is inferred from it.
  - **Shown.** The Inspector's entity page and the memory map list chains (who heard what from whom, oldest first).
    `packet-v20` offers at most 2 `told` lines **(proposal)**, as `<Fact kind="told">` (the packet's fact lines name
    their predicate with `kind=`), only when the message or
    the scene names the teller or the hearer, ranked as facts are; a line whose content says a secret still kept from
    someone in the scene is left out as an excerpt would be (D62), and strict and narrator modes apply.
- **A pin is an owner repair.** `owner_repair` kind `entity_pin` (migration `0038` widens the kind check): a name and
  its type, as `entity_exclude` names its target; removed like any repair; archived, kept by rebuilds, deleted with
  the chat. Under `packet-v20` a pinned character has a `<Cast>` group and its now and standing facts are `required`
  whether or not the turn names it: at most 3 groups beyond the cast's 4 **(proposal)**, most recently pinned first.
  The panel's person sheet has the switch.
- **`@name`.** With the setting `pin_at_mentions` on (off by default **(brief)**), an `@` at the start of a word in
  the user's message, followed by a name or alias of one of the chat's characters (exact after normalization, a
  trailing Korean particle allowed), pins that character for this request. An `@` inside a word (an address, a
  handle) or before anything that is no known name does nothing. Recorded with the owner's pins as
  `recall_options.pins`.

### What it does not change

`packet-v19` and every earlier policy, fresh or replayed; `extract-v16`, `-v17`, `-v18` and their keys; `clean-v3`;
the canon, summarize, reveal and embed generations; the default policy and compiler; the author's note.

## Out of scope

- A new default policy or compiler; a release tag.
- Hard POV isolation; anything a carried or told line would need beyond the soft marks (D9, D19).
- Trimming by the host's own setting, or anything written to a host chat.
- A generative call on the request path; a reranker that is on by default; a second reranker format on a guessed shape.
- Carried raw excerpts, carried memory in the target's extraction prompts, chains of links.
- A paid measurement: every check is zero-call (stub models); the owner's use on 6003 is the live check, as for
  Phase 58.

## Steps

1. This spec and ADRs 0082–0087 (docs), committed first.
2. **Pin what must not move, before any code changes.** A test with the extractor keys of `extract-v15…v18`, and the
   canon, summarize, reveal and embed keys, computed at `1b16ef6` for fixed settings; `packet-v20` added as
   `packet-v19` under a new name, replayed byte-identical.
3. **Migrations** `0036`, `0037`, `0038`, one commit each, with archive, restore, delete and upgrade-fixture coverage.
4. **`extract-v19`** (S7, S8's `told`): prompt, extension registry, `normalize`, the clock, `ADDS`.
5. **`packet-v20` read side** (S2.1, S3, S4, S7's and S8's lines, pins and `@name`).
6. **Recall** (S5).
7. **Carry** (S6): read, API, panel.
8. **Plugin** (S1, S2.2, S2.3): pure functions first, then `core.ts`, settings, Status and HUD; build.
9. **Panel and Inspector** (told chains, `[happened: …]`, the pin switch, rerank settings).
10. **Checks** (below), the scoped self-review (`AGENTS.md §14`), docs and `STATUS.md`.
11. **The copy** (C1–C3), then **6003** (the lead's gate; a fresh dump, backups and `rollback.sh` first).

Each small logical change is one commit **(brief)**.

## Acceptance criteria

Keys and replay
- A1. The pinned keys of step 2 are unchanged at the end of the phase.
- A2. `classify` is `adds` for `extract-v16 ↔ v19` and `extract-v18 ↔ v19`, both directions; activation then queues
  nothing on a covered chat and only uncovered turns on a partial one; with the model changed too it is `model`.
- A3. A fresh request under `packet-v19` compiles byte-identical packets before and after the phase on the same
  database (the zero-call replay over recorded traces, three runs, majority; `AGENTS.md §7` item 6), and every policy
  of `POLICIES` up to `packet-v19` passes its existing tests untouched.

Data
- A4. The three migrations apply to every upgrade fixture; row counts and id hashes of existing tables are unchanged.
- A5. An archive round-trips `conversation_carry`, `when_happened`, `story_clock` and an `entity_pin`; a link with one
  end outside the archive is left out and counted; deleting either chat removes its links.

Extraction
- A6. With `extract-v19` and a stub model: `when_happened` kept on `event` and `promised` only and dropped elsewhere
  and under other compilers; the clock line present only when a tracked clock exists as of the target turn, and
  recorded; `told` valid only under `extract-v19`, with its quote; `feeling` as under `extract-v18`.
- A7. `extract-v19`'s system prompt is at most 15 % longer than `extract-v18`'s (Phase 58's stop condition), reported.

Recall
- A8. `sem_query` on only under `packet-v20`, short message and a previous reply; recorded; replay off without it;
  the prefetch hits for a short message. Reranker: off unconfigured (no call made); reorders with a stub; timeout,
  error and malformed answers leave the fused order; a replay makes no call; the key is in no trace, log line or
  archive, and an archive that would hold it is refused.

Packet
- A9. Gone: pinned without a mention; not for the persona, a negation, a near miss, a recovered status, a place whose
  name contains a gone word, or a character the story brought back; at most 8; private, strict and narrator rules
  hold.
- A10. Return gap: annotated at 40 served turns and not at 39; not across unserved turns; not for a first appearance.
  Settled: at most 3, ordered as specified, only inside 15 turns, resting like supportive lines; a similar promise
  opens afresh after a close.
- A11. Coverage sentence present exactly when a replied turn is newer than the last served turn.
- A12. `told`, `happened`, pins and `@name`: lines as specified; `@` inside a word and unknown names do nothing; a
  told line that says a kept secret is withheld; every new line shape is dropped by `clean-v3` when a reply echoes it
  (K27), checked on each shape, except `<Summary>`: `clean-v3` does not drop a `<Summary>` line's text when a reply
  echoes it, today's story summaries included (accepted by the coordinator, 2026-11-23).
- A13. Carry: `continue` facts fold before turn 0 and are superseded by the target's story; `regression` lines never
  enter current facts, cast, gone pins or open threads, appear only for the named, and are withheld under strict and
  from a narrator who is not one of them; an edit of the source after the link changes nothing in the target; a
  removed link carries nothing; a replay reads the recorded link.

Plugin
- A14. Trim off, or no `trim` in the answer: the returned prompt is the input plus the packet, as today.
- A15. Trim on: the boundary moves only at multiples of `step` over a growing chat; the latest user turn and
  everything after it are never dropped; a merged-chat preset, a system-role chat message or any mismatch drops
  nothing and reports `format`; the host chat object is deep-equal before and after.
- A16. `end` goes before a trailing prefill; the guard line appears exactly when the packet lands after the user
  turn, and the packet plus the line fits the budget.
- A17. `[NMOS.memory]`: first occurrence replaced, the rest removed, in string and multipart content, in any role;
  removed on every early return and on failure; three consecutive calls return identical prompts; canon observation
  unchanged by it.
- A18. Sidecar down or slow: the prompt is the host's, with markers removed and nothing dropped.

Whole
- A19. The sidecar suite passes with `NMOS_TEST_REQUIRE_DB=1`, `tests/test_upgrade.py` included; the plugin's tests,
  typecheck and build pass; counts reported.

## The copy and the deployment

- C1. A fresh `pg_dump` of production, restored into a scratch database on the test PostgreSQL (never production's).
  **Before any sidecar, worker or request touches the copy, its `app_config` model rows are pointed at stubs** (a
  restored copy's settings override the environment). Then `nmos-migrate`, the switch to `extract-v19` and
  `packet-v20`: **0 jobs queued** before any worker runs; row counts and id hashes of source revisions, assertions,
  extractions, summaries, owner repairs, conversations and generations unchanged; `/v1/health` and `/v1/retrieve`
  answer.
- C2. On the copy, every gone pin and every return-gap annotation of every chat is listed and read before the
  deployment; a wrong one is fixed first.
- C3. **Rollback rehearsal.** Migrations are forward-only, so rollback is the old image and the old `.env`, not a
  restore (a restore would lose turns written since). The previous image does not know `extract-v19`, so its own
  `classify` reads a switch from `extract-v19` to `extract-v18` as a `version` change and would queue the latest turns
  of every chat again; a rollback therefore changes the compiler before it changes the image, in two steps with the
  worker stopped throughout (coordinator's decision, 2026-11-23): (1) the **new** image with the previous `.env`
  (`extract-v18`, packet policy unset) queues 0 jobs (`adds`) and makes `extract-v18` the most recently activated
  extractor generation; (2) the previous image (`edge-1b16ef6…`) with the previous `.env` and compose file then sees
  the same generation and queues 0 jobs; only then does the worker start. Step 1 alone is already a behavioural
  rollback; step 2 is for a fault in the new image itself. Writing `activated_at` by SQL is an emergency path only,
  for a new image that cannot start, and needs the owner's go. Rehearsed after C1, with a few stub-written
  `extract-v19` rows (`told`, `when_happened`) on turns no `extract-v16`/`-v18` extraction serves, an `entity_pin`
  repair and a `conversation_carry` link on the copy: both steps queue 0 jobs, and the previous image answers
  `/v1/retrieve` and the Inspector without error (its readers skip `told` rows and ignore the pin).
- D1. Production: a fresh dump, `.env` and compose-file backups and `rollback.sh` in
  `~/nmos-eval/phase60-backup-<timestamp>/`; the compose file passes `NMOS_PACKET_POLICY` and `NMOS_RERANK_*`
  through; the worker is held until the queue is checked; `/v1/health` reports the image, the schema and the plugin
  build.

## Stop conditions

- Any pinned key moves, or the switch would queue a job on the copy: stop; nothing is deployed.
- `packet-v19` differs anywhere: stop and move the change behind `packet-v20`.
- A gone pin or return gap on the copy is wrong and the rule cannot be made right without a model: that item ships
  off, and the report says so.
- Either step of the two-step rollback (C3) queues a job, or the old image does not run on the migrated copy: stop
  before production; the rollback would not hold.
- An item cannot be finished to its criteria: it stays off behind its switch, named in the report; a half item is
  never called done.

## Risk and release

High risk (the table at the top). Off path: an install that selects none of the switches sees three migrations (a
table, two nullable columns, a wider check) and nothing else. No tag. The 1.0 gate's quiet weeks restart at the
production deployment (`ROADMAP-1.0.md`); whether any of this is in `1.0.0`, and which defaults move, is the owner's
decision after the trial.
