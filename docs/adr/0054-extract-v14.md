# 0054 — `extract-v14`: a shorter context, synthetic examples, evidence in the turn

Status: accepted, 2026-09-30. Phase 19 step 3 (`docs/phases/PHASE-19.md` Q1–Q3, approved by the owner; the step-2
criterion amended by the owner the same day, `docs/perf/extract-v14.md`). Amends ADR 0008 (the context the model
sees) and extends the alias check of ADR 0012 to every quote. No migration, no plugin build.

## Context

A change to the extraction prompt, the registry or the normalizer makes a new extractor generation, and each chat's
recent window is extracted again at the provider's cost (ADR 0006, ADR 0014, D20). Two owner-approved changes waited
for the next generation (`docs/STATUS.md`, "Queued for the next extractor generation"): prompt examples without text
from the owner's chat (the repository is public) and quoted evidence found in the target turn for every assertion
(C2 of `docs/proposals/IDEA-SURVEY-2026-09-29.md`). A third was measured before the phase: the three context turns
take 40–42 % of a turn extraction's prompt, and cutting each context message at 1,000 characters instead of 2,000
used 17 % fewer input tokens and found as many ledger facts on sampled turns.

A turn extraction's rows are its target turn's facts (ADR 0008), yet about 5 % of `gemma`'s valid `extract-v13` rows
(0.5 % of `deepseek`'s) quote text that is not in their target turn; 55 of 66 quote a context turn, so the fact is
stated there, and a `resolved` row stated at the wrong turn closes a thread there.

## Decision

1. **Context messages at 1,000 characters** (`CONTEXT_CHARS`, Q1). Still three context turns
   (`NMOS_EXTRACT_TURNS`), the target turn's messages still up to 6,000 characters each. The generation's spec
   records `context_chars`, so the key changes.
2. **Synthetic examples** (Q2). The `because` example and the `addresses` examples of the extraction prompt and the
   example value of the `addresses` description use the persona 타쿠미 / Takumi and names already used in the tests,
   one for one, same shape. Canon reads show the same registry description and fingerprint it, so the canon generation
   changes too (its only change) and each chat's canon sources are read once more.
3. **Evidence in the turn** (Q3). `normalize(…, shown=shown_target(ctx))`, passed by the turn worker only: a row still
   valid after the other checks whose quote has at least `EVIDENCE_MIN_CHARS` (12) characters, and whose quote reaches
   less than `EVIDENCE_MIN` (0.7, the overlap of character trigrams over the quote's, as for reveals, PHASE-10) against
   the target turn as the model saw it (`shown_target`: each member's normalized text up to `TARGET_CHARS`, joined by
   line breaks; a quote from past that cut was not shown to the model), is stored
   `pending` with the reason "evidence not in the turn". Like any pending row it is never served (`facts.py` reads
   valid rows) and stays for audit. A shorter quote shares its few trigrams with most turns and would pass or fail by
   accident, so it is not checked; nor is a row without a quote. A row already parked keeps its own reason. Reveals are
   unchanged (their evidence already passes this test before they become `learned`). Canon reads do not pass the
   check: a canon text is not a turn. The earlier evaluation tools keep calling `normalize` without it, as the
   generations they measure did.
4. `COMPILER_VERSION` is `extract-v14`.

## Consequences

- A turn extraction's input is about a sixth smaller; its output somewhat larger (5–10 % on the sampled turns).
- A fact the model restates from a context turn no longer becomes current at the later turn. If its own turn's
  extraction missed it, it is lost until that turn is extracted again; measured on the evaluation copies, leaving the
  parked rows out lost one M0 v2 case of 55 per `gemma` run and none for `deepseek` (the owner accepted at most one
  case per run).
- Each chat's recent window (`NMOS_EXTRACT_BACKFILL`) is extracted again once, and its canon sources read again once;
  older turns keep the rows of the most recently activated earlier generation that covered them (D20).
- The Inspector does not list parked rows (out of scope).
