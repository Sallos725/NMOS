# Budget pressure: the notice and `packet-v4` — evidence

Date: 2026-09-27. Phase 10, owner request after step 5 (ADR 0036). No model calls: packets are compiled by the
sidecar's own functions on the restored copy of the owner's database (read-only), for the 9 recorded requests of
the owner's longest chat (15 memory lines offered each), with each request's own options, as in
`docs/perf/memory-mode.md`. Chat text is not quoted.

## 1. How much memory fits

Memory lines (state, promises, facts, claims) placed of those offered, and those left out for the budget. The
facts are read with `extract-v12` (what production serves now); its knowledge marks make lines longer than the
`extract-v10` facts the requests recorded (`docs/perf/memory-mode.md` §3: 60% at 600, 87% at 800).

| Budget | `packet-v3` placed | left out | `packet-v4` placed | left out | restatements |
|---:|---:|---:|---:|---:|---:|
| 600 | 73 / 135 (54%) | 62 | 73 / 129 (57%) | 56 | 6 |
| 800 | 100 / 135 (74%) | 35 | 100 / 129 (78%) | 29 | 6 |
| 1000 | 128 / 135 (95%) | 7 | 124 / 129 (96%) | 5 | 6 |
| 1100 | all | 0 | all | 0 | 6 |

The budget that holds everything (`fits_at`, `packet-v4` at 800): 1000 for 4 requests, 1100 for 5. With the
`extract-v10` facts: nothing left out for 2, 900 for 6, 1000 for 1.

## 2. What `packet-v4` leaves out

The same head and content twice, or a claim restating a fact of the same head: 6 of 135 offered lines with
`extract-v12` (a character's claim beside the narration's fact of the same feeling, twice per request in some),
11 of 135 with `extract-v10`. Lines that only share a value ("A feels toward B: 좋아함" and "B feels toward A:
좋아함") say different things and stay. Counting lines by their value alone gave 24 repeats over the 9
requests, most of them such pairs; that was the first estimate of "about 3 a request".

## 3. Cost on the request path

Finding `fits_at` compiles the same lines again, bisecting between the budget and 2000: 1.16 ms p50, 2.33 ms
at most over the 9 requests (`packet-v4`, at 600 and 800). It runs only when something was left out.

## 4. Real host (isolated PocketRisu v1.12.0)

The plugin built from this branch, with the memory budget set to 200 on a stub chat: the next request left 2 of
3 memory lines out, the trace recorded `memory_cut` 2 and `fits_at` 400 (the search took 1.26 ms), and the
Status tab showed "기억 2줄이 자리가 없어 빠졌습니다" with the suggested 400 and the reminder to lower PocketRisu's
max context by 200. Its button set the plugin's budget to 400; after a refresh the notice was gone.

## Limits

The suggestion comes from one request. The line format itself (tags and knowledge marks take about half of each
line, the Note a fifth of the packet; `docs/perf/memory-mode.md` §3) is unchanged: a compact format waits for the
response-model evaluation.
