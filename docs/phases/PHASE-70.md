# Phase 70 — Direct Editing Across Categories & Entity Notes (`entity_note`)

Status: **approved** (owner, 2026-11-26: implement both Stage 1 and Stage 2 for `0.7.0`). Not a roadmap stage.

**High risk** (`AGENTS.md §14`):
- **Schema / migration**: additive `owner_repair_kind_check` update (`migrations/0045_entity_note.sql`, no backfill).
- **Memory selection / packet compilation**: mention-triggered injection of owner `entity_note` lines in `retrieval.py` / `packet.py` (must preserve byte-identical packets when unused and byte-identical as-of replay per ADR 0027).
- **Owner input lifecycle**: rebuild survival, alias merge/split tracking, `entity_exclude` (`memory` scope) precedence, branch inheritance, archive export/restore, and conversation delete (ADR 0009).
- **UI sanitizer boundary**: inline edit/note controls in `views.py`, `inspector.ts`, and `ui.ts` with zero XSS sinks.

---

## Why

Real user feedback highlighted two pain points in long role-play chats (400+ turns):

1. *"How do I edit values for relationships, secrets, and items — not just facts?"* — The backend already backed all of them via `owner_repair`, yet the dedicated Memory Explorer tabs (`pairs`, `epistemic`, `items`) lacked inline repair buttons, `possesses` couldn't edit its holder (`subject`), and `+ Add fact` locked `world_fact` to `concept`.
2. *"Can I attach descriptions to items or entities so 400 turns later in-story objects don't keep changing appearance?"* — Automatic extraction doesn't track arbitrary object appearance across 400 turns without noise and re-extraction cost. An owner-authored, mention-triggered **`entity_note`** gives users a zero-LLM-cost, alias-aware mini reference card directly inside NMOS.

---

## Scope

### S1. Direct Editing Across Relationships, Secrets, Items & Add-Fact Form
- **`fact_correct` with `new_subject`**: allow correcting `subject` (validated by the same `version_key` safety check as `new_object`; `possesses` shares its item-keyed `version_key`, so changing an item's holder works both in-place and from a later turn). `_corrections(f)` offers `subject` + `object` for `possesses`.
- **`items` provenance**: `facts.memory_view` includes `fact_id` and `entity_id` on each item summary dict so `views.explore` can attach repair controls and entity notes directly to item cards.
- **Memory Explorer (`views.explore`)**:
  - **`pairs`**: inline `수정` drawer listing each current relationship / role / feeling / address row with its `fact_retract`, `fact_correct`, `fact_hidden`, `fact_lock` / `undo` buttons (plus existing `entity_exclude`).
  - **`epistemic` (secrets)**: keep per-character `secret_found_out` / `secret_keep` controls and add an inline `수정` drawer for the underlying secret fact (`fact_correct`, `fact_retract`, `fact_hidden`, `fact_lock` / `undo`).
  - **`items`**: show any attached `entity_note` and add an inline `수정` drawer for the current whereabouts fact (`possesses` holder/item, `located_in` place, `destroyed` reason) plus inline `entity_note` edit/delete.
  - **`entities`**: show any attached `entity_note` and inline `entity_note` edit/delete across all 5 entity types (`character`, `place`, `item`, `group`, `concept`).
- **Rich Person Sheet (`views.person(rich=True)`)**: add inline edit drawers for relationships (`s-rels`) and show the entity's note; `rich=False` and `views.memory(rich=False)` remain byte-identical to Phase 60 goldens.
- **Add-fact form (`ui.ts`)**: localized predicate labels, dynamic `subject_type` picker for multi-type predicates (`world_fact`, `located_in`, `possesses`, `event`), and inclusion of `destroyed`, `threat`, `question`, `owes`. Avoid duplicating `fact_hidden` when already emitted by the sidecar.

### S2. Entity Notes (`entity_note`, Migration `0045`, ADR 0096)
- **Migration `0045_entity_note.sql`**: add `'entity_note'` to `owner_repair_kind_check`.
- **Storage & resolution (`repairs.py`, `facts.py`, `api.py`)**:
  - `ENTITY_NOTE_MAX_CHARS = 300`, trimmed single-line text in `value = {"text": ...}`, `target = {"entity_type", "name"}`.
  - All 5 entity types supported; `entity_exclude` with `scope="memory"` blocks/suppresses notes (`scope="cast"` still allowed).
  - Posting a new `entity_note` for an entity that already has one supersedes the prior active row (`removed_at = now()`) in the same transaction.
  - Read-time fold `repairs.entity_notes(in_force, r)` resolves through aliases/splits; exposed in `view["entity_notes"]`, `GET /v1/conversations/{id}/entities` (`note: {id, text}`), `explore_data`, `person_data(rich=True)`, and Repairs/Attention views (`rk.entity_note`).
- **Mention-triggered packet recall (`retrieval.py`, `packet.py`)**:
  - Active under `ENTITY_NOTE_POLICIES` (`packet-v20`, `packet-v21`, matching `PIN_POLICIES` so frozen `packet-v19` and older stay untouched); zero-op when a chat has no active notes.
  - Tier 1 (`query` mention, score 3.0) & Tier 2 (`previous_ai` mention, score 2.0) → `required` in `g.lead`, exempt from overuse rest.
  - Tier 3 (pinned character in `g.pins`, or item currently held via `possesses` by a character explicitly named in `query` or `previous_ai`; score 1.0) → `supportive` in `g.facts`. Unrelated turns emit zero notes (0 tokens).
  - Capped at `ENTITY_NOTES_MAX = 5` per packet; emitted as `<Fact kind="entity_note" source="owner" locked="true" type="...">name: text</Fact>` (stripped by `clean-v3` and `clean-v4`).
  - Replays identically as of `known_at` (ADR 0027).
- **Entity Note editor in plugin (`ui.ts`, `inspector.ts`, `i18n.ts`)**:
  - Allow `entity_note` in `inspector.ts` `REPAIR` regex.
  - Inline card note form (`noteForm`) inside Explorer (`items` and `entities` cards) reading existing text safely from `.v-note-text`.
  - Dedicated `noteCard` in `ui.ts` on both Person Sheet (`/v1/views/c/{id}/person/{eid}`) and Inspector entity pages (`/v1/inspector/c/{id}/e/{eid}`) for all 5 entity types, with live `0/300` char counter, Save, and Delete.

---

## Out of scope

- Any extractor, canon, summary, or embedding generation change (zero LLM calls, zero jobs queued on upgrade).
- Multi-paragraph lore documents (covered by PocketRisu's chat-local lorebook).
- Author's Note prompt changes (`notes.py`) or `conversation_carry` snapshot schema changes.

---

## Acceptance criteria

1. **Migration & upgrade safety**: `0045_entity_note.sql` applies cleanly on every fixture in `fixtures/upgrade/*.sql` (`test_upgrade.py`), accepts `'entity_note'`, rejects unknown kinds, and leaves all existing rows intact.
2. **Entity note lifecycle (`test_phase70_entity_notes.py`)**:
   - Create, update (superseding prior row), undo/delete, validation (empty, >300 chars, unknown entity, `scope="memory"` exclusion), and support for all 5 entity types (`item`, `place`, `character`, `group`, `concept`).
   - Alias merge (`entity_link`) and `name_split` tracking, rebuild survival, archive export/restore round-trip, branch inheritance (`branch.inherit`), and conversation delete (ADR 0009).
3. **Packet & replay safety (`test_phase70_entity_notes.py`)**:
   - Zero packet diff when a chat has no `entity_note`.
   - Mention in `query` or `previous_ai` (including aliases) injects `<Fact kind="entity_note" source="owner" locked="true" type="...">` as `required` in `<Facts>`, does not rest across repeated requests, respects `ENTITY_NOTES_MAX = 5`, and is stripped by `clean_text` (`clean-v3`) and `clean_text_v4`.
   - Scene/held-item Tier 3 triggers cleanly when a scene character carries a noted item.
   - As-of replay (ADR 0027) reproduces packets before note creation, after creation, after edit, and after removal.
4. **Stage 1 direct edits (`test_phase70_entity_notes.py`, `test_phase69_views.py`)**:
   - `fact_correct` with `new_subject` updates a `possesses` holder both in-place and from a later turn while refusing cross-key `subject` changes at later turns.
   - `views.explore` renders inline edit controls on `pairs`, `secrets`, `items`, and `entities` cards with zero `<table>` elements and full XSS escaping; `views.person(rich=True)` includes relationship edit drawers and entity note display.
   - Phase 60 golden tests (`test_phase60_views_unchanged.py`) remain 100% byte-identical.
5. **Plugin UI & sanitizer (`phase70-ui.test.ts`, full `vitest` + `typecheck` + `build`)**:
   - `repairAction` accepts `entity_note:<uuid>` and rejects malformed values.
   - Explorer inline `entity_note` form, `fact_correct` with `subject`, upgraded `factAddCard` (dynamic `subject_type` for `world_fact`, `destroyed`), and `noteCard` on Person Sheet / non-character entity pages work end-to-end.
   - `test_docs_consistency.py` and `test_plugin_build.py` pass.
