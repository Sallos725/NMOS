# Proposal — Recall ideas from an anonymous comparison

> Status: proposal only, 2026-10-03. The owner requested documentation and Linear tracking, not implementation.
> Phase 28 remains the current correction phase. Its measurement gates still apply; this survey does not add
> release criteria, authorize ranking changes, or approve model calls. NMOS baseline: `e6fbcac` on `main`.

## 1. Evidence and publication boundary

This is a static reading of locally supplied memory-plugin distributions, compared with NMOS source and ADRs.
Another project's approach below means code or a prompt was observed, not that its runtime behavior, accuracy,
latency, or benefit to NMOS was measured. No comparative benchmark or model call was run.

The owner requires anonymity. This document, related Linear records and the pull request omit external project
names, authors, versions, filenames, local paths, URLs, unique identifiers and verbatim source snippets. There is
no project-to-label mapping. No external code is copied; approaches are restated in NMOS terms. Only NMOS sources
are linked. The supplied distributions remain outside the repository, so this public account cannot independently
reproduce the external source inspection.

One distribution delegates its current injection plan to a server provided as a binary. Its client also contains
older orchestration code. Rules found in that client are design references, not proof that its current server
executes them. This qualification matters particularly for the summary-relevance candidate below.

## 2. Comparison with current NMOS

| Area | Current NMOS | Another project's approach | Disposition |
|---|---|---|---|
| Search candidates | `retrieval.fuse` combines lexical, keyword and vector ranks; after excluding messages already in context, `gather` takes the top candidates. | Direct matches, recent context, the current scene and linked records supply separate queues; round-robin merging admits candidates before later ranking and packing. | S2: measure candidate coverage. This does not prove that every queue gets final packet space. |
| Supporting evidence | A fact can carry its stated `because`; thread openings and endings are linked. The Inspector can show a matching earlier causal event. Those causal links do not enter the packet. | Search seeds expand through declared references and, more broadly, shared scenes, entities or nearby records. | S1: consider bounded support retrieval; shared membership alone must not establish a semantic relation. |
| Older narrative | `summaries.packet_lines` offers a usable overall story without a query-relevance threshold, plus one sufficiently relevant older scene. Secret checks still apply. | Client code reduces an older narrative's space when it lacks query alignment and can omit it on an explicit topic change. Current server use is unverified. | S3: test optional story selection, preserving historical questions. |
| Role/thread endings | Phase 28 proposes listing current roles and ending the exact listed relation; existing open-thread hints already provide earlier state. | An extraction prompt supplies existing records and asks for the same stable identity on a change or completion, supported by the latest turn. | Useful for NMO-24 now, but substantially overlaps the approved correction. |
| Associative recall | Retrieval does not turn co-retrieval into an assertion or knowledge grant. | Graph activation spreads across weighted edges; co-activation strengthens associations and an optional rule can extend perspective membership. | A retrieval-only comparison idea. Co-activation is not evidence of truth or knowledge. |
| Operator feedback | The packet ledger records offered/placed lines and omissions; the Inspector and HUD show outcomes, coverage and model usage. | User-facing explanations distinguish retries, budget omissions and fallbacks; recently changed fields are marked. | S4: optional presentation improvement using existing NMOS evidence. |

NMOS references: [retrieval](../../apps/sidecar/src/nmos_sidecar/retrieval.py) (`fuse`, `gather`),
[summary selection](../../apps/sidecar/src/nmos_sidecar/summaries.py) (`packet_lines`),
[stated causes](../adr/0040-stated-causes.md), [packet ledger](../adr/0027-packet-ledger.md),
[model-call usage](../adr/0051-model-call-usage.md), and [Phase 28](../phases/PHASE-28.md).

## 3. What helps NMO-24 now

NMO-24 is the current Linear identifier of AGE-24, the identifier used in the phase documents.
Its present correction concerns role endings and identity; recall changes wait for measurements on corrected state.

**Reuse the existing relation, then check what actually ended.** Another project's extraction instructions reuse
an existing record's identity on completion. In NMOS this supports Phase 28's existing exact-role approach rather
than a new reconciliation rule. Identity reuse alone cannot tell which stay or job ended: the TARGET evidence must
refer to the listed role's party and place. A departure, a new residence or an absence is not automatically the
end of every earlier role. This is directly relevant to the work already tracked in NMO-24 and PR #251.

**Use the existing tests and stop conditions.** Keep the no-ending and wrong-role controls alongside genuine
endings, preserve past-state answers and report first connection separately from ordered backfill. The role hints
available in those two orders can differ. Fixed-input model probes cannot stand in for the sequential worker run
or the full live gate. These are reminders of the active work, not new acceptance criteria.

**Localize a remaining miss before changing ranking.** On the corrected copies, inspect the saved assertions,
resolved identities, current/history fold, retrieval candidates, excerpt text and packet ledger in that order.
Record whether the answer was never extracted, filed under another entity, retained in the wrong state, not
retrieved, missed by the excerpt, or dropped while packing. The existing ledger distinguishes placement from
retrieval; it does not prove the response model used a line. Such diagnosis can inform Phase 28's later re-scoping.

S1–S3 below are for that later decision. They cannot repair a wrong canonical state, and they must not hide one
by lowering its score. They are not blockers added to the current release.

## 4. Candidates after the state correction

### S1 — Bounded retrieval of supporting evidence

**Current NMOS:** `because` is carried as text. [ADR 0040](../adr/0040-stated-causes.md) deliberately keeps its
heuristic event links out of the packet because a wrong link would attribute a false turn. Thread lifecycles and
assertion source revisions provide other existing references.

**Another project's approach:** a directly matched record adds linked records to the candidate pool.

**Candidate:** begin with source revisions or explicit lifecycle references already supported by NMOS. Follow at
most one edge, with a separate candidate/token cap. Keep the heuristic causal-event match as a hypothesis unless
separately validated; do not promote it to ground truth. Same person, same scene or adjacency alone is insufficient.
Every added source must still be active, in the same conversation/worldline, within the request's as-of bounds,
outside existing prompt coverage and subject to the same knowledge restrictions. Record why it was considered.

**Evidence needed:** fixed-input replay cases where a relevant fact was found but its necessary support was absent;
answer-bearing support gained, unrelated support added, knowledge-boundary failures, budget and latency. No extra
generative call is needed for the proposed read-side comparison once separately authorized.

### S2 — Preserve useful contributions from different search routes

**Current NMOS:** RRF combines three routes, followed by a single top-candidate cut. Keyword recall already broadens
admission; a new hybrid search implementation is not the missing feature.

**Another project's approach:** round-robin merging gives separate suppliers a chance to contribute candidates.

**Candidate:** first measure whether one route's useful results actually disappear at the cut. Compare the current
union with bounded admission from the existing routes under the same total candidate and token budgets. Do not
automatically turn previous-response text into an admission signal: NMOS's current tie-break restriction follows
observed filler recall ([ADR 0004](../adr/0004-raw-recall-scoring.md)). A new context route is a separate experiment.

**Evidence needed:** questions with several requested facts, vector-on and vector-off runs, per-route candidate and
placed-evidence counts, duplicate/unrelated content, answer coverage and latency. A candidate quota does not imply
a final packet quota. Retain abstention when no route has enough evidence; do not fill a quota with weak matches.

### S3 — Decide when the overall story earns packet space

**Current NMOS:** overall story selection checks validity and secrets, but not query relevance. Scene-summary
selection already checks relevance; [ADR 0043](../adr/0043-story-and-cast.md) bounds the Story section's budget.

**Another project's approach:** older narrative is reduced or omitted when it lacks alignment with the current
request. This was observed in client source; its use by the current server was not established.

**Candidate:** compare current behavior with reducing or omitting the overall story for requests that do not need
it. Keep explicit historical questions and story-recap requests as controls. A topic change must not erase facts,
undo a role, bypass secrets, or reinterpret every ordinary use of a word such as "now" as a reset.

**Evidence needed:** the same corrected extraction and token reserve; current-state questions, scene changes,
"at first" questions and recap requests; answer coverage, stale/forbidden content and resulting packet size.
This does not fix K35, which concerns the summarizer's unbounded input, not summary selection for a response.

### S4 — Show which memory changed and why a request omitted memory

**Current NMOS:** histories, provenance, packet omissions, coverage and usage are inspectable already.

**Another project's approach:** recently changed fields are visibly marked and request outcomes are explained in
ordinary language.

**Candidate:** make existing evidence easier to navigate before adding another diagnostic store. Distinguish an
in-story state change from an extraction finishing or an owner repair; asynchronous work makes "changed this turn"
ambiguous. Check the existing panel first for duplication. This remains a UI proposal, outside Phase 28.

## 5. Existing work and approaches not carried forward

The [September survey's dated follow-up](IDEA-SURVEY-2026-09-29.md#7-follow-up-2026-10-03) records which candidates
have since landed: evidence-in-turn checks, provider-reported usage and fallback outcomes, and owner-join previews.
Directional relationships, speech/address history, locks, source invalidation and packet provenance already exist.
They are not new gaps discovered by this comparison.

Do not adopt co-activation as proof of identity, causality or character knowledge; automatic loss of raw evidence;
model-invented numeric relationship scores; response-model writes to canonical memory; or request-path generative
selection that bypasses NMOS's worker-only rule. A graph or another model call is not, by itself, evidence of better
recall. Any future exception needs its own owner decision and architectural review.

## 6. Order, verification and tracking

1. Continue NMO-24's existing Phase 28 correction and measurement. This document does not change its scope.
2. Classify the remaining misses on corrected state. Choose among S1–S3 only when that evidence supports a need;
   their numbering is not an approved implementation order.
3. If the owner selects an experiment, write its scope and measurable acceptance/stop criteria first. Keep the
   baseline fixed, vary one rule at a time, record policy/options for replay and preserve the original traces.
4. Report every relevant case and regression, with equal configured budgets, vector availability and latency;
   do not claim generated-answer accuracy from packet evidence alone. Live model comparisons need an approved
   call/token estimate. Stop on a false join, a wrong role ending, secret exposure or failure of the agreed gate.

**Risk if implemented:** S1–S3 are high risk under AGENTS §14 because they change memory selection, provenance or
knowledge-boundary handling. This change is documentation only; it changes no schema, defaults or runtime behavior.

Git is the durable technical record. Linear tracks the follow-up decision and links to this proposal and its PR;
the proposal is not duplicated as a Linear document. No comparative results are recorded because none were run.
