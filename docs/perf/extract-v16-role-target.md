# PR #251: the role's counterpart must appear in the target

2026-10-03. **High risk**: automatic role endings affect current versus historical state and provenance.
Base `ed108423fa5e6c278db80649e807a04ffee3107f`; the owner requested a correction if its benchmark failed.
Only opt-in `extract-v16` changes. Its prompt hash gives it a new generation; `extract-v15` and the default remain
pinned. No schema, identity resolution, reconciliation, request-path or plugin change.

## Observed defect and correction

S2 turn 99 promotes 윤하람 at a bakery. It does not name 오봉순, the innkeeper, or end the listed inn employment.
The model nevertheless selected that role (R5), `when: now`, with a real quote of the bakery promotion in runs
2 and 3. Production reconciliation closed the inn role. The run stopped after 41 calls: the five core checks
passed 13/15, with this case failing 2/3. This is a wrong derived state, not a missing retrieval candidate or a
packet-budget failure.

The [PR comment's proposal](https://github.com/Sallos725/NMOS/pull/251#issuecomment-5963888145) was checked against
preserved raw outputs before changing the parser. Requiring the counterpart's name inside the ending quote would
reject all **31 correct move/resignation endings**, as well as the eight known wrong ones, across five candidates
(`c582343`, `27c7658`, `0abb2fd`, `073b7a1`, `ed10842`). Requiring it anywhere in the shown TARGET instead retained
31/31 correct endings and rejected 8/8 known wrong ones. Eight other endings were retained and left unclassified.
These are offline replays, not additional model calls.

`role_party_named` implements the TARGET requirement before a listed negative is emitted. It recognizes the
counterpart's literal name and unambiguous character aliases from the generation's existing hints. For a role
toward the persona, it checks the other party using `entities.node`'s existing persona rule. The worker and
evaluation tool pass the bounded shown text, hints and persona. Old context, a name beyond the prompt limit,
`Ann` inside `Joanne`/`Anna`, `이안` inside `백이안`, or a shared alias cannot satisfy the check. The existing time, reference and
quote checks still apply; the quoted evidence is not rewritten.

This guard is deliberately incomplete: a pronoun-only counterpart can leave a stale role, and a counterpart
mentioned incidentally elsewhere in a turn can still accompany a wrong model decision. It does not prove that
all state transitions are correct.

## Fresh model measurement

Existing local endpoint, requested `gemma4:31b-cloud`, reported `gemma4:31b`; temperature 0, two concurrent calls,
one attempt per turn/run, no retries. Only the established synthetic S1/S2 input was prepared, with all 480 user
prompts and their text/hints/roles/pairs identical to the base; the system instruction changed. The 90 calls are
30 S2 scenes repeated three times, including the 27 alias-bearing turns. Preserved databases were read-only.

| Candidate | Completed calls | Input tokens | Output tokens | Call errors |
|---|---:|---:|---:|---:|
| `ed10842` | 41 | 388,432 | 50,501 | 0 |
| Base + TARGET counterpart guard | 90 | 886,161 | 109,506 | 0 |

| S2 case | Expected | Base runs 1 / 2 / 3 | Corrected runs 1 / 2 / 3 |
|---|---|---|---|
| 74: another job | Keep mentorship | pass / pass / pass | pass / pass / pass |
| 86: move planned | Keep guest role | pass / pass / pass | pass / pass / pass |
| 87: completed move | End guest role | pass / pass / pass | pass / pass / pass |
| 99: bakery promotion | Keep inn employment | pass / FAIL / FAIL | pass / pass / pass |
| 233: resignation | End employment | pass / pass / pass | pass / pass / pass |

These 15 checks use the preserved positive role plus measured assertions through production normalization,
identity resolution, `facts.version_key` and `facts._versions`. The model still proposed the wrong turn-99 ending
in corrected run 2; the guard blocked it. Raw-to-normalized parity holds for all 41 base and 90 corrected outputs.
The final persona-rule alignment changes no prompt and reproduces all 90 normalized outputs exactly.

On 81 alias-bearing calls, the expected aliases were retained on 2/2/2 turns for 윤하람/하람 and 12/14/14 for
백이안/이안. All 46 valid aliases name those two pairs; production resolution joins both in each run (6/6).

There are also three retained endings at turn 219, when 하람 leaves for school in the capital. The innkeeper is
present, so the guard permits them. These are **outside the five scored cases**: the historical v15 hints can
already be stale, and this probe does not establish the actual ending time of that employment. They are not
counted as independently verified correct endings. Do not turn the core 15/15 into a full no-wrong-ending verdict.

## Verification and evidence boundary

- New regression failed on the unmodified base; final scoped role/alias/probe tests: 47 passed.
- Final full sidecar suite: 947 passed, two dependency deprecation warnings, 222.51 s on isolated PostgreSQL.
- `git diff --check` passed. The unchanged plugin had already passed 196 tests, typecheck and build on `ed10842`.
- Worker integration checks read the retained role back through the API, including a counterpart name only beyond
  the model's TARGET limit. Reverse persona roles, known/ambiguous aliases, embedded names and pronoun-only misses
  have deterministic coverage.
- Scoped self-review covers current/history folding, provenance, bounded model evidence and generation isolation.
  The default-generation pin is in the scoped suite. Raw evidence and historical assertions are preserved.

Q5(c)'s full comparison, sequential v16 first connection/backfill, the turn-219 timing classification and the live
host gate remain unverified. No default switch or phase-completion checkbox is implied. No additional model call
was made on the independent space-station corpus.

Local evidence (not generated files committed to Git):

- `/tmp/nmos-pr251-ed10842-results/`: manifest, raw/normalized replies, status, 41-output parity and 13/15 findings.
- `/tmp/nmos-pr251-ed10842-verification/`: offline guard comparison, regression red/green logs and suite logs.
- `/tmp/nmos-pr251-party-target-results/`: manifest, patch, prompts and provenance, raw/normalized replies,
  90-output parity, 15/15 findings, 6/6 alias resolution, full output inventory and final-source parity.
- Corrected system SHA-256: `bcadcdb83d89cbbcec85fb20f13c75ea787d81e6544a1c100f4e20286d46bce6`.
- Final `extraction.py` SHA-256: `544caba322ae929c8e99f44ab173ce1496dcdd5ed409a755de5154e75b461eec`.
