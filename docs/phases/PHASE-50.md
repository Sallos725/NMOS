# Phase 50 — Notes for the author's note: the chronicle, what changed from the setting, how the characters stand

Status: **approved**, 2026-10-23 (AGE-88). An owner request, not a roadmap stage.
The shape below (S1–S7) was agreed with the owner in the design conversation of 2026-10-23.
**Q1–Q5 answered (owner, 2026-10-23): all as recommended.** **Implementation approved (owner, 2026-10-23):** built
now, tried on the test install (6131/6113) first, and deployed to the install the owner uses only after the quiet weeks
end (2026-10-27 at the earliest), with the owner asked again before that deploy.
**Not before the quiet weeks end** (the 1.0 gate's two quiet weeks run from 2026-10-13 to at least 2026-10-27, on the
install the owner uses): nothing of this phase lands on that install before then. It adds no packet policy, extraction
generation or migration, so by `docs/ROADMAP-1.0.md` it would not restart the count; the owner still chose to wait. A minor release (`1.1.0`) is proposed.

The owner read a request's `<Story>` section (`<Summary kind="story" turns="0-87">`) and found that it summarized
88 turns so briefly that important events were missing. The owner asked for a way to get, on request, a fuller account
of what has happened so far (the events, how they went, how they ended or that they are still open) written so that it
can be pasted into the chat's **author's note** at once. Asked what else NMOS holds that belongs in an author's note,
the owner added two sections, each generated on its own toggle: **what changed from the setting** and **how the
characters address and stand toward each other**.

**High risk if built** (`AGENTS.md §14`):
- **canon and provenance:** the author's note is a canon source (ADR 0045, 0047); this phase leaves NMOS's marked
  blocks out of the canon NMOS stores and reads (S5, Q1);
- **secrets:** the author's note reaches every prompt verbatim with no secret gate (HOST-FACTS H19), so these sections
  are a surface the read-time gate of ADR 0042 amendment 3 cannot protect (S4).

Invariants it touches (`AGENTS.md §3`): **the response model never writes canonical memory** (a model-written chronicle
pasted into the note and read as canon would do exactly that; S5 keeps it out); **the plugin never mutates host chat
data** (kept: the owner pastes, NMOS writes nothing to the host); **raw evidence is never destroyed** (Q1 (a) stores the
note's canon text without NMOS's own blocks; the host's note is untouched and the metadata records the blocks);
**every automatic semantic claim has provenance** (each line carries its turn).

## Why

1. **The story so far is short by construction** (read from the code, `main` at `6d593d4`). A scene summary covers 8
   turns in at most 5 sentences (`summaries.SCENE_PROMPT`, capped at `SCENE_CHARS` = 1,200), and the story so far
   compresses every current scene summary into at most 8 sentences (`STORY_PROMPT`, `STORY_CHARS` = 2,400). At 88
   turns that is 11 scenes in 8 sentences; the longer the chat, the more each scene loses. The scene summaries
   themselves are stored and current, but only the one the message is about reaches a packet (packet-v8, ADR 0043).
2. **The story so far is often held.** When a character a secret is kept from is in the scene, a summary is held at
   0.3 instead of 0.7 (ADR 0042 amendment 3); on the owner's chat the story was held in most scenes when that was
   measured. So the gap is less "no recap exists" than "the recap is short and often does not reach the prompt".
3. **The setting keeps being resent unchanged.** The card's fields, the persona and the active lorebook entries are in
   every prompt verbatim (H19), so when the story has changed something they state (a place, a status, a relationship,
   who holds an item) the prompt carries the old value every turn and the newer one only when a packet happens to.
   NMOS knows both: canon facts are stored as facts from before turn 0 (ADR 0047), and a newer story fact of a
   single-valued predicate supersedes them (`predicates.Predicate.cardinality`).
4. **Address and standing are stored per pair.** `addresses` (single, per object: what one character calls another),
   `relationship`, `role_toward` and `feels_toward` are facts between named characters, from canon and from the story.
5. **What happened, and how it ended, is already stored as data.** Threads (`threads.KINDS`: promise, goal, question,
   threat, debt) carry whether they are open or ended and the outcome (`resolved`, since `extract-v13`); the cast
   carries where each character is and in what condition; status windows carry their values.
6. **The host has no write for the author's note** that NMOS has observed (HOST-FACTS: the plugin reads `chat.note`
   through `getChatFromIndex`; the only host write NMOS uses is the persona's name, ADR 0023). A copy-paste text the
   owner places is the shape that needs no new host fact.

## Proposal

S1. **What the owner does.** In the panel's **This chat** card (Status tab, ADR 0048), a group
**작가의 노트용 정리 / For the author's note** with three toggles and one button:
- **연대기 / Chronicle** (S2), with its length (**짧게 3,000자** / **길게 6,000자**);
- **설정 변경점 / Changed from the setting** (S3);
- **호칭·관계 / Address and standing** (S3);
- **비밀 포함 / Include secrets** (off by default, S4);
- **만들기 / Make**: asks the sidecar for the toggled sections and opens their Inspector page (S6).

Only the chronicle calls a model; with it off, making the other sections is free. The panel says that the author's note
is sent with every request, so whatever is pasted is paid on every turn. Korean first, English beside it (`i18n.ts`).
The plugin stays light (`nmos-plugin-stays-light`): toggles and one button, as **Retry failed** is; the sidecar builds
and renders every text.

S2. **The chronicle** (owner, 2026-10-23: a model call, with an assembled fallback).
- **Input**, all of it already stored for the chat's head: every current scene summary in order; the story so far;
  the threads with their kind, state and outcome; the scene's cast with place and condition; the status windows'
  current values. Long chats: Q2.
- **One model call** writes it in the language of the chat, at most the chosen length, in three parts:
  **사건 / Events** (each: how it began, how it went, how it ended or that it is still open, with its turn range),
  **지금 / Now** (where things stand), **열린 일 / Open threads**. Only what the input says: no guesses.
- **A thread's state and outcome are not the model's to write.** The model is told which threads are open and how
  the ended ones ended, and a deterministic check compares each thread it names with the stored state: a thread told as
  ended that is open, or open that is ended, fails the reply (retried once, then the fallback).
- **The fallback** (no model configured, the call or its retry fails, or the owner chooses it): the same input
  assembled without a model, in the same three parts: the story so far and the newest scene summaries that fit as
  Events, ended threads with their outcomes under Events, the cast and status values as Now, the open threads as Open
  threads. The page says it was assembled without a model.

S3. **The two sections without a model.** Both are read from stored facts, with no model call: the facts the chat's
head serves now (the same reads the Inspector's memory view makes) and, for the first section, the canon facts of the
manifest in force (`canonfacts.rows`), joined on predicate and subject (and object, where `per_object`). They are rendered as short lines in the language of the panel, with the turn each value was
stated (`t42`; `설정` for canon).
- **Changed from the setting.** For each canon fact of a predicate whose newer value supersedes the older
  (`cardinality == "single"`, per subject or per (subject, object) as `per_object` says, and an item's holder,
  `HOLDER_PER_ITEM`) that a story fact now supersedes with another value: `설정: <canon value> → 지금: <story value>
  (t42)`. A canon fact an owner repair superseded is listed the same way, marked as fixed by the owner. Multi-valued
  predicates (`has_trait`, `world_fact`, …) accumulate rather than replace, so they are not listed: NMOS cannot tell a
  change from an addition there. An empty list says that nothing the setting states has changed.
- **Address and standing.** One line per ordered pair of named characters that has any of `addresses`,
  `relationship`, `role_toward`, `feels_toward` served now: `A → B: "선배"라고 부름 · 동아리 후배 · 신뢰` (from canon
  or the story, the newest served value of each; the user's character named as the chat names it, ADR 0023). Pairs
  are ordered by how recently either value was stated, at most `PAIRS_MAX` lines (30); an alias already merged
  (ADR 0058) is one character.

S4. **Secrets** (owner, 2026-10-23: left out by default, the owner's choice per request).
- **Off (default).** No section carries a line that is secret or private (`Line.private`, `kind == "secret"`) or a
  fact that is the content of one of the chat's secrets still kept from someone (`summaries.head_secrets`). For the chronicle, every secret still kept from someone is
  listed in the prompt as one it must not tell, as `summaries.secrets_block` does, but all of them, not a window's;
  the reply is then checked with `summaries.leaks` at the stricter bar (`LEAK_NEAR` = 0.3) for every secret, since the
  author's note is read in every scene. A held reply is retried once with the held secrets named; held again, the
  fallback is used, built only from lines that are not secret or private and from scene summaries the stricter bar does
  not hold.
- **On.** The secrets are given to the chronicle's model and written with who does not know them
  (`비밀: … (○○는 모름)`), and the two other sections keep their secret lines, marked the same way. The panel warns,
  before making them, that the author's note reaches every prompt and that a model can let a secret slip in front of
  the character it is kept from.

S5. **The markers, and what canon does with them** (Q1).
Each section is written between its own two marker lines, so the owner can replace one and keep the others:
`[NMOS 연대기 · t0–87 · 2026-10-23]` … `[/NMOS 연대기]`, `[NMOS 설정 변경점 · t120]` … `[/NMOS 설정 변경점]`,
`[NMOS 호칭·관계 · t120]` … `[/NMOS 호칭·관계]` (English: `chronicle`, `changed`, `address`).
The canon must not read them: text in the author's note is canon, "how things stand before the story begins"
(`canonfacts.PROMPT`), so a pasted section would become pre-story facts (and the changed values would come back as
canon, superseding nothing), and since canon is read per text (`canonfacts`: each new revision of the note, up to
`MAX_PARTS` × `PART_CHARS`), every paste would read the whole note again at the provider's cost.
- The canon hash is computed by the plugin (`canon.ts`, `add('note', chat.note)`) and only checked by the sidecar
  (`canon.sync`), so the sidecar cannot leave the blocks out before the hash. Q1 (a), recommended: the plugin removes
  every marked block from the note before it hashes and sends it, and records each block's kind and turn in the note
  entry's metadata (`nmos_blocks: [{"kind": "chronicle", "turns": "0-87"}, …]`); a new paste then changes the
  manifest's metadata, not the note's revision, and no canon read follows: `canonfacts.schedule` queues only
  revisions in force that are not read yet, and a read's window depends on the manifest only through `names_tag`,
  which reads the card's name hash and the persona's name, not the note's metadata. The sidecar also removes marked blocks from
  a canon text before `canonfacts` reads it, so an older plugin that sends them whole costs a read but never puts them
  in canon.
- A note without a marker hashes and reads exactly as on `main` (the off path is byte-identical).
- The packet's `<Story>` is unchanged (owner, 2026-10-23: the short story in the packet and the fuller chronicle in the
  note side by side). Nothing in the packet reads the note.

S6. **The Inspector page** `GET /inspector/c/{id}/notes`: each section made in its own read-only box with **Copy**
(the Clipboard API, and, where the plugin frame refuses it, as on iPhone Safari, a select-all fallback with a hint to
copy), the turn it reaches, for the chronicle whether a model wrote it or it was assembled, which secrets rule applied,
and each section's length. If the note's metadata names blocks (S5), the chat page shows how far each reaches:
**노트의 연대기는 t87까지, 지금은 t120 — 다시 만들까요?** The page reads only the cache (S7); after a restart it asks
the owner to press **Make** again.

S7. **The API and the cache.** `POST /v1/conversations/{id}/notes` with
`{sections: ["chronicle", "changed", "address"], chars: 3000 | 6000, secrets: bool, model: bool}` returns, per section,
`{text, turns, made: "model" | "assembled" | "facts", cached: bool, held: [...]}`, behind the same auth as the other
conversation actions. A 409 for the chronicle when the chat has no current scene summary yet (the panel says how many
turns until the first scene is due); the other sections answer with an empty list. Each section is cached in the
process, keyed by its input's fingerprint (the ids of the summaries and facts it read, the threads' states and
outcomes), the options and, for the chronicle, the generation: asking again with nothing changed makes no call.
Nothing is stored in the database; these are views, not memory, and no packet reads them.

## Amendment 1 (2026-10-23, from the code, before step 2)

Reading the code for the implementation plan (`docs/superpowers/plans/2026-10-23-phase50-author-notes.md`) changed
three details; the owner's decisions stand.
- **S2: Open threads come from the store.** The chronicle's Open threads part is rendered from the stored threads (who,
  what, kind, since when), not written by the model; the model writes Events and Now (`{"events": …, "now": …}`), told
  each thread's stored state and outcome. A part that is not the model's cannot misstate a thread, so the thread-state
  check is not needed. Status-window values are not in the input; "Now" comes from the current `located_in` and
  `has_status` facts.
- **S6: the panel shows the texts.** The panel inserts the Inspector's HTML as a fragment and runs none of its scripts
  (H15), so a Copy button must be the panel's own: the panel shows each section the API returns in a read-only box
  with Copy. There is no `/inspector/c/{id}/notes` page; the Inspector's canon section shows which NMOS sections the
  note carries and how far each reaches.
- **S3: no `identity`, at most 30 lines.** On the test install's copy (zero-call check, 2026-10-23) 57 of one chat's 68
  "changed" lines were a card's English identity told again in Korean or another true description ("Records clerk" →
  "중앙도서관 기록계"): the reason ADR 0047 amendment 1 already leaves `identity` out of the canon conflicts. It is left
  out here too; a line is said once (two canon texts or two spellings gave the same line) and at most 30, newest first.
- **S7: no 409.** A section with nothing to say comes back empty with its reason (`no_scenes` for a chronicle before
  the first scene summary, `none` otherwise), so the other sections still come.

## Out of scope

- Writing the author's note through the host (no observed host write; S1 is copy-paste).
- Changing the story so far, its caps or its prompts, or what the packet carries (`<Story>` stays as it is). A longer
  story so far in the packet, in chapters, is a separate proposal if the chronicle proves its worth.
- Sections that update themselves or are injected by NMOS.
- Other sections the conversation of 2026-10-23 listed and the owner did not choose: the owner's locked facts as rules,
  possessions and condition, who knows what. Each can be a later toggle on the same page.
- Changes of multi-valued predicates (S3).
- Carrying a chat's memory into a new chat: the sections can be pasted into a new chat's note, but NMOS's memory stays
  per chat.
- A marker inside messages.

## Questions for the owner

- **Q1 — where the marked blocks are left out of canon. Answered (owner, 2026-10-23): (a).**
  - (a) **Recommended:** the plugin removes them before the hash (S5), and the sidecar also removes them before a canon
    read. A paste costs no canon read, and an older plugin can only cost a read, never pollute. The stored canon text
    of the note then leaves out NMOS's own blocks; the metadata records that they were there and which turns they
    covered.
  - (b) Sidecar only: the note is stored verbatim (a new revision per paste) and the canon read leaves the blocks out
    and reuses the facts of an earlier revision whose text without the blocks is the same. Verbatim provenance and no
    plugin change, but a new reuse path in `canonfacts` (extractions are keyed per revision today).
  - (c) No marker handling: the sections are offered for a new chat's note only. Simplest; the same-chat use the owner
    asked for would pollute canon and pay a canon read per paste.
- **Q2 — long chats (the chronicle).** At 1,200 characters a scene, 40,000 characters of input hold about 33 scenes
  (264 turns). **Answered (owner, 2026-10-23): (a).**
  - (a) **Recommended:** one call always; the newest scene summaries up to the input cap, and the older part through
    the story so far and the threads' outcomes. Predictable cost; old detail is the threads'.
  - (b) Chapters on demand: groups of 8 scenes summarized first, cached in the process; one call per chapter on the
    first request after a restart (a 1,000-turn chat: about 16 calls, then 1).
  - (c) Chapters as a stored summary level made by the worker: no extra calls per click, but a projection change
    with a migration.
- **Q3 — the model. Answered (owner, 2026-10-23): (a).** (a) **Recommended:** the extraction model and endpoint, as summaries use (ADR 0042 item 4).
  (b) A separate setting for a stronger writer. Can be added later without changing the rest.
- **Q4 — release. Answered (owner, 2026-10-23): as proposed.** After 1.0.0, a minor release (`1.1.0`): plugin controls, a canon read change and a new endpoint
  are not a patch.
- **Q5 — measurement. Answered (owner, 2026-10-23): approved as proposed.** Zero-call checks first: S5's off path byte-identical on a copy of every gate chat's canon; a
  re-paste stores no revision and queues no canon job; the two fact sections and the fallback on every gate chat's
  copy, each checked against the Inspector's memory view (every changed value and every pair listed is served there,
  none secret with secrets off). Then one paid sample on a test copy: the chronicle at both lengths, secrets off, for
  the gate chat with the most secrets, every reply checked at 0.3 and the threads' states compared; the cost estimated
  and approved before the run. Whether the sections in the note improve the replies is the owner's own trial, not a
  gate.

## Steps

1. **Spec** (this file): Q1–Q5 answered and implementation approved (2026-10-23).
2. **Sidecar, no model:** the two fact sections (S3), the assembled chronicle (S2 fallback), the API, the cache and the
   Inspector page, the marker removal before a canon read (S5), with tests on synthetic chats only (public
   repository): a superseded canon value listed and an unchanged one not, a multi-valued predicate never listed, the
   pairs from canon and the story, the threads' states as stored, no secret in the default output, the cache, a note
   without a marker unchanged.
3. **Sidecar, the chronicle's model call:** the thread check, the leak check with retry and fallback (S2, S4), tested
   with the stub model.
4. **Plugin:** the toggles and the button, the marker removal before the hash and the metadata (S1, S5); the panel's
   warning texts.
5. **Measurement** (Q5) and the owner's check on a real host: paste each section, reload, a request, the canon
   unchanged.

## Amendment 2 (owner, 2026-10-23): one English Markdown note

Seeing three boxes, the owner judged that a user would not know what to do with them, and that the author's note,
which the model reads, is better in English Markdown. So:
- **One block, one box.** The parts the owner picks go into one text between `[NMOS note · t<turn> · <date>]` and
  `[/NMOS note]`, in this order: a header (`# Story memory (NMOS, as of turn N)` and one line saying the latest messages
  take precedence), `## Chronicle (tA–B)`, `## Now`, `## Open threads`, `## Changed from the setting`,
  `## Address and standing`; a part with nothing to say is left out. The panel shows the one text with one Copy button
  and, under it, how each part was made. The note entry's metadata names each block by its turn
  (`nmos_blocks: [{"turn": "87"}]`). This replaces S5's per-section markers and S1/S6's per-section boxes.
- **English.** The chronicle's model writes English whatever the chat's language; the labels of the other two parts
  are English. Names, titles, places and quoted words (a form of address) stay as the chat writes them: translating
  them would need another model call and could change what the story model calls someone. The assembled chronicle
  keeps the scene summaries in the chat's language under the English headings.

## Amendment 3 (owner, 2026-10-23): an open thread not said again for 30 turns stays out

On the test install's copy the longest chat (76 turns) had 34 open threads, 21 of them not said again for more than
30 turns: a same-afternoon appointment from turn 2 beside a lifelong debt from turn 6. Many open threads are done
without the story saying so (the extractor reported no end), and the note would tell the story model, every turn,
that they are still open. NMOS cannot yet tell an old thread that still matters from one long done: threads have no
importance (`salience` is for events only, ADR 0020). So, as the Inspector already does for "needs a look"
(`inspector.stale`, `STALE_TURNS` = 30, PHASE-13 Q6), an open thread whose last opening or restatement is more than 30
turns back is left out of the note's Open threads and of the chronicle's input; the panel says how many, and that they
can be checked or closed in the Inspector. A thread the story mentions again counts as recent again. Telling which
threads matter is Phase 51 (a draft), after 1.0.0 with the next extractor generation.

## Steps 2–4 evidence (2026-10-23)

Built on `claude/author-notes-story-summary-f721b1` (PR #315), plan
`docs/superpowers/plans/2026-10-23-phase50-author-notes.md`.

- **Sidecar.** `noteblocks.py` (the markers; no imports from the sidecar, since the canon reader needs it and `facts`
  imports `canonfacts`), `notes.py` (the sections, the chronicle, `Ask`, `make`), `canonfacts.process` (a `note` loses
  its blocks before a read), `POST /v1/conversations/{id}/notes`, the Inspector canon section's `note_blocks` line.
  `tests/test_notes.py`: 27 tests: the shared marker fixture, a marker inside a body, the canon guard against an older
  plugin, a paste that stores no revision and reads no canon (criterion 2), the two fact sections (identity left out,
  secrets off and on), the chronicle (open threads from the store, a held summary by `summaries.held` as the packet
  holds it, a reply that tells a secret asked again then assembled, an empty reply, a failed call not cached, the
  cache), the endpoint (the canon scenario's changes, the chronicle from real scene summaries with a stand-in model,
  404/422). The whole sidecar suite: 1,593 passed before the review fixes; the touched files' tests after them.
- **Plugin.** `notes.ts` (`stripNoteBlocks`, `copyText`), `canon.ts` (the note without its blocks, `nmos_blocks` in its
  metadata), the panel's form and result boxes (`ui.ts`, `i18n.ts`). 249 tests with typecheck; the canon manifest
  fixture's `with_note_blocks` entry gives the same id in both languages. Build `a9b4b54e4da5`.
- **Review** (scoped self-review, high risk: canon/provenance and secrets). Fixed: a failed model call was cached; the
  cache had no lock; a marker inside a body could close its block early; the panel's timeout was shorter than a call
  and its retry; summaries were held by the trigram check alone, not by `summaries.held` as the packet holds them.
- **Test install** (6131/6113, test-only): image `nmos-sidecar:trial-phase50-2dca211` since 2026-10-23 20:52 KST, the
  build's defaults as the candidate ran (backups `~/nmos-eval/p32-try/backup-20261023-2051-phase50` and `-2052-`;
  the candidate's containers kept stopped as `*-prev-candidate-6d3f2f7`). The database fingerprint (revisions,
  assertions, extractions, canon manifests, settings, generations, schema) is identical before and after. The plugin
  build is in `~/nmos-eval/p32-try/nmos-pocketrisu.js`; until it is re-imported, 6131 runs the older plugin, which the
  sidecar's canon guard covers.
- **Zero-call check (Q5)** on all 14 chats there: every request answered (5–96 ms); "changed" gave at most 12 lines
  after `identity` was left out (68 before on one chat), "address" at most 30 pairs, the assembled chronicle 1,174–2,971
  characters on the four chats with scene summaries. The chronicle's paid sample waits for the owner's approval of its
  estimate.

## Acceptance criteria

- A note without a marker gives the same canon hash, manifest and canon facts as on `main` (test).
- Pasting, replacing or removing any section in the note queues no canon job (with Q1 (a), the new plugin; test and
  the real-host check).
- With secrets off, no section holds a kept secret: no secret or private line in the fact sections, and no chronicle
  (model or assembled) held at 0.3, on the stub tier and the paid sample.
- Every changed value and every pair the fact sections list is what the Inspector's memory view serves at that head,
  and every thread the chronicle names is told in its stored state (open or ended, with the stored outcome).
- Making the two fact sections calls no model; asking twice for the chronicle with nothing changed makes one call.
- With no model configured, the chronicle is still made, marked as assembled.
- Packets are byte-identical to `main` for every replayed probe (nothing reads these sections).
