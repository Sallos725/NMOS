# Phase 41 — AGE-76 correction experiments

Date: 2026-10-09. Baseline: `fb095aa14b378bf03eb5b82f9804fa10b460793b`,
packet-v18. Status: the first candidate is rejected; the owner approved the
supplemental-ordering amendment after reviewing its limitation. No release or deployment is established by these experiments.
A separately authorized reduced actual-model run is in progress.

## Fixed evidence and method

The original paid P01 story contains its answer in accepted raw evidence, but
both the original query and its target-only form omit that answer under v18.
The previous harness did not persist the query embeddings. A reconstruction of
recorded vector-candidate IDs, rounded scores and order reproduces all twelve
original packets exactly. This is selection-stage instrumentation, not a fresh
vector search. A separate lexical-only lane has the same baseline miss.

Independent authored stories exercise the real sync/worker/retrieval/trace API
with deterministic extraction and embedding stubs. The oracle checks the exact
actor/action sentence and its source revision, plus forbidden text, source
visibility and token bounds. The frozen manifest is
`fixtures/recall/age76-particles.json`, SHA-256
`0f93cdb3ef97fae53a446f005fb9f2fd42677c29694a8c1e3dcc831a52c83cc8`.
Twenty-one queries are acceptance checks; one pronoun case is an observation.
Corrupting either the actor or expected source makes the scorer fail.

The historical gate uses actual durable query-vector caches and copied databases
in read-only transactions. Both snapshots use packet-v18; only the candidate gets
the explicit recorded-option override `keyword_particles=True`. Missing caches
raise an error. There are no new provider calls or writes to original databases.

## First candidate: expanded matches share one rarity score

| Check | Baseline | Candidate | Interpretation |
|---|---:|---:|---|
| Original P01, two prompts | 0/2 | 2/2 | Three of three, saved-candidate and lexical-only lanes |
| Authored acceptance queries | 10/21 | 21/21 | Three of three; stubs, not model quality |
| Pronoun observation | 1/1 | 1/1 | Outside the required correction scope |
| Historical recall | 289/314 | 293/314 | Five gains, one new failure |
| Historical exact quotes | 21/24 | 19/24 | Two new failures |
| Increased forbidden counts | — | 0 | r1 counted hits; r2 also compares individual phrase identities |

All 338 historical probes were run three times per snapshot: 2,028 evaluated
packets, no majority instability in that run. The candidate's 52 source blobs
were checked against a frozen manifest before and after every round. Its source
manifest digest is
`fdbb0e01640948135c767a04fa31c0c14d55c48769299afc29c280c147f53ae8`.

The new failures are `S6-1-default::c120_22_early`, `quotes::q-first-07` and
`quotes::q-said-22`. Expanded counts changed rarity weights and candidate order.
One quote falls from second to third beyond the unchanged two-quote cap. Another
is affected by lookup cancellation. In S6 the answer source remains a vector
candidate, but losing keyword-hit status changes the excerpt anchor and omits
the answer sentence. It is not a failure to retrieve the source itself.

The first 10k-message implementation also regressed API latency: in the cold
index experiment p50/p95 rose from 22.79/345.37 ms to 69.22/441.93 ms. This uses
synthetic long messages, an in-process API and no facts/vectors; it is not a
production latency estimate. A separate SQL prototype reduced the overhead,
but retained the rejected selection semantics and is not an accepted fix.

## Approved amendment: preserve existing matches, supplement free slots

The process-local experiment keeps existing keyword weights and order, then
appends only previously absent particle-hit revisions inside the same 50-entry
cap. It recovers all three regressions at normal deadlines, both P01 prompts and
all 22 authored queries, three of three. This prototype runs two separate route
budgets and therefore cannot establish production deadline or latency safety.

The concrete implementation proposal is:

1. Run the unchanged fuzzy lookups first; retain each word's result and actual
   lookup time. Keep the old rarity calculation and candidate ordering.
2. Look up exact particle matches only for eligible words, using the remaining
   part of that word's original 25 ms allowance and the same route deadline.
   A canceled or already broad fuzzy lookup cannot gain supplementary matches.
3. Union fuzzy and exact IDs for the supplemental breadth check: more than 200
   or more than half of eligible sources admits no supplement. The prior valid
   fuzzy hits remain as before. Do not count a canceled query as zero matches.
4. Do not alter any existing keyword candidate's score or position. Sort new
   candidates by supplemental rarity and the existing tie breaks, then fill only
   the unused positions up to 50. Keep the packet floor and downstream budgets.

This explicitly amends ordering and the use of the breadth gate; it is not just
a faster equivalent SQL query. A full legacy list admits no new revisions.
That limitation is observed in two of the three diagnosed historical probes,
and must be tested and disclosed rather than called a general long-chat repair.

One pre-existing S6 probe fails on both baseline and prototype when diagnostic
timeouts are deliberately relaxed. Its legacy success depends on which keyword
lookups time out. The proposed correction does not claim to repair that broader
timing sensitivity.

## Second candidate: implemented under the original deadlines

The frozen r2 Python-source manifest (52 files) is
`532becaaac70d143d47c7c4e6dea84313ccd75b3ce091610a198befe21969d3c`.
The implementation uses one route deadline and each word's remaining 25 ms,
skips supplementation when 50 existing candidates already fill the list, and
preserves original weights even when combined matching is too broad. A coarse
0.6 trigram filter only finds index candidates for the exact boundary check; it
does not lower the 0.8 fuzzy admission threshold.

Focused real-DB tests: 63 passed. Seven tests for the amended contract failed
against r1 before the implementation. On the frozen r2 source:

| Check | Baseline v18 | r2 v18 | Result |
|---|---:|---:|---|
| Original P01, two prompts | 0/2 | 2/2 | Three of three in both saved-candidate and lexical-only lanes |
| Authored acceptance queries | 10/21 | 21/21 | All three runs; plus the one pronoun observation |
| Historical recall | 289/314 | 291/314 | No new failed majority |
| Historical exact quotes | 21/24 | 21/24 | All three prior regressions recovered |
| Newly forbidden phrase identities | — | 0 | Compared individual phrases, not only total counts |
| Original K32 options | 10/17 | 10/17 | No new failure or forbidden phrase |
| Explicit current K32 options | 14/17 | 14/17 | Majority; baseline rounds 13/14/14, r2 14/14/14 |

All 338 historical probes ran three times per snapshot with actual cached query
vectors: 2,028 evaluations, no pass/fail instability. The two recall improvements
are two option variants of the same butcher question, not two independent story
findings. Old P01 trace packets reproduce exactly in 12/12 comparisons without
the override. Explicit v17 retains text, tokens and scores in 66/66 comparisons.

### Voyage records and qualitative review

The copied trial database has 85 replayable requests and 21 changed-prefix
exclusions. All 85 ran three times per snapshot with their cached Voyage vectors;
no token-budget or hidden-redaction violation was observed. These requests have
no frozen answer gold: this is a contract/delta review, not recall accuracy.

Four packet majorities changed. The placed facts, claims and summaries stayed
identical; the changes were excerpts. In one (`674f361260bd493b`, a trace hash),
a past emotional scene involving a third person became the reserved required
excerpt despite weak relevance to the requested combat scene. The prior combat
excerpt stayed placed with the same source/text, now supportive. Two supportive
excerpts fell below the relative floor; the useful combat-role information in one
was also preserved by a required claim and another combat excerpt. No concrete
wrong answer, actor misattribution or loss of that answer evidence was confirmed.

This is a real noise/overuse limitation, not a scored regression to conceal.
Preserving the keyword list does not promise an identical final packet: new
keyword evidence still participates in the existing global fusion and relative
excerpt floor. The compiler reserves its first surviving excerpt as required;
that label alone does not establish semantic relevance or unextracted status.
One of the other three changes had an unstable baseline first round; rounds two
and three supplied its majority. Private source text stays outside the repo.

### 10k-message cost

The actual frozen r2 implementation ran 11 queries in six alternating rounds
(132 API calls), using a newly populated synthetic long-message corpus, no
extraction/facts/vectors, and the same-code v17 bypass as comparator. There was
no manual index cleanup or prewarming; later calls are not claimed to be cold.

| API latency | v17 bypass | r2 v18 | Increase |
|---|---:|---:|---:|
| p50 | 20.749 ms | 34.685 ms | 13.936 ms |
| p95 | 351.576 ms | 373.579 ms | 22.003 ms |

The two target-name questions gained about 45 ms each, concentrated in the
keyword route. Up to four supplementary lookups plus the newly needed head count
and final source read add work. The exact breakdown is not separately measured.
Rare exact lookups read one heap row (5.669 and 3.382 ms); a common word stopped
at 201. No keyword route exhausted its overall deadline in these 132 calls.
This is a measured cost within the existing limits, not zero regression in
latency and not a production-host latency estimate.

### Suite and review

The first full suite ran with a real required database: 1,491 passed, four failed.
Two failures assumed the old v16 default. Two assumed no ordinary raw excerpt
could match a secret-only question; particle matching now finds a separate,
unmarked nod reply. The revised tests hold that ordinary reply in context for
the empty-packet assertion and separately check mixed visibility. The secret
source remains eligible, so a broken secret gate would still fail the test.
Redacted hidden provenance, zero offered-memory counts and exact replay remain
asserted. The corrected cases plus older-policy tests pass: 17 passed in 12.35 s.
Final full-suite verification is pending PR CI; the initial failures are retained.

The lead reviewed the five changed product files and directly relevant callers,
contracts and tests. Two bounded read-only checks found no additional blocker.
High risk: memory selection, provenance, inactive/stale-source and secret isolation,
and historical replay. The product source still exactly matches frozen r2.

The owner separately authorized three actual-provider stories/seven questions,
up to 18 generative calls, 40 embedded texts and USD 1.50. That run uses fresh
isolated databases, unchanged story oracles and paired three-run replays; results
are pending. It does not measure response-model answers or PocketRisu UI behavior.
No trial deployment was made by this correction.

Private local evidence: `/tmp/nmos-age76-evidence/gate/`,
`/tmp/nmos-age76-evidence/scenarios/`, and
`/tmp/nmos-age76-evidence/regression-diagnosis/`. Raw chat excerpts, database
credentials and full private packet artifacts are not committed here.
