# Phase 63 — Vector recall against the chat's background (mean-centered scene contrast)

Status: **closed** (owner, 2026-11-24): nothing is built; `packet-v19` (default) and `packet-v20` stay unchanged.
Drafted 2026-11-24; Q0 (a) approved by owner ("Step 1 OK"), Step 1 zero-call measurement ran
(`docs/perf/phase63-scene-contrast.md`), go/no-go gate not met, and the owner closed the phase without implementing
`packet-v21`. An owner request from a survey of another memory tool (`Flazer31/archive-center-2`, MPL-2.0):
**clean-room** — nothing of its code or prompt text is used; only the mathematical idea of centering unit vectors on
the chat's deliverable candidate corpus was tested against NMOS's `pgvector` chunk recall (`vectors.py`,
`retrieval.py`). Not a roadmap stage; **recall-only** (`AGENTS.md §7.6`).

**High risk** (`AGENTS.md §14`) once built:
- **memory selection (`retrieval.py`, `vectors.py`)**: changing vector scoring or vector-only abstention decides which
  excerpts enter `<Excerpts>`, and a mis-scoped mean pool can push every older candidate below zero (zero vector
  recall);
- **request-path latency**: computing a corpus mean over `revision_embedding` adds work on the request path, right
  after Phase 62 raised `NMOS_EMBED_MAX_CHUNKS` from 8 to 52 on production (multiplying chunks per long reply);
- **as-of replay fidelity (D39)**: the mean vector must use the trace's exact `upto`, `known_at` and effective
  `in_context`, and `packet-v20` and older must replay byte-identically.

Invariants it touches (`AGENTS.md §3`):
- **Unknown is a valid result**: a vector hit indistinguishable from the chat's background abstains rather than filling
  excerpt slots.
- **Inactive sources cannot influence generation** (invariant 7, D4, D8): the corpus mean is computed only over
  eligible head-membership chunks (`accepted`, `position > cut`, `position <= upto`, `known_at`, not `disabled` or
  `isComment`, `replies_only` respected) and excludes messages already in the prompt (`in_context`).
- **Retrieval ≠ utilization**: lexical (`pg_trgm`), keyword and exact-quote routes stay untouched; vector contrast acts
  on the vector route and vector-only candidates.

---

## Why

1. **Embedding anisotropy in a single long RP chat.** Every chunk in a chat shares the same protagonist names,
   setting, register and writing style. Cosine similarity (`1 - (re.embedding <=> q)`) mixes two signals: shared
   chat background and actual topical relevance to the current turn.
2. **A fixed similarity floor cannot adapt across models or chats.** `fuse()` (`retrieval.py`) admits a vector-only
   candidate whenever `sim >= vector_min_sim` (default `0.42`, D18). Embedders whose cosine floor on same-chat prose
   sits around `0.45–0.65` pass unrelated turns and small talk straight into RRF; conversely, an embedder with a lower
   mean cosine can miss valid older scenes at `0.42`.
3. **Mean-centering removes the constant chat direction.** For unit vectors $\hat{v}_i$ in the deliverable candidate
   pool $P$ and unit query $\hat{q}$, let $\mu = \frac{1}{|P|}\sum_{j \in P}\hat{v}_j$. Then:
   $$c_i = (\hat{v}_i - \mu) \cdot (\hat{q} - \mu) = \hat{v}_i \cdot \hat{q} - \hat{v}_i \cdot \mu - \hat{q} \cdot \mu + \|\mu\|^2$$
   A chunk whose raw cosine is high only because it resembles the chat's average prose ($\hat{v}_i \cdot \mu$ large)
   drops to $c_i \le 0$ when its deviation from $\mu$ is orthogonal or opposite to the query's deviation $\hat{q} - \mu$.
   The zero boundary ($c_i \le 0$) is identical for centered dot product and centered cosine similarity
   $\cos(\hat{v}_i - \mu, \hat{q} - \mu)$, while ranking differs between the two because centered dot favors chunks
   with larger $\|\hat{v}_i - \mu\|$ (outliers).
4. **Why the pool boundary matters.** If recent `in_context` messages are included in $\mu$, they pull the mean toward
   the current scene and can push legitimate older memories to $c_i \le 0$, yielding zero vector recall. Currently
   `vector_candidates()` (`vectors.py`) scans all head revisions without filtering `in_context`, and `retrieval.py`
   removes `in_context` only after `fuse()`. For contrast, `in_context` must be excluded from $\mu$.
5. **Phase 62 interaction (chunk weighting and scale).** Production now embeds up to 52 chunks per message (36,400
   normalized characters; Phase 62 amendment 1). A single 33k-character reply produces ~48 chunks while a short message
   produces 1. Whether $\mu$ averages **chunks** directly or **revisions** equally (mean per revision, then across
   revisions), and how fast `pgvector` computes it over 12k+ chunks, are empirical questions that Step 1 measures
   without calling any model.

---

## Proposal (pending Step 1 zero-call measurement and Q0–Q6)

### S1 — Deliverable candidate mean ($\mu$) in PostgreSQL (`vectors.py`)

- **Pool $P$:** the exact eligible chunks that `vector_candidates()` can deliver for this request — `active_membership`
  on `head`, `accepted`, `position > cut`, `position <= upto`, `known_at` respected, active/non-comment, `replies_only`
  respected, **and `so.host_logical_id` not in `in_context`** (using the effective `in_context` after Phase 60's
  optional trim, D3).
- **Unit normalization:** NMOS bundles `pgvector v0.8.6` (`tools/native/sources.json`) and `pgvector/pgvector:pg16`,
  which support `l2_normalize(vector)` and `avg(vector)`. Stored chunks and the query are unit-normalized on read
  (skipping zero/non-finite vectors) so non-unit local embedders behave the same as unit-norm cloud embedders.
- **Minimum pool guard (`MIN_POOL`, Q3):** when $|P|$ (eligible revisions) is below `MIN_POOL` (proposed `16`), contrast
  is skipped cleanly and recall falls back to baseline cosine, avoiding the ~50 % drop artifact in brand-new chats.
- **Degenerate query guard:** if $\|\hat{q} - \mu\| < \epsilon$ (proposed `1e-4`; query lies on top of the chat mean,
  e.g. generic small talk), contrast is undefined/zero; Step 1 checks whether vector-only candidates should abstain or
  fall back cleanly.
- **Pool weighting (Q2):** Step 1 measures both **per-chunk mean** (`AVG(l2_normalize(re.embedding))`) and
  **per-revision mean** (equal weight per message regardless of 1–52 chunks).

### S2 — Mode of operation (`packet-v21`, Q1)

Three zero-call variants are compared in Step 1 before locking the implementation:

- **Variant A — Vector-only noise pruning (conservative):** keep `vector_candidates()` raw-cosine top-50 and RRF
  ranking unchanged; compute `contrast` for the candidate chunks against $\mu$. In `fuse()`, a **vector-only**
  candidate (neither `user_score >= threshold` nor `keyword_score > 0`) is kept only when `sim >= vector_min_sim`
  **and** `contrast > 0` (Q4 also tests replacing `vector_min_sim`). Lexical, keyword and exact-quote hits are never
  pruned by contrast.
- **Variant B — Centered top-50 ranking + vector-only pruning:** rank chunks in `vector_candidates()` by **centered
  cosine** (`1 - ((u - mean) <=> (q_u - mean))`) — and compare against **centered dot** (`(u - mean) · (q_u - mean)`)
  in Step 1 — so distinctive older scenes can displace generic background prose in the top-50 entering RRF, while still
  gating vector-only hits by `contrast > 0`.
- **Variant C — Centered ranking only:** centered top-50 with the existing `vector_min_sim` floor and no `contrast <= 0`
  cutoff.

### S3 — Policy gating and as-of replay (`packet-v21`, D39)

- New packet policy **`packet-v21`** = `packet-v20` + S1–S2. Every policy set that holds `packet-v20` holds
  `packet-v21`.
- `DEFAULT_POLICY` stays `packet-v19` (code default unchanged; `packet-v21` is opt-in via
  `NMOS_PACKET_POLICY=packet-v21`, Q6).
- Under `packet-v20` and every older policy, no contrast SQL runs and every recorded request replays byte-identically.
- Under `packet-v21`, `audit.replay` computes $\mu$ using the trace's exact `upto`, `known_at`, `replies_only` and
  effective `in_context`, with zero model calls and no future vector leakage.
- Fail-open: any contrast computation failure logs a warning and falls back to baseline vector recall without failing
  the request.

### S4 — Trace and Inspector observability

- Record contrast diagnostics inside the existing `retrieval_trace` JSONB payload (no database migration):
  - request-level: `contrast_mode`, `contrast_pool` (eligible count), `contrast_q_norm` ($\|\hat{q} - \mu\|$),
    `contrast_removed` (count pruned), `contrast_ms`;
  - candidate-level: `contrast` score alongside `sim` and `rrf`.
- Surface the summary in the Inspector's retrieval trace view.

### S5 — What it does not change

- No SQL migration, no new extractor generation, no new embedding projection, no re-embedding, no model call on the
  request path, no plugin change.
- Lexical (`pg_trgm`), keyword and exact-quote routes stay unchanged.
- `<Facts>`, `<Cast>`, `<Threads>`, `<Story>`, `<Private>`, status windows and Phase 60's carry/trim/reranker stages
  stay unchanged (if a reranker is configured, it still runs after `fuse()` on the surviving eligible candidates).

---

## Out of scope

- Embedding extracted assertions/facts (NMOS embeds revision chunks, D18).
- A materialized/cached mean-vector table or schema migration (revisited only if Step 1 latency measurement shows
  on-the-fly SQL misses the latency budget).
- Changing `DEFAULT_POLICY`, tuning RRF `RRF_K`, or modifying `vector_min_sim` defaults without measurement.
- Any paid model run (`AGENTS.md §7.6` recall-only gate; owner paused paid runs 2026-10-25).

---

## Questions for the owner (open)

- **Q0 — Timing.** R7 keeps new phases to Stage 7 until `1.0.0`, while Step 1 is a read-only zero-call measurement
  with no code deployed.
  - **(a) Run Step 1 now on a throwaway copy of production and the benchmark databases, then decide whether to build
    `packet-v21`.**
  - (b) Defer until after `1.0.0`.
  - *Proposed: (a)* — zero cost, zero production change, settles whether contrast actually helps NMOS before writing
    production code.
- **Q1 — Mode (if Step 1 passes).**
  - (a) Variant A: vector-only pruning (`contrast > 0`) only.
  - (b) Variant B: centered cosine top-50 ranking + vector-only pruning.
  - **(c) Decide from Step 1's numbers** (default to (a) if recall is tied, pick (b) only if it improves recall with
    zero regressions and acceptable latency).
  - *Proposed: (c).*
- **Q2 — Pool weighting (after Phase 62's 52-chunk cap).**
  - (a) Per-revision mean (every message weighs equally regardless of 1–52 chunks).
  - (b) Per-chunk mean (`AVG(l2_normalize(re.embedding))`, simpler SQL).
  - **(c) Compare both in Step 1 and pick the better recall/latency trade-off.**
  - *Proposed: (c).*
- **Q3 — Minimum pool size (`MIN_POOL`).**
  - **(a) 16 eligible revisions** (skip contrast below 16).
  - (b) 8 eligible revisions.
  - (c) 2 (minimum mathematically defined).
  - *Proposed: (a)* — prevents dropping roughly half of candidates in short chats.
- **Q4 — Interaction with `vector_min_sim` (`0.42`).**
  - **(a) Keep both: `sim >= vector_min_sim` AND `contrast > 0`** for vector-only candidates (strictly tighter noise
    gate).
  - (b) Replace `vector_min_sim` with `contrast > bar` for vector-only candidates (allows low-raw-cosine distinctive
    hits).
  - *Proposed: (a)* as the conservative baseline, with (b) measured alongside it in Step 1.
- **Q5 — Interaction with `sem_query` (Phase 60 S5).** When a short user message (<40 chars) is embedded with the
  previous reply's tail:
  - **(a) Apply contrast normally** (check `sem_query` traces specifically in Step 1).
  - (b) Skip contrast when `sem_query` fired.
  - *Proposed: (a)*, validated separately on the `sem_query` slice in Step 1.
- **Q6 — Rollout and default.**
  - **(a) Selectable via `NMOS_PACKET_POLICY=packet-v21`; code default stays `packet-v19`** (switching production is a
    separate go-ahead that restarts the 1.0 quiet weeks, reversible immediately by setting `packet-v20`).
  - (b) Make `packet-v21` the default once criteria pass.
  - *Proposed: (a).*

---

## Steps

1. **Zero-call offline measurement (before any implementation).** Run a read-only evaluation script against a throwaway
   copy of production (never production's database) and the existing recall/replay benchmark databases (3 runs each,
   majority deciding per `AGENTS.md §7.6`). Measure:
   - Baseline `packet-v20` vs Variant A, Variant B (centered dot and centered cosine), Variant C; chunk-mean vs
     revision-mean; `vector_min_sim` kept vs replaced; `sem_query` slice vs regular queries;
   - Benchmark recall, exact quotes, and `irrelevant` (small-talk) probes;
   - Recorded production traces: echoed-excerpt retention (`audit.py`), vector-only excerpt drop rate, and packet token
     change;
   - Query latency (`vector` stage p50/p95) at production's chunk count (including 52-chunk embeddings once backfilled)
     and at 10,000 messages (`bench_scale.py` shape), checking whether CTE computation fits without a persistent cache.
   - Record all numbers in `docs/perf/phase63-scene-contrast.md`.
   - **Go/No-Go gate:** if no variant improves recall or cuts un-echoed noise without losing benchmark/echoed cases (or
     adds unacceptable latency with no clear win), stop here and close Phase 63 as measured-and-not-adopted (as in
     Phases 44 and 49).
2. **Build `packet-v21` (after owner approval of Step 1 and Q1–Q6).** Implement S1–S4 in `vectors.py`, `retrieval.py`,
   `packet.py`, `audit.py`, `config.py` and `inspector.py` + ADR. Add deterministic unit and DB tests covering:
   - synthetic unit and non-unit vectors (confirming `l2_normalize`);
   - `in_context` exclusion regression (a scene-aligned `in_context` cluster must not pull $\mu$ and zero out older
     candidates);
   - `MIN_POOL` and degenerate query (`||q̂ - μ|| ≈ 0`) guards;
   - lexical/keyword/quote hits never pruned by contrast;
   - as-of replay isolation (`upto`, `known_at`, effective `in_context`);
   - `packet-v20` and older byte-identical to `main`.
3. **Copy verification and scoped self-review.** Zero-call replay of production's recorded traces (`packet-v20`
   byte-identical, `packet-v21` clean), latency re-check, full sidecar test suite (`NMOS_TEST_REQUIRE_DB=1`), and
   scoped review (`AGENTS.md §14`).
4. **Owner trial (separate go-ahead).** Set `NMOS_PACKET_POLICY=packet-v21` on the test install, then production
   (restarts the 1.0 quiet weeks; instant rollback by switching back to `packet-v20`).

---

## Acceptance criteria

1. Step 1 measurements are recorded in `docs/perf/phase63-scene-contrast.md` with zero model calls before any
   implementation begins.
2. Under `packet-v20` and older, every benchmark probe and recorded production trace replays byte-identically to `main`.
3. Under `packet-v21`, no benchmark category is worse than `packet-v20` (and `0.1.x`), echoed-excerpt retention on
   recorded traces does not regress beyond the owner-accepted bound from Step 1, and either recall improves or
   un-echoed vector-only noise drops measurably.
4. Excluding `in_context` from $\mu$, `MIN_POOL`, non-unit stored vectors, zero/degenerate queries and `known_at`/`upto`
   as-of replay are each pinned by automated DB tests.
5. Lexical, keyword and exact-quote hits are never dropped by vector contrast.
6. Added `vector` stage latency stays within the Step 1 budget at production scale and 10,000 messages, and any
   contrast error fails open to baseline vector recall.

---

## Stop conditions

- Step 1 shows zero net gain (or recall/echo loss with no winning variant): stop and close the phase without building
  `packet-v21`.
- Any `packet-v20` or older replay differs from `main`: stop.
- On-the-fly mean computation causes `vector` stage latency to exceed the request deadline budget at 10,000 messages or
  at production's 52-chunk density: stop and bring caching vs deferral back to the owner rather than silently adding a
  migration.
- On the test install or production, `packet-v21` drops needed excerpts: switch `NMOS_PACKET_POLICY` back to
  `packet-v20` immediately (no image rollback or migration rollback needed).

---

## Risk and release

High risk once built (memory selection, request-path latency, as-of replay). Off path: at `packet-v19` (default) and
`packet-v20`, nothing changes and no contrast SQL runs. Ships behind `NMOS_PACKET_POLICY=packet-v21` with no schema
migration, no generation change and no plugin rebuild.
