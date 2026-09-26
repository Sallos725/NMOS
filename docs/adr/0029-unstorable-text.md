# 0029 — Text PostgreSQL cannot store

Status: accepted, 2026-09-26. Audit finding A-01 (`docs/audits/NMOS-AUDIT-2026-09-26.md`); the owner chose
option (c) of the review (`docs/audits/NMOS-AUDIT-2026-09-26-REVIEW.md`). Bug fix, not a phase feature. No
migration, no generation change, no plugin or hash-contract change.

## Context

A JavaScript string can hold a lone UTF-16 surrogate: half of a character outside the Basic Multilingual
Plane, e.g. an emoji cut in two by a script or a tool that truncates by code unit. The browser's
`JSON.stringify` sends one as `\udxxx`. Hash format v1 hashes it in that escaped form on both sides
(`canonical.ts`, `canonical.py`, vector 8 of `fixtures/unit/revision-hash-v1.json`).

The sidecar could not take it:

- Pydantic refuses a `str` holding a lone surrogate (`string_unicode`). FastAPI's 422 response echoes the
  input, and encoding that response fails, so the client got **HTTP 500**.
- Past validation, psycopg would fail the same way: PostgreSQL `text` and `jsonb` cannot hold a lone
  surrogate at all.

A message body with one got HTTP 500 from `/v1/sync/bodies` on every request, so that chat never synced
again (fail open: the chat went on, without memory). A persona, chat or character name with one failed
every `/v1/sync/reconcile` the same way. A query with one failed `/v1/retrieve` for that turn.

## Decision

1. **Verify as sent, store as representable.** A message body is validated as the raw string
   (`models.BodyText`). `ledger.store_bodies` checks its hash on the text as sent, then stores the content
   and metadata with each lone surrogate replaced by U+FFFD (`canonical.storable`). The revision keeps the
   host's hash, so later manifests match it and the chat syncs as usual.
2. **Other request text is made storable before validation** (`models.Text`): the conversation labels
   (character, chat and persona names, `character_ref`), a manifest message's `name` and special comments,
   the recall query and previous reply, and entity-link names. Host ids are not changed: an id holding a
   lone surrogate is refused with 422.
3. **Every jsonb value a sidecar or worker process writes** goes through `canonical.storable_json`
   (psycopg's `set_json_dumps`, set in `nmos_sidecar/__init__.py`): manifests, metadata, traces, config.
4. **Extraction replies.** `ChatModel.complete_json` applies the same replacement to the reply text and the
   parsed object, since a model can escape half an emoji too.
5. **A 422 never becomes a 500.** The sidecar's validation-error handler makes the echoed input
   representable before encoding it.

## Consequences

- The stored content of such a revision differs from the host's text by the replaced code units, and no
  longer re-hashes to its `revision_hash`. Nothing re-hashes stored content: the hash is checked only when a
  body arrives. This is the closest copy the database can hold. It does not weaken invariant 1: the text as
  sent could not be stored at all, and the hash still identifies it.
- Recall, extraction and the Inspector see U+FFFD where the broken half was.
- Cost: validating a manifest's names adds ≈6.5 ms at 10,000 messages (13.9 → 20.4 ms for the request model,
  one machine). The append fast path is ≈156 ms at 10k, and the host's own stall there ≈1.7 s (K1).
- Rejected: (a) replacing lone surrogates in both `normalizeText` implementations. That changes the hash
  contract and needs a plugin release. (b) Refusing such bodies with 422. That leaves the chat unsynced.
