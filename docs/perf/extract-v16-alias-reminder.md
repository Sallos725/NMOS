# extract-v16: an alias on first introduction, and a conflicting short name

2026-10-03, PR #251. **High risk: identity/provenance and current versus historical role state.**
The owner approved correction, sequential verification, then a fresh comparison with at most three
simultaneous model calls after the failures recorded in `extract-v16-fixed-hints-and-glass.md`.
The v15 default and its generation remain unchanged. This is not completion of Q5(c) or the live gate.

The independent glass-garden probe has no stored entity hints. On the old prompt it missed an alias even
when a newcomer explicitly gave both names and the narrator showed that person answering to the short
name. Numbered NAME PAIRS do not cover this first introduction. The v16 rule now distinguishes the two
paths: a listed pair uses `same_names`; an unlisted, evidenced pair uses `also_called`, even when the model
also writes an `addresses` fact or an event. An identity stated only by a character remains a claim.
The same check closes the input. It is also included in the system prompt fingerprint, so its change
creates a new generation. The worker and both evaluation tools pass the selected compiler to the input
builder; v15 gets no new reminder.

## Measured model results

The existing 14 authored synthetic cases and their gold checks were unchanged; no entity hints were
added. Three independent repeats, temperature 0, `gemma4:31b-cloud` through the owner's existing endpoint
`http://127.0.0.1:11500/v1`. Provider replies and usage were captured before parsing. No retries.

| Candidate | Actual calls | Observed result | Input / output tokens |
|---|---:|---|---:|
| System rule alone | 27 | First eight role cases 24/24; first name case 1/3, then stopped | 136,350 / 19,803 |
| System rule and closing check | 42 | All 14 cases pass in each repeat, 42/42 | 219,120 / 30,966 |

The successful candidate's system SHA-256 is
`4ffec3cbf0e891b0b9508162a90a39337a91d909e0f34ef86da3603a5d42a410`;
its extraction source SHA-256 is
`193941e253e96234a1f4f1cef31f45c6783b0701c2848f12c1f26e31aab175ed`.
Its full sidecar suite passed 947 tests (651.47 s, two dependency warnings).
The raw model run preceded `16c23e6` and must not be presented as a fresh model run of that commit.

## Integrating the counterpart change

`16c23e6` also allows a counterpart's given name without a stored alias when no other known full name
shares it. Replaying a negative control exposed a regression: when two characters explicitly own the
alias `무진`, the new name-part path re-added it after the existing ambiguity check removed it. This also
occurred when only the other character owned that alias. Both tests failed at the expected rejection.

The integrated check treats another character's explicit alias ownership as a blocker too. A bare
short-name entity still allows the unresolved split, as `16c23e6` intended. A distinct namesake known only
by that bare short name therefore remains a limitation; the check is a prerequisite, not identity proof.
It does not create an alias or join entities.

On the integrated source (`b054d160ac1730637fafd966da1aaf8d4e9c4ed74ac6ab470a805a9c6cb85d60`):

- Related tests: 59 passed, including the v15 pin, worker prompt delivery, real worker/API state checks,
  full-name collisions, persona handling, and both newly rejected alias-owner controls.
- **Offline replay only:** all 42 glass-garden replies still pass. The three preserved S1 resignation
  replies close the employment with their original hints; adding the conflicting alias owner blocks all
  three. No model calls or persistent sequential worker success are counted for this replay.
- A full-suite attempt from a flattened source snapshot could not locate migrations, causing 297
  failures and 118 setup errors. That runner setup is invalid evidence about product behavior. Its log
  is retained; the corrected run from the repository source layout passes **950 tests** (648.45 s,
  two dependency warnings).
- The actual sequential S1 extraction stopped at **88/240** after the move check failed. The earlier
  mentorship and eve-of-move checks passed. Input 863,423 / output 91,638 tokens; no errors or retries.
  The new generation had already joined the captain's names at turn 18 and both original split pairs
  by turn 33, confirmed by stored state readback. These alias successes did not make the move succeed.

## The sequential title omission and its correction

At turn 87 the model correctly reported R5 as ended now, with a TARGET quote. The stored counterpart
was `오봉순`, while the scene used `오 사장님`; earlier extraction had omitted the distinctive title alias.
The guard therefore rejected the ending. This is a missing alias upstream of the counterpart check,
not a wrong model ending or a packet-budget issue. In-memory replay with the previously measured v15
alias `오 사장` keeps the ending. That counterfactual is not a new model or worker success. The failed
copy, replies, stored readbacks and a complete archive are preserved.

At 88 calls this is within the owner's automatic-correction window. The v16 free-alias rule and closing
check now explicitly include a distinctive name-like title when the TARGET identifies that same person.
Shared generic titles are excluded; a character's unconfirmed identity claim stays a claim. The guard,
quote check and resolver do not change for this correction.

The new source SHA-256 is `13dd7d9d5028872a0051b638d4d7e958b63b6fc0e36d5350a2e4ad2b8117ee8e`,
the system SHA-256 is `6eea98fd21e8a0ad8cb40194b4b5d0bd47cefc2f791aca1b6f733675951d3548`, and the
generation is `extract-a5425536646f8cc3cc6fb6d80686bcbf`.

A fresh **54/54** probe passes: the unchanged original 14 cases x 3 plus four separately authored
follow-ups x 3 (`tools/scenarios/glass-garden-followup.json`). The follow-ups check a distinctive title,
a title shared by two people, an unconfirmed identity claim, and explicit employment termination when
a business closes but friendship continues. That last control passes 3/3; implicit closure without
an explicit ending remains outside its evidence. Input 283,320 / output 40,881 tokens, no errors,
retries or missing usage. Related tests pass 59/59; its full suite passes 950 tests (707.55 s,
two dependency warnings).

Sequential S1 restarts from its original input on a new isolated copy, 240 planned calls and initially
3,403,981 estimated input tokens (hints change as extraction proceeds). The fresh fixed-v15-hints
comparison is prepared for 1,440 new calls, 20,474,331 estimated input tokens, at most three concurrent
calls, no reused outputs. Both scenarios' known role cases now come first; inputs and gold stay fixed.
That comparison waits for sequential verification. A copied database runs the actual extraction
worker, stores assertions, and reads back the API and the read model through the scene. Reveal and
summary jobs and a live host are not run. That restart stopped at **87/240**, as described below.

## Preparing a move is still not moving out

The title correction's actual S1 worker stored the innkeeper's alias, but at turn 86 the model marked
packed luggage and a stripped bed as a completed ending. The same guest role was positive before the
turn and negative afterward in persistent readback. The accepted quote had no future word, so the
existing quoted-time check did not block it. The ending is premature: the character still spends that
night in the room and moves in the next turn. This is the model's time judgment, not an alias failure.
All 87 calls and the stopped copy's archive are preserved: input 853,016 / output 91,421 tokens, no
format errors or retries.

The system rule and final input check now explicitly distinguish packing, a stripped bed or farewell
gifts from completed checkout, and ask for the completed departure/termination itself. The same
`ROLE_COMPLETION_CHECK` is fingerprinted in the v16 system prompt and delivered by the actual worker.
It adds no parser heuristic. The new source SHA-256 is
`39a35eeba4f34edd919550271b89fd8aa3b5a49b7840e4ad65beaec0a9e9dcc0`, system SHA-256
`cc14ac3b8040d149408974baa31d430a8e73104fe8f7eb067a1ead7282ca8298`, generation
`extract-1ea447351329c1e64ab7e9f664e907b1`.

- The actual failed turn 86's context and stored hints, unchanged except for the new prompt: **3/3**
  fresh replies keep the guest role under the real normalizer/reconciliation check. Input 31,866 /
  output 3,096 tokens. This bounded comparison does not advance the stopped worker database.
- Original 14 glass cases plus four follow-ups, three fresh repeats: **54/54**, input 289,464 /
  output 41,682 tokens. Combined: 57 calls, no errors or retries.
- Related tests: **60 passed**. The final worker reminder regression failed at its missing-input
  assertion before the change; the v15 pin and the existing state checks pass afterward.
- The full sidecar suite passes **951 tests** (650.58 s, two dependency warnings); plugin tests pass
  196, typecheck and build pass. The fresh sequential S1 restart stops after 62 completed jobs, below.
  The 1,440-call comparison still waits for sequential verification.

The probe also needed a measurement correction: it previously removed every character claim before
entity resolution, while the product lets the resolver evaluate self-alias claims. It now passes all
valid rows to the real resolver and grades its accepted alias rows. A synthetic bad self-identification
wrongly passed the old probe and fails the corrected one; a valid self-introduction succeeds. Regrading
the title candidate's preserved 54 replies still passes all 54, without new model calls. The new 57-call
measurement uses the corrected grader. Product identity rules were not changed by this tool correction.

The diff-scoped self-review checked the identity/provenance risk, explicit conflict rejection, the
generation fingerprint, v15 isolation, compiler delivery, and unchanged quote and role reconciliation
rules. No schema, host, request path, default, or worker-order change is made.

## An address is not necessarily a name

The completion candidate (`6636ef3`) stops after **62 completed jobs / 64 attempts**. Turn 62 returns
an object with a comma after its last member twice, including its one retry. Code fences are tolerated
by the product parser and are not the cause. Input 631,905 / output 68,650 tokens; two format failures,
one retry. Both provider replies and the stopped database archive are retained.

Auditing that run also finds an identity defect at turn 34: Haram jokingly addresses Doyun as
`바다 박사님`, but the model records it as Haram's own alias. Production accepts self-alias claims;
the mistaken subject therefore matters. Persistent readback through turn 35 marks Haram ambiguous
and loses the previously established full/given-name join. Other bare titles were also over-extracted.
This is a wrong extracted fact, not a packet omission, and not evidence of an actual false merge.

The next v16 prompt distinguishes stable introduced names from casual or teasing addresses and bare
job/relationship titles, even when only one person is mentioned. A title alias must include a personal
name and be explicitly introduced as what that person is called. An honorific variant reuses the
existing alias spelling; the alias's subject is the person named, not the speaker. The closing check
also asks for valid JSON without a trailing comma. These prompt changes create a new generation;
the parser, identity resolver, schema, v15 and the role-ending checks remain unchanged.

The candidate source SHA-256 is `dcbbc3781156266a26a2fbcb3714834997a8d7b1a8e411f34eb7e53401364f04`,
system SHA-256 `258f7a43bfe3159f913f9ac2560d18b5bcc5684ab89525b371e2214fe0e22769`.
Related tests pass **60**. Two further synthetic negative controls cover teasing address ownership
and a bare job title; the original 14 cases and prior four follow-ups are unchanged. Bounded model
verification passes **69/69**: 20 independent cases x 3, plus three replies each to the preserved actual
inputs at turns 34, 62 and 86. Turn 34 checks that the teasing address creates no alias; turn 62 checks
JSON syntax only; turn 86 checks that the guest role stays. None writes to the old stopped database.
Input **426,798 / output 54,939 tokens**, zero errors, retries or missing usage. The source/system hashes
above pin this run; generation `extract-7e9f41da3278af76f30d8b6ffa5c646a` is new.

A fresh actual S1 backfill starts from turn 0 on its own copy, **240** planned calls and initially
**3,515,497** estimated input tokens. It stops after **63 completed jobs**, below. The 1,440-call
fixed-hint comparison waits; no full comparison or Q5(c) pass is claimed. The scoped review checked the
unchanged v15 path, fingerprinted worker input, preserved original probe cases and unchanged parser/
resolver rules. This remains high risk for identity/provenance and historical/current role state.

## A bare person description stays unconfirmed

The narrowed candidate (`b3795df`) passes its full sidecar suite, **951 tests** (652.44 s), and plugin
196 tests/typecheck/build. Its actual S1 worker still adds `추오월 → 영감` at turn 43, after the earlier
`추오월 → 추 영감` alias. A read of persistent state through turn 51 confirms that the full name becomes
ambiguous. The run is stopped after **63/240**, input **634,512 / output 69,971 tokens**, no format errors
or retries. Turn 62's previous JSON failure does not recur. The stopped archive and diagnosis are kept.

Two prompt-only candidates also fail on the same preserved turn 43. Descriptive-noun wording stops
after four calls (three turn-30 passes, then turn-43 failure; input 42,250 / output 3,457). Adding a short
synthetic Korean counterexample stops after two calls (one pass, then failure; input 21,846 / output
2,463). Neither runs the independent probe or sequential worker. No results are reused across prompts.

The next candidate adds a **v16-only normalization guard**. A character `also_called` with an exact bare
person label on either side is stored as `pending`, with reason `bare person description is not a
confirmed name`. It retains the source, raw reply and assertion; it cannot supply a canonical alias.
The finite Korean/English set covers common age, occupation and kinship descriptions, including
`영감`, `노인`, `선장님` and `old man`. It is included in the v16 prompt fingerprint, so changing the set
also changes the generation. It does not change the shared resolver or parser, v15, named titles such
as `최 선생`, full/given-name aliases, or the explicit `?description` path for an unnamed reveal.

This is deliberately conservative: even an explicitly introduced nickname equal to one of those bare
labels remains pending. The set is not a general semantic classifier or a guarantee against every
misleading description. The model still judges other aliases, and all benchmark identity gates remain.

The source SHA-256 is `8bf852f5da2046a02702269698e490df6c19816fd7b72b2879f7904bb94dd32b`, system SHA-256
`3337acb354a483486275d77ffdb2077a6f02e571c06d6ed38b872dacf155ed35`. Scoped tests pass **48**.
Six direct regressions fail on the old valid status. A real-worker regression reads back the retained
pending row and raw reply, and the API's unambiguous full/name-title pair. Disabling only the label
guard makes that regression fail at its pending-state assertion. Initial test-fixture errors (no closed
turn, then treating the entities API's list as an object) are preserved separately and are not product
failures. Fresh model and sequential checks are still required.

The guard candidate's 15 actual-input checks pass, but its independent run stops at the first qualified
title case in all three repeats: the model omits the alias, rather than the guard rejecting it. Total
**60 calls, 57 passes**, input 444,003 / output 48,121 tokens. The 14 original cases still pass 42/42.
This is a new omission, not a successful full correction.

The current wording explicitly allows a **surname** as the personal-name part of an introduced title,
and gives a short synthetic positive example with different names. It retains the exact bare-label
guard. The title and two new descriptive-noun cases run first to detect a recurrence sooner; every
case's input and expected result stay unchanged. All **66 independent samples** pass. The five actual
inputs (30, 34, 43, 62 and 86), three results each, also pass. Turn 62's third reply has a trailing JSON
comma; one separately retained same-input retry recovers it. Total **82 attempts / 81 passing results**,
input **592,225 / output 65,920 tokens**, one format failure, one retry, no unresolved error. Turn 62
checks syntax only; the remaining actual-input checks use the production normalizer.

Current source SHA-256 `9d3b0ce54af9ab6c1037b83ee6615776f11faaebd613016d5f4eb40d00940956`, system SHA-256
`1145964433355e3c7bbac40674338c357fe0417a21b080bacb0cea33bc215b5e`, generation
`extract-230b25a783b8b118584cce55e8b52cc3`. Scoped tests pass **48** (7.28 s, two dependency warnings).
A new S1 backfill starts at turn 0 with **240** planned calls and initially **3,756,085** estimated input
tokens. The harness now checks the three observed bad aliases at their turns; the preserved failing
rows fail those controls. Full tests after pushing and the sequential run remain pending; the fresh
1,440-call comparison has not started. The scoped review checks the pending-row provenance, exact
character-only matching, v15 isolation, generation fingerprint and unchanged resolver/reconciliation.

Local evidence stays under `/home/grantkim725/nmos-eval/pr251/2026-10-03/`:
`alias-fix-system-v1/`, `alias-fix-closing-v2/`, and `alias-fix-integrated-v3/` retain the distinct
candidates, hashes, raw replies, negative controls and logs. `RESULTS.md` links to actual files.
`sequential-alias-v3/` holds the stopped worker run; `full-alias-v3/` was prepared but made no calls.
`alias-fix-titles-v4/`, `sequential-alias-v4/` and `full-alias-v4/` separate the next generation's evidence.
`alias-fix-completion-v5/` preserves the final bounded checks; `sequential-alias-v5/` and `full-alias-v5/`
hold that candidate's executions. All three stopped sequential runs retain their original archives and
diagnoses. `alias-fix-scope-v6/` and `sequential-alias-v6/` separate the narrowed alias candidate.

## Bare-label set extended before the next full run

Review of `d870f33`: the exact-label guard lacked the forms of address role-play uses most, between
characters and toward a master or a guest, which are also the likeliest to be read as a nickname. The owner
paused the runs before the 1,440-call comparison, since any later change to the inlined set starts another
generation and another run. `BARE_PERSON_LABELS` now also holds 아저씨, 아줌마, 언니, 오빠, 형, 형님, 누나, 누님,
아가씨, 도련님, 주인, 주인님, 꼬마, 사부, 사부님, 대장, 대장님, and sir, madam, ma'am, miss, mister, kid, lady, lord,
my lord, my lady, young master, young lady, brother, sister, big brother, big sister (the English base forms
also with "the"): **60 → 107 labels**. Matching stays exact: `도경 언니` and `형준` remain eligible, pinned with
the new labels in `test_extract_v16.py`. The v16 system prompt grows by about **160 estimated tokens** (6,453 →
6,611) and the per-turn closing block by about the same. Scoped tests pass 82; no model call measured this
change. The earlier generation hashes above no longer describe the head.

## Match the ending to the listed residence (2026-10-03)

The preserved `d870f33` sequential run stopped after **145 completed jobs / 146 attempts**. Its diagnosis
and persistent readback identify **turn 88**, not the detection turn 144, as the first wrong ending:
the role was stated at turn 87; turn 88 furnishes the new attic and compares it with the former inn,
but the model marks that new residence ended and the worker stores a valid negative assertion.
Turn 144 emits no ending. The original replies, database archive and causal readback remain in
`sequential-alias-v10/s1-backfill-1/`; no result was replaced. The public handoff is
[PR #251's diagnosis](https://github.com/Sallos725/NMOS/pull/251#issuecomment-5967173862).

The owner approved a prompt correction: `ROLE_TARGET_CHECK` asks the model to match the listed role's
place and counterpart to the arrangement actually ended. Settling into a new role (unpacking,
furnishing, greeting neighbors) and comparison with a former home do not end the new residence.
An explicit termination still counts even immediately after the role was established. The check is
in both the fingerprinted v16 system prompt and the closing block after TARGET and the alias check.

The proposed previous-turn veto was withdrawn. A discarded ending is not automatically applied one
turn later, so the role can remain current indefinitely. Also, the listed turn is the latest positive
assertion's turn, which may be a restatement of an older role. Synthetic counterexamples reproduce
both limitations; they are not observations about the benchmark. No temporal veto or pending-role
mechanism is implemented. Parser, reconciliation, defaults and v15 generation stay unchanged.

The final candidate combines this wording with `3859ab7`'s **107 labels**. Using `packet.estimate_tokens`
with the formatted registry, system estimates are **6,453** (`d870f33`), **6,611** (`3859ab7`) and
**6,750** (combined). The added role check costs approximately **139 tokens** in the system prompt
and another **139** in a closing block when roles are listed; these are estimates, not provider usage.
Formatted system SHA-256: `57f74d1569f122d5335cc624aa711d308423a3e70d12882010c7fc97a188b1cf`.

Offline validation: the two focused files (`test_extract_v16.py`, `test_role_endings_target.py`) pass
**65 tests**. New synthetic worker cases capture the actual system/user prompts and read back both
a continuing residence and an explicitly ended next-turn residence through the API. Before the
patch, the settling case fails at the missing-rule assertion after state readback succeeds. The
v15 generation key stays unchanged against both earlier commits under the same test settings; v16
gets a distinct key. These checks prove delivery and deterministic handling, not model judgment.
The full sidecar suite passes **975 tests** in **656.98 s**, with no skips and two existing dependency
deprecation warnings. It runs the candidate's source with the existing Python 3.12 environment whose
`uv.lock` matches this checkout. No paid model calls are made by these tests.

Diff-scoped self-review: **high risk** for entity identity and current/historical role state. The combined
diff against `d870f33` retains the pending alias's raw evidence, preserves v15's prompt/key and the
existing reconciliation path, and allows an evidenced immediate ending. The new wording is fingerprinted
with the system prompt so older model results cannot silently stand in for this candidate. No schema,
request-path or fail-open code changes; real-model state correctness remains unverified.

**At implementation time, not yet run on this candidate:** model calls, sequential backfill, the full
1,440-call comparison and live acceptance. The next proposed action was to approve the exact bounded
call/token estimate for the preserved turn-88 input and controls for a normal next-turn termination, an older role restated immediately before its end,
and a different home's departure. Preserve every reply and inspect both raw endings and normalized
state. A passing bounded check precedes a fresh sequential copy; it does not complete the full gate.

## Bounded model check of `a1f4e81` (2026-10-03, 18:25 KST)

The owner approved model testing. This run freezes the source at
`a1f4e81c08f2ec407844e5190f8636b5152179bb` and uses the existing `gemma4:31b-cloud` route
(the provider reports `gemma4:31b`). It makes **12 calls**, one at a time, with **no retries**;
the planned input estimate is **124,713 tokens**, output forecast **12,700**, output stop budget
**20,000**. A wrong ending or format error stops the run immediately.

| Case | Input | Expected result | Fresh replies |
|---|---|---|---|
| Original turn 88 | Preserved story, context and hints; only the approved prompt blocks change | Keep the new residence; no listed role ends | 3/3 |
| Explicit next-turn ending | Authored control; role at turn 87, completed termination at 88 | End R1 | 3/3 |
| Older role restated immediately before its ending | Authored control; role introduced at 1, restated at 87, ended at 88 | End R1 | 3/3 |
| Former home ends, current home continues | Authored control; the same counterpart owns both homes | Keep the listed current residence | 3/3 |

**12/12 passed**, with **0 errors, 0 retries and no missing usage**. Provider-reported input is
**98,679 tokens**, including **83,008 cached input tokens**; output is **7,929 tokens**. Model request
durations total **40.096 s**. These are token counts and request durations, not a billing amount or
the preparation time. The three original-turn replies all return an empty `roles_ended`; the two
termination controls all name R1 as `now`, with a TARGET quote. The former-home control names no
ending. The same assertions also pass production normalization and role-history reconciliation.
No valid alias is produced in these cases; this is not a wider alias benchmark.

The previous prompt reconstructs byte-for-byte from its recorded input before the new prompt is
built. Before any paid call, the grader rejects the preserved wrong turn-88 reply and a deliberately
wrong answer to every control, and accepts the corresponding synthetic expected replies. Recorded
HTTP responses, parsed replies and grades are read back after execution; all 12 responses are HTTP
200 and the source hash is unchanged. The gold expectations never enter a model prompt.

Evidence is retained outside Git at
`/home/grantkim725/nmos-eval/pr251/2026-10-03/turn88-target-a1f4e81/`: `verify.py`, `snapshot/`,
`manifest.json`, `cases.json`, `system.txt`, the original prompt/reply, each call's prompt, HTTP body,
reply and grade, and `summary.json`. Source SHA-256:
`746112cd855d40920ce02320f03a5c73ca46da0b16c5b2573d844cee15186b5a`; runner SHA-256:
`8308c23c17f75d108b2b8d442e3c7dbdb9d452e994652e4959f97765c95d9762`.
The model/settings generation is `extract-4547e1d8ae60259ef55bbff1f48294da`; the system hash is the
combined candidate's hash above. The dry-run and `--execute` both exit 0.

This verifies the bounded role checks on fixed inputs, **not persistent sequential state**: the
benchmark database was read-only and no worker/backfill was run. Sequential S1, first-connection
behavior, the 1,440-call comparison, latency and the live gate remain open. Next is a fresh sequential
copy under this same generation, with the new residence checked at turn 88 rather than waiting
until turn 144; every failure and usage record must be retained. NMO-24 remains open.

## Sequential S1 on `a1f4e81`: turn 88 fails again (2026-10-03, 18:48 KST)

The owner approved one S1 backfill of **240 turns**, using the same immutable source snapshot and
`extract-4547e1d8ae60259ef55bbff1f48294da` generation as the bounded check. The initial input estimate
was **3,898,433 tokens**, output forecast **253,000**, output stop budget **320,000**; one call at a
time, no real format retries. The 1,440-call comparison was not started. Preparation restores the
unchanged baseline into a separate database and checks the 240 queued turns in story order.

**Verdict: defect.** The worker processes **89 jobs / 89 calls**, turns **0–88**, then the declared
turn-88 check fails and the runner exits **1**. This is not 89 successful semantic cases. The three
known bad-alias checks (30, 34, 43), mentorship continuity (74), eve of the move (86), and actual move
(87) pass. The new residence established at 87 is wrongly ended at 88. All 89 HTTP responses are 200;
there are **0 format failures, 0 retries, and no missing usage**. Turns 89–239 are not run.

| Measurement | Observed |
|---|---|
| Started / stopped (KST) | 18:43:11 / 18:48:30 |
| Elapsed to semantic stop | 318.977 s |
| Provider input | 1,020,111 tokens, including 510,656 cached |
| Provider output | 90,301 tokens |
| Sum of model-request durations | 318.628 s |

These are provider usage and elapsed measurements, not a monetary invoice. Remaining jobs stay
queued in the stopped isolated copy, with no worker continuing them.

At 88 the raw answer names **R1, `when: now`**, quoting a comparison with the former home rather than
a departure from the listed new residence. The worker writes a valid negative with the listed role's
exact value. The persistent view has the positive residence immediately before that turn and none
after it. A new read-only database connection reproduces both states and the directed residence
check fails independently. This is a model decision reaching stored current state, before retrieval;
there is no evidence of a missing prompt block. The recorded system and closing block both contain
`ROLE_TARGET_CHECK`, and the source, system and runner hashes match their pre-run values.

The TARGET and preceding context are identical to the bounded turn-88 case, but its input is not
identical: earlier fresh model results rebuild the entity and role hints. The fixed-input **12/12**
therefore remains a bounded result, and does not establish sequential correctness. This run does not
isolate which hint difference or model variation caused the recurrence. No new prompt, age veto,
pending-role mechanism, parser change, default change or paid restart was applied after the failure.

Before model execution, the directed grader rejected the preserved earlier failure and a synthetic
reverse-mentorship-only state, while accepting a synthetic retained residence. A simulated transport
self-test exercises one malformed response and one retry; its two simulated attempts are excluded
from every real-model count above. After the stop, all **583 source revisions** match the preparation
database verbatim, and all **481 active chat revision hashes** verify. The postmortem initially applied
the chat hash formula to every source type; the corrected read-only check and that tooling error are
both retained, with no model call or product change.

Evidence stays outside Git at
`/home/grantkim725/nmos-eval/pr251/2026-10-03/sequential-turn88-a1f4e81/`: the execution contract,
preparation, runner and its self-tests; all prompts, HTTP bodies, raw replies and stored assertions;
API and turn-bounded readback; failed checks; `s1-backfill-1/failure-diagnosis.json` and
`s1-backfill-1/stopped.nmos.zip`. A file-level integrity manifest verifies the preserved copy. Stopped
archive SHA-256: `f5b61a6b31cb0ef7bd862b1d010fc62d01d17165336be9b6082eb6441d3ca915`.
The original baseline and previous attempts remain intact.

Execution used the frozen snapshot's `apps/sidecar/src` on `PYTHONPATH` and the existing Python 3.12
environment to run `run_sequential.py --scenario s1 --mode backfill --repeat 1 --execute` (exit 1).
`diagnose.py` reopens the stopped database read-only, validates the stored failure and hashes, and
exits 0; its successful diagnosis does not turn the product verdict into a pass.

**Next:** an owner decision on the failed prompt mitigation, before another implementation candidate
or paid run, per Phase 28's wrong-role-ending stop condition. Use this newly preserved input when
assessing a follow-up; repeating the full sequence unchanged is not supported by this result.
First connection, the full comparison, latency and live acceptance remain unverified. NMO-24 stays
open and blocks NMO-7; the earlier 975 deterministic test passes do not override this observed defect.

## Offline prompt comparison and a confirmation experiment proposal (2026-10-03)

At the owner's request, compare the three preserved passing fixed-input prompts with the failed
sequential turn-88 prompt, with **zero model calls and zero database writes**. All three fixed-input
prompts are identical. The system, TARGET, context and **R1's parties, value and turn 87** match the
sequential prompt exactly. The former inn stay appears in neither role list. Other roles change from
five to three; entities, promises, threads and secrets differ. Neither list hits the eight-role cap.

Read-only reconstruction from each preserved database reproduces its recorded roles, and the whole
sequential user prompt rebuilds byte-for-byte. Replaying the same failed answer with either hint set
produces the same valid negative. Therefore no stale former-stay entry or R1 mapping defect is found
in this incident. This comparison does not prove which other hint difference or model variation caused
the failure. It supports no additional prompt patch or role-list implementation change by itself.

The owner proposed a separate short confirmation when the extractor says an ending is `now`, with
only TARGET and one role, and pending review on disagreement. The reviewable experiment is
[`ROLE-END-CONFIRMATION-EXPERIMENT.md`](../proposals/ROLE-END-CONFIRMATION-EXPERIMENT.md): exact prompt,
version 2 has fourteen unique inputs called once, fixed token bounds, unchanged quote/LATER checks,
and wrong-ending rejection paired with normal-ending `no` and total pending rates. Incorrect judgments
are recorded without stopping, per owner review. The 31 correct / 8 wrong historical observations map
to five distinct inputs; both S1 turn-233 full/given-name directions are also included. This supersedes
the unexecuted seven-input, three-repeat plan. It includes a raw
response census of six preserved sequential executions, with observed and extrapolated costs separated.
At proposal time no confirmation model call had run. The owner subsequently approved version 2;
the measured result is recorded below. Worker integration, pending review actions and ADR 0064
changes require a separate owner decision; the experiment does not authorize them.

Private evidence and full filled prompts are retained in
`/home/grantkim725/nmos-eval/pr251/2026-10-03/turn88-offline-confirmation-plan/` (initial diagnosis) and
`turn88-offline-confirmation-plan-v2/` (revised experiment and source snapshots). The source prompt
hashes, full diff, read-only reconstruction, parser replay and grading controls are preserved.

## Confirmation-only pilot: fourteen unique inputs (2026-10-03, 19:45 KST)

**EvidenceVerdict: defect** against the frozen pilot bar. The approved v2 calls complete **14/14**,
once each, with no transport/schema errors or retries. The runner exits **2 after completion** for
four nonpassing classifications; incorrect decisions and quote rejections do not stop the experiment.
Normal endings pass **8/8**, including both S1 turn-233 full/given-name directions: `no` rate and total
pending rate are both **0/8**. Non-endings give **2/6 valid no, 3/6 wrong accepts, 1/6 invalid quote**.
Turn 88 says no but supplies empty evidence. The other wrong accepts are the eve of moving,
mentorship continuing after a job change, and promotion without ending another employment.

Both valid rejections are authored controls. The preserved inputs alone have **0/4 valid non-ending
rejections, 3/4 wrong accepts and 1/4 invalid quote**. Their six normal variants cover only two scenes.
One accepted correct yes uses a verbatim but insufficient termination quote; quote presence does not
verify entailment. The unchanged verifier therefore lacks evidence for adoption despite low measured
normal-ending pending and token use. No actual pending-state persistence or review flow was tested.

Measured **8.545 s** elapsed (19:45:36–19:45:45 KST), **15,588 input / 501 output tokens**, including
832 cached input; median request 555 ms, maximum 1,059 ms. The provider reports `gemma4:31b` for
`gemma4:31b-cloud`. All raw HTTP bodies, requests, usage and grades are retained in
`/home/grantkim725/nmos-eval/pr251/2026-10-03/role-confirmation-v2-results/`. A zero-call fresh artifact
readback reproduces every grade and usage total and verifies frozen input/source hashes (exit 0).
The full case table, actual-scene/control split and cost projection calibrated from measured usage are
in [the experiment record](../proposals/ROLE-END-CONFIRMATION-EXPERIMENT.md#measured-confirmation-only-results-2026-10-03-1945-kst).

The fourteen approved calls are complete. Next is an owner decision on a different role-ending design;
no implementation or additional paid run follows automatically. NMO-24 remains open and blocks NMO-7.

## Follow-up preparation: rules and preceding context (2026-10-03)

The owner deferred v2 adoption and proposed keeping the termination rules and recent CONTEXT while
excluding other hint registries. The fourteen paired v3 requests were prepared with zero model calls;
ROLE/TARGET/gold/order are unchanged. The explicit turn-73 continuity is retained past the old
1,000-character context prefix. Input estimate 82,334, stop budget 90,568; the owner subsequently approved execution.
The offline sentence-LATER replay adds no rejection among located wrong quotes, retains all 31 historical
normal observations, leaves one v2 approximate quote unresolved, and exposes an authored false-withholding
case. No production guard changes. Full prompt, evidence-quality rubric, causality limits and source hashes:
[v3 proposal](../proposals/ROLE-END-CONFIRMATION-EXPERIMENT.md#version-3-proposal-restore-termination-rules-and-two-preceding-turns).

## Measured v3: correct labels, incomplete evidence (2026-10-03, 20:12 KST)

The owner-approved fourteen calls complete with **14/14 correct yes/no labels**, compared with 11/14
in v2. Wrong accepts fall **3/6 → 0/6** (86, 74, 99); normal acceptance stays **8/8**, normal pending **0/8**.
Four no replies have empty evidence (88, 74, 99, and the former-home authored control), so valid no stays
**2/6** and the unchanged full grader stays **10/14**. All cases finish before exit 2; no retry or technical
failure occurs. The bounded decision bar passes, but the required supporting-evidence contract does not.
Separate unblinded review records 6 supporting, 4 uncertain-completion and 4 missing quotes; it does not
change frozen gold or claim independent human validation. Full case outcomes and usage are in the
[v3 result](../proposals/ROLE-END-CONFIRMATION-EXPERIMENT.md#measured-v3-comparison-2026-10-03-2012-kst).

Actual input **49,165** / output **402**, elapsed **14.609 s**. Both raw artifacts and zero-call verification
are retained in `/home/grantkim725/nmos-eval/pr251/2026-10-03/role-confirmation-v3-results/`.
All fourteen ROLE/TARGET/gold/order pairs match v2; rules and context change together, so causality is
not isolated. Next: resolve the no-evidence and completed-ending evidence contracts before adoption.
No worker, generation or default change; sequential, full-comparison and live gates remain unverified.
