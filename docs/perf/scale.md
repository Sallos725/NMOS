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

Not measured here: PocketRisu itself (5k and 10k on the host: "Real-host check" below; 25k was not loaded), a
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

### Re-check after per-turn extraction (2026-09-23, ADR 0008)

Each sync now also computes the turn layout (`active_membership.turn` / `turn_hash`), and the append
path rewrites the last turn's rows. Same machine and tool, p50 (p95) in ms:

| 5,000 messages | `main` `0a31ce2` | per turn |
|---|---:|---:|
| Warm append, extraction off | 347 (382) (table above) | 336 (360) |
| Warm append, extraction on (jobs queued, no worker) | 352 (370) | 363 (402) |
| Edit near head, extraction on | 410 | 438 |
| Edit deep, extraction on | 406 | 427 |

At 1,000 messages with extraction off: append 70 (84), edits 95 / 84. Up to about 7 % more on the
sync path, within run-to-run noise at 1k. The envelope below is unchanged. Membership grows by the
two columns: 10.4 MB instead of about 9 MB at 5k.

### Deleting a conversation (2026-09-23, ADR 0009)

`ledger.delete_conversation` on one chat while a second chat of the same size stays in the database.
Each reply has one extraction with two assertions (synthetic rows, no model). Same machine, ms:

| Messages | before 0012 indexes | with 0012 indexes |
|---|---:|---:|
| 1,000 | 269 | 78 |
| 5,000 | 5,271 | 384 |
| 10,000 | — | 696 |
| 25,000 | — | 1,808 |

Without the indexes, the key checks scanned whole tables once per deleted row, so the time grew
quadratically. The largest single cost was the partial unique index on `extraction` (0011): the
check can't use it. With the indexes, about 75 % of the time is the `source_revision` delete itself
(guard trigger and key checks per row). The sync path is unchanged within run-to-run noise. Two runs each at
10,000 messages, `bench_scale.py`: warm append p50 738 / 745 → 739 / 741 ms, cold sync
9.60 / 9.64 → 9.63 / 9.57 s, edit near head p50 859 / 861 → 857 / 885 ms. Head membership grows by
about 6 % (20.7 → 21.9 MB at 10k).

### Append fast path (2026-09-23, ADR 0010, migration 0013)

A sync that provably extends the head is reconciled from the head's tail, and appends are stored as
`worldline_append` rows instead of rewriting the head commit's `delta` (2.2 MB at 10k). Same machine
(load ≈1.5) and tool, p50 (p95) in ms:

| Messages | 1,000 | 5,000 | 10,000 | 25,000 |
|---|---:|---:|---:|---:|
| Warm append, before (table above) | 71 (93) | 347 (382) | 715 (768) | 1,937 (1,978) |
| Warm append, fast path | 28 (39) | 97 (111) | 156 (191) | 430 (496) |
| Warm append, `NMOS_APPEND_FAST_PATH=0` (full path, append rows) | | | 592 (640) | |
| Edit near head (full path, unchanged) | 87 | 431 | 917 | 2,372 |
| Database size | 21 MB | 67 MB | 120 MB | 280 MB |

The append numbers include the harness encoding the request JSON (≈19 ms per request at 10k,
two requests per append), so the sidecar's own share at 10k is ≈117 ms p50. Of that, parsing and
validating the full manifest takes ≈31 ms per request (JSON ≈13 ms, pydantic ≈19 ms); the plugin sends
it twice (reconcile, then bodies with `then_reconcile`). Hashing the manifest takes ≈6 ms, the tail
queries ≈5 ms. Database size drops because appends no longer leave rewritten 2 MB `delta` versions
behind.

`tests/test_append_fast_path.py` checks that the fast and full paths leave identical ledgers, window
and turn data, jobs and observations over random host action sequences, and that divergence, a new
`allBefore` cut, or a repeated ID falls back to the full path.

### Incremental plugin manifest (2026-09-23, Track A, A2)

`scripts/bench-manifest.mjs` (Node 22), manifest after a two-message append, p50 (p95), including the
packet-cache key: 1k 1.1 (3.2) ms, 5k 8.1 (11.1) ms, 10k 17.2 (46.2) ms, 25k 47.0 (54.9) ms, with 2
messages hashed each time. Before: 19 / 84 / 175 / 474 ms p50.

### Broad lexical queries (2026-09-23, Track A, A3)

Lexical recall now first collects at most `BROAD_LIMIT + 1` (201) matching head revisions; the
statement stops there. More than 200 matches → lexical abstains for the request (trace
`lexical_mode: too_broad`) and vectors, state and facts still run; otherwise only the matched
revisions are scored. 10,000 messages, `bench_scale.py` chat, ms:

| Query | Matches | All matches collected | Capped at 201 | Retrieve (new) | Mode |
|---|---:|---:|---:|---:|---|
| `오늘은 바람이 차네` (in every reply) | 4,999 | 852 | 36 | 49 | too_broad |
| `하나` (the character's name) | 4,999 | 808 | 34 | 45 | too_broad |
| `기차역` (one of 8 places, every 8th reply) | 1,221 | 110 | 100 | 109 | too_broad |
| six selective questions | 0 | 3–8 | 3–7 | 9–17 | on |

Before, the two broad queries ran until `NMOS_LEXICAL_TIMEOUT_MS` (305 ms at 10k) and then abstained
as `timeout`. Trade-off: a word that occurs in more than 200 messages (the synthetic chat's `기차역`)
no longer brings its most recent mentions lexically; vectors still can. The evaluation baseline's
exact-quote and Korean paraphrase cases are unchanged (`docs/perf/eval-baseline.md`).

### Fact reads and generation fallback (2026-09-24, Phase 5 step 1, ADR 0014)

`bench_scale.py` now times `fact_versions` (run on every request with extraction on) after the edits:
stub extractions with one `located_in` assertion per turn under one generation, then a second
generation covering the latest 100 turns while the first serves the rest. 15 calls each, ms:

| Messages | Before: one generation p50 (max) | After: one generation p50 (max) | After: two generations p50 (max) |
|---|---:|---:|---:|
| 1,000 | 47 (63) | 6 (22) | 7 (7) |
| 5,000 | — | 33 (36) | 33 (35) |
| 10,000 | 50 (6,939) | 71 (88) | 71 (83) |

"Before" is the `v0.1.0-beta.10` query (one generation only); load ≈1.7 then, ≈2.7 for "after".
**The 7 s outliers were a released bug**, not noise: after the bench's edits the head commit is new,
its `active_membership` rows have no statistics, and the planner estimated one row. It then placed the
`allBefore` cut (a CTE joined to every row) inside a nested loop and re-ran it for each of 5,014 rows
(`EXPLAIN ANALYZE`: 6.9 s, 2.4 M temp blocks read). Every edit, reroll or swipe makes such a commit,
so a long chat with extraction on could lose memory for the next request. The cut is now a scalar
subquery that runs once (InitPlan): 62 ms for the same first call. `state.current_state` had the same
shape and is fixed the same way.

The first version of the fallback query picked each turn's generation with a self-join on a CTE; the
same underestimate made it a nested loop (≈930 ms at 10k). It now uses a window function. The
remaining ≈20 ms over the old p50 at 10k is the per-turn choice across all live extractions plus the
different load; it is within noise of the D24 margin (≈0.25 s at 10k).

### Real-host check (2026-09-23, PocketRisu v1.12.0)

Isolated `ghcr.io/pocketrisu/pocketrisu:latest` (v1.12.0), headless Chromium on the same machine,
stub chat model, this branch's sidecar. Chats: synthetic exports in the `bench_scale.py` shape
(5,000 and 10,000 messages, ~1,200-char Korean replies) imported through the chat import button. First
sync done once with `deadline_ms` = 60,000; then warm generations. `[NMOS] request done` timings, ms:

| Warm generation | 5,000 | 10,000 |
|---|---:|---:|
| Total added `beforeRequest` time | 1,450–1,490 | 2,590–2,810 |
| Chat snapshot (`getChatFromIndex`) | ≈90 | ≈190 |
| Manifest, this branch (A2) | 6–7 | 12–16 |
| Manifest, released beta.9 plugin | — | 139–149 |
| Sync (reconcile + bodies), plugin view | 1,190–1,360 | 2,090–2,510 |
| Sync, sidecar processing (both calls) | ≈105 | ≈135–165 |
| With `deadline_ms` = 800 | — | 8 of 8 fail open |

**The host stalls after the chat snapshot.** A tiny `GET /v1/health` placed before
`getChatFromIndex` returned in 7–18 ms; the same call right after it took ≈1,700 ms at 10k. At 5k the
stall (≈0.9 s) delayed the reconcile *response* instead: the sidecar answered in 57 ms, and the plugin
received it ≈0.9 s later. The 2.8 MB reconcile request itself crossed in 160–330 ms once the stall was
over. `getChatFromIndex` returns a deep copy of the whole chat (`v(chat)` in the V3 API), and the V3
API has no call that returns part of a chat. The released beta.9 plugin shows the same totals (≈2.7 s
at 10k), so the stall is not caused by A2's cache. The mechanism inside the host (garbage collection
after the copy is the likely candidate) was not isolated.

Consequence: the sidecar and plugin work (A1, A2) removed ≈700 ms of NMOS computation at 10k, but on
the real host a warm generation still needs ≈1.5 s at 5k and ≈2.7 s at 10k. The 800 ms envelope,
estimated without the host, did not hold at 5k.

**With the 3 s default (D24).** Same setup, plugin arg `deadline_ms` = 0 (default), eight warm
generations per chat after one first sync:

| Messages | Warm generation, ms | Memory added (3 s default) |
|---|---:|---|
| 5,000 | 1,413–1,761 | 8 of 8 |
| 10,000 | 2,694–2,766 | 8 of 8 (≈0.25 s margin) |
| 15,000 | 4,032–4,236 (measured with a 60 s deadline) | 0 of 8 — needs `deadline_ms` ≈5,000 |

First sync of a chat NMOS has not seen yet: 7.4 s (5k), 15.2 s (10k), 22.4 s (15k) of sidecar and
transfer time. With the default it completes over several generations (chunked bodies upload).

### Estimated added `beforeRequest` latency (warm path)

Plugin copy + manifest + sidecar append + selective retrieve; network and host snapshot overhead
excluded, so real numbers are higher:

| Messages | Estimate (p50) | Default deadline 800 ms |
|---|---:|---|
| 1,000 | ≈100 ms | met (real host: ≈200 ms, `phase0.md`) |
| 5,000 | ≈465 ms | met on desktop; little margin on a phone |
| 10,000 | ≈965 ms | **missed on every request → fail open (no memory)** |
| 25,000 | ≈2,550 ms | **missed on every request → fail open** |

With the append fast path (ADR 0010; plugin manifest unchanged): ≈405 ms at 10k (53 + 186 + 156 + 8)
and ≈1,040 ms at 25k (116 + 478 + 430 + 14), still above the deadline. Vector search (≈100 ms at 10k) and the query embedding call come on top when
embeddings are on. The envelope below is re-decided after the plugin-side work (Track A, A2) and a
real-host check.

Before the fast path: the sidecar still applies a sync that the plugin gave up waiting for, so the ledger stays current.
However, the next request repeats the same O(N) work, so above ≈8k messages memory is effectively off
unless `deadline_ms` is raised (≈1,200 ms at 10k on this machine).

Cold first sync of long chats already spans several requests by design (chunked, durable bodies
upload): ≈9 s of sidecar time at 10k, ≈27 s at 25k.

## Supported envelope (decision)

- The API accepts manifests up to **30,000 messages** (`MAX_MANIFEST_MESSAGES`; it was 20,000, which
  made a 25k chat fail with HTTP 422 before anything could be measured). 25,000 is the largest
  measured tier; the extra room keeps a growing chat syncing.
- **Within the default 3 s deadline (D24, 2026-09-23):** up to ≈10,000 messages on the real host
  (PocketRisu v1.12.0, desktop Chromium, measured machine), with little margin at 10k. The earlier
  "800 ms up to ≈5,000" was estimated without the host and did not hold there.
- **Beyond ≈10,000 messages:** synced correctly and never corrupted; memory needs a higher
  `deadline_ms` (≈5,000 at 15k), and replies start that much later. Phones were not measured.

## Bottlenecks found, and what was changed

1. **Lexical recall ignored the trigram index** (fixed). The planner cannot estimate `<%` and filtered
   every head row with `word_similarity`: 82 ms at 1k, 818 ms at 10k. The lexical statement now
   disables plain seq/index scans for itself only, which leaves the bitmap scan on
   `revision_text_trgm`: 1 ms at 1k, 0.05 ms at 10k (query plan), 9–13 ms per request.
2. **Broad lexical queries** (bounded; since A3 stopped at 200 matches, section above). A query whose words occur in nearly every message — the
   character's name alone (`하나`) or a phrase repeated in every reply — matched every row and scored
   each: 0.6 s at 1k, 6.2 s at 10k, 15.8 s at 25k, holding a pooled connection long after the plugin
   failed open. The lexical statement now has a budget (`NMOS_LEXICAL_TIMEOUT_MS`, default 300). When
   it runs out, lexical recall abstains for that request (trace `lexical_mode: timeout`); vectors,
   state and facts still run. Measured after the change: 305 ms at 10k.
3. **Warm sync is O(N) twice per generation** (fixed for appends: ADR 0010, section above). Profile of one append at
   10k (559 ms bodies + apply): `load_state` 212 ms (loads every known revision), `apply_plan` 151 ms,
   `plan` 104 ms, `manifest_hash` 34 ms. The first reconcile call (`needs_bodies`) repeats most of it
   (256 ms). On the plugin side, hashing every message is ≈19 µs per message.
4. **Exact vector search** grows linearly (≈11 µs per revision-chunk): acceptable to 10k (≈100 ms),
   277 ms at 25k with 1 chunk per revision. It stays exact (ARCHITECTURE D18) until the envelope needs
   more.

## Proposed next steps (measured)

In order of payoff:

1. **Done (ADR 0010).** **Append fast path on the sidecar.** When the manifest equals the head plus an appended suffix
   (verifiable against the stored head manifest hash and length, which observation compaction already
   uses), skip `load_state` of the whole chat and plan only the suffix. Also answer the first reconcile of an append with only the new
   keys. Expected: the sidecar append drops from ≈700 ms to tens of ms at 10k.
2. **Done (A2).** **Incremental manifest in the plugin.** Cache per-message hashes keyed by the message object's
   content fields, so a generation hashes only changed messages. Expected: ≈186 ms → a few ms at 10k.
   Suffix/delta verification or Merkle identity is only needed if (1) and (2) are not enough.
3. **Done (A3).** **Broad lexical queries:** score only a bounded, recency-ordered subset of index hits, or require
   the query to have a minimum number of distinctive trigrams, instead of relying on the timeout.
4. **Vectors beyond 10k:** an HNSW index scoped per projection, or keep exact search but limit it to
   revisions outside the prompt window.

Reproduce:

```bash
docker compose up -d postgres
cd apps/sidecar && uv run python ../../tools/bench_scale.py 1000,5000,10000,25000
cd adapters/pocketrisu-plugin && node scripts/bench-manifest.mjs 1000,5000,10000,25000
```
