# PR #251: a missing known alias blocks an ending; a new alias is not extracted

2026-10-03, measured code `7dbef462deb50e06b65497af20a42de57ecdc6ae`.
**Q5(c) remains unmet.** These results do not switch defaults or complete Phase 28.
The default v15, parser, reconciliation and production code were not changed after this measurement.
The guarantees under examination remain **high risk: identity, provenance and current/historical roles**.

## Fixed historical hints: stopped at 739/1,440

The fresh comparison reused no pilot outputs. S2 completed 240 turns three times (720 samples);
S1 completed 19 samples before the failure stop drained the in-flight calls. There were 743 attempts,
including four JSON-format failures, all recovered with one same-input retry each. Every HTTP response
and its reported usage was captured before parsing. Total measured usage, including failures/retries:
**7,427,015 input / 816,967 output tokens**, no missing usage. Each format error was an object-ending
trailing comma after `hidden_from`; no reply was repaired and admitted as a successful sample.

All 739 saved results reproduce through the actual production normalizer. The six declared role cases
per scenario give S2 **18/18**, S1 **15/18**, combined **33/36**. This is a count of those checks, not
739 semantically correct samples or a completed no-wrong-ending/alias gate.

S1 turn 233 fails in all three repeats (planned sample indices 736–738). The model names both listed
employment directions, R5 and R6, as ended `now`, with an accepted TARGET quote. However:

- The preserved v15 role and entity hint name the captain in full. TARGET uses only his given name.
- The fixed hint has no alias connecting them. `role_party_named` therefore rejects both endings.
- No negative role survives normalization; the preserved positive employment stays current under
  actual resolver/reconciliation checks. This is a missing ending after the model response, not a
  retrieval or packet-budget loss. The declared ending check is the same one used for S2.

An offline counterfactual augments only that hint with the full/given-name alias actually measured in
S2. All three unchanged replies then retain both endings and close the employee role. A synthetic
conflicting alias owner blocks them again, 3/3. These controls locate the missing condition; they are
**not** new model successes or proof that a sequential S1 worker has learned the alias in time.
The counterpart guard is unchanged; weakening it could restore the earlier wrong-employer endings.

The automatic stop was detected at 737 completions, outside the owner's first-quarter correction
window (360/1,440). No production correction or fresh full restart followed. Actual v16 sequential
hints must still be measured separately. Turn 219's ending time and other non-core transitions remain
unclassified; the completed S2 calls alone do not settle that gate.

## Independent authored story: stopped at 25/42

The existing `tools/eval_story_probe.py` and `tools/scenarios/glass-garden.json` were copied unchanged
and run with the same measured extractor source, `gemma4:31b-cloud` (reported `gemma4:31b`), temperature
0. Their earlier nine tool tests and dry-run were not model measurements. The call estimate was 42,
with 236,508 input tokens; gold expectations were not in the prompts.

The first eight role scenarios passed in all three repeats: **24/24**. The next sample,
`full-and-given-name-1`, failed: an explicit self-introduction plus narrated use of the short name
produced two `addresses` facts and one `event`, but **no `also_called` assertion and no `same_names`**.
Production normalization did not discard an alias: none existed in the raw reply. The actual resolver
did not join the two names. First divergence is the model's missing alias extraction.

This case supplies authored context but no stored entity hints or NAME PAIRS. It measures the free
alias rule, not whether a sequential worker would build a numbered pair from an earlier extraction.
The original script stopped at its first failed sample: **24/25 passed, 17 unrun**, no JSON/transport
errors or retries. Reported usage: **123,026 input / 19,729 output tokens**. No repeat failure rate is
claimed from the one measured name case.

## Preservation and next measurement

The actual user-readable file is
`/home/grantkim725/nmos-eval/pr251/2026-10-03/RESULTS.md` (not a directory link).
Its `full-residence-v2/` artifacts include `offline-audit.json`, `s1-failure-diagnosis.json`, raw HTTP
replies, prompts, status and STOP; `glass-garden-7dbef46/` contains the unchanged tool/cases, every reply
and individual grade. These synthetic-story artifacts stay local; they are not host evidence.

Sequential first-connection/backfill templates are prepared, with **zero model calls**. The next
batch runner is capped at three independent databases/calls, one ordered worker per database. It
waits before issuing new calls if available RAM falls below 8 GiB or one-minute load exceeds 75% of
logical CPUs. The observed host had 16 logical CPUs and about 14.7 GiB available RAM. No production
Ollama setting was changed. The full prepared batch would be 2,880 samples and 36,119,616 estimated
input tokens before retries; backfill hints change dynamically, so that token figure is a forecast.
No sequential paid run, default switch, or live-host gate is claimed here.

Validation of this report: journal/status totals, 739 raw-to-normalized comparisons, 36 declared role
checks, three counterfactual and ambiguity controls, and the saved independent probe grade. The
unchanged measured code's earlier full suite is 947 passed; it was not rerun for this documentation.
