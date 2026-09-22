# Phase 2 — Bounded LLM Extraction, Predicate Registry, Fact Versions

> Owner authorization: 2026-09-22. First phase that calls an LLM (asynchronously, never on the
> request path). Optional: without `NMOS_LLM_URL` NMOS behaves exactly like Phase 1.

## Goal

Accepted turns are compiled into **typed assertions with provenance** (D6, D7, invariant 10).
Single-valued predicates form **fact versions**: the current value and its history, both answerable
(invariant 5). The packet can carry a few relevant facts instead of raw excerpts.

## In scope

1. **LLM client**: OpenAI-compatible `/chat/completions` (Ollama, OpenRouter, vLLM, …), JSON-only
   prompt, strict parsing, timeouts, bounded retries in the worker only.
2. **Predicate registry** (closed, code-defined): subject/object types, cardinality, epistemic class.
   Anything else becomes a `pending` assertion that is stored but never injected.
3. **Worker** (`nmos-worker`, separate process/compose service): Postgres job table with
   `FOR UPDATE SKIP LOCKED`, retries with backoff, dead-lettering.
4. **Bounded context (D7)**: extraction of a revision sees at most the previous `K` (default 6)
   active messages. Extractions are keyed by `(revision, window_hash, compiler_version)`;
   `window_hash` is materialized on `active_membership`, so any edit inside the window makes the
   old extraction non-matching **immediately** (D8) and re-queues work.
5. **Lazy compilation (D5)**: only `accepted` revisions are extracted.
6. **Fact versions**: current value = latest valid assertion (by position) whose extraction matches
   the head window; history = all of them in order.
7. **Packet `<Facts>` section**: facts relevant to the latest user/AI turns (lexical match on
   subject/object/value), out-of-context provenance only, budgeted before excerpts.
8. Inspector: assertions and fact history per conversation; job queue status.

## Out of scope

Embeddings, principal/character-POV filtering, verifier model, threads, MCP.

## Acceptance criteria

- [ ] With no LLM configured, nothing is queued and all Phase 0/1 behavior is unchanged.
- [ ] Worker processes jobs concurrently without double-processing (SKIP LOCKED test).
- [ ] Invalid/unknown predicates are stored as `pending`, never injected.
- [ ] An edit at position p masks extractions in `[p, p+K]` synchronously and re-queues them.
- [ ] Fact versions: superseding single-valued facts; history preserved; deleted/retracted sources
      never contribute.
- [ ] Real LLM run (Ollama-compatible endpoint) extracts facts from a Korean test chat.
