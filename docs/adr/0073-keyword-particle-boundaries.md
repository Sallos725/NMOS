# 0073 — Exact Korean particle boundaries in keyword recall

Status: bounded correction approved by the owner, 2026-10-09 (AGE-76,
PHASE-41 amendment 1). Shared-deadline implementation, cached-vector replay and
10k-message measurement are complete; final suite and reduced actual-model
verification are in progress. Amends ADR 0052 matching/order as bounded below,
not its rarity/time limits or ADR 0068's activation threshold.

## Context

A keyword such as "차건혁" does not meet the existing 0.8 trigram word-similarity
threshold against "차건혁은", while an irrelevant later name list does. In the
original P01 scenario the answer remained a vector candidate, below the fused
excerpt activation floor. Both v17 and v18 missed it with spare token budget.
A semantic assertion was never emitted by the original extraction model, but the
raw source was intact and should be available to the keyword route.

## Decision

- Under v18, allow an existing Hangul keyword followed by one explicit particle
  from a bounded list, with word boundaries on both sides. No arbitrary prefix,
  question-ending, morphology, name join, or per-scenario word is added.
- Use an index candidate filter followed by the exact boundary check. Keep fuzzy
  admission at 0.8, the excerpt floor at 0.5, and all active/accepted/cut/context,
  stale, secret, count, rarity and deadline rules. The candidate query plan and
  measured cost are acceptance requirements, not assumed from an index name.
- Record `keyword_particles` in recall options. Fresh requests default it on,
  effective only in packet-v18. Missing historical values replay as false;
  explicit comparison overrides are reported. v16/v17 retain their old matching.
- No normalizer output, schema, extraction generation, embedding, provider call,
  plugin, or canonical fact changes. Choosing raw evidence does not create an
  extracted fact or claim that the response model used the evidence.

Amendment 1 (owner approved, 2026-10-09, after the first candidate's regressions):
preserve legacy fuzzy weights and ordering, then append previously absent exact
particle revisions only to free slots in the existing 50-candidate list. Combined
fuzzy/exact breadth gates the additions without erasing existing valid hits.
Exact lookups use only the remaining portion of each word's original 25 ms and
the one original route deadline. A canceled/broad legacy lookup cannot contribute
a supplement. A full old list admits no supplement; the owner explicitly accepts
that limitation. This is a bounded ordering amendment, not a global ranking or
threshold change. Its implementation and evidence must still pass the gate.

## Measurement boundary

The original P01 query embeddings were not persisted. Reconstructed recorded
vector candidates reproduce all twelve original packets, but do not constitute
fresh vector search. The frozen candidate recovers both answers three of three
in that selection-stage experiment and separately in lexical-only replay.
Independent constructed API stories use authored extraction/vector stubs and
source-linked expectations: 11/22 baseline to 22/22 candidate (one pronoun case
is an observation, 21 are acceptance cases). All three rounds agree. These are
candidate measurements, not a passed final gate or actual host/model results.

The first candidate is rejected for adoption. The full cached-vector historical
gate ran 338 probes three times per snapshot. Recall improved from 289/314 to
293/314, but exact quotes fell from 21/24 to 19/24: one recall and two quote
probes newly failed, all consistently. Reported forbidden counts did not increase. Expanded
match counts changed rarity weights, candidate order and the two-quote selection;
lookup deadlines caused additional loss. Aggregate gains cannot override these
regressions. The first 10k-message implementation also increased latency.

A process-local experiment retains existing keyword weights/order and appends
only previously absent particle-hit revisions inside the existing candidate cap.
It recovers the three normal-deadline regressions and both P01 prompts, three of
three. It is not production evidence: the experiment uses two route budgets.
Retaining a full existing 50-candidate list admits no additional candidates, so
this is deliberately narrower than replacing the ranking. The subsequent shared-deadline
implementation passes all 338 probes by three-run majority without new failures
or forbidden phrases; recall is 291/314 and quotes 21/24. API p95 on 10k synthetic
messages rises by 22.003 ms. One of four changed Voyage packet majorities adds
weakly relevant context, while retaining the answer evidence: preserving keyword
order does not freeze the final fused packet. [Full evidence](../perf/phase41-keyword-particles.md).
One old
historical probe also fails with deliberately relaxed lookup deadlines on both
baseline and prototype; that pre-existing timing sensitivity is not corrected or
counted as a new pass here.
