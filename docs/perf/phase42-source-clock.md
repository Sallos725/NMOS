# Phase 42 — The clock on a recalled source

2026-10-10; baseline `38ea7e5`; candidate runtime hashes in
`fixtures/eval/phase42-source-clock/source-manifest.json`. The frozen candidate
used by the replay matches the working runtime byte for byte. No provider calls,
live 6113 writes, normalizer, extractor generation or schema changes.

## Observed problem and correction

On the read-only deployment copy, 39 Date/Time observations and six date/time
observations retain literal clocks. There are 248 recorded placed excerpt/quote
lines whose exact revision has a clock that is absent from that line. This is
not 248 wrong answers, distinct requests, or prompts without any date. A short
source counterexample retained its clock already; a long synthetic source
reproduced the omission. Running the missing-clock expectation against the
baseline failed at that expectation.

The v18 supplement is limited to explicit time questions, two already placed
source revisions and spare budget. It preserves the original lines and attaches
literal source-status observations, not a calculated event timestamp. Missing
clocks, conflicting stored aliases, inactive sources, restricted memory modes
and full budgets abstain. Existing parser last-match-wins behavior remains.

## Executed comparisons

| Claim | Entry point and evidence | Result |
|---|---|---|
| Original recall does not regress | `audit.replay`, 338 probes × two snapshots × three rounds; `historical-comparison.json` | 291/314 recall and 21/24 quotes both sides; no new majority failure, forbidden hit or pass/fail instability |
| Copied Voyage requests retain original content | `audit.replay`, 85 eligible requests × two snapshots × three rounds, existing cached query vectors only | All 85 original-ledger majorities equal; four requests receive two source clocks each; 16/255 paired packet comparisons differ, including four single-round original-ledger variations. No budget violation. No answer oracle |
| The supplement reaches real source clocks | Eight authored exact-source lexical probes on copied real records, three rounds, both options | Target selected 24/24; clock attached 21/24 (seven sources), one source lacks spare budget in all rounds; original ledger equal 24/24; exact stored values and token bound checked |
| Exact provenance and isolation | `pytest tests/test_source_time.py` against disposable PostgreSQL | 13 passed: old scene, recorded/legacy replay, v16/v17, strict/narrator, bounds, parser version, disabled/edited sources, other card/chat, ambiguous aliases, secret overlap, XML escaping, two-source cap, tight budget, late-read abstention, actual SQL cancellation/transaction recovery, flashback caveat |

The final real-source probe run had no original-ledger differences. An earlier
run had one independent-gather variation; it is not erased by the later run.
Pure compilation tests pin unchanged source selection and old ledger for the
same gathered input. The Voyage corpus has no hidden rows, so its zero hidden
violations is not evidence of hidden-candidate correctness; the focused tests
exercise the exclusion.

## Review and interpretation

High risk: source provenance, secret isolation, historical replay and token bounds.
The lead reviewed the entire correction diff and direct call sites. A scoped
read-only reviewer found an unhashable list in the new audit reference; this was
confirmed, moved outside the reference and covered by `audit.compare` regression.
The reviewer also proposed rejecting repeated identical parser keys. That change
was not adopted: the existing parser explicitly chooses the last matching key.
Reinterpreting its result here would diverge from current-state behavior. The
flashback test and packet note instead pin that the clock is literal source
context and does not date an embedded event. Multiple stored aliases still
abstain. No external cross-model review was run.

An added test initially expected an edited-away revision's old clock to remain
eligible. That expectation conflicted with the accepted-only lifecycle rule;
it was corrected to assert raw evidence retention and clock exclusion. The
product code did not change to accommodate it.

Private raw packets, traces and database credentials are not committed. Checked-in
summaries contain aggregate scores and hashed source identifiers. The replay and
probe scripts ran from `/tmp/nmos-timecheck`; the test and source manifest make
the bounded contract reproducible without distributing the owner's chat.

Final host-generated answers, inferred event dates, calendar arithmetic, fresh
model extraction and the two-week usage gate were not tested by this correction.
Translation filtering is deferred to AGE-79 by the owner; clean-v3 remains intact.

## Local suite

The full sidecar suite passed: 1,528 tests, no skips, 971.54 seconds, PostgreSQL
required on the disposable 55449 instance. Three additional boundary tests were
then added; the final focused module contains 13 cases. Platform CI runs the
combined 1,531-test tree. `python3 tools/check_release.py v0.4.0` and diff whitespace
checks pass. The plugin runtime is unchanged by Phase 42; its 237 tests and build
are checked by the release CI.

## Latency at 10,000 messages

The in-process retrieve API used 10,000 synthetic long messages, 5,000 source
clocks, eight authored temporal questions and six alternating off/on rounds
(96 requests). Both lanes use v18; only source_clock differs. All 48 enabled
requests actually added clocks. No extraction, vector or provider calls.

After the full suite and focused tests finished, API p50 was 95.221 to 96.907 ms;
p95 101.301 to 103.190 ms (+1.889 ms). The clock stage's p95 was 2.54 ms, maximum
2.81 ms. This excludes network and is neither production latency nor individually
cold requests. A preceding run concurrent with the full suite had API p95
109.708 to 190.395 ms despite clock-stage p95 2.48 ms. Both are retained; the
isolated task run did not reproduce that large tail difference. An initial
broad-query harness did not exercise clock additions and is not evidence for
the enabled route; the final harness asserts that the route added clocks.
