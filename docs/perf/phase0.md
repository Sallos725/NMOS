# Phase 0B latency (2026-09-22)

Measured in the real host: PocketRisu `a14c911` (isolated instance, `http://localhost:6101`),
headless Chromium 1223, plugin `nmos_memory` 0.1.0, sidecar + PostgreSQL 16 via `docker compose` on
the same homelab machine (loopback, no TLS). Model: `tools/spike_stub_llm.py`. Every row is 20
consecutive real sends unless noted. "Added latency" is measured inside the plugin
(`[NMOS] request done` debug log: snapshot + manifest + reconcile/bodies + retrieve + inject).
Sidecar timings come from the sidecar's own request log (handler time, excluding network).

| Chat | Path | p50 | p95 | Target |
|---|---|---:|---:|---|
| ~490 messages (recall chat) | added `beforeRequest` latency | 89 ms | 119 ms | p95 < 300 ms |
| ~490 messages | sidecar `/v1/sync/reconcile` | 20.2 ms | 30.0 ms | p95 < 50 ms |
| ~490 messages | sidecar `/v1/sync/bodies` (+ apply, 2 new revisions) | 17.0 ms | 21.5 ms | — |
| ~490 messages | sidecar `/v1/retrieve` | 6.3 ms | 40.8 ms | p95 < 150 ms |
| ~1,000 messages (8 sends) | added `beforeRequest` latency | ≈200 ms | 221 ms | p95 < 300 ms |
| ~1,000 messages | sidecar reconcile / bodies / retrieve | ≈25–44 / ≈43 / ≈46 ms | — | see above |
| 1,000 messages, **first sight** | added latency incl. uploading 1,000 bodies (4 chunks) | 746 ms (1 sample) | — | inside 800 ms deadline |

Breakdown at ~1,000 messages (plugin side): manifest build 11–23 ms (1,000 SHA-256 via
`crypto.subtle`), sync ≈100–115 ms (two round trips), retrieve ≈65 ms.

Optimizations made after the first measurement (both kept):

1. Retrieval computed the `allBefore` cut once per candidate row (1,017 loops, 94 ms). It is now a
   single query, and candidates are prefiltered with the trigram operator `<%`. 1,000-message
   retrieve: 170 ms → 45 ms.
2. Host observations stored the full manifest JSON (≈250 KB) on every request. They now store a
   compact column form, and only the appended tail for append-only syncs.

Not measured: a phone browser, HTTPS through PocketRisu Remote Access, a sidecar on a different
machine, chats above 1,000 messages.

## Phase 3 hybrid recall (2026-09-22)

Korean 120→150-message chat, max context 1,500 tokens (≈40 messages in the prompt), vectors
(`qwen3-embedding:0.6b`, Ollama, RTX 2060 SUPER) and facts enabled. Added `beforeRequest` latency was
107–155 ms over 5 sends: query embedding ≈20 ms, sidecar total ≈30–60 ms. The first query after Ollama
unloads an idle model exceeds `NMOS_EMBED_TIMEOUT_MS` (300 ms) and falls back to lexical for that one
request.
