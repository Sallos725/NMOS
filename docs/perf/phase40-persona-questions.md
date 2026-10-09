# Phase 40 — Persona questions, measured 2026-10-09

AGE-18 / K32, [PHASE-40](../phases/PHASE-40.md), [ADR 0072](../adr/0072-persona-questions.md).
The owner brought this correction back into 0.4.0. It is implemented behind opt-in
`packet-v18`; the repository default remains v16 and the existing 6113 deployment
remains v17. This report does not mark the phase or release complete.

## Cause and correction

ADR 0023 excludes persona names from ordinary mention scoring. The original K32
questions also use a given name absent from the stored aliases. The company answer
is a character claim; the first-gate answer is a minor event. Under current options,
three events mentioned by the previous reply filled the event quota before that
asked event could enter, even with unused fact slots.

The explicit-question route resolves only an unambiguous persona subject, including
an unshared Korean given name. It ranks at most two matching facts/claims at mention
1.5, between an ordinary current-query mention (2) and previous-reply mention (1).
The shared cap, event quota, history/minor-event rules and token budget remain.
Claims keep their speaker and provenance. Narration, indirect questions and uncertain
subjects do not gain the bonus. No stored identity, prompt or generation changes.

## Source and method

Base: `c1702661d00bb93e5f7aab5b03a5618d36d0dc2d`, PR #291. Frozen final candidate:
`f41c1f27e60ac0cb2f77fe80bfdc57c8cddf6164d288c93155f2ca4bf621d1a3`
(SHA-256 manifest of 53 runtime/replay source files, checked byte-for-byte against
the working tree). [Public aggregate](phase40-persona-questions.json) contains no
private messages, gold answers or trace UUIDs. Local evidence is under
`/tmp/nmos-age18`; source snapshots, manifests and initial/intermediate results are
retained there. Private original probes and copied databases are not committed.

Use `audit.replay` with the exact baseline/candidate source, copied databases and
existing embedding caches. Compare each case by majority over three independent
runs. The original K32 queries, gold, database head and prompt window are unchanged.
The historical-options run preserves all trace flags. A separate diagnostic enables
the current options explicitly: `first_cue`, `lexical_keywords`, `history_marks`,
`name_variants`, and `excerpt_anchor=keywords`. It is not historical trace reproduction.
K32 uses its original extractor/summarizer with vectors off and a 4,000-token budget.

No new embedding or generative calls; no writes to the original database. The 65
previously authorized Voyage query vectors were reused, not regenerated. Final
comparisons total 2,487 replays, plus 255 prior Voyage baseline replays reused.
Exploratory candidates and interrupted runs are excluded from that count.

## Results

| Set | v17 rounds | v18 rounds | Per-case majority |
|---|---|---|---|
| Standard Recall, 314 probes | 289 / 289 / 289 | 289 / 289 / 289 | unchanged, 289/314 |
| Exact quote, 24 probes | 21 / 21 / 21 | 21 / 21 / 20 | unchanged, 21/24 |
| Original K32, 17 probes, historical flags | 9 / 9 / 9 | 10 / 10 / 10 | 9→10 |
| Same K32, current-options diagnostic | 11 / 12 / 12 | 14 / 14 / 14 | 12→14 |

No newly failing case by majority or new forbidden case in any comparison. The
standard benchmark's existing 14 forbidden-phrase hits per round remain; this is
not a claim of zero stale content throughout the existing product. One candidate
quote round fell to 20 and is retained rather than replaced by a favorable rerun.

Both original K32 target questions (company and first gate) pass 3/3 with current
options. With historical `first_cue=False`, the company question improves 3/3 but
the first gate remains failed. The old trace does not silently acquire a new flag.
The remaining three current-options cases and broader standard failures are not
claimed fixed by this bounded correction.

Voyage: 85 saved requests × 3 candidate runs = 255 hybrid replays; hidden-contract
violations 0, over-budget packets 0, maximum 3,979/4,000 tokens. Per-trace majority
packets match the prior fixed-v17 baseline. These requests have no independently
annotated semantic gold; this establishes compatibility, not answer accuracy.

## Synthetic latency

Existing `tools/bench_story.py`, 10,000 messages, 5,000 facts, 624 scenes, summaries
on, 4,000-token budget, no provider. Each run measures 15 requests across five
question types; two types explicitly ask about the synthetic persona `인물0`.
The sync manifest supplies that persona name. Policy order is v17/v18, then v18/v17,
using fresh throwaway databases. Replay and pytest were not running alongside it.

| Round | v17 p50 / p95 (ms) | v18 p50 / p95 (ms) |
|---|---|---|
| 1 | 128.01 / 223.16 | 133.84 / 224.93 |
| 2 | 133.90 / 247.75 | 133.94 / 241.28 |

The paired p95 differences (+1.76 ms, −6.47 ms) are within this small sample's
variation. No speedup or hard production latency guarantee is claimed. This is
synthetic timing, not live host evidence. Parallel replay durations are not used
as latency measurements. The local wrapper is `/tmp/nmos-age18/bench_persona.py`;
to reproduce against a disposable test PostgreSQL, set `NMOS_TEST_ADMIN_URL`, use
the existing benchmark with `BENCH_BUDGET=4000`, override its first two `QUERIES`
to `인물0은 지금 어디 있어?` and `인물0은 예전에 어디 살았어?`, and include
`persona_name=인물0` in each sync manifest. All other benchmark options are defaults.

## Checks and review

- Final focused suite: 157 passed (persona questions, v18 integration, v12/v14/v16,
  prior release recall fixes, hidden ledger/audit and documentation consistency).
- New persona-question unit file: 43 passed, including the event-quota regression
  reproduced before the ranking correction and current-query precedence.
- API/DB regressions cover sync → attributed claim/fact → trace → replay, and source
  replacement making the old assertion ineligible. These inputs are synthetic.
- Full sidecar/plugin/native results must be read from PR #291's checks for its
  final commit. The earlier candidate's 1,446 local passes are not final-r5 evidence.
- Lead reviewed the complete change against `c170266` and direct selection/label
  dependencies. **High risk:** retrieval selection and isolation, provenance,
  stale-state exclusion and bounded budgets. Two child agents divided implementation
  and copied-data replay; neither performed an external cross-model review.

## Remaining acceptance

No fresh host turn or generative live gate was run for v18. After an owner-approved
test deployment/default choice, the reduced live check must exercise the company
and first-gate questions using the chat's actual persona spelling and fresh
extraction. Inspect the resulting packet, source turn, attributed claim and answer;
include ordinary third-person narration and another character's question as controls.
Use the corrected pacing from AGENTS section 7.6. New paid calls require their own
estimate and authorization. A two-week use period has not been completed here.

Unsupported grammar, ambiguous names, missing extraction and tight budgets remain
limitations. Merge, default promotion, 6113 deployment, release versioning and tag
publication are not performed by this correction report.
