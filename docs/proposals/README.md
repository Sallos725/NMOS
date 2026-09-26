# NMOS Next-Work Proposals

> Status: proposal only. These documents do not authorize a new phase or change the current scope in
> `AGENTS.md`, `ARCHITECTURE.md`, or `docs/STATUS.md`.

This directory splits the recommended next work into two tracks.

| Track | Proposal | Authorization |
|---|---|---|
| A | [Current-scope stabilization](TRACK-A-STABILIZATION.md) | May proceed as performance, correctness, test, and documentation work, subject to the decision gates inside the proposal |
| B | [Phase 5+ semantic and narrative roadmap](TRACK-B-PHASE-5-PLUS.md) | Requires explicit owner authorization and a normative phase specification before implementation |
| — | [Speech level and forms of address](SPEECH-AND-ADDRESS.md) (2026-09-26) | New extractor generation: requires an owner decision (Q1–Q4) |

The recommended order is:

1. Complete Track A's measured append-path work and evaluation baseline.
2. Use the new measurements and benchmark failures to decide the exact Phase 5 scope.
3. Author and approve the normative Phase 5 document.
4. Start only the first accepted Track B slice.

A1 and A2 of Track A are independently releasable and do not wait for the rest of the track.

Owner decisions for B0 (2026-09-23): Phase 5 = B1 only, B2 next, canon in B4, retention of
superseded generations, recent-window re-extraction — Track B §4, "Owner decisions". B0 done:
`docs/phases/PHASE-5.md` and ADRs 0012–0014, approved 2026-09-23; B1 is Phase 5.

Revised 2026-09-23 after review against the code and `docs/perf/`: A1 preconditions and
no-migration head length, end-to-end latency targets including retrieval, A2 cache scope, A3 query
cost, A4 constraints, A5 evaluation tiers; B1 narrowed (coarse modality, no narrative time,
resolution as its own projection), re-extraction cost, MCP host-evidence precondition, owner
decisions split by stage.

Phase 8 draft review (PR #64): the review handoff
[`PHASE-8-PR64-REVIEW-HANDOFF.md`](PHASE-8-PR64-REVIEW-HANDOFF.md) and the response
[`PHASE-8-PR64-REVIEW-RESPONSE.md`](PHASE-8-PR64-REVIEW-RESPONSE.md). Neither authorizes Phase 8.

The two tracks are complementary. Track A makes the existing beta faster and easier to evaluate;
Track B expands what NMOS can represent.
