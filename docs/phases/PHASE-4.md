# Phase 4 (soft) — Character Knowledge Annotations

> Owner authorization: 2026-09-22, as a subset for the public beta (ARCHITECTURE D19).
> Written after the fact (2026-09-22) to record what shipped in `v0.1.0-beta.2`. Optional: without
> `NMOS_LLM_URL` there are no facts and therefore no annotations.

## Goal

Invariant 6 ("character knowledge is not world knowledge") in a form that works for sim bots, where one
generation writes every character (D9): facts say **who knows them**, and the packet tells the model so.

## In scope

1. **Extraction** records `known_by` / `hidden_from` (character names) per assertion, alongside the
   Phase 2 predicate and provenance. Stored in `migrations/0006_knowledge.sql`.
2. **Packet**: facts carry `known_by` / `hidden_from` attributes; the `<Note>` tells the model that
   characters not listed in `known_by` do not know the fact.
3. **Ranking**: a fact hidden from a character addressed in the latest turns is ranked first, so the
   model sees the secret together with who must not know it.

## Out of scope

Hard character-POV isolation (filtering the packet per principal), group-chat principals (the tested
PocketRisu build has no group chat, HOST-FACTS S13), threads/causal links, verifier model, MCP.
These are Phase 5+ and need a new owner-approved phase document.

## Acceptance criteria

Status 2026-09-22 — met. Evidence: `apps/sidecar/tests/test_extraction.py`
(`test_knowledge_annotations_reach_the_packet`, `test_secret_hidden_from_addressed_character_is_selected`);
real sim-bot run described in `docs/STATUS.md` (RisuRealm bot, fresh install from release assets).

- [x] Extracted facts carry `known_by` / `hidden_from` into the packet.
- [x] A fact hidden from the addressed character is selected ahead of other facts.
- [x] Without an LLM configured, behavior is unchanged from Phase 1.
- [x] Documented as guidance to the model, not isolation (README, `docs/guide.ko.md`).
