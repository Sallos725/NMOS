# Phase 19 — One new extractor generation: shorter context, synthetic examples, evidence in the turn

> **Status: approved (2026-09-30) as proposed; complete (2026-10-01).** `deepseek-v4.1-flash`'s M0 criterion was missed
> and accepted by the owner (K41). Not a stage of `docs/ROADMAP-1.0.md`: it ships the
> changes queued for the next extractor generation (`docs/STATUS.md`, "Queued for the next extractor generation") and
> the owner's request of 2026-09-30 to cut what extraction costs without losing quality. Stages 7–8 become Phase 20+.
> No release.

## Why one generation

A change to the extraction prompt, the registry or the normalizer makes a new extractor generation, and a new
generation re-extracts each chat's recent window at the provider's cost (ADR 0006, 0014, D20). Two approved changes
have been waiting for the next one so that cost is paid once (owner, 2026-09-26). This phase adds a third, measured
first, and ships the three together as `extract-v14`.

## Questions and proposed answers

| # | Question | Proposed answer | Alternatives |
|---|---|---|---|
| Q1 | How much of the previous turns does the model see? | **Each context message cut at 1,000 characters instead of 2,000** (`CONTEXT_CHARS`); still the three previous turns, the target turn still up to 6,000 characters a message. Measured before this spec (below): 17 % fewer input tokens and as many ledger facts found or more. | Keep 2,000; two context turns instead of three (measured: fewer facts found, rejected). |
| Q2 | What replaces the prompt's examples taken from the owner's chat? | **Synthetic examples, one for one**: the `because` example and the `addresses` examples in the extraction prompt and the example value in the `addresses` description (`predicates.py`), rewritten with the persona 타쿠미 / Takumi and names already used in the tests. Same shape and length, so the prompt teaches the same thing. Canon reads show the same `addresses` description in their prompt and fingerprint it (`canonfacts.py`), so this makes a new canon generation too: each chat's canon sources are read once more (on production, 7 canon calls and ≈13k input tokens were recorded), and nothing else about canon changes. Approved 2026-09-28 (PR #149); the repository is public. | Remove the examples (the model loses the pattern they show). |
| Q3 | Which assertions need their evidence in the target turn? | **Every assertion of a turn extraction whose quote is at least 12 characters**: the quote must be found in the target turn's text by the test reveals already use (`threads.similarity` ≥ 0.7, `EVIDENCE_MIN`, PHASE-10), the text being what the worker gives the model (the members' normalized text joined by line breaks). One that is not is stored but parked as `pending`, reason "evidence not in the turn", as an alias without evidence is today (ADR 0012): it is never served (`facts.py` reads valid rows only) and stays in the ledger for audit. A shorter quote passes that test by accident, so it is left as today and counted, as is a row without a quote. The check is a parameter the turn worker passes to `normalize`; canon reads call the same normalizer and do not pass it (their only change is Q2's description). The Inspector does not list parked rows today (out of scope). The prompt already asks for "a short quote from the TARGET turn". Approved 2026-09-29 (C2 of `docs/proposals/IDEA-SURVEY-2026-09-29.md`), to be measured before it ships. | Check reveals only (today); reject instead of park. |
| Q4 | What is re-extracted, at what cost? | **What a new generation re-extracts today**: each chat's recent window (`NMOS_EXTRACT_BACKFILL`, 100 turns); each older turn keeps serving the rows of the most recently activated earlier generation that covered it (D20), unchecked, until "extract all history" (K29). Canon sources are read again once (Q2). On the owner's production (2026-09-30): 8 chats, 141 turns, so 141 turn calls; at production's median input (12,274 tokens over 7 recorded calls) less 17 %, about 10,200 input tokens each, ≈1.4M in all. Summaries written after the switch read `extract-v14`'s secrets; stored ones keep theirs (as for any generation). The model, the packet policy and recall do not change. | — |
| Q5 | How is it measured? | **Offline first, then a bounded spend** (steps 2 and 4). The offline checks need no model call. The paid runs are estimated in advance and run only after the owner's OK, **from the implementation branch before it merges**, so `:edge` never carries an unevaluated generation. | Ship without measuring Q3 (the survey said to measure). |
| Q6 | Is this high risk (AGENTS.md §14)? | **Yes**: it changes which extracted facts become current (Q3) and what every chat stores after re-extraction. One independent review of the implementation. | — |

## Evidence behind Q1 and Q3 (measured 2026-09-30, outside the repository; numbers only)

Production turn extractions (Phase 17 usage, `gemma4:31b-cloud`, 7 calls): median input 12,274 tokens, 13 % of it
reported as cached, output about one ninth of input. Rebuilt offline from the evaluation copies, a turn extraction's
prompt is about 29 % instructions and registry (constant), 40–42 % the three context turns (six messages; the long
ones at their 2,000-character cap), 14–21 % the target turn and 10–14 % the hints.

Sampled turns: the first 60 turns of the synthetic chat (Phase 18's, 240 turns) in which its ledger says a fact is
stated (turns 1–132; 105 facts), and 20 turns of the owner's M0 chat (no per-turn gold, counts only). Hints come from
the copy's existing generation, so every variant sees the same; `gemma4:31b`; each variant run three times against
three runs of today's prompt. A ledger fact counts as found when a row names one of its characters and its object or
value overlaps the fact's sentence (trigram overlap ≥ 0.5, any predicate, polarity or modality): a recall measure with
no precision check.

| | today (3 runs) | context 1,000 characters (3 runs) | two context turns (1 run) |
|---|---|---|---|
| ledger facts found, any row (of 105) | 72, 74, 70 | 78, 74, 74 | 68 |
| ledger facts found, valid rows after the Q3 check | 70, 72, 69 | 77, 73, 73 | 67 |
| valid rows the Q3 check would park | 2.7 %, 2.2 %, 1.6 % | 1.0 %, 1.4 %, 1.7 % | 2.6 % |
| … of them rows that find a ledger fact | 0 | 0 | 0 |
| rows parked by today's normalizer (types, aliases, outcomes) | 10, 9, 9 | 6, 6, 6 | 7 |
| addresses / relationships extracted | 14–16 / 7–9 | 20–22 / 10–12 | 18 / 8 |
| input tokens (sum of 80 turns) | 785k | 653k (−17 %) | 685k (−13 %) |

The Q3 rows apply the check to every quote, before the 12-character floor was added. Every valid row carried a
quote; 6–13 per run were shorter than 12 characters. Two runs of today's prompt share only
about half their rows (the model is not deterministic at temperature 0); the shorter context shares about a third with
today's, so it extracts somewhat different rows: more addresses and relationships, which a recall-only count cannot
tell from repeats of a pair's current value (step 2 checks that). Output tokens rose 5–10 %, so the net saving is about
11–14 % of an extraction's tokens, depending on the provider's output price. The last third of the synthetic chat,
where most history and open threads are, was not sampled (step 4 adds it).

## Goal

After this phase a turn extraction costs about a sixth less input, its prompt holds no text from the owner's chat,
and an extracted fact whose quoted evidence is not in the turn it was extracted from does not become current by
itself.

## In scope (Phase 19)

1. `extract-v14`: `CONTEXT_CHARS` 1,000 (Q1); synthetic examples (Q2); the evidence check in `normalize`, passed by
   the turn worker only (Q3); the compiler version and the generation's fingerprint change accordingly (D20).
2. Tests for each; the evaluation tooling needed to run the sampled-turn comparison from the repository
   (`tools/`), without chat text in the repository.
3. The measurements below, `docs/perf/extract-v14.md`, ADR 0054, ARCHITECTURE (D64), STATUS (the queue emptied),
   README and the Korean guide (what the re-extraction costs and what a parked row means), KNOWN-ISSUES, CHANGELOG.

## Out of scope (Phase 19)

- Shortening the instructions or the registry (a prompt rewrite; a separate proposal if the owner wants it).
- The number of context turns, the target turn's cap, the hints' size, the model, and canon or summary prompts.
- Re-extracting older turns (K29) and any change to recall or the packet.
- Listing parked rows in the Inspector, and the evidence check for canon reads.
- Deploying to the owner's production (the owner's call, AGENTS.md §13).

## Acceptance criteria

The noise below is estimated from three runs of today's prompt and is itself rough.

- [x] Every existing test passes; new deterministic cases (`tests/test_extract_v14.py`, `tests/test_eval_extract_sample.py`): a context message is cut at 1,000 characters and the target
      is not; the prompt's examples use only the synthetic names; a quote found in the target turn keeps an assertion
      valid, a quote found only in a context turn parks it with its reason, a quote under 12 characters and a row
      without a quote are unchanged, a reveal behaves as before, a canon read does not apply the check; the extractor
      generation key changes, and the canon generation key changes only through Q2's `addresses` description.
- [x] Step 2 (offline, no model call; met 2026-09-30, `docs/perf/extract-v14.md`), on the evaluation copies' `extract-v13` rows and on the sampled-turn runs of
      the shorter context, reported per extraction model, per predicate and per `epistemic`: **the share of valid rows
      the Q3 check would park is at most 10 %, and leaving them out lowers the cases passed of no M0 v2 run by more
      than one** (Phase 18's `packet-v10` runs, `docs/perf/lexical-recall.md`; amended 2026-09-30 by the owner from
      "none of them is a fact line placed in the packet of an M0 v2 case that passed": six such rows were placed and
      none answered its case, `docs/perf/extract-v14.md`); and the shorter context's
      `addresses` and `relationship` rows that only repeat the pair's current value are not more frequent than today's.
- [x] Sampled turns (met 2026-09-30, `docs/perf/extract-v14.md`), the first 60 and the remaining 31 ledger turns (three runs of `extract-v14` against three of
      today's prompt): ledger facts found among valid rows, mean not below the lowest of today's runs; the Q3 check
      parks at most 10 % of valid rows and no row that finds a ledger fact; each ledger kind of secrets and reveals
      that today's prompt finds is still found; input tokens at most 85 % of today's.
- [ ] M0 v2 re-extracted with `extract-v14` (met by `gemma4:31b` and the synthetic cuts; missed by `deepseek-v4.1-flash` on M0 v2, accepted by the owner 2026-09-30, K41) on its evaluation copies with both extraction models of Phase 18, and the
      synthetic cuts with `deepseek-v4.1-flash` (the only model of their Phase 18 baseline), evaluated at `packet-v10`, 4,000, vectors on and off, against `docs/perf/lexical-recall.md`'s
      `extract-v13` numbers: cases passed and needing memory not lower by more than one per run; forbidden phrases
      placed not higher in total; the Q3 check parks at most 10 % of each model's valid rows.
- [x] Review per AGENTS.md §14 (one Codex review of step 3, its finding fixed) (high risk, one independent review).
- [x] Documentation listed in scope (step 5, 2026-10-01).

## Steps (one pull request each)

1. This document, approved; AGENTS §2, STATUS and the roadmap name Phase 19.
2. The offline measurements (no model call) and their report in `docs/perf/extract-v14.md`; Q3 amended if the owner
   decides so.
3. `extract-v14`: the three changes, tests, review. **Not merged until step 4's criteria hold.**
4. The paid evaluation from step 3's branch, after the owner's OK for its estimate: sampled turns, 91 turns × 3 runs
   (≈273 calls, ≈2.3M input tokens); full re-extraction of the evaluation copies: M0 v2's two chats (246 turns) with
   both models and the synthetic chat (240 turns) with `deepseek-v4.1-flash`, 732 calls (≈6–7M input tokens); their
   canon sources read again where they have any (a few calls). Results in
   `docs/perf/extract-v14.md`; then step 3 merges.
5. Documentation; Phase 19 complete.

Every merge reaches the owner's `:edge`; no tag (AGENTS.md §13).

## Stop conditions

Stop and ask the owner when:

- the evidence check would park more than 10 % of valid rows, or any row that finds a ledger fact, or leaving the
  parked rows out would lower an M0 v2 run's cases passed by more than one;
- `extract-v14` misses a criterion above, or its gain holds for one extraction model only;
- a schema change or migration looks necessary;
- a paid run would go beyond its estimate by more than a quarter.
