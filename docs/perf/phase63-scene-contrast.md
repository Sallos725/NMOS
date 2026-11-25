# Phase 63 Step 1 — mean-centered scene contrast (zero-call measurement, 2026-11-24)

Read-only offline measurement on branch `docs/phase63-scene-contrast`. **Zero paid model calls.** No production code
changed. Numbers only — no chat text, prompt text or credentials appear here.

- **Production copy:** fresh `pg_dump` of production restored to a throwaway database on test PostgreSQL (:5436,
  `nmos_p63_step1`, stored API keys deleted, dropped after measurement). Active embedding projection:
  `voyage-4-large` (1024-dim, `max_chunks = 52`, 12,318 chunks, 0 queued jobs), `vector_min_sim = 0.30`.
- **Recall gate (338 probes):** the 314 bench probes and 24 exact-quote cases on throwaway clones of the eight
  `nmos_b030_*` databases (migrated through `0039` on the clones only; originals untouched; clones dropped after
  measurement). Query vectors were computed locally once per unique text with Ollama `qwen3-embedding:8b` (4096-dim,
  `http://127.0.0.1:11434/v1`) and cached across all variants and rounds; 3 rounds per variant, majority deciding
  (`AGENTS.md §7.6`).

**Outcome: Go/No-Go gate not met — Phase 63 closed (owner, 2026-11-24; nothing built).** Chat-level embedding anisotropy is real (`||μ||` median 0.67–0.77), but every
centered-ranking variant regressed on both the 338-probe gate and production reply-echo retention, vector-only
pruning gave 0 recall gain while cutting echoed and un-echoed excerpts at roughly 1:1 (saving ~11 tokens), and the
extra `pgvector` work slowed the vector stage by **3.5–4.6×** (+56–71 ms on production's largest 52-chunk chat,
+110–122 ms at 10,000 chunks). Phase 63 stopped at Step 1 and was closed without building `packet-v21`.

---

## 1. Stored vector norms and chat anisotropy (`||μ||`)

All stored vectors in both models are already unit-norm (`L2 = 1.00000`). Centroid norm `||μ||` (average cosine
similarity of a chat's chunks to the chat mean; `||μ||²` approximates average pairwise cosine) confirms strong
within-chat anisotropy:

| Dataset (model, cap) | Chunks | L2 norm (min / med / max) | Chats (≥16 revs) | Chunks/rev (med / max) | `‖μ‖` chunk-mean (min / med / max) | `‖μ‖` rev-mean (min / med / max) |
|---|---:|---|---:|---:|---|---|
| Production copy (`voyage-4-large`, 52) | 12,318 | 1.00000 / 1.00000 / 1.00000 | 18 | 9.22 / 18.77 | 0.676 / **0.699** / 0.778 | 0.611 / **0.668** / 0.718 |
| Bench `S0main` (`qwen3-embedding:8b`, 8) | 515 | 1.00000 / 1.00000 / 1.00000 | 1 | 2.96 / 2.96 | 0.771 | 0.750 |
| Bench `S1` (`qwen3-embedding:8b`, 8) | 1,068 | 1.00000 / 1.00000 / 1.00000 | 1 | 2.01 / 2.01 | 0.746 | 0.753 |

---

## 2. 338-probe recall gate (`packet-v20`, local Ollama `qwen3-embedding:8b`, 3-round majority)

Every variant ran with `vectors = on` on all 1,014/1,014 probe runs (338 × 3; 203 unique query embeddings cached
locally). All 338 probes are shorter than 40 normalized characters, so Phase 60's `sem_query` fired under `packet-v20`.

| Variant | bench (314) | quotes (24) | total (338) | gained | lost | pruned/rd | mean tok |
|---|---:|---:|---:|---:|---:|---:|---:|
| `baseline` (`packet-v20`) | **300** | **19** | **319** | +0 | -0 | 0.0 | 2,231 |
| `A_rev_p16` (prune vec-only `c ≤ 0`, rev-mean, pool≥16) | 300 | 19 | 319 | +0 | -0 | 40.0 | 2,231 |
| `A_chunk_p16` (prune vec-only `c ≤ 0`, chunk-mean, pool≥16) | 300 | 19 | 319 | +0 | -0 | 44.0 | 2,229 |
| `A_rev_p8` (pool≥8) | 300 | 19 | 319 | +0 | -0 | 40.0 | 2,231 |
| `A_rev_p2` (pool≥2) | 300 | 19 | 319 | +0 | -0 | 40.0 | 2,231 |
| `A_rev_nosim` (replace `vector_min_sim` with `c > 0`) | 300 | 19 | 319 | +0 | -0 | 40.0 | 2,231 |
| `B_cos_rev` (centered cosine top-50 + prune, rev-mean) | 298 | 19 | 317 | +2 | **-4** | 0.0 | 2,211 |
| `B_cos_chunk` (centered cosine top-50 + prune, chunk-mean) | 296 | 19 | 315 | +0 | **-4** | 0.0 | 2,209 |
| `B_dot_rev` (centered dot top-50 + prune, rev-mean) | 292 | 19 | 311 | +2 | **-10** | 0.0 | 2,207 |
| `C_cos_rev_only` (centered cosine top-50, no prune) | 298 | 19 | 317 | +2 | **-4** | 0.0 | 2,209 |

- `irrelevant` (small talk) was already **20/20** at baseline and unchanged across every variant.
- **Variant A** gained 0 cases and saved 0–2 tokens per packet on average.
- **Variants B and C** regressed across `past` (-2), `address` (-1), and `planted` (-1); `B_dot_rev` additionally
  dropped `promise` (-3) and `early` (-1 net), matching the theoretical outlier-norm bias of unnormalized centered dot.

---

## 3. Production copy replay (`packet-v20`, `voyage-4-large` 52-chunk, zero API calls)

Production embeds with OpenAI-compatible `{model, input}` and no `embed_query_instruction`, so for any non-`sem_query`
single-chunk user message, its stored `revision_embedding` vector is the exact query vector. Of 753 fresh traces on the
copy, 657 non-`sem_query` traces had a stored single-chunk user vector, and **394** had intact prefixes and replayed
cleanly (`status = ok`, `vectors = on`, 350 of them with a real character reply for echo scoring via `audit.echo`).
The 14 `sem_query` traces on production were excluded here because their live concatenated query text is not stored as
a single revision vector (replaying them without calling Voyage would require an approximated vector).

| Variant | replayed | pool ≥ min | pruned cands (traces) | ex placed | ex echoed | ex un-echoed | vs base: echoed lost / gained | un-echoed cut | mean tok |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `baseline_0.30` (prod setting) | 394 | 0 | 0 (0) | 1,409 | **790** | 484 | -0 / +0 | 0 | 1,984 |
| `A_rev_p16` | 394 | 149 | 587 (101) | 1,373 | 781 | 472 | **-11** / +2 | 15 | 1,973 |
| `A_chunk_p16` | 394 | 149 | 326 (83) | 1,385 | 779 | 477 | **-14** / +3 | 14 | 1,975 |
| `A_rev_p8` | 394 | 173 | 666 (125) | 1,329 | 760 | 451 | **-32** / +2 | 36 | 1,957 |
| `A_rev_p2` | 394 | 190 | 677 (135) | 1,321 | 756 | 447 | **-36** / +2 | 39 | 1,954 |
| `A_rev_nosim` | 394 | 149 | 684 (106) | 1,399 | 789 | 490 | -11 / +10 | 15 | 1,983 |
| `B_cos_rev` | 394 | 149 | 319 (50) | 1,392 | **753** | **516** | -282 / +243 | 186 | 1,957 |
| `B_cos_chunk` | 394 | 149 | 147 (41) | 1,423 | **732** | **558** | -292 / +234 | 190 | 1,949 |
| `B_dot_rev` | 394 | 149 | 320 (50) | 1,387 | **744** | **519** | -340 / +293 | 215 | 1,957 |
| `C_cos_rev` | 394 | 149 | 0 (0) | 1,415 | **756** | **521** | -280 / +244 | 184 | 1,962 |
| `base_0.42` (code default) | 394 | 0 | 0 (0) | 1,236 | 722 | 394 | -69 / +1 | 89 | 1,925 |
| `A_rev_0.42` | 394 | 149 | 269 (79) | 1,224 | 717 | 389 | -75 / +2 | 97 | 1,921 |
| `B_cos_0.42` | 394 | 149 | 113 (35) | 1,225 | 698 | 406 | -320 / +226 | 239 | 1,911 |

Key observations:
- **Centered ranking (`B_*`, `C_*`) strictly degraded excerpt quality on real production chats:** net reply-echoed
  excerpts dropped by **-34 to -58** while un-echoed excerpts **increased by +32 to +74**. Because NMOS embeds raw
  multi-sentence prose chunks (rather than short distilled memory records), subtracting the corpus mean boosts
  stylistic/formatting outliers instead of topically relevant scenes.
- **Vector-only pruning (`A_*`) was near-indiscriminate:** `A_rev_p16` cut 15 un-echoed excerpts at the cost of 11
  echoed excerpts (-9 net echoed vs -12 net un-echoed, saving 11 tokens); `A_chunk_p16` lost more net echoed excerpts
  (-11) than un-echoed ones (-7). Lowering `MIN_POOL` (`p8`, `p2`) amplified the echoed-excerpt loss (-30 to -34 net).
- **Replacing `vector_min_sim` (`A_rev_nosim`)** kept echoed excerpts nearly flat (-1 net) but **added** +6 un-echoed
  excerpts.

---

## 4. PostgreSQL `pgvector` SQL latency

Measured on `pgvector 0.8.6` (`nmos-postgres-1`), 2 warm-up + 20 timed runs per query (median / p95 in ms).

### Production copy (top 5 chats by chunk count, 52-chunk `voyage-4-large`, 1024-dim)

| Chat chunks (revs) | `baseline` med / p95 | `A_chunk` med / p95 | `A_rev` med / p95 | `B_cos_chunk` med / p95 | `B_cos_rev` med / p95 | `B_dot_rev` med / p95 |
|---|---:|---:|---:|---:|---:|---:|
| 1,839 (115) | **19.6** / 22.2 | 82.5 / 85.4 | 75.9 / 78.9 | 96.0 / 97.6 | 90.3 / 95.4 | 89.5 / 99.6 |
| 1,425 (199) | **14.2** / 14.9 | 66.1 / 71.2 | 59.9 / 62.5 | 74.6 / 76.8 | 72.5 / 77.1 | 69.9 / 74.4 |
| 1,125 (175) | **10.9** / 12.6 | 53.1 / 54.7 | 50.1 / 51.9 | 61.9 / 63.5 | 59.0 / 59.8 | 60.8 / 67.2 |
| 954 (99) | **12.6** / 13.3 | 46.4 / 55.0 | 45.7 / 52.7 | 52.1 / 58.8 | 53.1 / 55.8 | 49.3 / 52.8 |
| 926 (57) | **11.7** / 12.1 | 41.8 / 43.9 | 42.5 / 44.2 | 49.0 / 50.2 | 48.6 / 49.2 | 47.5 / 48.7 |

### 10,000-chunk synthetic scale (1024-dim, throwaway `TEMP TABLE`, real `voyage-4-large` vectors tiled)

| Query | median (ms) | p95 (ms) | max (ms) | vs baseline |
|---|---:|---:|---:|---:|
| `baseline_10k` | **44.7** | 45.4 | 47.3 | 1.0× |
| `A_prune_10k` | 154.5 | 164.5 | 164.9 | **3.5× (+110 ms)** |
| `B_cos_10k` | 166.2 | 170.2 | 174.5 | **3.7× (+122 ms)** |
| `B_dot_1pass_10k` | 163.6 | 176.9 | 187.9 | **3.7× (+119 ms)** |

Even with the algebraic 1-subtraction dot form, computing the CTE mean and normalizing/subtracting in SQL multiplies
`vector` stage latency by **3.5–4.6×**.

---

## 5. Why mean-centered contrast did not transfer from AC2 to NMOS

1. **Different embedding units:** AC2 embeds short, distilled memory statements; NMOS embeds raw 700-char narrative
   prose chunks (up to 52 chunks/reply after Phase 62). Subtracting the prose centroid rewards stylistic outliers
   rather than topical matches.
2. **Existing noise controls already do the job:** NMOS separates structured `<Facts>`/`<Threads>`/`<Cast>`/`<Story>`
   from raw `<Excerpts>`, fuses `pg_trgm` + keyword + vector via RRF, applies `EXCERPT_FLOOR` and Phase 34 resting,
   and already passes 20/20 `irrelevant` small-talk probes (`packet-v19`).
3. **Negative cost/benefit:** paying +56–122 ms per request for 0 benchmark recall gain, net echoed-excerpt loss on
   production, and ~11 tokens saved does not justify `packet-v21` or a materialized mean-vector cache.
