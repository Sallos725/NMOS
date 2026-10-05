# PR #251: a new job does not end a continuing mentorship

2026-10-03. **High risk**: automatic role endings affect current versus historical state and provenance.
The local correction changes only `extract-v16`'s prompt. Its system hash changes; `extract-v15`'s prompt and
generation key stay pinned by tests. No parser, identity, database, queue-order or default change.

## Observed failure and correction

Base: `c582343c0266606b81620f698fb25cd229d9db8d`, PR #251's head at measurement. The owner requested another benchmark
and authorized a correction if it failed. The first nine calls passed the existing guest/eve/employment checks.
The wider run stopped after 76 completed calls when S2 turn 74 incorrectly ended the existing mentorship in runs
1 and 3. A new surveying job was treated as ending the protagonist's role as the mapmaker's student, although
turn 73 explicitly continued evening lessons and turn 75 still called the protagonist that person's student.

The correction says that a listed role is between its two people; a new job, workplace or rank does not itself
end that arrangement. CONTEXT can establish continuity, but only the TARGET can supply an ending. The role
reference, time, quote and exact listed-value checks remain unchanged.

## Measurements

Endpoint: existing local Ollama `/v1`, requested `gemma4:31b-cloud`, reported `gemma4:31b`; temperature 0,
two concurrent calls, one attempt per turn/run, no retries. Inputs are the previously authored S1/S2 synthetic
story: all 960 stored messages were byte-matched against the authored source or its scripted overrides before
the run. No S0 real-chat input was sent. Preserved benchmark databases were opened read-only.

| Candidate | Completed calls | Reported input tokens | Reported output tokens | Call errors |
|---|---:|---:|---:|---:|
| PR head `c582343` | 76 | 707,319 | 92,999 | 0 |
| Same base + local continuity prompt | 27 | 259,161 | 31,657 | 0 |

Every run below used the actual preserved v15 positive role plus the measured v16 assertions, production
`ended_roles`, `normalize`, `entities.resolve`, `facts.version_key` and `facts._versions`. Raw-to-normalized
parity was checked for all 76 original outputs and all 27 corrected outputs.

| S2 target | Expected | Base runs 1 / 2 / 3 | Corrected runs 1 / 2 / 3 |
|---|---|---|---|
| 74: new job, continuing mentorship | Keep mentorship | FAIL / pass / FAIL | pass / pass / pass |
| 86: eve of the move | Keep guest role | pass / pass / pass | pass / pass / pass |
| 87: completed move | End guest role | pass / pass / pass | pass / pass / pass |
| 233: resignation | End employment role | pass / pass / pass | pass / pass / pass |

The corrected sample also repeated turns 73, 75, 99, 139 and 187 three times each. No valid negative role was
written on these 15 calls. **Turn 99 remains a warning about the model's raw decisions**: it still reported an
ending with a malformed descriptive role reference, rejected by the unchanged parser (two `planned`, one `now`).
This is fail-closed parsing, not proof that the model understood the promotion correctly. At turn 139 a fixed
historical hint may already be stale; this probe cannot establish the world's current role there.

Limitations: fixed preserved v15 hints, S2 only so far, no sequential v16 worker/backfill, no full 1,440-call
comparison and no final alias regression verdict. These passes do not complete Phase 28 or authorize a default
switch. A single retained wrong alias or wrong closure still fails the wider evaluation.

Local evidence directories (owner machine; not committed generated responses):

- `/tmp/nmos-pr251-c582343-results/`: `status.json`, `calls.jsonl`, `extended-findings.json`, raw/normalized replies.
- `/tmp/nmos-pr251-codex-role1-results/`: `manifest.json`, `candidate.patch`, `status.json`, `smoke-findings.json`,
  `input-provenance-check.json`, raw/normalized replies and `sidecar-suite.log`.
- Corrected system SHA-256: `04382e9643b3fc87a2936c0d1ba58d6fba69151225549b333609695add6459b1`.
- Corrected `extraction.py` SHA-256: `39430b64efeb1d79a617fd9ed6b92b1369cc719974d649c5828de097bfc934ad`.

## Independent authored probes

The owner requested new names and a completely new story. `tools/scenarios/glass-garden.json` has 14 independent
synthetic scenes in an orbital ecology station. It is authored test input, not observed host evidence. Each
case supplies its own earlier roles and context; gold expectations never enter the prompt. It covers continuing
mentorship, promotion, temporary absence, planned/actual/cancelled departure, resignation, actual mentorship
termination, ending one of two relationships, positive aliases, name-only evidence, namesakes and a combined
alias/ending case. The separate personal story/card pack is under `~/nmos-bench/유리정원-정거장/`.

From `apps/sidecar`, prepare without any model call:

```bash
uv run python ../../tools/eval_story_probe.py --out /tmp/glass-garden-dry --runs 3
```

The measured dry-run plans **42 calls and 213,654 estimated input tokens** on this local prompt (output tokens
are not estimated). Actual calls require `--execute --url URL --model MODEL` and a new output directory.
No calls on this new corpus were made as part of this result. The tool stops at the first failed case/error,
does not retry or overwrite previous outputs, and records prompts, hashes, raw replies, usage and production
normalization/reconciliation results. It does not replace a database worker/backfill benchmark.

## Verification and scoped review

- Phase 28 tests: 30 passed against an isolated test PostgreSQL instance.
- Sidecar suite after the continuity fix: 921 passed in 221.18 s; two dependency deprecation warnings.
- Added independent-probe tests, run separately after that suite: 9 passed. They check a wrongly ended mentor,
  a missed actual ending, the wrong party, a false namesake join, full-name-only evidence, no-call dry-run,
  failure stopping/raw retention, unsafe IDs/invalid seeds, and an ending expressed under a proven alias.
- `git diff --check` passed. Review covered the changed prompt and its direct normalization/reconciliation
  dependencies, tests, authored cases and probe runner. Historical evidence is retained; no wider migration,
  identity or request-path behavior is changed. Actual RisuAI card import is not part of this software verdict.

## Handoff

Changed:
- Follow-up correction for PR #251, based on `c582343`: continuity prompt, regression tests, independent synthetic
  probe and evidence documentation. Comment `5961194165` records the measurements made before the owner authorized
  committing and pushing the correction to the same PR branch.

Verified:
- Original failure 2/3; corrected core 12/12 across 27 calls; sidecar 921 tests and probe 9 tests passed.
- New corpus dry-run: 42 planned calls, 213,654 estimated input tokens, zero actual calls.

Not verified:
- Complete Q5(c), alias regression verdict, sequential v16 worker/backfill, live host scenarios and RisuAI UI import.

Risks:
- High risk: wrong automatic endings can change current versus historical state. Raw turn 99 decisions still need
  scrutiny; the conservative time-word guard can also reject a correct ending when its quote includes other text
  (the authored probe's `과제를 내주었다` matches `내주`). No time-word behavior was changed here.

Next recommended step:
- Review the local diff, then continue the remaining measured acceptance checks; retain raw-response inspection
  and the stop condition. Do not infer default-switch readiness from this bounded correction.
