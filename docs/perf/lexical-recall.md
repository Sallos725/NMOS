# Lexical recall and excerpt length (Phase 18)

`docs/phases/PHASE-18.md`. Numbers only: the cases stay outside the repository (the owner's chats are private; the
synthetic set is not published yet, Q5).

## Setup

- **M0 v2** (Q5): the owner's two M0 chats (main 40 cases, sample 2 15) with the gold re-annotated on 2026-09-30 from
  the raw chat only, several wordings per phrase. Copies of the evaluation databases; extractions `deepseek-v4.1-flash`
  and `gemma4:31b-cloud` (the Phase 15 extractions), each with its own summaries.
- **Synthetic set**: a 240-turn Korean role-play written for benchmarking (≈497,000 characters; 167 ledger facts, 79 of
  them replaced during the story), cut at turns 30, 60, 120 and 240, 25 cases per cut derived from the fact ledger;
  the secret cases (whose right answer is "does not know") are left out here, 90 cases remain. Recorded with a 32,000-
  token host context; extraction `deepseek-v4.1-flash`.
- Replays with `tools/eval_rp.py` (read-only), packet policy and budget as given, vectors on and off (`--no-vectors`,
  labelled in the output). **Query embeddings come from a separate evaluation Ollama** (CPU), never production's:
  its vectors of the same model are within cosine 0.995–0.998 of production's, so a baseline and a change are always
  measured with the same embedder.
- New per case (step 2): whether lexical recall returned any candidate, and the length of each excerpt placed.

## Baseline: `packet-v9` at 4,000 (2026-09-30)

| Run | passed | needing memory | forbidden placed | lexical found a candidate | excerpt median (chars) | mean tokens |
|---|---:|---:|---:|---:|---:|---:|
| M0 main, deepseek, vectors on | 26/40 | 10/23 | 1 | 18/40 | 69 | 2,933 |
| M0 main, deepseek, vectors off | 25/40 | 8/23 | 0 | 18/40 | 78.5 | 2,350 |
| M0 main, gemma, vectors on | 31/40 | 15/23 | 1 | 18/40 | 69 | 2,767 |
| M0 main, gemma, vectors off | 30/40 | 13/23 | 0 | 18/40 | 78.5 | 2,184 |
| M0 sample 2, deepseek, vectors on | 11/15 | 9/12 | 2 | 2/15 | 99 | 3,816 |
| M0 sample 2, deepseek, vectors off | 11/15 | 8/12 | 0 | 2/15 | 581 | 2,843 |
| M0 sample 2, gemma, vectors on | 8/15 | 6/12 | 2 | 2/15 | 101 | 2,625 |
| M0 sample 2, gemma, vectors off | 5/15 | 2/12 | 0 | 2/15 | 595 | 1,449 |
| synthetic 30, vectors on | 23/23 | 2/2 | 0 | 4/23 | 88 | 1,286 |
| synthetic 30, vectors off | 22/23 | 1/2 | 0 | 4/23 | 85 | 505 |
| synthetic 60, vectors on | 17/22 | 1/4 | 2 | 4/22 | 82 | 2,036 |
| synthetic 60, vectors off | 18/22 | 1/4 | 1 | 4/22 | 85.5 | 1,289 |
| synthetic 120, vectors on | 13/22 | 0/5 | 8 | 6/22 | 79 | 2,540 |
| synthetic 120, vectors off | 16/22 | 0/5 | 3 | 6/22 | 83 | 1,782 |
| synthetic 240, vectors on | 13/23 | 3/11 | 2 | 9/23 | 78 | 3,455 |
| synthetic 240, vectors off | 13/23 | 2/11 | 1 | 9/23 | 90 | 2,733 |

- **Lexical recall found a candidate for 43 of 145 queries (30 %)**, the same with vectors on or off (it runs
  either way): 45 % on the main chat, 13 % on sample 2, 17–39 % on the synthetic cuts. The criterion is 80 %.
- **Excerpts stay one or two short sentences** (median 69–101 characters with vectors) although `excerpt_chars` is
  960 at 4,000. Sample 2 without vectors places few excerpts, a couple of them long unbroken passages, hence 581–595.
- Vectors raise cases needing memory on M0 (+2 on each main run, +1 and +4 on sample 2) and bring stale lines on the
  synthetic 120 cut (8 forbidden placed against 3 without).

Reproduce: `tools/eval_rp.py <cases dir> --db <copy> --extractor <key> --summarizer <key> --policy packet-v9
--budget 4000 --projection <key> --embed-url <evaluation Ollama> [--no-vectors] --json`.

## Step 3: keyword lexical recall (`packet-v9` at 4,000, keywords on) (2026-09-30)

The same runs with the keyword route forced on (`--keywords on`; these requests were recorded before it, so a plain
replay runs without it, ADR 0052). Baseline → with keywords (after the reviews' fixes, the 25 ms keyword slice and one deadline for the route):

| Run | passed | needing memory | forbidden placed | lexical found a candidate | mean tokens |
|---|---:|---:|---:|---:|---:|
| M0 main, deepseek, vectors on | 26 → 26 | 10 → 10 | 1 → 1 | 18 → 37 | 2,933 → 3,023 |
| M0 main, deepseek, vectors off | 25 → 26 | 8 → 9 | 0 → 0 | 18 → 37 | 2,350 → 2,871 |
| M0 main, gemma, vectors on | 31 → 30 | 15 → 14 | 1 → 1 | 18 → 37 | 2,767 → 2,857 |
| M0 main, gemma, vectors off | 30 → 30 | 13 → 13 | 0 → 0 | 18 → 37 | 2,184 → 2,664 |
| M0 sample 2, deepseek, vectors on | 11 → 11 | 9 → 8 | 2 → 0 | 2 → 15 | 3,816 → 3,909 |
| M0 sample 2, deepseek, vectors off | 11 → 11 | 8 → 8 | 0 → 0 | 2 → 15 | 2,843 → 3,898 |
| M0 sample 2, gemma, vectors on | 8 → 9 | 6 → 6 | 2 → 0 | 2 → 15 | 2,625 → 3,421 |
| M0 sample 2, gemma, vectors off | 5 → 7 | 2 → 4 | 0 → 0 | 2 → 15 | 1,449 → 3,335 |
| synthetic 30, vectors on | 23 → 23 | 2 → 2 | 0 → 0 | 4 → 18 | 1,286 → 1,294 |
| synthetic 30, vectors off | 22 → 22 | 1 → 1 | 0 → 0 | 4 → 19 | 505 → 667 |
| synthetic 60, vectors on | 17 → 16 | 1 → 1 | 2 → 3 | 4 → 20 | 2,036 → 2,047 |
| synthetic 60, vectors off | 18 → 17 | 1 → 1 | 1 → 2 | 4 → 20 | 1,289 → 1,783 |
| synthetic 120, vectors on | 13 → 16 | 0 → 1 | 8 → 4 | 6 → 20 | 2,540 → 2,627 |
| synthetic 120, vectors off | 16 → 17 | 0 → 1 | 3 → 3 | 6 → 20 | 1,782 → 2,507 |
| synthetic 240, vectors on | 13 → 13 | 3 → 2 | 2 → 1 | 9 → 21 | 3,455 → 3,470 |
| synthetic 240, vectors off | 13 → 13 | 2 → 2 | 1 → 1 | 9 → 21 | 2,733 → 3,404 |

- **Lexical recall found a candidate for 131 of 145 queries (90 %)**, from 43 (30 %): the step's 80 % criterion.
  On the synthetic 30 cut the count differs by one between the two runs (18 and 19): a word whose lookup lands near
  its 25 ms slice can be dropped in one run and kept in another.
- Without vectors, cases needing memory +3 over the four M0 runs (main deepseek +1, sample 2 gemma +2); with vectors,
  −1 on two runs (main gemma, sample 2 deepseek), inside "no run worse by more than one case". The phase's +4 is
  measured with `packet-v10` (step 4).
- Forbidden phrases placed fell on M0 (6 → 2 with vectors) and on the synthetic 120 and 240 cuts (8 → 4, 2 → 1); the
  synthetic 60 cut gained one each way. Passed rose on the synthetic 120 cut (13 → 16 with vectors, 16 → 17 without).
- Latency at 10,000 messages (`tools/bench_story.py`, budget 4,000, three alternating runs against `main`): retrieve
  p50 119.9 → 129.9 ms (+10.0), p95 422.7 → 219.3 ms. The p95 is not this change's doing: in every run on `main`
  one of the 15 requests (a repeated question) hit the whole-message route's 300 ms timeout, and in no run of this
  branch did it; the whole-message route is unchanged, and why it did not time out here is not known yet (a cache or
  index warmed by the keyword lookups is a guess). The keyword route itself adds 5–60 ms to a request (per request,
  measured in `gather`: ≈5–7 ms when its keywords are rare, 29–60 ms when some are too common).


## Step 4: `packet-v10`, excerpts that grow (2026-09-30)

All runs at 4,000 with the keyword route on except the first column. "Whole length" grew each excerpt to `excerpt_chars`
(960 at 4,000); `packet-v10` as merged caps the growth at four sentences (owner, 2026-09-30, ADR 0053).

| Runs (passed / needing memory / forbidden placed) | `packet-v9` | v9 + keywords | whole length | **`packet-v10` (≤ 4 sentences)** |
|---|---|---|---|---|
| M0 v2, four runs, vectors off | 71 / 31 / 0 | 74 / 34 / 0 | 79 / 41 / 2 | 77 / 37 / 0 |
| M0 v2, four runs, vectors on | 76 / 40 / 6 | 76 / 38 / 2 | 80 / 43 / 4 | 80 / 42 / 2 |
| synthetic, four cuts, vectors off | 69 / 4 / 5 | 69 / 5 / 6 | 69 / 11 / 13 | 70 / 10 / 12 |
| synthetic, four cuts, vectors on | 66 / 6 / 12 | 68 / 6 / 8 | 64 / 14 / 29 | 66 / 10 / 17 |
| excerpt median, M0 main (gemma, vectors on) | 69.0 | 75.0 | 60.0 | 98.0 |

- Growing to the whole length answered the most (vectors off, M0: 41 needing memory against 31 for `packet-v9`) but
  placed replaced values much more often on the synthetic chat, whose facts change often (29 with vectors against 12).
  With ten excerpts at 4,000 the fitter fell back to the one-sentence form for most of them (88 of 158 placed on 20 M0
  cases), so the median excerpt even shrank. Keeping five excerpts changed little (tried; 31 forbidden with vectors).
- The four-sentence cap keeps most of the gain on M0 (42 of whole length's 43 with vectors) and cuts the replaced values
  on the synthetic chat from 29 to 17 (`packet-v9`: 12, keywords alone: 8).
- Against the criteria (`packet-v10` with keywords vs `packet-v9`, 4,000): without vectors +6 cases needing memory over
  the four M0 runs (≥ +4); with vectors +3, +1, −1, −1 (no run worse than one); forbidden placed on M0 6 → 2 (≤ +2);
  median excerpt 69 → 98 characters (1.42×, restated criterion ≥ 1.3×); lexical recall found a candidate for 131 of 145
  queries (≥ 80 %); one-off details on the synthetic chat 5 → 9 (≥ +3); one category worse by more than one case,
  "count" at the 60 cut (3 → 1), accepted by the owner.
- Latency at 10,000 messages (budget 4,000, three alternating runs against `main`): p50 123.2 → 135.3 ms (+12.1). In
  one of the three `main` runs the whole-message timeout did not occur (p95 161.6 ms), so it is intermittent.
- Two runs of the same code differ in a few cases (e.g. lexical found 37 or 36 on one run): a keyword whose lookup
  ends near its 25 ms slice is kept in one run and dropped in another.


## Step 5: the owner's recorded requests, latency, real host (2026-09-30)

### Recorded requests replayed (read-only, counts only)

The owner's production requests with a ledger (45, 2026-09-23 to 09-30; 11 could not replay because their chat has
changed since) replayed read-only against the production database with `main`'s code: `packet-v9` without the keyword
route (A) against `packet-v10` with it (B), each at its recorded budget (≈600–2,000). Nothing was sent to a model:
first without vectors, as 70 % of those requests ran (K34), then with the query embedded by a separate CPU instance of
the same embedding model (only 7 requests were of the current projection; the others replayed lexical only). Only
counts were kept.

| 34 requests | A: `packet-v9`, no keywords | B: `packet-v10` + keywords |
|---|---|---|
| excerpts placed, vectors off | 0 | 24 (in 10 requests; median 140 characters) |
| excerpts placed, vectors where available | 31 (median 95) | 43 (median 115) |
| facts / threads / claims placed | 138 / 9 / 4 | 132 / 9 / 4 |
| mean tokens (vectors off) | 321 | 410 |
| placed lines only B has | — | 24 excerpts, 1 fact (vectors off) |
| placed lines only A has | 7 facts (the budget went to excerpts) | — |
| keyword route | — | on 29, every keyword too broad 5; 2 keyword-only excerpts left out for a secret |

- No line only B places is a secret (a Private line) or a thread: the thread lines are the same nine, and a closed
  thread is never offered. No placed excerpt of either side repeats a secret kept from someone (the summaries'
  test, ADR 0042, with the scene's cast). No packet went past its budget.
- Without vectors `packet-v9` placed no excerpt at all on these requests: the whole-message route found nothing above
  its bar. The keyword route gave excerpts to 10 of the 34.
- Replayed with their own policy and vectors, 5 of the 7 requests of the current projection reproduced exactly; one
  differed in one excerpt (the CPU instance's vectors differ slightly from the GPU's, cosine 0.995–0.998), and one
  lacked one canon fact line. The production build's code (before this phase) leaves out the same line, so it is not
  this phase's doing; it is recorded for a separate look.

### Latency

`tools/bench_story.py` at 10,000 messages, budget 4,000, three runs alternating with `packet-v9` (the code before
step 3), retrieve p50 / p95 in ms:

| Questions | `packet-v9` | `packet-v10` + keywords |
|---|---|---|
| the benchmark's eight and one of four common keywords (「창가 등대 바람 오늘 기억나?」, each in every reply) | 122.5, 126.7, 123.7 / 419–451 | 133.8, 135.6, 147.5 / 451–457 |
| that question alone, every request | 418.1, 421.3, 425.1 / 441–452 | 454.9, 449.0, 450.5 / 482–485 |

- Over the benchmark's questions the median run is +11.9 ms (criterion +15). Asked alone every time, the question
  adds 29 ms: one of its words is in every reply and uses its whole 25 ms slice before it is dropped; the other three
  take ≈2 ms each. `packet-v9` already takes 421 ms there, the whole-message route running to its 300 ms timeout. A
  10 ms slice would bring it to +16 ms and drop more words of middling frequency in long messages; the owner accepted
  the criterion as measured over the benchmark's questions (2026-09-30).
- Profiling that question showed K40: three of its four words matched no message at 0.8, since each stands with a
  particle in the text ("창가에", "바람이", "오늘은").

### Real host

The isolated PocketRisu v1.13.0 with stub models (chat, extraction, and an embedder slower than the 150 ms timeout
for queries), `main`'s plugin build and sidecar: a chat whose second message says "앵무새, 그 녀석 이름은 …" followed by
88 messages of other talk, then the question "처음 만났을 때 다들 그 늙은 앵무새를 뭐라고 불렀는지 기억나?". The
request took 252 ms (retrieve 82 ms); the trace says `packet-v10`, `keyword_mode` on; the prompt the stub received held
that message as a four-sentence excerpt ending in "…", and the progress display said "✓ 기억 주입 (551자)".
