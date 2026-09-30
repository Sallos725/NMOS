# 0051 — What NMOS's own model calls used

Status: accepted, 2026-09-29. Phase 17 step 2 (`docs/phases/PHASE-17.md` Q1–Q3, approved by the owner; Q3 amended
by the owner the same day). Migration 0027; no plugin build.

## Context

The owner pays for extraction. NMOS counted its model calls (the Inspector's coverage) but not what they used, so the
cost of a chat's memory, or of a new extractor generation, could only be guessed. Providers answering the
OpenAI-compatible API report it in the response: `usage.prompt_tokens`, `completion_tokens`, and on some providers
`prompt_tokens_details.cached_tokens` and `completion_tokens_details.reasoning_tokens`. Embedding responses report
`prompt_tokens` only. Some providers, and some local servers, report nothing.

## Decision

1. **Only what the provider reported, never an estimate** (Q2). A call's usage is a JSON object: `calls` (1), `ms`
   (the call's wall time, request to parsed reply), `model` (the name the provider answered with), and `input`,
   `output`, `cached`, `reasoning` token counts, each only when the response carried it as a non-negative integer.
   A response with neither `input` nor `output` is "not reported".
2. **Kept with the row the call produced** (Q3): a nullable `usage jsonb` on `extraction` (a turn's window or a canon
   part), `summary` (a scene or the story) and `revision_embedding` (one chunk, one call; the owner chose the row over
   the embedding job, which is pruned 7 days after it finishes). A rebuild or a new generation discards or leaves old
   rows, never rewrites them, so each keeps the usage of the call that produced it, and the archive (ADR 0050) carries
   it like any other column.
3. **Three states that are not a count.** NULL is a row written before migration 0027 ("not recorded").
   `{"calls": 0}` is a row written without asking the model (too little text). A row whose call reported nothing
   has `calls`, `ms` and `model` only.
4. **`complete_metered` and `embed_metered`.** `ChatModel.complete_metered` returns the reply and its usage;
   `complete_json` is it without the usage, for its other callers. The worker's handlers pass `complete_metered`.
   A handler's `complete` may still return two values (the tests' stand-ins, the evaluation tools): its rows record
   NULL, as no call's usage is known.

## Consequences

- A call that failed (an HTTP error, a reply without JSON) wrote no row and is not counted, though a provider may
  bill it; retries of a failing job are invisible here. An embedding job embeds every chunk of a message before it
  stores any, so when a later chunk fails the earlier chunks' calls are not kept either, and the retry calls them
  again (as before this ADR: which chunks count as embedded is not Phase 17's to change).
- Totals are of the rows NMOS still holds. Embeddings of a projection another replaced are pruned (retention, O5,
  ADR 0015) and their usage with them, so a chat's embedding total drops after the embedding model changes; the owner
  chose to say so rather than keep usage apart from the rows (2026-09-30, Copilot review of #185).
- The reply model's usage is not NMOS's (the host logs it); money is not computed (prices vary, the owner's are local
  or flat).
- The request path is unchanged: it writes no usage (a query embedding is not stored).
