# Phase 47 — "Not a character": the owner leaves a name out of the cast and the relationships

Status: **draft**, 2026-10-14. A correction found by tester feedback, not a roadmap stage. Not approved for
implementation. Questions Q1–Q3 are open.

**High risk if built** (`AGENTS.md §14`):
- a migration on stored owner input (`owner_repair`'s kind check);
- a change to what memory reads select (entities and the facts that name them leave the view and the packet);
- identity: it decides which names are one entity that does not count.

## Why

1. **A name that is not a character can still become one in memory.** A tester reported that the name of a
   simulation-style bot card (a status-window or game-master card, not a person in the story) appeared in the
   Inspector's people and relationships. Extraction reads the turn text; a name the text uses like a speaker or a
   party to a relationship becomes an entity with facts (ADR 0012).
2. **Two different cases hide behind "not a character".** The bot card's name is not part of the story: nothing it
   "says" is a fact about the world. A monster the party fights is the other kind: it is not a person, but facts
   about it (what it is, who killed it, what it dropped) are the story, and a question about it must still be answered
   from memory. Extraction files both under the same entity type, so one all-or-nothing exclusion would either keep the
   bot's noise or erase the monster's history.
   - **Measured, read only, on the owner's trial copy (2026-10-14; numbers only, no chat content).** A monster filed
     as a `character` has 3 facts of its own (2 `also_called`, 1 event) and appears as a participant in 15 other
     rows: 9 events of real characters and 6 `destroyed` facts of items. It is never an object, and it has no
     standing-pair fact (`relationship`, `role_toward`, `feels_toward`, `addresses`), so it shows in the people list
     and in no relationship pair. Most of what memory knows about it is other subjects' facts. A scope that drops
     facts by subject, or by who takes part, would erase those events; only `cast` keeps them.
3. **The owner has no way to say "this is not a character".** The repairs of ADR 0044 can retract one fact (`fact_retract`),
   correct one, close a thread or split two names. None removes an entity. Entities are derived from facts
   (`entities.Resolution.entities`), so the only workaround is to retract every fact that names the entity, one at a
   time. A name with dozens of facts makes that unusable, and a new fact on the next turn brings it back.
4. **Raw text and derived rows are never edited** (invariants 1, 2). The fix has to be owner input applied at read time,
   found by what it says and not by an id, so a rebuild or a new extractor generation keeps it (ADR 0044 §2). The
   name joins (ADR 0025) and splits already work that way.

## Proposal

S1. **A new owner repair kind, `entity_exclude`.**
- Target: the entity's type, the name the owner saw and a `scope`, `cast` or `memory` (Q1). The read matches the
  name through entity resolution
  (`repairs._ekey`), so every name the story joins to it follows.
- Stored in `owner_repair` like the other kinds: the chat, `created_at`, `removed_at`, an optional note. Undo sets
  `removed_at`. A rebuild keeps it. Deleting the chat deletes it (ADR 0009).
- Migration `0030` is reserved by the held Phase 45. This phase takes the next free number when it is
  implemented, and replaces `owner_repair_kind_check` the way `0029_state_dismiss.sql` did.

S2. **What a read does with an excluded entity**, by scope.
- **`cast` ("not a character").** The entity leaves the cast, the people list and every relationship pair of the
  Inspector and of `<Cast>` in the packet. Its facts stay: the memory view, the packet's fact lines and recall are
  unchanged, so "how was the monster killed?" still finds its facts. Its name is no longer offered as a character
  (a speaker, a pair end).
- **`memory` ("not part of the story").** Everything `cast` does, and the facts whose subject is the entity, and the
  relationship and role facts it is one end of, also leave the memory view. A row that lists the entity only among its
  participants, under another subject, stays (the measured monster has 15 of those). They are not deleted: the view omits them
  after resolution (`facts.memory_view`, beside `apply_facts`). A fact that names the entity as an object beside a
  real character stays: the real character's memory of it is still theirs.
- Raw turns can still come back as excerpts (invariant 1).

S3. **Guards.** The API answers 422 with the reason, as ADR 0044 §6 does, when:
- the name is the chat's persona or a character the host names for the chat;
- the name resolves to no entity of the chat;
- the entity is already excluded.

S4. **A preview before it applies**, like a join or a split (ADR 0055): how many cast entries, relationship pairs
and facts leave. `expect` on the repair and on its removal checks the preview's fingerprint.

S5. **Replays** (ADR 0027): a read as of an earlier time sees only the exclusions in force then, so a recorded
packet replays as it was. A packet line an exclusion removed leaves no ledger row. The repair list shows what each
exclusion hid.

S6. **Panel and Inspector.** The Inspector HTML stays read-only (H15). The panel adds a **캐릭터가 아님 / Not a
character** button on a character's page and on each relationship row, a line in the chat's Repairs section for each
exclusion (what it hides, undo), and the preview's counts in the confirm step. Korean first, English beside it
(`i18n.ts`). The plugin stays light (`nmos-plugin-stays-light`): the preview and the matching are the sidecar's.

S7. **No change to extraction.** The extractor still extracts the name; the exclusion applies at read time. Telling
the extractor not to (a hint in the prompt) is a new generation and the full live gate. It is out of scope here.

## Out of scope

- Extractor-side prevention (S7), or a card-level "this card is a tool, not a story" switch.
- A bulk or automatic detector of non-character names.
- Deleting the entity's facts, rows or raw turns. Nothing is deleted.
- The model and reasoning questions from the same feedback: extraction sends no reasoning parameter
  (`llm.py` request body), so it follows the provider's default. A docs note is a separate trivial edit.

## Questions for the owner

- **Q1 — one action or two.** A monster or an object filed as a person (the owner's example: a monster in one
  chat's memory) needs `cast`; a simulation bot card's name needs `memory`.
  - (a) Two scopes, one button. **Recommended:** **캐릭터가 아님** applies `cast` by default, because it never loses a
    fact and the monster case is the common one. The preview then offers **기억에서도 제외 / Also leave its facts out**
    with the counts that would go, so `memory` is a second, explicit choice and never the default.
  - (b) `cast` only in this phase. The bot card's facts keep filling the packet, so it does not fully solve the case
    that started this phase.
  - (c) `memory` only. Erases a monster's history. Not recommended.
- **Q2 — what the button is called and where it lives.** Recommended: **캐릭터가 아님** on the character page and on
  relationship rows only, with no bulk select in this phase.
- **Q3 — the gate.** The change touches memory selection but no prompt, generation or worker (`AGENTS.md §7.6`,
  recall only). Recommended: the zero-call replay gate, then no live run. Say if the owner wants a reduced live run.

## Steps

1. This spec, and the owner's answers.
2. **Sidecar.** `entity_exclude` in `repairs.KINDS` and `plan`, the migration, the read in `facts.memory_view`, the
   guards, the preview, the repair list and tests:
   - the repair survives a rebuild and a new generation;
   - a joined name follows, a split name does not;
   - the persona and an unknown name are refused;
   - scope `cast` leaves every fact and every recall result unchanged, and scope `memory` drops the subject facts and
     the pair facts but keeps a fact that names the entity as an object beside a real character;
   - a replay as of an earlier time ignores a later exclusion;
   - with no exclusion, every read is identical to `main`.
3. **Panel.** The buttons, the Repairs lines, the preview confirm, i18n, and a rendered check on the synthetic test
   instance (headless Playwright, `pocketrisu-test-harness`).
4. **Measurement** (zero calls, recall-only gate). Every gate probe under the current default policy, three rounds,
   majority deciding, with and without an exclusion of a synthetic non-character name added to a copy.
5. **Default and docs.** `docs/STATUS.md`, an ADR (next free number), `docs/KNOWN-ISSUES.md`, the README's Inspector
   section.

## Acceptance criteria

1. With no exclusion in force, a replay of every gate probe is identical to `main` before this phase (three rounds).
2. On a synthetic chat with a bot card name and a monster: `cast` on the monster removes it from the people list, the
   relationship pairs and `<Cast>` and changes no packet fact line or recall result; `memory` on the bot name also
   removes its subject facts. Undo restores all of them.
3. The exclusion holds after a rebuild and after a re-extraction with another generation.
4. The persona, a host character and a name the chat never mentions are refused with a reason.
5. Export → restore round-trips the repair. A restore into a build without its migration is refused as for any newer
   schema.
6. A retrieve with 100 exclusions at 10,000 messages costs at most +5 ms p50 over `main`. (Phase 13 measured +7 ms for
   100 fact repairs, and the owner accepted that miss; this one is held to the same bar and reports the number.)

## Stop conditions

- A probe is lost by the majority over rounds with no exclusion in force. Stop, diagnose and report.
- A `cast` exclusion changes a packet fact line, or a `memory` exclusion hides a fact of a real character. Stop and report before widening.
- The migration cannot be made without rewriting stored rows. Stop and ask.

## Evidence rules

The repository is public. Tests and fixtures use synthetic names and invented bot cards only. The feedback that
started this phase, and any chat it came from, stays out of the repository.
