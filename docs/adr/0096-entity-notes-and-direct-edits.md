# 0096 — Entity notes (`entity_note`) and direct editing across categories

Status: accepted, 2026-11-26, PHASE-70. Builds on ADR 0044 (owner repairs), ADR 0076 (`entity_exclude`), ADR 0087 (`entity_pin`), and ADR 0027 (accountable packets and as-of replay). Migration `0045`.

## Context

Tester feedback surfaced two practical gaps in daily long-chat usage (400+ turns):

1. **Editing non-fact views felt hidden or incomplete.** Although relationships (`relationship`, `role_toward`, `feels_toward`, `addresses`), secrets, and items (`possesses`, `located_in`, `destroyed`) are all backed by `view["facts"]`, their dedicated Memory Explorer cards (`pairs`, `epistemic`, `items`) and rich Person Sheet lacked inline repair controls (`fact_correct`, `fact_retract`, `fact_hidden`), `possesses` could not correct its holder (`subject`), and the Add-fact form hardcoded `world_fact` to `concept`.
2. **In-story objects lose physical details after hundreds of turns.** Items, places, groups, and concepts introduced mid-story (outside the lorebook) have no dedicated appearance/description predicate, and even `world_fact` rows are labeled `supportive` under `packet-v16+` (`named_by_words`), so they can rest or lose budget slots during normal narration. Expanding automatic extraction to capture every visual detail would require a new extractor generation, increase per-turn output tokens, introduce background-prop noise, and force expensive re-extraction of existing chats.

## Decision

1. **`entity_note` is an owner repair (`owner_repair`, migration `0045`).**
   - `target`: `{"entity_type": "character|place|item|group|concept", "name": "<resolved name>"}`.
   - `value`: `{"text": "<trimmed single-line note, 1..300 chars>"}`.
   - Supports all five entity types (`ENTITY_TYPES`), including the persona. Entities excluded with `scope="memory"` (`entity_exclude`, ADR 0076) cannot be noted and have existing notes suppressed on read; `scope="cast"` exclusions still keep their notes.
   - No new table, no new query on `/v1/retrieve`, no extractor or embedding generation change. Notes survive rebuilds and new generations, follow `entity_link` merges and `name_split` separations via read-time entity resolution (`r.entity`), inherit automatically on branches (`branch.py`), export/restore in archives (`archive.py`), and delete with the conversation (`ADR 0009`).
   - Saving a new `entity_note` for an entity that already has one marks the previous active row `removed_at = now()` in the same transaction so the Repairs list stays tidy while preserving full audit history and as-of replay.
2. **Mention-triggered packet injection (zero cost when unused, replay-safe).**
   - Active under `ENTITY_NOTE_POLICIES` (`packet-v20`, `packet-v21`, matching `PIN_POLICIES` so frozen `packet-v19` and older remain permanently untouched). Notes are still stored, editable, and visible in Memory Explorer / Inspector under every policy. When a chat has no active `entity_note`, gather and compile are completely untouched (byte-identical packets).
   - Selection tiers (at most `ENTITY_NOTES_MAX = 5` notes per packet):
     - **Tier 1 (score 3.0, required, `g.lead`)**: entity name or alias (including `name_variants` aliases; or `FIRST_PERSON` for a persona note) appears in the current user message (`query`).
     - **Tier 2 (score 2.0, required, `g.lead`)**: entity name or alias appears in `previous_ai`.
     - **Tier 3 (score 1.0, supportive, `g.facts`)**: character is explicitly pinned (`g.pins`), or an `item` is currently held (`possesses`, positive) by a character explicitly named in `query` or `previous_ai`. Unrelated turns mentioning no noted entity (and no holder of a noted item) inject zero notes (0 tokens).
   - Rendered as `<Fact kind="entity_note" source="owner" locked="true" type="<entity_type>"><name>: <text></Fact>` inside `<Facts>`:
     - Stripped by both `clean-v3` and `clean-v4` if echoed (K27).
     - Uses existing `locked="true"` note explanation without altering older packet notes.
     - Provenance `ref = {"repair": "<repair_id>", "entity": "<entity_id>"}`. Tier 1 & Tier 2 notes are added to `g.named` and exempt from overuse rest so repeated item mentions keep consistent descriptions across 400+ turns.
   - Because `memory_view(..., known_at=at)` filters `owner_repair` by `created_at <= at AND (removed_at IS NULL OR removed_at > at)`, all historical traces from before a note existed replay byte-identically (ADR 0027).
3. **Holder correction (`new_subject`) on `fact_correct` and direct UI exposure.**
   - `RepairRequest` adds optional `new_subject` (max 120 chars). `repairs._plan_fact` accepts `new_subject` under the same `version_key` guard as `new_object` (for `possesses`, `version_key` is keyed by the item, so correcting the holder works both in-place and from a later turn).
   - Memory Explorer (`views.explore`) exposes inline edit drawers on `pairs`, `epistemic` (secrets), `items` (current whereabouts fact + `entity_note`), and `entities` (`entity_note`); rich Person Sheet (`views.person(rich=True)`) and the Inspector entity page (`/e/{eid}`) expose an inline Entity Note editor for all 5 entity types. Default `views.memory(rich=False)` and `views.person(rich=False)` remain byte-identical to Phase 60 goldens.
   - The Add-fact form (`ui.ts`) offers localized predicate labels, dynamic `subject_type` selection for multi-type predicates (`world_fact`, `located_in`, `possesses`, `event`), and `destroyed`/`threat`/`question`/`owes`.

## Consequences

- Zero LLM cost, zero extraction generation churn, and <1 ms read overhead on the request path.
- Token budget impact is zero unless a noted entity actually appears in the turn/scene, bounded by 300 chars/note and 5 notes/packet.
- Long multi-paragraph lore documents remain best served by PocketRisu's chat-local lorebook; `entity_note` is intentionally scoped to concise reference cards for in-story entities.
