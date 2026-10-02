# 0061 — The query embedded while recall reads

Status: accepted, 2026-10-02. A correction under AGE-24 (real-chat recall), for K34; amends D18 (ADR 0005, PHASE-3)
in where the request path waits for the query's embedding, not in what it does with it. No migration, no plugin build,
no new packet policy, no new recall option.

## Context

Recall embeds the user's message once and searches the chat's vectors with it (D18). The call had `embed_timeout_ms`
(300) of its own, after lexical recall and before every other read: a slower embedder gave the request no vectors,
and the request still paid the wait. On the owner's production 70 % of recalls went without vectors, every one a
timeout; the ones that had them took 280 ms at the median and 452 ms at the 95th percentile, because the sidecar reaches
the embedder through a proxy (K34, `docs/perf/packet-fill.md`). Vectors are worth cases: on the M0 chats they add one
or two cases that need memory per run (`docs/perf/lexical-recall.md`), and the AGE-27 question, before `extract-v15`,
passed in replays only because a vector excerpt brought the answer and failed live because that request's embedding
timed out. Raising the timeout (the K34 workaround) buys the vectors with a slower reply.

The reads that follow the embedding do not need it: the state, the facts and threads (the memory view's fold, the
largest read: ≈105–280 ms at 10,000 messages), the scene's cast and the summaries depend on the message, the previous
reply and the window, not on the candidates. Only the vector search, the fusion with lexical recall and the excerpts do.

## Decision

1. **Asked for first, collected after the reads** (`retrieval.QueryEmbedding`). When the message is not empty and an
   embedder serves the projection, recall starts the embedding call on its own thread before lexical recall, runs
   lexical recall, the keyword route, the state, the memory view (facts, threads, cast, claims), the narrator's note,
   the cast groups and the summaries, then collects the embedding: it waits **at most `embed_timeout_ms` from that
   point**. Then the vector search, the fusion, the excerpts, and what the memory mode withheld taken out of them, as
   before. The thread holds no database connection; the request thread keeps the one connection.
2. **The wait is bounded as before.** The wait after the reads is bounded as the whole call was: a request whose
   embedder does not answer costs what it cost (the reads, then the timeout), and one whose embedder answers while the
   reads run waits nothing. The embedder gets the reads' time in addition — ≈100–300 ms at the measured sizes, which is
   where the owner's production fallbacks sit (280–450 ms behind a proxy). The bound is on the wait for the embedding,
   not on the whole request: a request that now has vectors where it fell back before pays the vector search and
   compiles a fuller packet, as every request with vectors always did (`docs/perf/query-embedding.md`: ≈60 ms at the
   95th percentile on the requests that gained vectors from a 700 ms embedder, at an unchanged median).
3. **The call is bounded at `EMBED_CALL_FACTOR` (2) × the timeout**, per network phase as before (httpx: the time to
   connect, to write, and until the answer starts). It must outlast the reads plus the wait to be of use, and it must
   end soon after the request has given up on it, since an embedder serves one request at a time (`vectors.process_embed`:
   a queued batch delayed a query by 582 ms) and a call nobody waits for would hold it for the next request's query. The
   result of a call the request gave up on is dropped; the thread ends with the call.
4. **Fail open as before.** A call that fails (an address, a key, the server) or is not collected in time leaves the
   request lexical; the trace's `vector_mode` says `fallback: …` with the reason (now "embedding not answered within N ms
   after recall's reads" for the timeout), the retrieve answer says `fallback`, and the panel and the progress display
   say so as since Phases 15 and 17. An answer of the wrong shape is the `ValueError` it was.
5. **Timings.** The trace records `embed` as the embedder's own time (from the call's start to its answer, mostly spent
   during the reads; absent on a fallback), `embed_wait` as what the request waited for it after the reads, and `vector`
   as the search alone. `lexical`, `keywords`, `fit` and `sidecar_total` are as before.
6. **Replays.** A replay compiles with the same options and the same inputs, and vector search runs on the same vector:
   nothing recorded changes, so recorded requests replay as they were (ADR 0027). An evaluation replay that gives the
   embedding 5,000 ms (`tools/eval_rp.py`) waits up to that after the reads and lets the call run twice as long.
7. **Asked for at the sync** (`retrieval.Prefetched`, `api.bodies`). The plugin syncs the chat before it asks for the
   packet, and the bodies it uploads carry the user's new message — the same text it then sends as the query
   (`queryTexts`). When the sync's manifest ends in a user message whose body is in the upload, the sidecar starts
   that text's embedding at once (before the sync's own database work), keyed by the projection and the exact text
   with its query prefix; the retrieve that follows takes it in place of starting a call, and records `embed_lead`,
   how long before recall the call began. An entry keeps the embedder object it was asked of and is given only to a
   request whose embedder is that object: a settings save rebuilds the embedder (`api.rebuild`), and an entry asked of
   the old one is dropped, not served to the new (an id is no identity: a new object can get a collected one's `id()`,
   which is how the first draft could have searched a new projection with the old model's vector; Codex on #242). An
   entry whose call has already failed is not given either: the request asks again, as one without a prefetch does,
   and falls back only if that call fails too (Codex on #244). The embedder so has the sync's time as well (the host's
   reconcile and bodies take 0.3–2.5 s on a long chat, `docs/perf/scale.md`). The prefetched call may run at least 2 s
   (`PREFETCH_CALL_MIN_MS`, or twice the timeout when that is more), since its request follows by the sync's time; an
   entry no request takes within a minute is dropped, and one is taken once. A replay never takes one (it compiles
   from its own reads, ADR 0027), and a text that differs from the synced message (a probe, an evaluation) is embedded
   as in item 1. Nothing is stored.

## Consequences

- A request whose embedder answers within the reads' time plus the timeout has vectors, where before it needed to
  answer within the timeout alone. The wait's worst case is unchanged; a request whose embedder answers during the
  reads is faster than before by the time it no longer waits; one that gains vectors spends what vectors cost.
- The sidecar runs one extra thread per request with an embedder, for the length of the call. A call abandoned by its
  request runs on to at most twice the timeout (a prefetched one to at least 2 s).
- A request that follows its sync finds its embedding under way or done: on a long chat the sync alone outlasts a
  production embedder's call, so such a request waits for nothing and has vectors. One embedding call per generation
  as before (the retrieve reuses the sync's); a sync whose retrieve never comes (a reroll served from the plugin's
  cache) costs one call.
- `tools/bench_story.py` takes `BENCH_EMBED_MS=N` with `BENCH_RECALL=wide`: a stub embedder that answers after N ms,
  so the request path can be measured with an embedder as slow as production's; the result says how many of its
  requests had vectors. Measured: `docs/perf/query-embedding.md`.
- Not changed: the timeout's default and meaning for the user (`NMOS_EMBED_TIMEOUT_MS` is still what a request may wait
  for the embedding, now after the reads), the vector search, the fusion, the ranking, the budget. K34 stays listed:
  a cold model (an unloaded Ollama, ≈18 s) still gives no vectors to the request that wakes it.
