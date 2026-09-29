# Phase 17 — What NMOS's own model calls cost, and fallbacks told from failures

> **Status: approved (2026-09-29) with every proposed answer (Q1–Q7); current.** The owner chose to run it after
> Phase 16 (2026-09-29). Source: C4 and C5 of `docs/proposals/IDEA-SURVEY-2026-09-29.md`. No release.

## Questions and proposed answers

| # | Question | Proposed answer | Alternatives |
|---|---|---|---|
| Q1 | Which calls? | **Every model call the worker makes for a projection:** extraction, summaries, canon reads. Embeddings too, as input tokens only, where the endpoint reports them. | Extraction only. |
| Q2 | What is recorded? | **What the provider reports, never an estimate:** input, output, cached input and reasoning tokens from the response's `usage` (OpenAI-compatible fields, `prompt_tokens_details.cached_tokens`, `completion_tokens_details.reasoning_tokens`), the model name and the call's duration. A response without `usage` records none, shown as "not reported". | A tokenizer estimate when the provider reports nothing. |
| Q3 | Where? | **One nullable `usage` JSON column on `extraction` and `summary`**, written with the row it produced, so a rebuild or a new generation keeps the old rows' cost for audit. Embeddings: a counter per projection in the same column shape on the job. One migration. | A separate call-log table. |
| Q4 | Where is it shown? | **The Inspector's coverage, per chat and per generation:** calls, input / output / cached tokens, and the share of calls that reported usage. The panel's Status tab: this chat's totals in one line. No money: prices vary by provider and the owner's are local or flat. | A price table; a global dashboard. |
| Q5 | Which request outcomes does the HUD show? | **Besides "injected", "nothing relevant", "off for this chat" and "skipped": "injected, lexical only"** when the retrieve answer says vectors fell back (K34), and **"injected (reused)"** for a cached packet on a reroll, both in the neutral style, not as warnings. | The Status tab only (today). |
| Q6 | What does the HUD show after background work? | **"Done" becomes "N facts, M summaries"** from the coverage change since the request, when the sidecar reports it; otherwise "done" as today. | Unchanged. |
| Q7 | How is it measured? | **Recorded usage matches the provider's** on the local test model (Ollama) and one hosted endpoint the owner names (a few calls, owner OK for the spend); the HUD outcomes on the isolated real host (fallback forced with a short embed timeout, reroll within the cache time); no change in request-path latency (the request path writes nothing new). | Unit tests only. |

## Goal

The owner pays for extraction. Today NMOS counts its model calls but not their tokens, and the HUD shows a recall
that fell back to lexical search the same as a full one. After this phase the owner can see what each chat's memory
cost in tokens, from the provider's own numbers, and the HUD says when memory was served in a reduced way.

## In scope (Phase 17)

1. Reading `usage` from chat-completion and embedding responses in `llm.py`; storing it with the rows (Q1–Q3).
2. Migration: `usage jsonb` on `extraction` and `summary`, and on the embedding job's record (Q3).
3. Inspector coverage and a Status-tab line (Q4).
4. HUD outcomes and the "done" summary (Q5, Q6); strings in both languages; a new plugin build.
5. Docs: `docs/guide.ko.md` (what the numbers mean), CHANGELOG, KNOWN-ISSUES K34 (the HUD now says it).

## Out of scope (Phase 17)

- Prices, budgets or limits on spending.
- Usage of the reply model (the host's own request log has it).
- Any change to what is extracted, recalled or injected.

## Acceptance criteria

- [ ] Usage recorded for extraction, summaries and canon reads matches the provider's numbers on the local model and
      on one hosted endpoint (Q7); a response without `usage` records none and shows "not reported".
- [ ] Old rows (before the migration) show "not recorded", and a rebuild keeps each row's own usage.
- [ ] The Inspector shows totals per chat and per generation; the Status tab shows this chat's line.
- [ ] On the isolated real host: "lexical only" appears when vectors fell back, "reused" on a cached reroll, and
      neither appears as a warning.
- [ ] Request-path latency at 10,000 messages unchanged (`tools/bench_story.py`, as Phase 15).
- [ ] Phase 16's archive exports and restores the new column (a round trip on a copy).
- [ ] A review per AGENTS.md §14 (a migration: high risk).

## Steps (one pull request each)

1. Spec approved; AGENTS §2 and STATUS name Phase 17 current.
2. Usage read and stored (Q1–Q3), migration, tests; the hosted-endpoint check with the owner's OK.
3. Inspector and Status tab (Q4).
4. HUD outcomes and summary (Q5, Q6), plugin build, real-host check.
5. Measurements, docs, Phase 17 complete.

## Stop conditions

- A provider the owner uses reports usage in a shape the answer to Q2 does not cover.
- The HUD change needs a host call it does not have (H16).
- The migration conflicts with Phase 16's archive format.
