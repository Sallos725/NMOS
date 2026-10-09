# Phase 42 — A recalled source's status-window clock

Status: approved for a bounded pre-release correction by the owner, 2026-10-10.
The owner paused v0.4.0 publication to check current date/time and the time of past
scenes, requested a quick correction if feasible, and authorized the existing
measurement database after its credential-read approval boundary. This correction
runs beside Phase 39; it does not start a roadmap stage.

## Evidence

The read-only `adf0baa` deployment-copy database contains 39 Date/Time observations
and six date/time observations. Date has 17 distinct values; Time has five. The
second card has one date and six clock values. Among recorded placed excerpts or
quotes whose exact source revision has a clock, 248 source lines lack that clock.
This counts lines, not distinct requests, incorrect answers or missing values in
the entire prompt. A short synthetic source can retain its status window in the
excerpt, so the omission is not universal. Existing current-state and history
reads retain dates/times; generic history recall returns only the last six changes
and does not join the recalled source to its own historical clock.

## Bounded correction

- Keep packet-v18 as the owner-selected default. Record a new recall option;
  historical traces missing it replay with it off; v16/v17 remain unchanged.
- For explicit temporal questions only, attach the literal date/time recorded by
  an active card-bound parser on the exact revision of an already placed excerpt
  or quote. Use at most two source revisions and only remaining packet budget.
  Preserve every existing selected line, order, excerpt wording and token budget.
- Label these as source-status times, not inferred event occurrence times. An
  embedded flashback, a vague value such as Morning, a fictional calendar and a
  clock after a scene do not justify conversion, duration arithmetic or a precise
  event timestamp. State this distinction in the packet.
- Retain exact revision, turn and rules provenance. Do not borrow the current
  clock, a neighboring turn, another chat/card, a future revision, an inactive
  source or a parser version other than the request's. Conflicting stored aliases abstain. The existing parser contract (the last match of the same key wins) remains authoritative; this does not validate a user-defined parser's interpretation.
- Only already-eligible and placed sources can expose a clock. Apply existing
  secret/memory gates to the added text; hidden candidates provide no clock.
  Strict and first-person narrator modes conservatively omit this supplement.
  Keep current-state retrieval unchanged. Missing source clocks and full budgets
  remain valid abstentions, not occasions to invent time.

## Verification

1. Freeze real-record diagnostic counts and the short-source counterexample.
2. Reproduce the missing clock with a long synthetic source and multiple later
   dates. Pin source identity, edited/disabled/card-mismatched sources, duplicate
   rules, misleading flashback prose, tiny budgets and secret gates.
3. Compare the original and corrected packets: source selection and original
   content unchanged, clocks agree with exact source observations, budget held;
   repeat historical and Voyage cached-query gates three times without API calls.
4. Verify new recorded replay, old missing-option replay and explicit v16/v17.
5. Run scoped and full tests, platform CI and a diff-scoped high-risk review before
   adoption. Existing model responses may be reused; no new paid calls or live
   6113 writes are authorized by this correction. Final host-generated answer
   quality and the two-week gate remain separately unverified.

## Stop conditions and exclusions

No schema, extraction generation, normalizer, provider, host orchestration, new
runtime dependency or calendar engine changes. Do not promise full event-time
reasoning, facts-only source enrichment or dates for a source that was not
retrieved. Stop adoption if old packet content changes, privacy/provenance is
weakened, replay regresses or latency materially increases without explanation.

High risk: recall provenance, secret isolation, historical replay and token bounds.

## Evidence record

Implementation and copied-data evidence: [source-clock report](../perf/phase42-source-clock.md).
Platform CI remains the adoption gate; final host-answer quality is not claimed.
