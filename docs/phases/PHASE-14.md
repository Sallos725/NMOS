# Phase 14 — Verification and Repair, part 2: canon sources (Stage 6)

> **Status: approved 2026-09-28 (owner), in progress.** Stage 6 of `docs/ROADMAP-1.0.md` (original §7.6, §66,
> §80.3; Track B, B7), part 2: what the character card, the lorebooks, the persona and the author's note say becomes
> source for memory, next to the story. Phase 13 Q0 put canon sources and export/restore in this phase; Q0 below
> gives export/restore its own phase. The owner chose to start Phase 14 on 2026-09-28 and decided no release for now.
> The owner answered Q0, Q3, Q4/Q7 and Q8 with the proposed answers and took the others as proposed (2026-09-28).

## Questions and answers

Each answer in bold was NMOS's proposal; the owner accepted every one (2026-09-28).

| # | Question | Proposed answer | Alternatives |
|---|---|---|---|
| Q0 | One phase for canon and export/restore, or two? | **Two.** Phase 14: canon sources. Phase 15: export and restore of the ledger, the owner's input and settings, which closes Stage 6. Each is a separate kind of work, and export/restore needs no host evidence. | One phase; export/restore first. |
| Q1 | Which canon does NMOS read? | **Four sources, their story parts only:** the character card's `name`, `desc`, `personality`, `scenario` and the greeting the chat started from; the lorebook entries of the character, the chat and the active modules; the chat's persona (`personaPrompt`); the chat's author's note (`note`). Not the card's instructions (`systemPrompt`, `postHistoryInstructions`, `creatorNotes`), example messages or assets. | The card only; everything the card holds. |
| Q2 | How does canon reach NMOS, and how is it kept? | **The plugin reads it at each request and sends only what changed, as a hash manifest does for messages; the sidecar keeps each canon text as an immutable source revision of the conversation** (a card edit makes a new revision; the old one is kept as history, invariant 1). A request records the canon revisions in force, so it replays as it was (ADR 0027). Canon is kept per conversation, as the host shows it to that chat. *Step 2 (H19):* the card is read off the request path, because reading it clones the current chat; the rest is read with each request. | A panel button that imports canon on demand; canon shared across a character's chats. |
| Q3 | Does a model read canon, and when? | **Yes, the extraction model, as its own projection (a `canon` generation), so the message extractor and its generation do not change and nothing is extracted again.** The card, the persona and the author's note are read once per revision (a few calls when they change). A lorebook entry is read once the host first puts it in a prompt (the plugin sees which entries' text is in the outgoing prompt), not all at once: a large lorebook costs calls only for the entries the story uses. The Inspector shows the calls made. | Every lorebook entry at once; no model (names only, Q6). |
| Q4 | Canon or story: which wins? | **The story, from the turn it says something new; canon is the state before turn 0.** A card that says someone is 16 is superseded by the story's "turned 17". A story statement that contradicts canon at the same time (not a change the story tells) is listed in "Needs attention" as a conflict, with the owner's choices: keep the story's, keep canon's (a lock, Q7), or leave it. | Canon always wins; the newer source wins. |
| Q5 | What changes in the packet? | **Almost nothing on its own:** the host already sends the card and the lorebook entries it activates, and NMOS does not send what the host sent (D3). A canon fact reaches the packet like any fact only when its text is not in the prompt (an entry the host did not activate this time, an edited-away card line), and a locked fact (Q7) holds against a story statement. No new packet policy unless step 5 shows one is needed. | Canon facts always in the packet; a `<Canon>` section. |
| Q6 | Names from canon, without a model? | **Yes.** The card's `name`, the persona's name, and a lorebook entry's keys as names of one thing: when one key is a known entity's name and no other key names another known entity, the other keys become its aliases (K31: a given name alone, K8). An entry whose keys name two known entities joins nothing. Extraction's entity hints list canon names too. The owner can split any of them (ADR 0044). | Only with a model (Q3); not at all. |
| Q7 | Canon lock? | **An owner repair kind `fact_lock` (ADR 0044's table and undo): the locked version stays current; a later story statement of the fact is kept as a conflict, not a new version.** It applies to canon facts and to the owner's corrections. | No lock yet; lock every canon fact by default. |
| Q8 | Host evidence first? | **Yes, step 2, on the owner's PocketRisu version (v1.13.0; `HOST-FACTS.md` is on v1.12.0):** `getCharacter`, `getCurrentLorebookEntries`, the chat's `note` in `getChatFromIndex`, the persona through `getDatabase` (already granted), permission prompts, timing and size at request time, what a card or lorebook edit changes, and which entries are in a request's prompt. Also a re-check of NMOS's existing host facts on v1.13.0. **With the owner's OK, a count-only inventory of the canon of the two measured chats** from a copy of the owner's PocketRisu save (entries, keys, field lengths; no text leaves it). | Source reading only; skip the inventory. |
| Q9 | How is it measured? | **Deterministic conflict fixtures for each source kind; on both measured chats with their canon: M0 no category worse, the secret gate 6 of 6, the K31 given-name probes, the model calls canon took; an upgrade from Phase 13 `main`; a real-host smoke (a card edit makes a new revision, a conflict shows, a lock holds); retrieve latency at 10,000 messages with a 200-entry lorebook within +5 ms p50 of Phase 13 `main`; one Codex review.** | Synthetic canon only. |
| Q10 | Release? | **None**, as decided on 2026-09-28. | — |

## Goal

NMOS knows what the story started from. The names the card and the lorebooks give count as mentions, a story that
drifts from the card shows up for the owner to judge, and a fact the owner locks holds. The model reads canon only
where the story uses it, and the message extractor is untouched.

## Evidence behind the scope

- **The host exposes canon to the plugin** (source reading, PocketRisu v1.13.0, `src/ts/plugins/apiV3/v3.svelte.ts`
  and `src/ts/storage/database.svelte.ts`; to be observed in step 2):
  - `getCharacter()` returns the current character's snapshot. Its story fields are `name`, `desc`, `personality`,
    `scenario`, `firstMessage` and its alternates, `globalLore` (the character's lorebook) and `chats`. It needs no
    permission in the source.
  - `getCurrentLorebookEntries()` returns the character's, the chat's (`localLore`) and the active modules' entries:
    `key`, `secondkey`, `comment`, `content`, `mode` (`normal`, `constant`, `multiple`, `child`, `folder`),
    `alwaysActive`, `selective` and an optional `id`. It returns every entry, activated or not.
  - A chat carries `note` (the author's note) and `bindedPersona`. NMOS already reads the chat through
    `getChatFromIndex`.
  - `getDatabase` lists `personas` (with `personaPrompt`) among the keys a plugin may read. NMOS already has that
    permission for the persona's name (ADR 0023, `HOST-FACTS.md`).
- **The owner runs PocketRisu v1.13.0** (the container's `package.json`, 2026-09-28). Since the owner moved to it,
  production recorded 16 requests with NMOS memory; `HOST-FACTS.md` was observed on v1.12.0.
- **What NMOS lacks without canon.**
  - A character called by a given name alone is no mention (K31): the lorebook is where such names are usually
    listed.
  - A persona narrated in the third person does not bring its own facts (K32).
  - Nothing tells NMOS the story's starting state. A card fact the story never repeats is invisible to memory, and
    a story that contradicts the card (a wrong eye color, a relationship the card forbids) goes unnoticed.
- **What NMOS already does with the prompt.** It sends nothing whose source revision is in the outgoing messages
  (D3), and the architecture already calls the lorebook canon for conflict checks, not a retrieval payload (D3).

## In scope (Phase 14)

1. **This document**, approved.
2. **Host evidence (Q8).** On an isolated PocketRisu v1.13.0: the canon calls, permissions, sizes and timing,
   edits, and which entries a request's prompt holds; a re-check of the existing host facts; `HOST-FACTS.md`. With
   the owner's OK, a count-only canon inventory of the two measured chats (outside the repository).
3. **Capture (Q1, Q2; ADR, migration 0025).**
   - The plugin sends a canon manifest with each sync, and the sidecar stores each canon text as an immutable source
     revision of the conversation.
   - A request records the canon revisions in force and the entries its prompt held.
   - The Inspector lists a chat's canon: each source, its revisions, and what is in force.
   - The plugin build changes; the owner installs it.
4. **Names (Q6).** The card's and persona's names, and the lorebook keys, in entity resolution and in extraction's
   hints, with the guard of Q6. Owner splits apply.
5. **Canon facts (Q3, Q4, Q5).**
   - A `canon` projection reads the card, the persona, the author's note and each entry a prompt held, with the
     extraction model.
   - Its assertions are facts from before turn 0 (source `canon`), superseded by the story from the turn it says
     something new.
   - A contradiction at the same time is listed in "Needs attention" with its choices.
6. **Canon lock (Q7):** `fact_lock` as an owner repair, with undo.
7. **Evaluation (Q9)**, upgrade, real-host smoke, latency, Codex review, documentation.

## Out of scope (Phase 14)

- Export and restore (Phase 15, Q0).
- Writing canon: the plugin never changes the card, a lorebook or the persona (host data stays read-only).
- Transition rules with pending, conflicting and rejected outcomes, and a semantic verifier (§20; not in Stage 6's
  done criteria).
- Group chats (the host has none, `HOST-FACTS.md`); hard POV isolation; story time (R4).
- A change to the message extractor or its generation.

## Acceptance criteria

- [ ] Every existing test and memory-evaluation case passes; recorded packets replay as they were.
- [ ] Host evidence for each canon source kind on PocketRisu v1.13.0 is in `HOST-FACTS.md`, and the existing host
      facts are re-checked there.
- [ ] Deterministic cases for each source kind:
  - capture, a new revision on an edit, and replay as of an earlier request;
  - names from canon, including the guard of Q6;
  - a canon fact superseded by the story, and a contradiction listed;
  - a lock that holds, and its undo;
  - an entry read only once a prompt held it.
- [ ] On both measured chats with their canon: M0 no category worse; the secret gate 6 of 6; the K31 given-name
      probes; the model calls canon took, reported.
- [ ] Upgrade from Phase 13 `main` (`tests/test_upgrade.py`).
- [ ] Real-host smoke on an isolated PocketRisu v1.13.0: a card edit makes a new canon revision; a contradicting
      story statement is listed; a lock holds in the next packet; undo releases it.
- [ ] Retrieve latency at 10,000 messages with a 200-entry lorebook within +5 ms p50 of Phase 13 `main`
      (`tools/bench_story.py`).
- [ ] One Codex review (AGENTS.md §14) of the capture, resolution and fold changes, each finding confirmed or rejected.
- [ ] `ARCHITECTURE.md` (decisions), ADRs, README, the Korean guide, KNOWN-ISSUES (K31, K32), CHANGELOG.

## Steps (one pull request each)

1. This document, approved. **Done** (2026-09-28).
2. Host evidence and the canon inventory. **Done** (`docs/HOST-FACTS.md` "Canon sources", H19;
   `docs/perf/canon.md`):
   - Every canon source is readable on v1.13.0, and an entry's text is in a prompt exactly when the host activated
     it.
   - `getCharacter()` clones the current chat (82–93 ms at 10,000 messages), so the card is read off the request
     path. Everything else costs about 1 ms, or rides on the chat read NMOS already does.
   - Sample 2's lorebook keys would make six characters' given names mentions (K31); the longest chat's keys are
     not names.
   - Reading only what a prompt held starts sample 2 at its 45 always-active entries, of 165.
   - The existing host facts held on v1.13.0.
3. Capture: migration 0025, ADR 0045, plugin and sync, the Inspector's canon list. **Done** (ADR 0045, D55):
   - canon kept per chat as immutable `canon` revisions, and manifests (each key's text hash and metadata,
     identified alike by plugin and sidecar) as the chat's canon at one time; a request records its manifest and
     the keys its prompt held, so it replays with its own canon;
   - `POST /v1/sync/canon`: a manifest, then the texts asked for, verified against their hashes; a late upload of
     an older observation is not applied;
   - the plugin uploads in the background, one upload per chat at a time. It reads the card off the request path,
     again at once when its description leaves the prompt;
   - the Inspector's folded "Canon" section;
   - no message pipeline reads canon; a state rebuild reads messages only;
   - a new plugin build.

   The step's Codex review found eight defects in the first cut (replays, ordering, a failed read, metadata, keys,
   the cache, deletes, sizes), all fixed with tests (ADR 0045).
4. Names from canon.
5. Canon facts, conflicts, and `fact_lock`.
6. Evaluation, real-host smoke, upgrade, latency, Codex review, documentation.

Every merge reaches the owner's `:edge`; no tag (AGENTS.md §13).

## Stop conditions

Stop and ask the owner when:

- the host does not expose a canon source as the source reading says, or asks for a permission the owner has not
  granted;
- reading canon would need writing host data, a host change, or a new permission;
- canon costs more model calls than step 2's inventory predicts, or a chat's canon is too large to keep per request;
- canon makes an M0 category worse or fails the secret gate;
- latency exceeds the criterion.
