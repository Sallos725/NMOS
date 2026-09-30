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
replay runs without it, ADR 0052). Baseline → with keywords (after the review's fixes and the 25 ms keyword slice):

| Run | passed | needing memory | forbidden placed | lexical found a candidate | mean tokens |
|---|---:|---:|---:|---:|---:|
| M0 main, deepseek, vectors on | 26 → 26 | 10 → 10 | 1 → 1 | 18 → 37 | 2,933 → 3,023 |
| M0 main, deepseek, vectors off | 25 → 26 | 8 → 9 | 0 → 0 | 18 → 37 | 2,350 → 2,871 |
| M0 main, gemma, vectors on | 31 → 30 | 15 → 14 | 1 → 1 | 18 → 37 | 2,767 → 2,857 |
| M0 main, gemma, vectors off | 30 → 30 | 13 → 13 | 0 → 0 | 18 → 37 | 2,184 → 2,665 |
| M0 sample 2, deepseek, vectors on | 11 → 11 | 9 → 8 | 2 → 0 | 2 → 15 | 3,816 → 3,902 |
| M0 sample 2, deepseek, vectors off | 11 → 11 | 8 → 8 | 0 → 0 | 2 → 15 | 2,843 → 3,896 |
| M0 sample 2, gemma, vectors on | 8 → 9 | 6 → 6 | 2 → 0 | 2 → 15 | 2,625 → 3,424 |
| M0 sample 2, gemma, vectors off | 5 → 7 | 2 → 4 | 0 → 0 | 2 → 15 | 1,449 → 3,335 |
| synthetic 30, vectors on | 23 → 23 | 2 → 2 | 0 → 0 | 4 → 18 | 1,286 → 1,294 |
| synthetic 30, vectors off | 22 → 22 | 1 → 1 | 0 → 0 | 4 → 19 | 505 → 667 |
| synthetic 60, vectors on | 17 → 16 | 1 → 1 | 2 → 3 | 4 → 20 | 2,036 → 2,082 |
| synthetic 60, vectors off | 18 → 17 | 1 → 1 | 1 → 2 | 4 → 20 | 1,289 → 1,783 |
| synthetic 120, vectors on | 13 → 16 | 0 → 1 | 8 → 4 | 6 → 20 | 2,540 → 2,627 |
| synthetic 120, vectors off | 16 → 16 | 0 → 0 | 3 → 3 | 6 → 20 | 1,782 → 2,509 |
| synthetic 240, vectors on | 13 → 13 | 3 → 2 | 2 → 1 | 9 → 21 | 3,455 → 3,470 |
| synthetic 240, vectors off | 13 → 13 | 2 → 2 | 1 → 1 | 9 → 21 | 2,733 → 3,404 |

- **Lexical recall found a candidate for 131 of 145 queries (90 %)**, from 43 (30 %): the step's 80 % criterion.
  On the synthetic 30 cut the count differs by one between the two runs (18 and 19): a word whose lookup lands near
  its 25 ms slice can be dropped in one run and kept in another.
- Without vectors, cases needing memory +3 over the four M0 runs (main deepseek +1, sample 2 gemma +2); with vectors,
  −1 on two runs (main gemma, sample 2 deepseek), inside "no run worse by more than one case". The phase's +4 is
  measured with `packet-v10` (step 4).
- Forbidden phrases placed fell on M0 (6 → 2 with vectors) and on the synthetic 120 and 240 cuts (8 → 4, 2 → 1); the
  synthetic 60 cut gained one each way.
- Latency at 10,000 messages (`tools/bench_story.py`, budget 4,000, three alternating runs against `main`): retrieve
  p50 122.5 → 136.7 ms (+14.2), p95 421 → 218 ms. Before the slice a two-syllable word could keep the index busy until
  the lexical budget ran out (≈300 ms, twice in 15 requests).
