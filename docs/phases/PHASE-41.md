# Phase 41 — Korean particle boundaries in keyword recall (AGE-76)

Status: approved for bounded correction and synthetic verification by the owner,
2026-10-09, through the explicit orchestrate request to start the discussed fix.
This correction runs beside Phase 39. It is not a new roadmap stage. The owner
separately selected packet-v18 as the 0.4.0 default. Implementation, zero-call replay and performance evidence are in
[the measurement report](../perf/phase41-keyword-particles.md); final suite and
reduced actual-model verification are in progress. No release or new deployment is implied.

## Evidence

On fb095aa, the paid synthetic P01 story has the answer in an accepted raw reply:
"차건혁은 주전자 뚜껑을 닫았다." The extraction returned no assertion for it.
Both the original query with incidental persona narration and the target-only
query fail three of three replays under v17 and v18. The answer is a vector
candidate but falls below the existing relative excerpt floor. The keyword
"차건혁" scores 0.75 against "차건혁은", below the 0.8 keyword threshold,
while an irrelevant later list "차건혁," scores 1.0. These are observations from
one synthetic story, not an estimate of real-world frequency.

## Authorized slice

1. Correct matching of an existing Korean keyword at an exact word boundary with
   an explicit, bounded particle suffix. Investigate this upstream miss before
   changing excerpt selection. Preserve fuzzy matching, the 0.8 threshold, the
   0.5 excerpt floor, candidate/rarity limits, active-source filters and timeouts.
   A longer unrelated name or lexical suffix must not gain an exact-particle hit.
   No morphological dependency, semantic inference, or per-case name/answer rule.
2. Limit activation to fresh packet-v18 requests using a recorded recall option.
   Historical traces missing the option replay with it off. Explicit replay
   overrides enable the candidate for a measured comparison; old v16/v17 policies
   retain their behavior even if an override is present.
3. Select packet-v18 as the default, preserving explicit policy overrides.
   Update the default's contract and user documentation. This decision does not
   make AGE-76 fixed or the live answer-quality gate complete.
4. If particle matching alone fails, diagnose with the fixed cases before making
   a further bounded proposal. No blanket threshold relaxation, universal
   required-label promotion, or extraction of every minor action is authorized.

### Amendment 1 — supplement without displacing existing keyword candidates

Approved explicitly by the owner, 2026-10-09, after the first candidate introduced
one recall and two quote regressions and the process-local alternative was shown.
This amends ADR 0052's ordering and breadth application only for the recorded v18
correction option; it does not change the global fuser or excerpt activation bar.

- Run legacy lookups first, preserving their rarity weights and candidate order.
- Exact particle lookups share the same overall deadline and may use only the
  unspent portion of each word's original 25 ms lookup allowance. A canceled or
  already broad legacy lookup cannot authorize additional matches.
- Admit supplementary matches only when the combined fuzzy/exact revision count
  passes the original 200-source and half-of-eligible-source limits. A failed
  supplemental breadth check does not erase previously valid legacy matches.
- Preserve all existing candidate scores/order. Append only absent revision IDs,
  ranked by supplemental rarity and existing tie breaks, to unused positions in
  the same total cap of 50. A full legacy list gains no additional candidate.
- The owner accepts this last limitation as the bounded scope. Verify it rather
  than expanding the cap or replacing existing candidates. Shared-deadline
  implementation, all probes and performance must pass before adoption.

## Acceptance and evidence

- A1: original P01 query and target-only query recover the right actor/action's
  source excerpt by three-run majority, without a persona-fact bonus.
- A2: independent synthetic API stories vary names, particles, actions, question
  forms and distractors; expected sources and forbidden outcomes are frozen
  before the candidate. Include prefix collisions, the wrong actor doing the
  same action, narration, hidden, inactive, stale and already-in-context sources.
- A3: current keyword rarity, cap, per-word and route deadline behavior remain;
  the PostgreSQL plan uses the trigram index and the 10k-message comparison
  reports latency without claiming unmeasured production performance.
- A4: unchanged historical traces and old policies keep the old option behavior;
  new requests record the option and replay it. The default request path selects
  v18 and an explicit v16/v17 selection still works.
- A5: existing recall, exact quote, persona, hidden/rest, budget, inactive-source
  and today's correction tests pass. Compare old/new snapshots on every available
  gate probe, three times each, with no newly failed majority or newly forbidden
  value. Report per-case differences, not only totals.
- A6: docs, issue and PR state distinguish code/tests from actual host evidence.
  Reduced live model/host verification follows the successful zero-call gate;
  additional paid calls require their own estimate and authorization. Missing
  cached embeddings must never be silently substituted or sent to a provider.

Existing P01 traces retain candidate scores but no durable query vectors were
found in the original in-memory harness cache. Frozen-vector-candidate replay is
permitted as selection-stage evidence only, explicitly labeled; it is not a new
embedding/vector-search measurement. Constructed fixture vectors and extraction
rows are synthetic, not actual model or host results. Existing durable caches
may be reused for the broader historical gate without provider calls.

## Out of scope and stopping conditions

No schema/migration, normalizer output, extractor prompt/generation, worker,
provider, plugin, host orchestration, auth or new runtime dependency changes.
No production database writes or deployment; use copied or throwaway databases.
Stop candidate adoption on a new failed/forbidden gate probe, material unexplained
latency regression, weak provenance, or a need to widen into a new extraction or
ranking design. Record uncertainty; do not rewrite gold or the original score.

High risk: memory selection, stale/inactive-source isolation, secret gates and
historical replay. The lead reviews the full task diff and checks these guarantees
against executed tests and source-linked packets before reporting completion.
