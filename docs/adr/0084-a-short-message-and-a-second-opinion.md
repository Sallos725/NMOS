# 0084 — A short message asks with the reply before it; an optional reranker

Status: accepted, 2026-11-23, PHASE-60 (S5). Amends D18 and D70 (the query's embedding input), ADR 0027 (what a trace
records) and `AGENTS.md §4` "Models" (what the request path may call). No migration.

## Context

A message of a few characters ("응", "그래서?") embeds as almost nothing, so vector recall returns noise or nothing.
And the fused order (RRF of lexical, keyword and vector) has no model that reads query and candidate together.
`AGENTS.md §4` allowed the request path one model call: the query's embedding.

## Decision

1. **`sem_query`: the embedding input only.** Under `packet-v20`, a normalized message under 40 characters with a
   previous reply is embedded as the reply's last 400 characters, a line break, the message. Lexical and keyword
   recall, fact relevance and anchors read the message alone, as before. Recorded; unrecorded replays off.
2. **The prefetch builds the same text.** The sync-time prefetch (D70) uses the same function on the head's stored
   reply, so the common case still has its embedding waiting. A mismatch falls back to the bounded wait, then to
   lexical recall, as today.
3. **`AGENTS.md §4` is amended:** the request path may make, besides the query embedding, **one non-generative
   rerank call**, only when the owner configured a reranker, bounded by its own timeout on the sidecar (the request
   carries no remaining deadline; the plugin's deadline around the whole request still fails it open on the plugin's
   side), failing open to the fused order. The embedding timeout plus the rerank timeout should stay well under the
   plugin's deadline (3 s by default). Generative calls stay in the worker.
4. **Opt-in by configuration, not by default.** No URL and model, no code path that calls. No new dependency: the
   sidecar's `httpx`.
5. **A replay never calls.** The trace records each candidate's rerank score, `rerank_used` and `rerank_ms`; an as-of
   replay applies the recorded scores. A request whose reranker failed replays in fused order, because that is what
   it used.
6. **The key is a credential.** Stored and redacted like the model keys, bound to its endpoint's host, never in a
   trace, a log or an archive.
7. **One wire format is built from knowledge, others only from documentation.** `standard` (`POST <url>/rerank`,
   `results[]` or `data[]` of `{index, relevance_score}`) covers the common hosted rerankers. Any further format is
   added only against its provider's published request and response, with a fixture; none is guessed.

## Consequences

- A configured reranker adds latency up to its timeout and sends candidate text to its endpoint; the settings say so.
- The reranker is not part of any generation key: it reorders, it derives nothing stored.
- A reranker that is slow for a while silently returns the fused order; the trace's `rerank_used` shows how often.
