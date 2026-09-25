# 0012 — Entity identity: read-time resolution, evidenced aliases, name hints

Status: accepted, 2026-09-23, with `docs/phases/PHASE-5.md` (owner approval, PR #34).
Owner decisions behind it: Track B §4 "Owner decisions" and the Phase 5 design questions of
2026-09-23 (name hints: yes, recorded and bounded).

## Context

Facts are keyed by the text the extractor wrote (`facts.version_key`). Known issue K8: "지도" and
"해안 지도" are two items, so a transfer the extractor names differently leaves two holders, and two
different items with one name collapse into one. Knowledge marks (`known_by`, `hidden_from`) are
free-text names too (ADR 0007).

Two facts shape the fix:

- **A deterministic resolver cannot merge names on its own.** "지도" may or may not be "해안 지도".
  Merging without evidence is the error the Track B stop conditions forbid ("entity resolution would
  silently merge ambiguous actors"). What the resolver can do safely is exact-name identity plus
  aliases the story itself establishes.
- **The extractor chooses the names.** Most K8 cases come from the model naming the same thing
  differently in different turns, because it only sees the target turn and `K` context turns (D7).
  It cannot reuse a name it has never seen.

The Track B proposal sketched persisted `entity` and `entity_alias` tables with their own resolver
generation. Facts are already computed at read time from head membership (`fact_versions`, ADR 0011),
which gives invalidation (invariant 7) for free. A persisted entity projection would need its own
invalidation on every edit, delete and reroll.

## Decision

1. **Entities are a read-time projection.** On every fact read, the sidecar resolves the subject and
   object mentions of the active assertions (the same rows `fact_versions` reads, D8 masking included)
   to entities, deterministically and without LLM calls. Nothing is stored; a resolver change is a code
   version (`RESOLVER_VERSION`), and "rebuilding" is the next read. Invalidation follows head
   membership exactly as facts do.
2. **Identity rule.** A mention is `(entity type, normalized name)`: NFC, casefold, collapsed
   whitespace (the existing `_norm`). Within one conversation:
   - the same type and normalized name is one entity;
   - `{{user}}`, `{user}`, `user` and `유저` are the user's persona entity (as `USER_NAMES` today);
   - a new predicate `also_called` (any entity type; value: the other name) links two names **only when
     both names occur in the normalized text of the turn the assertion comes from**. That check is
     deterministic. An `also_called` claim that fails it stays a `pending` assertion with a reason;
   - linked names form one entity. Its display name is the name mentioned first on the head. Its ID is
     `uuid5(conversation, RESOLVER_VERSION, type, normalized display name)`, stable for a given ledger;
   - different types never merge: an item "지도" and a place "지도" are two entities.
3. **Ambiguity is a result.** If a bare name is an alias of two or more entities of the same type
   (e.g. "하나" established for both "하나 선배" and "하나 후배"), a mention of that bare name resolves to
   `ambiguous`, lists the candidates, and is not linked. Its fact stays keyed by the text as today, and
   the Inspector shows it as ambiguous. Transliteration or similarity alone never links names.
4. **Merges are reversible because they are not stored.** An alias exists only while the turn that
   established it is active. Edit or delete that turn and the next read splits the entity again. Owner
   merge/split corrections are out of scope for Phase 5 (they would be source/audit data, Track B B7).
5. **Name hints in extraction (D7 amendment).** The extraction prompt gets the known entities of the
   chat: the resolved entities mentioned on the head **before the target turn**, most recently
   mentioned first, at most `NMOS_EXTRACT_HINTS` names (default 40), each with its type. The model is
   told to reuse a listed name when the target turn clearly refers to that entity, and to name a new
   entity otherwise. The list sent is stored on the extraction row (`hints`), so every extraction
   records what it saw. The hint count is part of the extractor generation key (D20).
6. **Hints do not make an extraction stale.** Extraction validity stays keyed by the target turn and
   its `K` context turns (`turn_hash`, D17). If the turn that introduced a hinted name is later edited
   or deleted, extractions that used the hint stay valid: a hint is naming guidance, and every
   assertion still needs evidence from the target turn. The recorded `hints` show what guided the name.
7. **Keys move to entities.** `version_key` uses the entity ID where a mention resolves and the
   normalized text where it is ambiguous or unresolved. ADR 0011's holder-per-item rule then applies
   per item entity, so "해안 지도" held by A and later by B (with "지도" reused through hints or
   linked by `also_called`) has one current holder.

## Amendment (2026-09-24, owner, after the real-model tier)

A character's `also_called` about **their own** name links it: the claim's speaker (`asserted_by`)
resolves to the claim's subject, e.g. a transfer student saying "다들 하루라고 불러 줘" links 미나토 하루카
and 하루. The model labeled that alias a claim in 3 of 3 runs (`docs/perf/phase5-extraction.md`), so the
narration-only rule never linked a self-introduction. A claim about someone else's name ("쟤는 하나야")
still links nothing. An impostor who introduces themself under another's name can therefore merge two
entities until that turn is edited or deleted; the Inspector shows the turn each alias came from.

## Amendment (2026-09-24, Phase 8, ADR 0021)

Typed participants of an assertion (`event`, `goal`, `knows`, `destroyed`) are mentions too, under
`resolve-v2`. The resolver reads them in a second pass, after every subject, object and evidenced alias
name, so they never change an existing entity's representative spelling, name order, aliases or
grouping. They never create alias edges. KNOWN ENTITIES candidates still come from subject and object
mentions only (item 5), and the serialized hint block is unchanged by participants.

## Amendment (2026-09-24, ADR 0023)

The persona's name as the host reports it for the conversation (e.g. 유우마) is a persona name for
characters, like `{{user}}` (`resolve-v3`). The extractor writes a named persona either way, so without
it one person was two entities. The persona entity is left out of KNOWN ENTITIES under any name.

## Amendment (2026-09-25, ADRs 0024, 0025)

An `also_called` is also valid when one name occurs in the turn and the other is exactly a name of the
same type the extraction was shown in its hints: a turn revealing who a character listed as unnamed
(`?` description, `extract-v9`) is. The owner's links (`entity_link`) join two mentioned names
(`resolve-v4`); a linked name is never ambiguous. Item 4 is amended for merges only: an owner merge is
owner input, stored and reversible; there is still no owner split. An entity is named after its first
name that is not a `?` description.

## Consequences

- K8 is reduced where the model reuses hinted names or the story states an alias. It is not
  eliminated: a model can still coin a new name, and "지도" vs "해안 지도" with no alias statement and
  no hint reuse stays two items. The Inspector lists entities, their names and ambiguous mentions, so
  remaining splits are visible.
- **Hints can cause a false merge.** A different map introduced as "지도" while "해안 지도" is hinted
  may be written as "해안 지도". The prompt limits reuse to clear references, and Phase 5 acceptance
  includes a real-model case with a second, different item of the same kind. If it fails, hints are
  switched off (`NMOS_EXTRACT_HINTS=0`, a new generation) rather than weakened silently.
- Prompt cost rises by the hint list: about 40 names × 5–8 tokens ≈ 200–300 tokens per call, against
  ≈1.06k prompt tokens per turn measured in `docs/perf/turn-extraction.md` (≈20–30 % more prompt
  tokens; an estimate, measured in Phase 5).
- Extraction input now depends on history beyond the `K`-turn window, through names only. D7 is
  amended accordingly; the extraction row records the dependency.
- Fact reads do more work per request (resolution over all active assertions). Phase 5 measures it at
  1k/5k/10k messages; if it exceeds the Phase 5 latency bound, the projection is persisted per head
  commit instead (same rules, stored with `RESOLVER_VERSION`, rebuilt without LLM calls). That fallback
  is decided by measurement, not built in advance.
- Knowledge marks (`known_by`, `hidden_from`) are resolved for display in the Inspector only. Packet
  semantics stay as ADR 0007 until principal identity is authorized (Track B, B5).
- Branches are separate conversations (D14), so entity identity never crosses chats.
