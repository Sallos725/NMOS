# PR #251: closing a business does not end a residence

2026-10-03. **High risk:** current versus historical roles and their provenance. Base `f747f4f`;
only opt-in `extract-v16`'s system rule and closing reminder change. The parser, reconciliation,
schema, request path, plugin and default `extract-v15` are unchanged. The prompt fingerprint creates
a new extraction generation; results from the old prompt are not results for this correction.

## Failure and first divergence

The full fixed-input S1/S2 comparison stopped at **507 successful samples out of 1,440 planned**
(all S2, 169 turns per run; 90 samples reused from the identical-prompt pilot). There were 509 attempts,
including two JSON-format failures, each recovered by one same-input retry requested by the owner.
Reported usage was 4,923,443 input / 553,965 output tokens, including the pilot and retries; the first
failed reply's token usage was not captured and is not included in those totals.

At S2 turn 144, the map shop closes when its owner retires. The resident keeps the key and access to
his workbench; the TARGET does not end his stay. All three replies nevertheless named the resident
role R1 as ended `now`, quoting the shop's door closing. The counterpart's name and the quoted text
are present, so both guards pass. Production normalization, identity resolution and `facts._versions`
then remove the preserved positive residence. The six role cases score **15/18**, failing this one
in every run. This is a wrong extraction decision that becomes wrong derived state. Retrieval and
packet selection were not involved in this reproduction.

## Correction and bounded measurement

The rule distinguishes business closure or retirement from a resident moving out or a mentorship
ending. It tells the extractor to check continued accommodation, access and the relationship at the
end of the TARGET. The closing reminder repeats this check beside the model's decision.

| Candidate | Calls | Input / output tokens | Residence kept | All six role cases | Name joins |
|---|---:|---:|---:|---:|---:|
| System rule only | 24 | 237,834 / 28,192 | 1/3 | 16/18 | Not used as an acceptance result |
| Rule and closing reminder | 24 | 239,370 / 27,483 | 3/3 | 18/18 | 6/6 |

Each candidate measures S2 turns 144, 74, 86, 87, 99, 233, 33 and 35 three times with the existing
local `gemma4:31b-cloud` endpoint (reported `gemma4:31b`), temperature 0 and two concurrent calls.
There were no call errors or retries in either 24-call check. Context, TARGET, hints, roles and name
pairs are preserved; the second candidate also changes the closing reminder. All 24 final outputs
match production normalization. The six role cases keep the mentorship, planned stay, unrelated
inn employment and residence, and end the completed stay and resigned employment. Actual resolver
checks join both target name pairs in each run. These are fixed historical v15 hints, not a sequential
worker or backfill result. The prompt is a measured mitigation, not a deterministic semantic guard.

## JSON-format diagnosis

The first failure (S2 turn 62, run 2) had no retained raw response, so its exact malformed token is
unknown. Capturing the provider body before the production parser exposed the second failure
(turn 79, run 3): two object-ending trailing commas after `"hidden_from": []`, at cleaned response
lines 94 and 122. `finish_reason` was `stop`. Removing those commas parses offline, but that repaired
text was **not** accepted as a model result. Both failures used fresh same-input retries; the original
failures and extra usage remain in the journal. Production JSON parsing was not relaxed.

Ollama documents that [Cloud does not support structured outputs](https://docs.ollama.com/capabilities/structured-outputs).
The measured endpoint returned fenced text despite `response_format: json_object`; the request alone
did not guarantee valid JSON. Raw provider responses are now retained by the benchmark before parsing.

## Evidence and remaining gates

Final scoped tests: 47 passed. Final full sidecar suite: 947 passed, two dependency deprecation
warnings, 208.99 seconds on isolated PostgreSQL. The measured source matches the final working tree.
The existing prompt-tail expectation was updated for the added reminder. `git diff --check` passed.
Diff-scoped self-review checked generation isolation and the unchanged parser/reconciliation path:
the default v15 generation pin passes; the v16 system fingerprint changes with the reminder; actual
measured negative roles still close only their listed values. No deterministic semantic guarantee is
claimed, and the no-wrong-ending gate remains necessary.

The owner's durable evidence root is `/home/grantkim725/nmos-eval/pr251/2026-10-03/`:
`nmos-pr251-f747f4f-comparison` holds the stopped run and failed-response diagnosis;
`nmos-pr251-residence-fix` holds the unsuccessful first candidate;
`nmos-pr251-residence-fix2` holds the final 24 calls, prompts, source snapshot, patch and checks.
The old runs remain separate. Final system SHA-256:
`19e2be70eb37f75e218bdb7c94e0aab317ffb8eb068607c569c5833147c123c9`.

The full comparison must restart for the new prompt. The owner authorized quota use and a restart
after correction when a defect appears in the first quarter: 360 of the 1,440 planned calls.
First-connection/backfill and live-host gates still remain, including turn 219's ending time.
No default switch or phase-completion claim follows from the bounded check.
