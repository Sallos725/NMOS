# 0006 — Projection generations, coverage policy, normalized text

Status: accepted, 2026-09-22. Issues #6, #7, #8, #9, #13. Decisions D20, D21.

## Context

Derived memory must be rebuildable from source ledger + compiler + configuration (invariant 2).
Up to beta.3 the configuration part was not part of any identity:

- Extractions were keyed by `(revision, window, compiler_version)` and jobs deduped by
  `extract:<rev>:<win>:<compiler_version>`. Changing the LLM model or endpoint queued a backfill that
  the dedupe key and the "already done" check both suppressed, so **a model change never re-extracted**.
- Embeddings were keyed by model name. Moving to another endpoint that serves a model with the same
  name mixed two vector spaces. With equal dimensions, cosine similarity still ran and could return
  plausible but meaningless results.
- The worker reloads settings every 30 s, so a job queued right after a settings change could run on
  the previous model.
- A compiler bump hid every older fact but re-queued only the latest 100 messages per chat. The
  "stale extractions exist" check then stayed true forever, because history is kept on purpose.
- Lexical recall searched raw content while everything else used `clean_text()`, so words inside
  dropped `<Thoughts>` blocks could create hits that the injected excerpt did not contain.

## Decision

1. **Generation keys.** `projection_generation(key, kind, model, endpoint, spec)` holds a SHA-256
   over a JSON spec. For extraction, the spec is compiler version, system-prompt fingerprint,
   predicate-registry fingerprint, normalizer version, endpoint identity (scheme/host/port/path,
   lower-cased, no trailing slash), model, JSON mode, temperature, window and char limits. For
   embeddings, it is endpoint identity, model, normalizer, chunker version, chunk size, max chunks
   and document profile. API keys are never included: rotating a key re-derives nothing.
2. **Binding.** Job dedupe keys and payloads include the generation, and so do `extraction.extractor_key`
   and `revision_embedding.projection`. `claim()` only returns jobs whose `(kind, generation)` a
   handler implements. Jobs for another generation stay queued until a matching handler exists,
   and the processing functions refuse a mismatch. On activation, queued jobs of other generations
   become `obsolete`. Switching a provider off (no URL or model) makes its queued and running jobs
   `obsolete` in the same transaction as the settings save, so no further job starts even before the
   worker reloads; a request already in flight finishes but is not retried (#18). Work that became
   `obsolete` and is wanted again (switching back, re-enabling) is revived in place, since the job key
   is unique across statuses.
3. **Active generation.** The most recently activated generation of each kind. Facts read only its
   extractions, and vector search compares only its vectors. It stays active while the provider is
   switched off, so turning extraction off does not erase facts.
4. **Coverage policy on activation** (startup, or any settings change that changes a key):
   - queue the latest `backfill` eligible items of every chat (priority 250 extraction / 200
     embeddings);
   - queue every older item that some earlier generation had covered at background priority (900 / 950),
     so upgrades restore previous coverage instead of shrinking it to the recent window;
   - never queue an item that already has a current-generation row or a `dead` job. The policy is
     idempotent: a restart with a complete generation queues nothing.
   Items never covered before (history beyond the first-sight backfill) are not queued automatically
   and are reported as `not_queued`.
5. **Coverage is measurable.** For each conversation: eligible, compiled/embedded, pending, failed
   (dead), not queued, only-older-generation, truncated targets, partially embedded revisions.
   Exposed at `GET /v1/conversations/{id}/coverage`, in `/v1/health` (active keys) and in the
   Inspector. Anything below 100 % is labelled partial.
6. **Upgrade: pre-generation rows are inactive.** Existing embedding rows become `legacy:<model>`.
   Their endpoint was never recorded, so their vector space is unknown: a beta.3 install could have
   switched endpoints under the same model name without re-embedding. They stay stored for audit and
   are never searched; step 4 re-embeds every revision they covered. (Until #17 they were adopted into
   the first projection with a matching model name; that could compare two different spaces.) Old
   extractions keep `extractor_key = NULL`: they are auditable but inactive, and step 4 rebuilds them.
7. **Normalized text (D21).** `revision_text(revision, normalizer, clean_content, original_chars,
   clean_chars)` with its own trigram index. Lexical recall, embedding, extraction and excerpting read
   it, and the query and previous AI turn are normalized too. `NORMALIZER_VERSION` is part of both
   generation keys. Rows are written at ingest and backfilled at startup (`nmos-rebuild --text` rebuilds
   them); the raw trigram index is dropped.

## Consequences

- Changing model or endpoint re-derives all previously covered history, at the provider's cost. The
  recent window comes first. Facts from the new generation replace the old ones as they are compiled;
  until then the Inspector shows partial coverage.
- Keys hash a fingerprint of the prompt and the registry, so editing either creates a new generation
  even without a manual compiler bump. Validation-logic changes still need a `COMPILER_VERSION` bump.
- Old generations accumulate. Pruning them is part of the open retention decision (O5).
