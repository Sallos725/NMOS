# Track A Proposal — Current-Scope Stabilization

> Proposed next work; not a phase expansion. This track is limited to performance, correctness,
> evaluation, tests, and documentation for behavior already authorized through the Phase 4 soft
> subset. Any semantic change that requires a new ontology or weakens an invariant stops at its
> decision gate.

## 1. Executive summary

The recommended immediate project is to make the existing beta remain useful on long chats without
changing its memory model:

1. add a verified append fast path to the sidecar;
2. reuse unchanged per-message manifest work (hashing, normalization, bodies) in the plugin;
3. bound broad lexical queries before the database timeout;
4. resolve known predicate-transition errors within the existing assertion model, where possible;
5. establish a reproducible RP memory benchmark for current features.

The highest-value outcome is a warm append at 10,000 messages that stays within the default request
deadline on the measured desktop setup while preserving every existing reconciliation invariant.

A1 and A2 are independently releasable (target: `v0.1.0-beta.10`); they do not wait for A4 or A5.

## 2. Why this should be next

The current large-chat benchmark shows that retrieval itself is not the main bottleneck:

- selective lexical retrieval is about 9–13 ms at 10,000 messages;
- exact vector retrieval is about 102 ms at 10,000 messages;
- plugin manifest hashing is about 186 ms;
- sidecar warm append is about 715 ms;
- the estimated warm request is about 965 ms, above the default 800 ms deadline.

That estimate covers plugin copy + manifest + sidecar append + selective lexical retrieval only. The
plugin calls reconcile → bodies → retrieve sequentially (`core.ts`), and retrieve also pays exact
vector search (≈102–113 ms at 10k) and the query embedding call (up to `NMOS_EMBED_TIMEOUT_MS`,
default 300 ms). Once A1/A2 remove the O(N) sync work, these become the dominant terms, so every
latency target below is stated end to end.

The current request path repeats full-chat work even when the only change is the normal two-message
append. The sidecar remains correct after the plugin times out, but the next request repeats the same
O(N) work, so memory is effectively unavailable beyond roughly 8,000 messages under the default
deadline.

There is also a known semantic error inside the existing predicate model: `possesses` is multi-valued
per subject, so returning or transferring an item can leave both the old and new holder as current
facts. The per-turn extraction experiment exposed this independently of extraction quality.

## 3. Goals

### G1 — Preserve correctness

- No append fast path may accept an edit, delete, swipe, disable, reorder, branch, import, or reroll
  as an append.
- The active transcript remains host-authoritative.
- Raw revisions remain immutable.
- Stale semantic rows remain masked synchronously.
- All fast paths fall back to the existing full reconciliation path when a precondition is uncertain.

### G2 — Reduce warm append cost

- Avoid loading every known revision and rebuilding a full reconciliation plan for a verified suffix.
- Avoid recomputing SHA-256 for unchanged messages in the plugin.
- Keep first sight, divergence, and recovery behavior unchanged.

### G3 — Improve bounded degradation

- Broad lexical queries should do bounded useful work or abstain early rather than consume their full
  timeout while scoring most of the conversation.
- Embedding and lexical failures remain independent; one channel failing must not suppress valid
  state or facts.

### G4 — Establish a quality baseline

- Convert representative long-RP failures into deterministic fixtures.
- Measure correctness and memory overuse, not only retrieval latency.

## 4. Non-goals

This track does not add:

- first-class entities, events, narrative time, causal links, or open threads;
- a transition-verifier model or conflict queue;
- hard character-POV isolation;
- MCP tools or forensic agents;
- lorebook/persona/card ingestion;
- a graph database, ANN index by default, or PocketRisu fork;
- group-chat orchestration;
- a new source-of-truth model.

Those belong to Track B or a later owner-approved phase.

## 5. Work packages

### A1 — Verified sidecar append fast path

#### Design

For a conversation with an existing head:

1. Read bounded head metadata: head commit, manifest hash, and head length
   (`max(position) + 1` on `active_membership`, an index lookup on its `(commit_id, position)` primary
   key).
2. Let `old_len` be the head length.
3. Require `new_len > old_len`.
4. Compute the manifest hash of the request prefix `messages[0:old_len]` and require it to equal the
   stored head manifest hash.
5. Require the suffix to be a plain append in the sense of `plan()`:
   - no suffix `host_logical_id` is already a head member (one indexed lookup of the suffix IDs
     against head membership; `plan()` maps by ID, so a repeated ID would be a reorder or edit, not an
     append);
   - no suffix message has `disabled: "allBefore"` (a new cut changes the turn layout of the whole
     prefix, `reconcile.turn_layout`).
6. Treat only the suffix as new. Look up lifecycle for suffix keys only; request bodies only for
   suffix revisions not already stored. Answer the first (`needs_bodies`) reconcile of an append the
   same way, without `load_state`.
7. Apply append membership operations and recompute only what an append can change:
   - provisional → accepted: computed from the head members whose lifecycle is `provisional`
     (a lifecycle query), not from a fixed positional tail — `_acceptance` walks back to the last
     enabled user message, which a disabled user message can push arbitrarily far;
   - turn grouping and anchor movement of the last turn, using the stored absolute `turn` index;
   - `window_hash` for suffix positions and `turn_hash` for turns whose `K`-turn window reaches the
     suffix;
   - extraction and embedding scheduling.
8. Compute and store the new full manifest hash.
9. On any mismatch, missing metadata, unexpected lifecycle, or failed replay assertion, execute the
   existing full reconciliation path.

The prefix hash check is the safety barrier. Length or tail identity alone is insufficient because a
deep edit can accompany a tail append. The prefix hash is necessary but not sufficient: step 5 closes
the cases where a matching prefix still does not make the request an append.

#### Schema consideration

No migration is expected: head length is an index lookup (step 1). Add conversation head metadata
through a new numbered migration only if measurement shows that lookup is a cost, and then update it
in the same transaction as head membership. Do not modify an applied migration.

Outcome (ADR 0010): head length needed no migration, but measurement found a different O(N) cost —
each append rewrote the head commit's `delta` jsonb (2.2 MB, ≈117 ms at 10k). Migration 0013 stores
appends as `worldline_append` rows.

#### Tests

- pure append, including acceptance of the previous provisional reply;
- append after plugin/sidecar restart;
- deep edit plus append must reject the fast path;
- delete plus append, reorder plus append, swipe plus append, and disable plus append must reject it;
- a suffix repeating a head `host_logical_id` must reject it;
- a suffix containing an `allBefore` cut must reject it;
- a provisional reply before a disabled user message is accepted exactly as the full planner does;
- same prefix with missing suffix body resumes safely over multiple requests;
- duplicate request is a no-op;
- fast-path result equals the existing full planner's ledger and membership result;
- turn hashes and queued jobs equal the full-path result;
- transaction failure leaves the prior head intact;
- a structural counter shows the fast path was taken and did not call `load_state` (no wall-clock
  assertions in CI).

### A2 — Incremental plugin manifest hashing

#### Design

Maintain a bounded per-chat cache keyed by host logical message ID. Each entry stores:

- the hash-relevant canonical fields or a cheap equality snapshot;
- the resulting revision hash;
- selected swipe identity/content;
- the chat identifier and cache generation.

Each request still walks the transcript in order to build the manifest, but per-message work runs only
for new or changed messages. The final ordered manifest hash is still rebuilt so order changes remain
visible.

SHA-256 is not the only per-message cost. `buildManifest` currently also runs, for every message:
`canonicalJson` (NFC per field), a second `normalizeText` of the content for the bodies map, and the
`specialComments` regex over the message data. The cache covers all of them, and the manifest entry's
non-hash fields (`name`, `swipe_count`, `special_comments`) are cached with it. Bodies are built lazily,
only for the keys the sidecar asks for.

Cache correctness requirements:

- the equality check compares the full hash-input strings and fields; a non-cryptographic hash or
  digest must not stand in for it — a collision would hide a change, the sidecar would see a noop, and
  stale state would be injected;
- never key by array index or `generationId` alone;
- clear or segregate on chat change/import;
- detect changes to every revision-hash input, including `disabled`, selected swipe, role, comment
  state, speaker metadata, and generation ID;
- bound memory and evict old chats: full content at 10k messages is ≈24 MB (UTF-16) per chat, so keep
  at most one or two chats;
- fall back to a fresh hash if cache state is incomplete or malformed.

#### Tests

- unchanged 10,000-message manifest hashes, normalizes, and builds bodies for zero messages after
  warm-up (counted, not timed);
- one deep edit hashes exactly the changed message while changing the final manifest hash;
- swipe, disable, continue, reroll, import, and duplicate IDs across chats remain distinguishable;
- cached and uncached manifests are byte-identical to the committed cross-language hash vectors;
- cache eviction cannot alter output.

### A3 — Broad lexical-query bounding

Evaluate two conservative alternatives against the current timeout-only behavior:

1. retrieve a bounded, recency-ordered set of trigram index hits and score only that set;
2. require a minimum amount of distinctive query evidence before opening a broad lexical route.

The cost of a broad query is the heap recheck of `<%` (`word_similarity`) on every bitmap candidate.
An `ORDER BY position LIMIT n` over the same statement does not reduce that recheck, so alternative 1
needs a two-stage query (cap or count the candidate set first, then score the capped set).
Alternative 2 needs term-frequency evidence that does not exist yet. Before choosing, record
`EXPLAIN (ANALYZE, BUFFERS)` for a selective and a broad query at 10k and put the plans in the
decision.

Selection criteria:

- no regression on exact-quote and Korean paraphrase fixtures;
- predictable upper bound on rows scored;
- an explicit trace reason such as `bounded`, `too_broad`, or `timeout`;
- vector, state, and fact routes continue even when lexical abstains.

Do not introduce an opaque learned reranker in this track.

### A4 — Existing-predicate transition correctness

Start with the measured ownership-transfer case and do not generalize prematurely.

#### Decision gate

Before code, write an ADR choosing one of:

- **Item-centric ownership:** introduce an existing-model predicate whose single-valued subject is
  the item and whose object is the current holder.
- **Explicit termination assertion:** extend the current assertion semantics to close an earlier
  multi-valued fact.
- **Defer to Track B:** keep `possesses` as an accumulating historical relation and stop presenting it
  as authoritative current ownership until the new transition model exists.

Trade-off:

- item-centric ownership is small and deterministic but creates migration/compatibility questions;
- explicit termination begins a larger temporal model and may exceed current scope;
- deferral is safest architecturally but leaves a known product limitation, and the fix then waits
  for Track B's B1 and B2.

Constraints that apply to every option and must be stated in the ADR:

- **Free-text names:** subjects and objects are still text. Item-centric supersession is keyed on the
  item's name, so "해안 지도" and "지도" are different subjects and two current holders reappear
  silently. Any fix here is partial until entity identity exists (Track B, B1).
- **Generation cost:** a registry or prompt change is a new extractor generation (D20). Activation
  re-queues every item an earlier generation covered, so existing users pay LLM calls for their history
  on upgrade. The ADR estimates this cost (≈3.1k tokens per turn with the model in
  `docs/perf/turn-extraction.md`).

Recommendation: item-centric `held_by` (subject item, object character, single-valued), with
`possesses` kept as accumulating history and no longer presented as current ownership. Explicit
termination belongs to Track B's transition verifier (B2).

Acceptance requires a deterministic fixture where an item moves A → B → C, plus a historical query
that still shows earlier holders while the current projection shows only C. It also requires one
recorded real-model run on the `turn-extraction.md` chat, reporting how often the item name stayed
consistent enough for supersession.

### A5 — RP memory evaluation baseline

Add a reproducible benchmark harness without model-generated ground truth, in two tiers:

- **Deterministic tier (gates CI):** a stub extractor with fixed assertions, so the result depends
  only on reconciliation, invalidation, retrieval, and packet compilation. Metrics are measured on the
  packet, not on a generated answer: whether the gold fact or evidence is present, whether a stale,
  false, or other-branch item is present, and the token cost.
- **Model tier (reported, never gating):** the same cases with a real extractor, reported with the
  metadata listed below. No judge model is introduced; accuracy remains a packet-level measure.

Initial cases:

- current state after several transitions;
- historical state;
- refused user action;
- edit/delete/reroll/swipe invalidation;
- branch isolation;
- exact quote;
- Korean paraphrase recall;
- soft knowledge annotation and unknown semantics;
- irrelevant-memory suppression;
- broad-query abstention;
- long-chat latency tiers.

Compare at least:

- recent context only;
- lexical raw recall;
- lexical + vector;
- full current NMOS packet.

Metrics:

- current-state and historical-state accuracy;
- false-memory and branch-contamination rate;
- retrieval precision/recall at the configured packet budget;
- irrelevant-memory rate;
- packet token cost;
- p50/p95 manifest, reconcile, retrieve, and total added latency.

Model-dependent extraction evaluations must report model, endpoint type, prompt generation, settings,
run count, and failures. Synthetic fixtures must be labelled as synthetic and never presented as host
evidence.

## 6. Acceptance criteria

Track A is complete only when:

- all existing 137 sidecar and 41 plugin tests still pass;
- new fast-path equivalence and rejection tests pass;
- migrations apply cleanly and rebuild still reproduces active membership;
- benchmark results are committed to `docs/perf/` with machine and workload details;
- CI checks structural counters (fast path taken, rows loaded, messages hashed), not wall-clock time;
- at 10,000 messages on the existing benchmark machine:
  - warm sidecar append p95 (both round trips) is at most 150 ms;
  - warm plugin manifest/hash p95 is at most 60 ms;
  - the estimated end-to-end warm `beforeRequest` p95 — snapshot copy, manifest, sync, and retrieve
    including vector search and a measured query-embedding latency — is at most 500 ms, leaving
    300 ms of the default 800 ms deadline for network and host overhead;
- a real-host check at 5,000 and 10,000 messages confirms the envelope, using a synthetic chat
  (`tools/make_synthetic_chat.py`, labelled synthetic) imported into the isolated PocketRisu test
  instance;
- if a tier cannot be loaded into the real host, the report says so explicitly;
- every broad-query abstention is visible in the retrieval trace;
- the ownership-transition decision is either implemented and tested or explicitly deferred with an
  updated known limitation;
- `docs/STATUS.md`, README limits, and performance documentation reflect the measured result.

Performance targets are goals, not permission to weaken reconciliation. If the target cannot be met
without trusting an unverified delta, stop and report the evidence.

## 7. Suggested implementation order

1. Add structural counters and re-record the 1k/5k/10k baseline with `tools/bench_scale.py`.
2. Implement A1 sidecar append detection and rejection tests.
3. Implement bounded-tail application and compare it with the full planner.
4. Re-measure before changing the plugin.
5. Implement A2 incremental manifest and re-measure end to end; real-host check; release
   `v0.1.0-beta.10`.
6. Implement A3 broad-query bounding after recording the query plans.
7. Write the A4 ownership ADR and fix or defer it.
8. Land A5 benchmark baseline and update public limits.

Prefer separate reviewable commits for detection, application, plugin cache, lexical policy, semantic
decision, and benchmark evidence.

## 8. Risks and stop conditions

Stop and ask the owner if:

- append verification requires trusting plugin state that the sidecar cannot independently verify;
- the ownership repair requires a general temporal/event model;
- a new runtime dependency appears necessary;
- measurements suggest a PocketRisu bridge or fork is required;
- the optimized and full planners produce different logical ledger states;
- mobile or real-host evidence contradicts the documented performance envelope.

## 9. Deliverables

- optimized sidecar append path with safe fallback;
- incremental plugin manifest hashing;
- bounded lexical policy and trace reasons;
- ownership ADR and resulting fix or explicit deferral;
- reproducible benchmark tooling and result document;
- updated tests, status, README, and changelog when released.
