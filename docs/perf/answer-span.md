# Answer-span evaluation — Phase 27 (AGE-31)

2026-10-02, read-only replay measurements on PR #245 head
`fa86d955a85947670e33d9ca8ce7e89608e42e37` (merged as `69704fe`).
**Neither anchor meets the current acceptance criteria.** The main chat gains the required memory answers,
but `focus` increases the forbidden-phrase total and both anchors miss the packet-size bound.
At the time of this measurement Phase 27 was incomplete and `packet-v10` the default; this report changed no product
code or acceptance criterion.

**Decision (the owner, 2026-10-02, after this measurement; Phase 27 step 3):** the tie-break anchor is the question's
keywords (today's anchor met the stop condition on forbidden phrases, 93 → 96; the keywords anchor passed every stop
condition at 87 with the largest gain); Q5's size bound is one-sided — the median packet size per set must not grow by
more than 5 %, and smaller is allowed, since the two rules bound excerpts below `excerpt_chars` by construction and the
case and forbidden criteria caught no loss on the set that shrank (+1 case, forbidden 2 → 0); `packet-v11` is the
default (ADR 0063 amended, `docs/phases/PHASE-27.md` Q1b and Q5). The measurement below is as recorded before that
decision.

## Setup and limits

- Entry point: unmodified `tools/eval_rp.py` → `audit.replay`. The test PostgreSQL at `127.0.0.1:5436` holds existing evaluation copies; every connection is read-only.
- Policies: `packet-v10`, `packet-v11 --anchor focus`, `packet-v11 --anchor keywords`; budget 4,000, keyword route on, three runs of each combination.
- Main and sample 2: the Phase 25 `extract-v15` copies and their existing summary generations. Synthetic cuts: the Phase 18 `extract-v13` copy and existing summaries. Embedding projection: `embed-8ff0a8d435c02d61ed4939dcd7b68ff8`.
- Query embeddings only: local `qwen3-embedding:8b`, via a loopback HTTP bridge into an existing network-disabled container with a read-only model volume. No extraction or answer-model calls. Every vectors-on CLI case reports that vector search ran; no skipped cases.
- CLI replays preserve the options recorded in the old traces, including the pre-Phase-21/24 values of `first_cue`, `history_marks` and `name_variants`. The auxiliary first-cue and Phase 21/24 probes enable all three, and the keyword route, with vectors off.
- The auxiliary probes reuse the existing Phase 24 harness: restored-copy windows narrowed to 20 messages, existing given-name/romanized-name probes, and the 15 synthetic first-cue/identity questions. Product ranking and excerpt functions are not monkeypatched. These are packet-evidence scores, not generated-answer scores or held-out validation.
- Some independent read-only auxiliary probes overlapped the CLI runs. Some counts and sizes varied; all repetitions are reported. This run does not establish the cause of that variability and is not latency evidence.
- Size below means the median of the three per-run median packet token estimates. This statistic is kept distinct from mean tokens and excerpt character length; the size gate was not relaxed for smaller packets.
- Raw cases, names, gold, questions, chat text and per-case results stay outside the repository. Local evidence directory: `/tmp/nmos-age31-results/` (protocol, commands, JSON, stderr, harnesses and numeric case deltas). The source checkout and the owner's workspace were unchanged.

## Main memory-needed questions

| Setting | v10 (runs 1 / 2 / 3) | v11 focus | v11 keywords |
|---|---:|---:|---:|
| Vectors on | 16 / 16 / 16 of 23 | 18 / 18 / 18 | 19 / 19 / 19 |
| Vectors off | 14 / 14 / 14 of 23 | 15 / 15 / 15 | 16 / 16 / 16 |

Both anchors meet the main-chat gain criterion. Q1b prefers today's `focus` when its gain holds,
but the other-set forbidden-phrase stop condition prevents treating that result as acceptance of `focus`.

## All CLI sets

Pass counts are runs 1 / 2 / 3. Forbidden counts are summed across those three runs.

| Set | Cases per run | v10 passes | focus passes | keywords passes | Forbidden: v10 / focus / keywords | Size change: focus / keywords |
|---|---:|---:|---:|---:|---:|---:|
| main-off | 40 | 31 / 31 / 31 | 32 / 32 / 32 | 33 / 33 / 33 | 0 / 0 / 0 | +0.44% / -0.15% |
| main-on | 40 | 31 / 32 / 32 | 34 / 34 / 34 | 35 / 35 / 35 | 4 / 3 / 3 | +1.31% / +0.11% |
| s2-off | 15 | 7 / 7 / 7 | 7 / 7 / 7 | 8 / 8 / 8 | 0 / 0 / 0 | -3.32% / -6.96% |
| s2-on | 15 | 8 / 7 / 8 | 9 / 9 / 9 | 9 / 10 / 9 | 2 / 0 / 0 | -11.78% / -14.88% |
| synth120-off | 22 | 15 / 15 / 15 | 15 / 14 / 15 | 15 / 14 / 15 | 21 / 21 / 21 | +0.00% / -1.95% |
| synth120-on | 22 | 14 / 14 / 14 | 13 / 13 / 13 | 14 / 14 / 14 | 24 / 27 / 24 | +0.02% / -3.36% |
| synth240-off | 23 | 15 / 15 / 15 | 15 / 15 / 15 | 14 / 14 / 14 | 3 / 3 / 3 | +0.03% / -1.94% |
| synth240-on | 23 | 14 / 14 / 14 | 13 / 13 / 13 | 14 / 14 / 14 | 6 / 9 / 9 | -3.98% / -1.98% |
| synth30-off | 23 | 21 / 21 / 21 | 21 / 21 / 21 | 21 / 21 / 21 | 6 / 6 / 6 | +0.00% / -4.63% |
| synth30-on | 23 | 21 / 21 / 21 | 21 / 21 / 21 | 21 / 21 / 21 | 6 / 6 / 6 | +0.28% / -2.36% |
| synth60-off | 22 | 19 / 19 / 19 | 19 / 19 / 19 | 19 / 19 / 19 | 6 / 6 / 6 | +0.00% / -0.30% |
| synth60-on | 22 | 17 / 17 / 17 | 17 / 17 / 17 | 18 / 18 / 18 | 15 / 15 / 9 | +1.34% / -0.45% |

Across the 12 CLI sets, forbidden phrases total **93 → 96 with focus**, and **93 → 87 with keywords**.
With focus, the synthetic 120- and 240-turn vectors-on cuts each place one additional forbidden phrase per run;
the decreases elsewhere do not offset both increases. No other CLI set loses more than one passed case in any run.

On sample 2, vectors on, the size statistic is **3,878 → 3,421 tokens with focus (−11.78%)** and
**3,878 → 3,301 with keywords (−14.88%)**. Keywords also reduces the vectors-off statistic
**3,763 → 3,501 (−6.96%)**. All exceed the ±5% bound in the direction of smaller packets.

## Auxiliary probes

Each combination ran three times; pass counts below stayed the same under both anchors.

| Probe group | Result in each repetition |
|---|---:|
| Synthetic first-cue/identity (15 questions) | 8/15; 1 forbidden phrase |
| Phase 21 restored copies: first values | 5/5 and 7/8 |
| Phase 21 restored copies: identity | 7/7 and 4/4 |
| Phase 24 romanized-name probes | 10/24 and 2/6 |
| Phase 24 sample 2 | 12/17 overall, 8/13 needing memory; no forbidden phrase |
| Phase 24 sample 2 name probes | 3 full-name and 3 given-name probes held |

The auxiliary harness records size medians for probe groups, not each subcategory separately.
For example, keywords reduces the restored-copy group median from 3,269 to 3,036 tokens (−7.13%)
and the Phase 24 sample-2 group from 2,682 to 2,483 (−7.42%). These group statistics do not establish
compliance with a per-subset size bound. The CLI sample-2 failures alone already reject that gate.

## Acceptance and next boundary

| Claim | Executed evidence | Verdict |
|---|---|---|
| Main vectors-on memory gain ≥2, three runs; no loss vectors off | CLI replay counts above; main-gain check exits 0 | verified |
| No other CLI set loses more than one case per run | All 12 sets, three runs per policy/anchor | verified within CLI scope |
| Forbidden total does not increase | focus 93 → 96, keywords 93 → 87 across CLI sets | defect for focus; verified within CLI scope for keywords |
| Median size within ±5% | sample-2 deltas above | defect for both anchors |
| Scorer, vector accounting and pure v11 text checks | Six selected existing pytest cases, 6 passed | verified within selected-test scope |
| Full suite, remaining API deterministic cases, historical v10 replay identity against the base | Not run in this measurement | not run |
| 10,000-message latency and live three-bench NMOS lane | Not run after the acceptance failure | not run |

Gate controls: the main-gain check reads the saved measurements and exits 0. Its negative control changes only
an in-memory summary to remove the gain; it exits 3 for the intended “gain below +2” failure. Original measurements
are preserved; the control is not benchmark evidence. The final aggregate checker exits 1 for the observed
size/forbidden failures, with all 12 CLI sets complete.

Under PHASE-27's stop conditions, the owner must decide the next direction before implementation resumes:
address focus's forbidden increase, or consider keywords and explicitly decide whether smaller packets may be
exempted from the size criterion. This document chooses neither, does not amend Q1b or Q6, and does not switch
an anchor or the default. After that decision, the remaining checks and live-host evidence are still required.

## Request-path latency (step 3, Phase 27's last criterion)

`tools/bench_story.py 10000` with `BENCH_BUDGET=4000`, the default questions and no embedder (the shape of the other
perf pages' latency rows), in a four-core container pinned to two cores, three rounds a side run in turn
(`NMOS_PACKET_POLICY=packet-v10`, then the default `packet-v11`). Each run is 15 requests on the 10,000-message chat.

| Round | `packet-v10` p50 / p95 (ms) | `packet-v11` p50 / p95 (ms) |
|---|---:|---:|
| 1 | 208.0 / 377.8 | 209.5 / 302.7 |
| 2 | 223.0 / 331.9 | 211.5 / 288.2 |
| 3 | 218.9 / 292.6 | 222.6 / 359.9 |
| median | **218.9** / 331.9 | **211.5** / 302.7 |

The rounds overlap (208–223 against 209–223 ms p50), so the difference between the medians is noise, as expected: the
two rules are pure functions on text the request has already read. Not a measurement of the owner's chats, whose
questions carry the cues and vectors these rules act on; the live bench is.

## Reproduce the CLI comparison

Use the evaluation copies, case directories and generation keys from the local protocol; the example leaves
private locations and database connection details to the owner. The endpoint must be the local evaluation embedder.

```bash
cd apps/sidecar
uv sync --frozen
uv run python ../../tools/eval_rp.py <cases> --db <evaluation-copy> \
  --extractor <extractor-key> --summarizer <summary-key> \
  --projection embed-8ff0a8d435c02d61ed4939dcd7b68ff8 --embed-url <local-evaluation-endpoint> \
  --policy packet-v10 --budget 4000 --keywords on --json
# Repeat with --policy packet-v11 --anchor focus and --anchor keywords.
# Run each combination three times; add --no-vectors for the lexical comparisons.
```

For the selected verification, run:

```bash
uv run pytest -q \
  tests/test_eval_rp.py::test_a_case_passes_on_every_gold_phrase_in_any_wording_and_no_forbidden_one \
  tests/test_eval_rp.py::test_each_case_says_whether_vectors_ran_and_a_named_projection_is_searched \
  tests/test_eval_rp.py::test_excerpt_lengths_count_characters_of_each_placed_excerpt \
  tests/test_packet_v11.py::test_the_story_splits_where_the_cases_expect \
  tests/test_packet_v11.py::test_the_cues \
  tests/test_packet_v11.py::test_the_cue_growth_stays_within_its_length_and_cuts_a_long_sentence
```
