# Phase 3 — Hybrid Retrieval (lexical + vector), Fusion, Abstention

> Owner authorization: 2026-09-22. Embeddings only (no generative calls on the request path).
> Optional: without `NMOS_EMBED_URL` retrieval stays lexical.

## Goal

Recall that works for paraphrases and Korean text, not only shared trigrams.

## In scope

1. **Embedding client**: OpenAI-compatible `/embeddings` (e.g. Ollama `qwen3-embedding`).
2. **pgvector** storage for revision chunks; exact cosine search restricted to the head membership
   (chat-sized sets; no ANN index needed yet). Storage stays behind the retrieval module (inv. 9).
3. **Worker job** embeds accepted revisions (chunked); model name + dimension recorded; changing
   the model re-embeds.
4. **Request path**: the query embedding is computed with its own short timeout; on failure the
   request falls back to lexical-only (fail open, recorded in the trace).
5. **Fusion**: reciprocal-rank fusion of lexical and vector candidates; **abstention**: a candidate
   needs lexical score ≥ threshold or cosine ≥ `NMOS_VECTOR_MIN_SIM`.
6. Facts (Phase 2) are ranked by entity mention in the latest turns plus lexical match. *(Beta
   deviation: ranking facts by their source revisions' fused scores is deferred.)*

## Acceptance criteria

Status 2026-09-22 — met. Evidence: `apps/sidecar/tests/test_vectors.py`; live Korean run with `qwen3-embedding:0.6b` (ADR 0005): five paraphrased questions recalled the right out-of-context passage; Ollama cold start exceeded the 300 ms embed timeout once and fell back to lexical; added latency 107–155 ms.

- [x] Paraphrased question recalls the right out-of-context excerpt that lexical recall misses
      (Korean test chat, real embedding model).
- [x] Embedding service down → packet still built lexically within the deadline.
- [x] Inactive revisions never recalled through the vector path (tests).
- [x] p95 added latency stays < 300 ms on a 500-message chat with vectors enabled.
