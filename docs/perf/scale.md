# Large-chat envelope (2026-09-22, issue #12)

## Setup

Homelab machine (16 cores, load ≈2.5 from other services), PostgreSQL 16 + pgvector in `docker
compose`, loopback.

- **Sidecar numbers:** `tools/bench_scale.py` drives the real FastAPI app in-process (request parsing,
  validation and handlers included; TCP excluded). Each size gets a fresh database, and `ANALYZE` runs
  after the bulk load (steady state for a long-lived chat).
- **Plugin numbers:** `adapters/pocketrisu-plugin/scripts/bench-manifest.mjs` runs the real
  `buildManifest` (one SHA-256 per message via WebCrypto) in Node 22. A desktop browser is similar; a
  phone will be slower. The earlier real-host measurement at 1,000 messages (manifest 11–23 ms,
  `docs/perf/phase0.md`) matches the Node figure (19 ms).

**Synthetic chat:** alternating short user turns and ~1,200-char Korean replies with a status block
(the shape of a sim-bot RP). No LLM or embedding service is involved; vector search uses one random
1,024-dim vector per revision (the dimension of `qwen3-embedding:0.6b`), which is a lower bound because
long revisions have up to 8 chunks.

Not measured: PocketRisu itself at these sizes (a 25k-message chat was not loaded into the host), a
phone browser, TLS/remote sidecars.

## Results

p50 (p95) in ms unless noted. "Append" = one generation: the previous reply plus the new user turn,
i.e. reconcile → `needs_bodies` → bodies + `then_reconcile`.

| Messages | 1,000 | 5,000 | 10,000 | 25,000 |
|---|---:|---:|---:|---:|
| **Plugin** snapshot copy (`structuredClone`) | 5 | 17 | 53 | 116 |
| **Plugin** manifest + SHA-256 | 19 (34) | 94 (106) | 186 (223) | 478 (537) |
| Reconcile payload | 0.3 MB | 1.5 MB | 3.0 MB | 7.5 MB |
| **Sidecar** warm append (2 new messages) | 71 (93) | 347 (382) | 715 (768) | 1,937 (1,978) |
| Edit near head (divergence commit) | 88 | 393 | 820 | 2,251 |
| Edit deep in history (position N/10) | 85 | 379 | 808 | 2,319 |
| Lexical retrieve, selective query | 5–8 | 6–13 | 9–12 | 11–13 |
| Vector search (exact cosine, head only) | 10 (13) | 50 (56) | 102 (113) | 277 (337) |
| Cold first sync: reconcile + bodies (chunks of 250) | 33 + 886 | 254 + 4,431 | 797 + 8,814 | 4,579 + 22,434 |
| Database size | 22 MB | 74 MB | 146 MB | 303 MB |
| `host_observation` per append | 2.7 KB | 2.7 KB | 2.7 KB | 3.2 KB |

Storage at 25k: source 25 MB, normalized text 12 MB, membership 28 MB, commits 55 MB, observations
30 MB (from the cold sync), embeddings 137 MB (1 chunk per revision).

### Estimated added `beforeRequest` latency (warm path)

Plugin copy + manifest + sidecar append + selective retrieve; network and host snapshot overhead
excluded, so real numbers are higher:

| Messages | Estimate (p50) | Default deadline 800 ms |
|---|---:|---|
| 1,000 | ≈100 ms | met (real host: ≈200 ms, `phase0.md`) |
| 5,000 | ≈465 ms | met on desktop; little margin on a phone |
| 10,000 | ≈965 ms | **missed on every request → fail open (no memory)** |
| 25,000 | ≈2,550 ms | **missed on every request → fail open** |

The sidecar still applies a sync that the plugin gave up waiting for, so the ledger stays current.
However, the next request repeats the same O(N) work, so above ≈8k messages memory is effectively off
unless `deadline_ms` is raised (≈1,200 ms at 10k on this machine).

Cold first sync of long chats already spans several requests by design (chunked, durable bodies
upload): ≈9 s of sidecar time at 10k, ≈27 s at 25k.

## Supported envelope (decision)

- The API accepts manifests up to **30,000 messages** (`MAX_MANIFEST_MESSAGES`; it was 20,000, which
  made a 25k chat fail with HTTP 422 before anything could be measured). 25,000 is the largest
  measured tier; the extra room keeps a growing chat syncing.
- **Within the default 800 ms deadline:** up to ≈5,000 messages (measured machine, desktop browser).
- **5,000–30,000 messages:** synced correctly and never corrupted, but requests exceed the default
  deadline and fail open unless `deadline_ms` is raised. This is a documented limit, not a supported
  latency target.

## Bottlenecks found, and what was changed

1. **Lexical recall ignored the trigram index** (fixed). The planner cannot estimate `<%` and filtered
   every head row with `word_similarity`: 82 ms at 1k, 818 ms at 10k. The lexical statement now
   disables plain seq/index scans for itself only, which leaves the bitmap scan on
   `revision_text_trgm`: 1 ms at 1k, 0.05 ms at 10k (query plan), 9–13 ms per request.
2. **Broad lexical queries** (bounded). A query whose words occur in nearly every message — the
   character's name alone (`하나`) or a phrase repeated in every reply — matched every row and scored
   each: 0.6 s at 1k, 6.2 s at 10k, 15.8 s at 25k, holding a pooled connection long after the plugin
   failed open. The lexical statement now has a budget (`NMOS_LEXICAL_TIMEOUT_MS`, default 300). When
   it runs out, lexical recall abstains for that request (trace `lexical_mode: timeout`); vectors,
   state and facts still run. Measured after the change: 305 ms at 10k.
3. **Warm sync is O(N) twice per generation** (not changed; proposal below). Profile of one append at
   10k (559 ms bodies + apply): `load_state` 212 ms (loads every known revision), `apply_plan` 151 ms,
   `plan` 104 ms, `manifest_hash` 34 ms. The first reconcile call (`needs_bodies`) repeats most of it
   (256 ms). On the plugin side, hashing every message is ≈19 µs per message.
4. **Exact vector search** grows linearly (≈11 µs per revision-chunk): acceptable to 10k (≈100 ms),
   277 ms at 25k with 1 chunk per revision. It stays exact (ARCHITECTURE D18) until the envelope needs
   more.

## Proposed next steps (measured, not implemented)

In order of payoff:

1. **Append fast path on the sidecar.** When the manifest equals the head plus an appended suffix
   (verifiable against the stored head manifest hash and length, which observation compaction already
   uses), skip `load_state` of the whole chat and plan only the suffix. Also answer the first reconcile of an append with only the new
   keys. Expected: the sidecar append drops from ≈700 ms to tens of ms at 10k.
2. **Incremental manifest in the plugin.** Cache per-message hashes keyed by the message object's
   content fields, so a generation hashes only changed messages. Expected: ≈186 ms → a few ms at 10k.
   Suffix/delta verification or Merkle identity is only needed if (1) and (2) are not enough.
3. **Broad lexical queries:** score only a bounded, recency-ordered subset of index hits, or require
   the query to have a minimum number of distinctive trigrams, instead of relying on the timeout.
4. **Vectors beyond 10k:** an HNSW index scoped per projection, or keep exact search but limit it to
   revisions outside the prompt window.

Reproduce:

```bash
docker compose up -d postgres
cd apps/sidecar && uv run python ../../tools/bench_scale.py 1000,5000,10000,25000
cd adapters/pocketrisu-plugin && node scripts/bench-manifest.mjs 1000,5000,10000,25000
```
