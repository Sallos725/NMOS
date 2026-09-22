# Phase 1 — Deterministic State, Inspector v0, Traces

> Owner authorization: 2026-09-22 ("complete to public-beta quality"). No LLM calls.

## Goal

Machine-shaped content that bots emit (status windows, HTML/regex display blocks) becomes
**current-state facts with provenance**, parsed deterministically (D10). Users can see what NMOS
stored and why a packet looked the way it did through a read-only inspector.

## In scope

1. **Parser rules** loaded from a JSON file (`NMOS_PARSERS_FILE`, optional). Rule kinds:
   - `regex`: a Python regex with named groups. Either `key` + group `value`, or groups `key` and `value`.
   - `block`: `start`/`end` regexes delimit a block; each line inside matching `key<sep>value`
     (separators `:`, `：`, `=`, `|`, `｜`) becomes a pair.
   - Optional `character` (host character ref, i.e. `saying`) and `role` filters; `prefix` for keys.
2. **`state_observation` projection** (rebuildable): `(revision, rule_id, rules_version, key, value)`,
   written when a revision body is stored, and rebuilt by `nmos-rebuild --state`.
3. **Current state** = for each key, the value from the latest *accepted, active, not-cut,
   not-disabled* revision in head membership. Because it is computed through head membership,
   edits, deletes, rerolls and swipes invalidate it synchronously (D8).
4. **Packet `<State>` section**: current state whose source revision is out of the outgoing
   context, with `as_of_turn`, within the same budget (state first, then excerpts).
5. **Inspector v0** (read-only HTML, served by the sidecar at `/inspector`): conversations, head
   membership with lifecycle, commits, current state, recent retrieval traces.
6. `GET /v1/conversations`, `GET /v1/conversations/{id}/state`, `GET /v1/conversations/{id}/traces`.

## Out of scope

LLM extraction, embeddings, editing through the inspector, parser authoring UI.

## Acceptance criteria

Status 2026-09-22 — met. Evidence: `apps/sidecar/tests/test_state.py` (parsers, invalidation through membership, rebuild, budget, inspector escaping); live PocketRisu run with `config/parsers.example.json` injected `<State>` (장소/시간/HP as of turn 59) only after that turn left the prompt; inspector rendered live conversations.

- [x] Parser rules of both kinds produce state from stored revisions; invalid rules are reported at
      startup and skipped, never crash the sidecar.
- [x] Current state follows edit / delete / swipe / reroll / disable / allBefore through head
      membership (tests).
- [x] State is rebuildable: deleting `state_observation` and running the rebuild reproduces it.
- [x] Packet contains `<State>` only for out-of-context state and never exceeds the budget.
- [x] Inspector pages render for a real host conversation; they escape all content.
