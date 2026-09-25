# 0025 — The owner joins names by hand

Status: accepted, 2026-09-25. Owner request after `v0.1.0-beta.16` (not a phase feature): a character
shown without a name and later named must become one entity, and the owner wants a way to fix such
cases themself, besides the automatic link of ADR 0024. Amends ADR 0012 item 4 ("owner merge/split
corrections are out of scope") for merges only, and D26.

## Context

Entity identity is a read-time projection (ADR 0012): names are joined only by evidence in the story
(both names in one turn, a self-introduction, and since `extract-v9` a reveal of a listed description).
When the model misses the evidence, or when turns were extracted by an older generation, two names of
one character stay two entities, and nothing but a re-extraction could change that. The owner knows who
is who.

## Decision

1. **Owner links are owner input, not derived memory.** Table `entity_link` (migration 0019): a
   conversation, an entity type, a name and the name it is the same as, as the Inspector showed them,
   with `created_at` and `removed_at`. A rebuild keeps them. Deleting the conversation deletes them
   (ADR 0009).
2. **Resolution (`resolve-v4`).** A link joins its two names whenever the head mentions both with that
   type; a name the head does not mention (its turn was edited or deleted) links nothing until it is
   mentioned again. The owner outranks the story: a linked name is never ambiguous, and when the story's
   aliases made it ambiguous, its own automatic aliases are ignored and only the owner's link joins it,
   so the other candidates do not merge. Nothing else changes: the persona rule, participants and the
   display name (ADR 0024 item 5) apply as before.
3. **API.** `POST /v1/conversations/{id}/entity-links` with `entity_type`, `name`, `same_as` (both must
   be mentioned on the head with that type, and be different names; otherwise 422), answered with the
   link and the joined entity. `POST /v1/conversations/{id}/entity-links/{link}/remove` sets
   `removed_at`; the next read resolves the names as the story alone does. The entity list carries each
   entity's current links.
4. **Panel.** On an entity page of the Inspector, the panel shows the entity's links with an undo
   button, and a picker of the other entities of the same type (most mentioned first) with a join
   button. The Inspector's entity tables show a "Joined by the owner" column. The Inspector HTML itself
   stays read-only (H15).
5. **Hints.** Extraction resolves hints with the owner's links, so after a join KNOWN ENTITIES shows the
   joined names as one entity and the extractor reuses them.

## Consequences

- One click fixes a split the story never resolves, including turns extracted before `extract-v9`, with
  no model call and no re-extraction. Facts, threads and version keys follow at the next read.
- Joins change entity ids where the joined entity's display name changes; an Inspector page open on the
  old id says the entity is gone, and the panel moves to the joined entity.
- There is no owner split: a false automatic alias stays until its turn is edited or deleted. A split
  would need its own rule for groups joined through several aliases; it waits for a case.
- The owner can join names that are not the same person; the link is visible and undoable, and nothing
  is deleted.
