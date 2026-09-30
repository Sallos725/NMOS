# Phase 18 — Recall by the words that matter

> **Status: complete 2026-09-30** (approved 2026-09-30 by the owner, after Phase 17). Not released.
> Amended 2026-09-30 after the spec PR's review: five boundary cases made explicit (Q1–Q4, criteria); the intent is
> unchanged. Amended again 2026-09-30 by the owner after step 4's measurements: excerpts grow to at most four
> sentences (Q3), and the excerpt-length criterion is restated (below). At step 5 the owner accepted the latency
> criterion as measured over the benchmark's questions with the four-common-keyword question among them (below).

## Questions and proposed answers

Each answer in bold was NMOS's proposal; the owner approved the document with them (2026-09-30).

| # | Question | Proposed answer | Alternatives |
|---|---|---|---|
| Q0 | When? | **Right after Phase 17**, before any Stage 7 work: it is small, measured, and it changes every later measurement. 70 % of the owner's production recalls went without vectors (K34), so lexical recall is what most requests get. | After Stage 7; fold into a later stage. |
| Q1 | What is a keyword? | **Deterministic, no new dependency.** The cleaned user message split on spaces and punctuation; a fixed list of Korean particles and question endings stripped from each word's end (은/는/이/가/을/를/의/에/에서/에게/한테/랑/과/와/도/만/로/으로, -야/-지/-까/-더라 …); a short stop list (뭐, 왜, 어디, 누구, 언제, 지금, 요즘 …); keep words of 2+ Hangul syllables or 3+ Latin letters. A word whose stripped stem would fall under that length keeps
its original form (민지, 사과), and where an ending may belong to a name both the word and its stem are kept. At most
four keywords per request, longest first. No morphological analyzer (that would be a new runtime dependency, AGENTS.md §8). | A morphological analyzer; the extractor's entity names only. |
| Q2 | How does a keyword recall a message? | **A second lexical route beside today's.** Each keyword matches a message when `word_similarity(keyword, clean_content) ≥ 0.8` on the normalized projection (D11, D21; the trigram index still serves it). A keyword matching more than 200 head messages is too broad and is dropped, as D15 does for a whole query. A message's keyword score is the sum of its keywords' rarity weights (`log(N / matches)`). Today's whole-message route stays unchanged; both lists join the vector list in the same reciprocal-rank fusion, and a keyword hit is its own admission signal there (today `fuse` admits only a whole-message score above the threshold or a vector above its minimum, which would drop a keyword-only hit with vectors off). The keyword route shares one time budget (`NMOS_LEXICAL_TIMEOUT_MS`) across its keywords and abstains, recorded, when it runs out. | Replace the whole-message route; keywords only when the whole message finds nothing. |
| Q3 | How long is an excerpt? | **As long as its budget says.** Today an excerpt is the two consecutive sentences that share most trigrams with the query, cut at `excerpt_chars`: measured, excerpts are 69–80 characters (median) at every budget from 2,000 to 16,000 and never longer than 175, so packet-v9's longer excerpts (ADR 0049) never happen. Proposed: start from the best sentence (keyword hits first, then trigrams) and add neighbouring sentences, alternating after and before, until `excerpt_chars` — **at most four sentences (owner, 2026-09-30: growing to the whole length placed replaced values much more often, `docs/perf/lexical-recall.md` "Step 4")**. A best sentence longer than `excerpt_chars` is cut there with "…", as today; under budget pressure the packet fitter still shortens or omits excerpts as it does now. | Keep two sentences; a fixed three. |
| Q4 | Versioning? | **`packet-v10`** (the excerpt rule) as the new default, and the keyword route as a recorded recall option (`lexical_keywords`). Recorded requests replay as they were (ADR 0027): `packet-v9` and the whole-message route alone stay available. A trace that did not record `lexical_keywords` replays with it off (a replay overlays recorded options on today's defaults, so a missing value must not mean the new default). | Change `packet-v9` in place. |
| Q5 | Measured on what? | **The owner's M0 chats with the blind re-annotated case set (2026-09-30: gold written from the raw chat only, several wordings per phrase) as M0 v2, and a synthetic 240-turn Korean role-play written for benchmarking, with 100 cases derived from its fact ledger.** Both stay outside the repository for now (the owner's chats are private; publishing the synthetic set is proposal P3's decision). Runs with vectors on and off, since production mostly runs without them. | M0 v1 only. |
| Q6 | Release? | **None until the owner asks**, as for Phases 10–17. | A tag after merge. |

## Goal

A question that names something the story said finds the message that says it, with or without vectors, and the
packet shows enough of that message to answer.

## Evidence behind the scope

Measured 2026-09-29/30 outside the repository (numbers only; step 2 records the baseline in `docs/perf/`).

- **The whole-message lexical route rarely fires on natural questions.** A question's `word_similarity` against the
  message that answers it is diluted by the question's other words. Share of evaluation queries for which lexical
  recall returned any candidate: M0 main 20 of 40, M0 sample 2 2 of 15, synthetic 4 and 5 of 25 (two cuts).
  Example (synthetic): a question naming a pet scored 0.32 against the answering message, under the 0.4 bar; each of
  its two keywords alone scored 1.0 on exactly that message and on no other above 0.8.
- **Without vectors, recall loses cases.** M0 v2 at 2,000 (`packet-v8`), passed of 40 / 15: main deepseek 27 with
  vectors, 25 without; main gemma 29 and 28; sample 2 deepseek 10 and 7; sample 2 gemma 8 and 4. Production ran
  70 % of recalls without vectors (K34).
- **Excerpts stay one or two short sentences.** With `packet-v9` on M0 main (20 cases, gemma extraction), budgets
  2,000 / 4,000 / 8,000 placed 86 / 200 / 400 excerpts of median length 69 characters each time (90th percentile
  95–98, maximum 150), while `excerpt_chars` rose from 480 to 1,920: the two-sentence window, not the cap, sets the
  length. The synthetic chat gave the same picture (median 76–80, maximum 175). In a synthetic case the
  right message was recalled, but its excerpt was the sentence naming a pet, and the name stood in the next sentence.
- **What helped instead.** More excerpts and facts (packet-v9) raised M0 cases needing memory by +6; room given to
  longer raw passages is where the remaining one-off details are (a long-context baseline answered them).

## In scope (Phase 18)

1. **This document**, approved; STATUS and AGENTS.md §2 name Phase 18 current.
2. **Evaluation tooling and baseline.** `tools/eval_rp.py` reports per case whether lexical recall found a candidate
   and the excerpt lengths; runs with vectors off are allowed when asked for explicitly (and labelled). The
   `packet-v9` baseline on M0 v2 and the synthetic set, vectors on and off.
3. **Keyword lexical recall (Q1, Q2; ADR 0052 amending ADR 0004 / D15).** Keyword extraction as a pure function with
   tests; the keyword route; fusion; the too-broad rule per keyword; the recall option recorded on traces.
4. **Excerpts that fill their length (Q3, Q4; `packet-v10`).** Sentence growth around the best sentence up to
   `excerpt_chars`; `packet-v9` kept for replays; the budget-pressure advice (ADR 0036) checked against the new sizes.
5. **Evaluation and documentation**: M0 v2, synthetic set, the owner's recorded traces replayed (read-only, with the
   owner's OK), latency, a real-host smoke, review, docs.

## Out of scope (Phase 18)

- Vector recall changes (chunking, thresholds) and the embedding model.
- The extraction prompt's size, first-connection re-extraction (K29), and summaries' cost (K35).
- Verifying that an extracted fact's evidence quote is in the source; prompt-cache-friendly packet placement; panel
  diagnostics. Each is a separate proposal.
- Publishing the synthetic benchmark (proposal P3).

## Acceptance criteria

- [x] Every existing test and memory-evaluation case passes; recorded `packet-v9` requests replay as they were.
- [x] Deterministic cases: keyword extraction (particles, endings, stop words, names, Latin words, a query of stop
      words only, a name that an ending rule would shorten below two syllables, more than four keywords); a keyword
      too broad is dropped; a keyword-only hit is kept with vectors off and under the whole-message threshold; a
      message found by both routes is fused once; the route abstains when its time budget runs out; a trace without
      `lexical_keywords` replays with it off; `packet-v10` excerpts grow to `excerpt_chars` and stop at a sentence,
      a best sentence longer than `excerpt_chars` is cut there, and the fitter's shortening and omission still work
      when room runs out; nothing past the budget; at `packet-v9` nothing changes.
- [x] Lexical recall returns a candidate for at least 80 % of M0 v2 and synthetic queries (from 13–50 %).
- [x] M0 v2, `packet-v10` with keywords at 4,000 against `packet-v9` at 4,000, both chats, both extractions:
  - vectors off: cases needing memory at least +4 in total over the four runs;
  - vectors on: no run worse by more than one case;
  - forbidden phrases placed: at most +2 in total, none of them from a thread or a secret.
- [x] Synthetic set (4 cuts, 32k context), vectors on: the one-off detail category at least +3 over the cuts, and no
      category worse by more than one case per cut (the owner accepted one exception on 2026-09-30: "count" at the
      60 cut, −2, with the four-sentence cap).
- [x] Excerpts grow: the median placed excerpt at 4,000 on M0 v2 at least 1.3 times `packet-v9`'s (restated by the owner,
      2026-09-30: with ten excerpts at 4,000 no growth rule reached a 250-character median, since the fitter falls
      back to one sentence under budget pressure).
- [x] Retrieve latency at 10,000 messages within +15 ms p50 of `packet-v9` at 4,000 (`tools/bench_story.py`),
      including a question of four common keywords (each in more than 200 messages, `docs/perf/scale.md`). Met as
      measured with that question among the benchmark's (+11.9 ms); asked alone every time it adds 29 ms (421 → 450 ms,
      `packet-v9` already hits the whole-message timeout there): accepted by the owner, 2026-09-30.
- [x] Real-host smoke on an isolated PocketRisu v1.13.0.
- [x] Review per AGENTS.md §14 (retrieval semantics: high risk, one independent review).
- [x] `ARCHITECTURE.md` (D15 amended, D62), ADR 0052, README, the Korean guide, KNOWN-ISSUES, CHANGELOG.

## Steps (one pull request each)

1. This document, approved; AGENTS §2, STATUS and the roadmap name Phase 18 next. **Done** (2026-09-30).
2. Evaluation tooling and the `packet-v9` baseline (vectors on and off). **Done** (`docs/perf/lexical-recall.md`): `audit.replay` reports lexical
   recall's outcome; `tools/eval_rp.py` reports per case whether lexical recall found a candidate and the excerpt
   lengths, labels runs without vectors, reads an older request's prompt window at the head (membership is kept for
   the head only), and a probe replays although the request's own message was since deleted. Baseline: lexical recall
   found a candidate for 43 of 145 queries (30 %); excerpt median 69–101 characters.
3. Keyword lexical recall, ADR 0052, tests. **Done** (ADR 0052, D62, `docs/perf/lexical-recall.md` "Step 3"):
   lexical recall found a candidate for 131 of 145 queries (90 %); an excerpt only the keyword route found is left out
   when it repeats a secret still kept from someone (owner, 2026-09-30).
4. `packet-v10` excerpts, tests, plugin build if the panel's budget advice changes. **Done** (ADR 0053, D63, `docs/perf/lexical-recall.md` "Step 4"): excerpts
   grow from the sentence holding most keywords by up to four sentences (owner's choice over the whole length); the
   phase's M0, synthetic and latency criteria met as restated; no plugin build (the budget advice is unchanged).
5. Evaluation, the owner's traces, real-host smoke, latency, review, documentation; Phase 18 complete. **Done**
   (`docs/perf/lexical-recall.md` "Step 5"): on 34 of the owner's recorded requests `packet-v10` with keywords placed 24
   excerpts without vectors where `packet-v9` placed none, and no secret, thread or line past the budget that
   `packet-v9` would not; the real host injected a grown excerpt the keyword route found; K39 and K40 recorded.

Every merge reaches the owner's `:edge`; no tag (AGENTS.md §13).

## Stop conditions

Stop and ask the owner when:

- the keyword route places a secret, a closed thread or a stale value that `packet-v9` would not, on any evaluated
  case or recorded trace;
- M0 v2 misses the criteria above, or the gain depends on one extraction model only;
- latency exceeds the criterion, or the keyword route needs an index or migration to meet it;
- a morphological analyzer or any new runtime dependency looks necessary.
