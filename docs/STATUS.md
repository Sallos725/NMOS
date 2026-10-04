# NMOS Status

## Current phase

**Phase 28 — A role that ends, and a name said two ways: approved 2026-10-03, current as a correction phase (AGENTS
§7 item 5); step 2 in review (#251).** Spec `docs/phases/PHASE-28.md` (under AGE-24; a correction found by measurement, not a
roadmap stage). The owner's live run on `e13dee7` met the real-chat target (S0main full-history memory cases 8/10,
10/10, 8/10) but not the combined no-regression gate (S1 final 21/25 → 19/25, S2 full history 22/25 → 20/25, S3
6/6 → 5/6, S4b 3/3 → 2/3 against the historical lane; single runs, aggregates only, the result files stay with the
owner). Two defects confirmed in its traces: a role stays current after the story ends it (the ending extracted as
another predicate, or in other words), and a full name and its given name resolve to two entities with separate
histories. Approved answers: `extract-v16` shows the extractor the roles in force (`CURRENT ROLES`) and ends one
by its number, written by the worker with the listed value (ADR 0013 unchanged), and links a character written in full and by part of the name as an alias
(Q4, decided after the first answer was measured; below); behind `NMOS_EXTRACT_COMPILER`, off by default, measured by
the owner (per-defect replays, an `extract-v16` comparison after an approved estimate, then live runs three times
each, medians and every run). Excerpt and ranking changes wait for that re-measurement. **High risk (AGENTS.md
§14)**: identity and provenance, current versus historical state, extraction generations, knowledge boundaries,
replay.
Step 1 the spec (#250). **Step 2 (#251, in review), off by default** — ADR 0064 (proposed), D73; `extract-v16`
(`NMOS_EXTRACT_COMPILER`; `extract-v15`'s key pinned unchanged): CURRENT ROLES and the alias of a name and its part
(the part checked on its own in the turn); `tools/eval_extract_sample.py --compiler`; deterministic cases in
`test_extract_v16.py`, the first-connection limit pinned. The first answer to Q4, a read-side join
(`given_name_join`), was measured by the owner on #251's head (nine preserved copies, 837 reads, no model call): no
join on any read, the S4b (2/3) and S2 (22/25) replays unchanged, since the split pairs occur together in the text of 3
and 20 turns but in no turn's assertions; withdrawn and removed before merge. The owner's `extract-v16` run on
`a5c888a` (S2's role-ending turns first; stopped at 39 of 1,440 calls by the stop condition): 0 of 6 listed roles
closed, the model giving the role's name without the listed description; the ending is now named by number (R1, …) and
written by the worker. Re-run on `4a7c11c` (22 calls): values exact, the employment ending 3/3 and the move 2/3, but the
stay ended on the eve of the move 3/3; each ending now states `when` and only one over in the TARGET turn ("now")
closes the role. On `37af724` (9 calls): eve kept 3/3 and resignation ended 3/3, the move 0/3 (a quote joining a CONTEXT
and a TARGET sentence with "..."); a joined quote now counts by its passage in the TARGET turn, at the same bar. On
`2e4ccfd` (9 calls): move 3/3, resignation 3/3, eve kept 2/3 (once "now" on a sentence about the next day); a quote
that places the change later (`LATER`) now closes nothing. On `162b515` (9 calls): eve 3/3, resignation 3/3, move 1/3
(twice quoting the previous turn's room assignment); the rule now asks for the TARGET turn's own words for what happens
there. On `c582343` the three checks passed 3/3 each, but the wider run stopped at 76 calls: a new job
wrongly ended a continuing mentorship at S2 turn 74 in 2/3 runs. The local correction clarifies that a job,
workplace or rank change does not itself end the relationship between the listed people. A 27-call remeasurement
kept that mentorship 3/3 and retained all three earlier checks (12/12 total); the sidecar suite passed 921 tests.
This is a bounded check with preserved v15 hints, not the complete Q5 (c) comparison or a sequential worker run.
Evidence and limitations: `docs/perf/extract-v16-role-continuity.md`. The owner also requested an independent story:
`tools/eval_story_probe.py` prepares 14 authored space-station cases, 42 calls for three runs; dry-run and nine
tool tests passed, with no model call on that new corpus. Next: the remaining Q5 (c) comparison, alias checks and
first-connection/backfill measurements; no default switch or acceptance checkbox is implied by this correction.
On `27c7658` the owner re-ran the core role checks (12/12 kept) and then every S2 turn that writes a known full name
and its part apart (27 turns × 3, 81 calls): no `also_called` at all, so the run stopped at 111 of 1,440 calls. Those
pairs are now listed to the model (NAME PAIRS, N1, …) and confirmed by number (`same_names`), the worker writing the
alias (ADR 0064 item 2). `LATER`'s 내주/내달 now count only as nouns, not inside 내주다/내달리다. On `0abb2fd` (90
calls): roles 12/12; the pairs were listed on 21 of the 27 turns, but 46 of 63 answers named a pair by its names
instead of its number and were refused (no alias kept, none wrong); the prompt now asks for the number, shown for N1.
On `073b7a1` (S2, 30 scenes × 3): both name pairs joined 3/3 (all answers by number), core roles 12/12, but turn 99's
bakery promotion ended the role toward the inn's owner in 2/3 runs (13/15 with it); the role rule and closing line now
say a new role or promotion toward someone else never ends a listed role toward a different person.
On `ed10842`, the same wrong ending persisted in 2/3 runs; stopped at 41 calls. The correction now requires the
listed counterpart's name or an unambiguous known alias in the shown TARGET, not merely in old hints. A quote-only
name check was rejected by offline measurement: it would also drop all 31 measured correct endings. Replaying
the actual guard keeps those 31 and rejects the eight known wrong endings. A fresh 90-call S2 probe passes the
five role checks in all three runs (15/15); both name pairs resolve in every run (6/6). The model still proposes one
wrong turn-99 ending, now blocked. Three further endings at the school departure (turn 219) are outside those core
checks; fixed v15 hints do not establish their true ending time. This is not the full Q5 (c) or a sequential v16
worker/backfill verdict. Evidence, tests and conservative misses: `docs/perf/extract-v16-role-target.md`.
The wider `f747f4f` comparison stopped at 507 successful samples (509 attempts, including two recovered JSON
format errors): S2 turn 144's shop closure incorrectly ended the resident's stay in 3/3 runs. The first divergence
is the model's role-ending decision, before retrieval. The system rule and closing reminder now distinguish
business closure from residence or mentorship, and check continued access at the end of the TARGET. A fresh
24-call check passes all six role cases (18/18) and both name joins per run (6/6); system-only wording had still
failed 2/3. Evidence and the JSON diagnosis: `docs/perf/extract-v16-role-closure.md`. The owner authorized a new
full run, preserving every result, with correction and restart for a defect found within its first quarter.
The fresh `7dbef46` comparison stopped at 739/1,440 samples (743 attempts; four recovered JSON errors).
S2's six declared role cases pass 18/18, S1's 15/18: the S1 resignation model output is correct under the
declared check, but the fixed v15 hint lacks the captain's full/given-name alias and the counterpart guard
rejects the endings in all three repeats. Separately, the independent glass-garden model probe passes its
first 24 role samples, then misses the explicit alias in sample 25; 17 samples remain unrun. Both are
criteria misses, not full acceptance. The failure is beyond the owner's 360-sample automatic correction
window; no further production patch or full restart was made. Evidence and isolated counterfactuals:
`docs/perf/extract-v16-fixed-hints-and-glass.md`. Sequential copies and a three-call concurrency cap are
prepared, with zero sequential model calls. Next: decide the follow-up for missing alias extraction and
measure whether sequential v16 hints resolve the conservative ending miss; no default change.
The counterpart check now also counts the counterpart's given name alone when no other known full name shares it
and it is not the persona's (ADR 0064 item 1), which is what blocked S1's resignation; not yet measured.
The owner then approved missing-alias correction, sequential verification and a fresh comparison capped at
three model calls. The v16 free-alias rule and closing check pass the unchanged independent glass-garden
probe 42/42 (no hints added); system-only wording had still missed the first name case 2/3. The new counterpart
path also needed a known-alias conflict guard: it had re-added a short name explicitly owned by another
character. Related tests pass 59/59; integrated offline replay keeps glass 42/42, closes the preserved S1
resignation 3/3, and blocks conflicting alias ownership 3/3. These replays are not new model or sequential
successes. The corrected full suite and sequential worker comparison are in progress; no default change or
Q5 completion. Evidence and the preserved runner migration-path error: `docs/perf/extract-v16-alias-reminder.md`.
Follow-up: that corrected suite passes 950 tests, but actual sequential S1 stopped at 88/240. It stored the
three intended name joins, then missed the move because the innkeeper's distinctive title alias was absent.
The v16 prompt now explicitly retains an evidenced distinctive title, without accepting a shared generic
title or promoting an unconfirmed identity claim. The unchanged original probe plus four separate controls
pass 54/54, including explicit employment termination despite continued friendship (3/3). Related tests
pass 59; a fresh full suite and sequential S1 are running. The new full comparison is prepared, not started.
That title candidate's suite passes 950 tests, but sequential S1 stops at 87/240: packed luggage and a stripped
bed are incorrectly marked as checkout on the eve of the move. A fingerprinted final completion check now
distinguishes preparation from a completed ending. The identical failed input passes 3/3 fresh calls; the
independent cases pass 54/54, related tests 60/60. The probe's resolver input was corrected to include valid
self-alias claims as production does; the earlier 54 replies still pass on regrading. That full sidecar suite
passes 951 tests; plugin tests 196, typecheck and build pass. Its sequential restart stops at 62 completed
jobs / 64 attempts: turn 62 has a trailing JSON comma twice. Audit also finds a teasing address wrongly
recorded as the speaker's own alias, making a correct full/given-name join ambiguous in stored state.
The next v16 prompt limits titles to explicitly introduced names containing a personal name, excludes
casual addresses, distinguishes the person named from the speaker, and asks for no trailing JSON comma.
Related tests pass 60; bounded model verification passes 69/69 (60 independent samples plus nine fresh
replies to the actual failed inputs; the three turn-62 replies check syntax only). Input 426,798 / output
54,939 tokens, no errors or retries. Fresh sequential S1 restarts from turn 0 under its new generation.
That candidate (`b3795df`) passes 951 full sidecar tests and 196 plugin tests/typecheck/build, but its worker
stops after 63/240 when a narrated bare age label (`영감`) makes an existing name ambiguous. Input
634,512 / output 69,971 tokens, no format errors or retries. Two further prompt-only candidates fail on
the preserved input after four and two calls. A v16-only guard now retains an exact bare person-label
alias as pending, preserving its raw reply and assertion. Its finite Korean/English set is fingerprinted
with the new prompt; even a nickname identical to a listed bare label remains pending. Named titles and
the `?description` reveal path still work. Scoped tests pass 48, including persistent worker/API readback
and a mutation that disables the guard. New model and sequential verification are in progress.
Paused by the owner before the next full run to extend the set with the forms of address role-play uses most
(아저씨, 언니, 오빠, 형, 누나, 아가씨, 도련님, 주인님, 꼬마, 사부, 대장, sir, my lady, young master, …): 60 → 107 exact
labels, a new generation, about 160 more system-prompt tokens; not yet measured (ADR 0064 item 2).
The first guard candidate misses the qualified title in all three independent repeats (57/60 total),
so the prompt now explicitly allows an introduced surname-and-title name and gives a synthetic positive
example. The new candidate passes 66 independent and 15 actual-input results: **82 attempts / 81 passes**,
input 592,225 / output 65,920 tokens, one trailing-comma failure recovered by one same-input retry.
Scoped tests pass 48; a fresh S1 backfill restarts at turn 0 (240 planned calls, input estimate 3,756,085).
The 1,440-call comparison still waits. All stopped copies are preserved; no parser, resolver, default or
Q5 gate changes. Details and limitations: `docs/perf/extract-v16-alias-reminder.md`.

The preserved `d870f33` sequential run stopped at 145 completed jobs / 146 attempts. Its first wrong
residence ending is turn 88, while settling into the new attic and comparing it with the former inn;
turn 144 only exposed the already-missing role. The owner approved a prompt correction together with
the 107-label set: match the listed role's place and counterpart to the arrangement actually ended,
and distinguish settling in from leaving. Explicit next-turn endings remain allowed; a proposed
previous-turn veto was withdrawn because a discarded ending need not be stated again. No pending-role
mechanism is added. The final v16 prompt is a new generation; v15 stays unchanged. Model verification,
sequential restart and the full comparison remain pending; the earlier passing replies do not verify
this candidate. Focused tests pass 65 and the full sidecar suite passes 975; validation and the bounded
next check are recorded in the same perf note.
The owner-approved bounded model check of `a1f4e81` then passes **12/12**: three fresh replies to the
preserved turn 88 retain the new residence, and three repeats each of explicit next-turn termination,
an older role restated before ending, and a former-home departure pass. Input **98,679** / output
**7,929** tokens; no errors or retries. This is fixed-input model output and production postprocessing,
not a fresh sequential worker run. The owner then approved a new S1 sequential copy under that same
generation. It stops at **turn 88 after 89/240 calls** (0-based turns 0–88), with **0 format errors or
retries**: the model again ends the new residence using a comparison with the former home. The worker
stores the negative, and a fresh read-only connection confirms that the residence is absent. The new
rule is present in both prompt blocks; the target/context match the bounded case, but sequentially
rebuilt hints differ. Thus the bounded 12/12 does not establish sequential correctness. Input
**1,020,111** / output **90,301** tokens; **318.977 s** to the stop. Raw replies, the stopped database
archive and causal readback are preserved. No correction or paid restart follows this failure.
The requested zero-call comparison rules out a stale former-inn role or mismatched R1: both inputs
list the identical new residence as R1, and both role lists rebuild from their respective databases.
The surrounding hints differ; causal sensitivity is not established. A proposed confirmation-only
experiment freezes TARGET plus one role and reports wrong-ending rejection beside normal-ending
pending rates. After owner review, version 2 uses **14 unique inputs once each** (8 normal, 6 non-ending),
including both S1 turn-233 directions with the full/given-name mismatch. The historical 31 correct and
8 wrong observations collapse to 5 unique confirmation inputs; all sources are mapped, not counted as
39 new cases. Semantic mistakes are recorded without stopping; only technical errors, changed hashes
or budgets stop the probe. The owner then approved it; **all 14 calls completed at 19:45 KST** with
no technical errors or retries. Normal endings pass the frozen grader **8/8**, including both S1
turn-233 directions; normal-ending `no` and total pending rates are **0/8**. Non-endings yield **2/6 valid
no, 3/6 wrong accepts, 1/6 invalid quote** (turn 88 returns no with empty evidence). Both valid rejections
are authored controls; preserved non-endings alone yield 0/4 valid no and 3/4 wrong accepts. One correct
yes also quotes text that does not itself establish termination; the frozen matcher does not check
entailment. **The pilot bar is missed.** Input **15,588** / output **501** tokens, elapsed **8.545 s**;
the exit code is 2 after all cases, not an early technical stop. The unexecuted 21-call plan remains superseded.
Six preserved sequential runs supply observed call counts; the new pilot usage calibrates explicitly
projected per-240 token costs. Spec, results and evidence: `docs/proposals/ROLE-END-CONFIRMATION-EXPERIMENT.md`.
The owner proposed restoring the existing role-ending rules and recent CONTEXT while excluding other
hint registries. V3 was prepared with the same 14 ROLE/TARGET pairs and full preserved preceding two turns
(the detailed turn-73 continuity exceeds the old 1,000-character context prefix), then approved separately.
All **14 calls complete at 20:12 KST**: decision labels **14/14**, wrong accepts **0/6** (v2: 3/6), normal
acceptance **8/8** and normal pending **0/8**. Valid no remains **2/6** because four no replies have empty
evidence (88, 74, 99 and the authored former-home control). The frozen grader stays **10/14**; all cases
run before exit 2. Separate evidence review marks four accepted resignation quotes as uncertain about
completion timing. Input **49,165** / output **402**, elapsed **14.609 s**, no errors or retries; request,
source and paired ROLE/TARGET hashes verify. The bounded decision bar passes; the evidence contract does not.
An offline sentence-LATER replay blocks no additional located wrong ending, including turn 86; one v2
quote cannot be located exactly, and a declared synthetic control exposes false withholding. Keep the
original guard for primary scoring and separately grade quote support/weakness/uncertainty. V3 supports
the revised direction on this sample without establishing causality or sequential correctness.
After owner review, the experiment contract requires a valid TARGET quote for yes and makes the no
quote optional. A zero-call regrade preserves all yes outcomes: **v3 14/14, v2 11/14**; the four absent
no quotes are now allowed, while uncertain yes evidence remains separately recorded. The owner separately
approved the **17-call** follow-up: **17/17 pass at 20:36 KST**, new-story diversity **5/5** and previously
used glass regressions **12/12**. Normal acceptance **8/8**, normal pending **0/8**, wrong acceptance **0/9**;
all eight yes quotes are literal and support termination in the recorded review. Three optional no quotes
are absent. Input **14,440** / output **478**, elapsed **9.436 s**, no errors/retries; frozen prompt, requests,
source hashes and fresh artifact readback verify. This is a short synthetic probe, not a sequential verdict.
Next: decide ADR 0064/phase amendment and v16 worker adoption scope before a fresh sequential S1 check
at turn 88. A pending-role review flow remains unimplemented.
First-connection, full-comparison and live gates remain open; NMO-24 still blocks
NMO-7. No default or generation change follows from recording these results.
Implemented after the owner's handoff (ADR 0064 item 4): under `extract-v16` each listed ending that passes the
existing checks is confirmed by one more call with the measured v3 prompt (ending rules, the role, the two preceding
turns whole, the TARGET; no other hints). Only a yes quoting the TARGET ends the role; a no, an invalid answer, a
quote check failure or a failed call holds it as a pending row (`role ending not confirmed: …`) with the first reply
and every confirmation kept in the extraction's raw record; usage sums them, kept apart under `confirm`. A new
generation (the confirmation is in v16's fingerprint); `extract-v15` unchanged. A held normal ending keeps the role
current; a review item is not implemented and not an approved policy. Tests use stand-in models only. Next: the
owner's fresh sequential S1 from turn 0 under this generation, with turn 88's stored state read back.
The owner's review of `62f10d0` found a confirmation reply that was not valid JSON lost its text and usage, and
replies were cut at 4,000 characters; corrected (the client's `ReplyError` keeps what came back and the call's usage;
replies are kept whole), with tests through the real client and a fresh database read. No model call; the
confirmation request has no output-token limit (the experiment's 512 was its own envelope).
The owner's review of `17f3900` found an error status (HTTP 400 or above) whose body reports usage counted the
call but not its tokens; the client reads usage from such a body now (none stays "not reported"). Client-only: the
generation key is unchanged.
The owner-approved fresh sequential S1 on `4e76c70` completed all **240 jobs / 247 calls**
(240 extraction + 7 confirmation) in **1,036.248 s**, with no technical errors or retries.
The seven declared role scenes pass: turn 88's wrong cleaning-as-ending candidate is held pending,
its residence survives a fresh DB read, and normal ending gold closes **2/2 scenes (3/3 roles),
pending 0**. But final name joins pass **1/3**, so the run exits 1, an accuracy failure.
The joins existed initially: a wrong `백이안 → 곽 조합장` alias at turn 81 breaks one; the legitimate
`윤하람 → 람이` alias at turn 182 makes the other ambiguous under the existing resolver's
multiple-neighbour rule. Read-only per-scene counterfactuals confirm the triggers; no rows were
changed. Other misattributed aliases at 200/237 and an uncertain sponsorship ending at 227 need
review. Input **2,901,339** / output **257,567**, confirmation separately **32,527 / 242**;
provider counts and stored totals agree on fresh readback. Next: alias attribution and legitimate
multiple-alias resolution review, not another model run. First connection, full comparison and
live gates remain unrun; v15 stays default. Details and limits:
`docs/perf/extract-v16-alias-reminder.md` (fresh S1 with worker confirmation). The owner-authorized
81/182/200/227/237 excerpts, preserving original/stored directions and actual entity hints,
are in `fixtures/model/phase28/2026-10-03-s1-confirmation-review/` for independent review.
Claude's review of those excerpts and the owner's decisions (2026-10-03): turns 81 and 200 joined a known character
the turn never names; under extract-v16 a known name now stands in only for a `?` description or a character the turn
writes another way (ADR 0064 item 2; offline on the preserved rows: 81 and 200 pending, 182 valid, 237 not caught).
Turn 227 is a wrong ending (the quote ends the patron's office, not the patronage); the confirmation prompt gains one
paragraph (v4, ADR 0064 item 4). Both are a new extract-v16 generation. The owner-approved **32-call v4
re-measurement on `443a5c4` passes 30/32 but fails its acceptance bar** (23:56 KST): original fourteen 13/14, additional seventeen 17/17,
turn 227 0/1. The patronage still ends on a quote of imprisonment; one normal captain-to-navigator ending
is withheld. Wrong acceptance **1/16**, normal pending **1/16**; turn 88 remains no. Input **71,382** /
output **894**, **23.791 s**, errors/retries 0, estimated **$0.01035108** without cache discount.
Source/request/response/usage readback and production grading agree; related tests **78 passed**.
Quote quality is reported separately (yes: Supports 10, Weak 4, Uncertain 2). See
`docs/proposals/ROLE-END-CONFIRMATION-EXPERIMENT.md` (v4 results). **Stop before fresh sequential S1**:
Claude reviews the two preserved failures; no automatic prompt revision or additional paid run is approved.
An alias confirmation for names the turn allows (237) and the resolver's treatment of one person's two names (182, ADR 0012) are NMO-35:
outside Phase 28, before 0.3.0, the resolver last. The implementation used no model calls; the subsequent
measurement above used 32.
Owner decision on that review (2026-10-03): **v4 withdrawn, v3 restored** (31/32 on the same inputs). The 227 class
(an arrangement ended on the counterpart's arrest, fall or loss of office) is a known, counted wrong ending that no
longer stops a run on its own (ADR 0064 item 4, PHASE-28 stop conditions). extract-v16 is still a new generation by
the alias rule. Next: a fresh sequential S1 from turn 0 on this head, with the owner's approval and budget.
Design review after v4 (Codex's recommendation; `docs/proposals/ROLE-END-REVIEW.md`): one model cannot be made exact on
endings, and a held ending only catches a disagreement. Owner decision, implemented (PHASE-28 Q7): the Inspector's
"Needs attention" lists every role ending applied in the last 30 turns (retract to keep the role) and every held one
(restore to end it at its turn), with existing repair kinds, no migration, no model call. Whether PHASE-28's
zero-wrong-ending condition becomes a counted ceiling is still the owner's to decide.
Owner decisions the same evening: the stop condition is now a ceiling (at most one wrong automatic role ending per
run, each counted; a new kind still stops, PHASE-28). And S1 turn 182 is fixed for extract-v16: a part checked apart
no longer makes its full name ambiguous (ADR 0012 amendment), so 윤하람 / 하람 / 람이 are one person and 237's wrong
alias leaves only 람이 ambiguous; extract-v15 resolves as before. Accepted cost: one wrong alias beside a full name's
part now joins. The next fresh S1 is the owner's (run by Codex) with an identity gate of 3/3.
Codex's S1 on `c0b0a5b` (2026-10-04, `docs/perf/extract-v16-c0b0a5b-sequential.md`) stopped at turn 233 (a
resignation called `planned`, its reverse left out) with names 2/3 (turn 200's `윤하람 → 도도`, NMO-35); its retry
stopped at turn 117 on the experiment's 4,096-token output cap. Owner decisions (2026-10-04): an ending marked planned,
and the reverse of an ending, are asked of the confirmation and held for the owner on a yes, never applied (PHASE-28
Q7 amendment, ADR 0064 item 4); the next S1's experimental output cap is **8,192** tokens per main call (production
sends none), recorded as a changed condition. More confirmation calls than the earlier 32-call ceiling assumed.
The S1 on `4cc7ddd` (generation `extract-ba2d952e57b5e468cef813c6e6f52273`, 8,192-token cap,
`docs/perf/extract-v16-4cc7ddd-sequential.md`) is **incomplete**: it stopped at turn 62 after 62/240 jobs and 63 calls
(701,043 input / 65,299 output, about $0.124 uncached) on a reply with a trailing comma (`"hidden_from": [],` before
`}`); 0–61 had eight correct aliases, no role ending, names 3/3 at 61. The same comma at the same place broke turn 62 in
every earlier run that reached that state, a same-input retry included, so the worker's retry could never pass it. A reply is now parsed without a comma that ends a list or an object, outside
strings, and only after the strict parse failed (`llm.without_trailing_commas`): replaying 1,329 preserved replies,
1,323 parse exactly as before, the five turn-62 replies now parse, and a reply cut by the output cap still fails. No
prompt or fingerprint changes, so no generation key changes (`extract-v15`'s included); the raw reply is kept as it came.
The owner's fresh S1 on that fix (`8fe66d1`, same generation and envelope, `docs/perf/extract-v16-8fe66d1-sequential.md`)
completed 240/240 turns: the declared role scenes pass 7/7 (233's resignation applied in both directions, 88's wrong
ending held by a confirmation no), 6 endings applied, 1 held, 1 planned doubt dropped (158), no wrong ending, no false
join; but names 2/3 at 239, the turn-200 alias `윤하람 → 도도` recurring (NMO-35). 248 calls, 2,906,444 input /
255,349 output, about $0.509 uncached, 18 min 20 s. No reply needed the comma fix (turn 62's input differed).
Phase 29 step 2 (NMO-35; spec #256, approved 2026-10-04), on this branch: inside `extract-v16`, a free character alias
that would newly join two names is confirmed by one more call about those two names (ADR 0064 item 2 amendment); a
held alias is pending, joins nothing and is listed under Needs attention. A new `extract-v16` generation; `extract-v15`
unchanged. The fixed-input probe passed 60/60 ($0.023; `docs/perf/phase29-alias-confirmation-probe.md`). Owner decisions
the same day: a held alias in Needs attention carries the owner link (Q5 A, a plugin change), and under extract-v16 the
presence check reads a Hangul or Latin name only as a word of its own (no stored S1 row changes). The fresh S1 on the
new generation then passed (`9aa7c57`, `extract-b88669ca66664b77df6ac117d741ea8e`,
`docs/perf/extract-v16-9aa7c57-sequential.md`): 240/240 turns, **names 3/3, role scenes 7/7**, no wrong ending, no false
join; at turn 200 the main reply wrote `윤하람 → 도도` again and the alias confirmation held it (no); 250 calls, about
$0.509 uncached, 19 min. One development story only: S2, the independent probe, the 1,440-call comparison, first
connection, the 10k gate and the live runs remain.
Thirteen independent synthetic scenarios from the owner's diversity pack, through the worker on `9aa7c57` (live lane,
`docs/perf/phase29-diversity-smoke.md`): 12/13 pass the expectations fixed before the run; R04 fails by a naming error in
those expectations (the stored state is right, a post-hoc regrade passes); no wrong ending, no false join; $0.049.
Q5 (c) on S1 (`docs/perf/extract-v16-q5c-s1.md`): the fixed-input comparison (S1 × 3 on the v15 hints, two workers)
passes 21/21 declared role checks with names 3/3 in every run, no wrong ending, no false join ($1.54); it found that a
`?description` revealed by name was always held, fixed in `cd68657` (`extract-v16` now `extract-ccb3d153…`). The
first-connection lane (newest first) gets 4/7 and names 1/3 with no false join: no turn sees any earlier role or name,
so the corrections do not apply to a long chat NMOS sees for the first time ($0.47). Backfill, how an existing chat
re-extracts, is the passing sequential lane. A change to first-sight order is the owner's decision.

**No other phase is current.** Phase 23's final owner check passed on Windows and Mac (2026-10-02); the small
dashboard Refresh follow-up is recorded below. Stages 7–8 remain unauthorized.

**Phase 27 — The excerpt lands on the answer (`packet-v11`): approved, measured and complete 2026-10-02, not
released.** Spec `docs/phases/PHASE-27.md` (AGE-31 under AGE-24; a correction found by measurement, not a roadmap
stage, run beside Phase 23, then current, as Phases 24 and 25 were; the owner's order: before 0.3.0, AGE-7).
From the diagnosis of draft PR #241: the request often retrieves the
message that holds the answer and excerpts another part of it. Two rules in a new packet policy: a message found by a
word route and by vectors excerpts within its vector chunk, and a why or contents question grows its excerpt by
characters (320) instead of four sentences; the prototype's one-case rules and passage embeddings stay out. The
review of #242 measured the other suspected cause, the embedding chunk cap: the M0 main packets are the same under a
cap of 24. Step 1 the spec (#243). Step 2 the implementation behind `NMOS_PACKET_POLICY` (#245; ADR 0063, D72; twelve
deterministic cases; the tie-break anchor as the recorded recall option `excerpt_anchor`), measured by the owner on
#245's head with both anchors (#246, `docs/perf/answer-span.md`: twelve sets, three runs each; the M0 main scores the
same in every run, a few other sets varying by one case within the bound):
the M0 main cases that need memory with vectors `packet-v10` 16/23, `packet-v11` with today's anchor 18/23, with the
question's keywords 19/23 (without vectors 14 → 15 → 16); forbidden phrases over the twelve sets 93 → 96 → 87; no set
worse by more than one case; no set's median packet size larger by more than 0.11 % (main, within the 5 % bound),
sample 2's smaller (−14.88 % with vectors, −6.96 % without).
Step 3 (the owner's two decisions, 2026-10-02): **Q1b, the keywords anchor** (today's anchor met a stop condition,
the forbidden rise); **Q5's size bound one-sided** (smaller packets allowed: the rules bound excerpts below
`excerpt_chars` by construction, and the case and forbidden criteria caught no loss); **`packet-v11` the default**,
`packet-v10` kept as `NMOS_PACKET_POLICY=packet-v10`. Every acceptance criterion met: the latency one by
`tools/bench_story.py 10000` (three rounds a side: p50 218.9 ms under `packet-v10` against 211.5 under `packet-v11`,
the rounds overlapping). The owner's live run that followed, and the Phase 28 it led to, are above.
**High risk (AGENTS.md §14)**: memory selection (what text an excerpt shows; pinned by `test_packet_v11.py`,
`test_packet_v10.py`, `test_memory_eval.py`; recorded requests replay as they were) and K39 (the cue growth within
320 characters; noted there).

**Phase 22 — A re-extraction that keeps what it found: approved and complete 2026-10-01, not released.** Spec `docs/phases/PHASE-22.md`
(AGE-25 under AGE-24, an urgent correction found by measurement): "Extract all history" asks a small reveal check
instead of extracting again a turn extracted before an earlier turn's secret (K29), and a narrated fact a
re-extraction of the same generation dropped is listed in "Needs attention" with a Restore repair (`fact_restore`).
The owner chose the direction (Q1) and accepted every proposed answer (Q2–Q8), among them one row per dropped fact
with its own Restore and the same generation only in the panel. Step 1 (the spec) done. Step 2 (ADR 0057, D66,
migration 0028): "Extract all history" queues a reveal check (kind `reveal`) for each turn extracted before an earlier
turn's secret and keeps its extraction; a check lists the turn's OPEN SECRETS and answers `secrets` only, and its
`learned` rows are served while the extraction it checked serves the turn; the chat's coverage counts checks. No
plugin change. Amended after a post-merge review (ADR 0057 amendment 1): a check is asked again when it listed a secret
an earlier turn found out (either finishing order), and a turn's latest check is served, not its generation's latest
activation (replays unchanged by an activation). Step 3 (ADR 0044 amendment 3): a narrated fact a re-extraction of
the same generation dropped (matched one to one with the new rows; held nowhere else in memory) is listed in "Needs
attention" with **Restore**, counted on the panel's chat card and by `GET …/dropped`; `fact_restore` adds it back as
the owner's version at its turn while the turn reads the same, and applies to the story's row when the turn states it
again. A new plugin build. Step 4 (`docs/perf/reextract-loss.md`, `tools/reextract_loss.py`): listed now, 31 on the
M0 main chat (AGE-25's occupation among them), 24 and 95 on the bench's other chats, 0 on the restored production copy
(its re-extractions were under generations no longer serving; the spec's 106 counted those) and 66 on that copy
re-extracted with `extract-v14`; on the damaged M0 copy the occupation restored passes AGE-25's case and Undo fails it
again. The paid run (the owner's OK for 68 calls, `gemma4:31b`): no extraction discarded, 324k input and 1.5k output
tokens against the press's 727k and 85k, M0 main 36/40 (as before the press, the damaged copy 35/40), AGE-25's case
passed; the checks found every reveal the press found of the secrets both read the same way but one, which reads as
the press's false positive (a plan carried out, not found out): that criterion missed as written, and the owner
accepted it (2026-10-01). Keeping a re-extraction's dropped facts automatically (the owner's option 3): not now (owner,
2026-10-01; K29 no longer re-extracts and Restore is there). Phase 22 complete. Latency at 10,000 messages unchanged (fact read p50 105.2 → 105.9 ms). High risk (AGENTS.md §14): stored data,
re-extraction and owner repairs.

**Phase 21 — "At first": how it started, when the message asks: approved and complete 2026-10-01, not released.** Spec
`docs/phases/PHASE-21.md` (AGE-26 under AGE-24, a correction found by measurement): a message with a first cue (처음,
최초, 예전, 원래, "at first", …) gets the oldest of several similar events and a standing fact's earlier versions that
the chat window no longer holds. The owner approved every proposed answer (Q1–Q6) and asked that a model call
classifying the message be reviewed later, outside this phase. Step 1 (the spec) done. Step 2 (ADR 0056, D67): the cue
(`facts.FIRST_CUE`), events mentioned first and then oldest with no lexical bar for `minor` ones, equal scores to the
older fact, a standing fact in the window kept when an earlier version starts before it; recorded as `first_cue`, off
in a replay of an older trace. Ordered by whether an event is mentioned, not by the mention's score (which carries a
secret's or the persona's bonus): the M0 main case passes only so (replays: 6/10 → 7/10). After review, an earlier
version counts only when the prompt does not hold it (a canon statement whose key the prompt held does not) and every
such version has the current one's knowledge marks (K42): the `extract-v14` copy's first-cue probes 6/8 → 7/8, the
eighth's first version is the persona card the prompt holds. No migration, no plugin build. K42, found in that
review (earlier versions printed under the current version's knowledge marks, since `packet-v5`), fixed at the owner's
request (ADR 0038 amendment 1, recorded as `history_marks`): no case of any set changes. Step 3
(`docs/perf/first-cue.md`): every criterion met — M0 main 6 → 7 of the 10 cases that need memory, the restored copies'
first-cue probes 5/5 and 6 → 7 of 8, the synthetic 25-case sets unchanged (23, 24), no new forbidden phrase; retrieve
p50 at 10,000 messages +1.9 ms without the cue and +1.2 ms with it, within the rounds' spread. Phase 21 complete. High
risk (AGENTS.md §14): memory selection.

**Phase 24 — A name as the story says it: approved and complete 2026-10-01, not released.** Spec
`docs/phases/PHASE-24.md` (AGE-28 under AGE-24, a correction found by measurement): a character's three-syllable
Korean name is also mentioned by its given name, and a Hangul word by a character held under a romanized name, on a
fixed spelling key; wherever a message is matched against names, behind the recorded option `name_variants`. Step 1
(the spec) done. Step 2 (ADR 0058, D68): `variants.py` gives each request one mapping of the other names its characters
go by, used by fact selection (a mention and a secret's holder addressed), threads, the scene's cast and its names; a
name only knowledge marks hold counts too, so a secret kept from a character addressed by a variant stays private;
`<Cast>` puts the characters the message names first (a given name in the previous reply had pushed the one asked
about out of its four groups); recorded as `name_variants`, older traces replay without it; no migration, no plugin
build. High risk (AGENTS.md §14): memory selection. Step 3 (`docs/perf/name-variants.md`, three runs of every set):
the synthetic first-cue cases 5 → 8 of 15, the restored copies' Hangul probes for romanized characters 8 → 10 of 24
and 0 → 2 of 6, every other set unchanged, no new forbidden phrase; retrieve p50 at 10,000 messages −0.6 ms, +2.5 ms
with every question naming a character, within the rounds' spread. Phase 24 complete. K32 measured and left out.

**Phase 25 — `extract-v15`: a role between two people, its own fact: approved and complete 2026-10-01, not
released.** Spec `docs/phases/PHASE-25.md` (AGE-27 under AGE-24): a new predicate `role_toward` (tenant of, employer of,
teacher of…; one current value per direction) next to a pair's relationship, read as a standing fact; one extractor
generation that replaces the unreleased `extract-v14` before `0.3.0`. Step 1 (the spec) done. Step 2 (ADR 0059, D69):
`extract-v15` implemented on its branch (`role_toward` in the registry, `relationship` narrowed to personal ties, the
prompt's line on a place and a role with a synthetic example; `role_toward` in `facts.STANDING` and
`canonfacts.PREDICATES`; the Inspector's pair view has a Role column), merged with step 3 (#232).
Step 3 (`docs/perf/extract-v15.md`, owner OK 2026-10-01; 449 calls, 3.90M input and 0.57M output tokens, the output
43 % above the estimate, owner accepted): every criterion met — the AGE-27 role in 3 of 3 runs; sampled turns 116 ledger facts
(lowest `extract-v14` run 113), `relationship` rows at the bar; the M0 chats +1 case on the main chat, sample 2 equal,
the AGE-27 case passing with vectors off. High risk (AGENTS.md §14): stored data (a new generation) and memory
selection (a new standing predicate). Per call `extract-v15` reads about 3.5 % more input and writes 5.5 % more
output than `extract-v14` on the same turns. Phase 25 complete. Next, outside the phase: the owner deploys `:edge`,
rebuilds production with `extract-v15` and dumps it; Stage 6's repair-survival check on that dump; AGE-23; `0.3.0`.

**Phase 26 — A repair whose item is gone suggests where it belongs now: approved and stopped 2026-10-01, nothing
merged.** Spec `docs/phases/PHASE-26.md` (Stage 6, AGE-23; an exception to R7 granted by the owner). Step 2 (PR #238,
closed, branch kept) was measured on the `extract-v15` production copy: 40 of the owner's 68 repairs apply, none missed
where its item is still quoted; the owner read all 18 repairs with candidates and found every item gone for good, none
come back reworded. The owner stopped the phase; Stage 6's done criterion is reworded ("or, when the generation no
longer states its item, is listed under Needs attention") and met: **Stage 6 complete** (`docs/ROADMAP-1.0.md`).
The review's measure of re-extraction drift (same generation 74 % of facts again, `extract-v14` → `extract-v15` 61 %)
is on AGE-30. Next: `0.3.0` (AGE-7) with the owner's OK for the tag.

**Under AGE-24, not a phase (2026-10-02): vectors that arrive in time, and the chunk cap a setting (ADR 0061, D70;
ADR 0062, D71; K34, K13).** The four sub-issues of AGE-24 are done (Phases 21, 22, 24, 25); its criterion (the M0
main cases that need memory at 8 of 10 or better, measured live by the owner's bench harness) stood at 7 of 10 in
replays with vectors off, and live requests lost what vectors add (one or two such cases per M0 run, and the AGE-27
excerpt) when the query's embedding missed its 300 ms (70 % of production recalls on the proxy path, K34). Three
changes, none to the ranking, the budget or the recorded options: (1) the query's embedding call runs on its own thread
while lexical recall, the facts, threads, cast and summaries are read, and the request waits for it at most
`embed_timeout_ms` after those reads, so no request waits longer for the embedding and the embedder has the reads'
time too (one that now has vectors pays the search and a fuller packet, as any request with vectors did); (2) a sync
whose bodies carry the chat's newest user message starts that text's embedding at once, and the retrieve that follows
(the plugin's query is that text) takes it, so the embedder has the sync's time as well and such a request waits for
nothing — the entry is the projection's and the embedder object's it was asked of, so a settings save in between
leaves it unused (the first draft keyed it by `id()`, which a rebuilt embedder can reuse: Codex on #242 reproduced a
stale vector that way); (3) the chunk cap is a setting, `NMOS_EMBED_MAX_CHUNKS`, part of the projection key, default
8 as before. The first draft raised the default to 24 on the belief that the cap cut the owner's ≈10,000-character
replies in half; measured on the M0 v2 main chat's evaluation copy (Codex, on #242) its 147 messages normalize to at
most 5,481 characters (15,621 raw), no span changes between 8 and 24, and a copy re-embedded under 24 compiled the
same 40 packets (16/23 needing memory, 32/40 in all) — so the default stays, the key is the release before's, and
nothing re-embeds on upgrade. Deterministic cases in `test_query_embedding.py`, `test_prefetch.py`, `test_vectors.py`,
`test_long_messages.py`. Measured (`docs/perf/query-embedding.md`): at 10,000 messages a 400 ms stub embedder gave
`main` 0 of 15 requests with vectors at 644 ms p50 and this branch 15 of 15 at 534 ms; on the owner's host against the
real Ollama (40 questions × 3 rounds a side, the sidecar's sync → retrieve path) the median went 226.83 → 163.52 ms
on production's direct path (1,000 ms timeout) and 322.93 → 176.88 ms on the former proxy path (300 ms), every request
took its sync's embedding (120 of 120), and no request fell back on either side — production reaches Ollama directly
now, so K34's 70 % is the proxy path's history, not a figure this run can show shrinking. **High risk (AGENTS.md
§14)**: memory selection (vector candidates reach the fusion where the embedding used to miss its timeout; the
ranking, the bars and the budget are unchanged), projection provenance and isolation (the default projection's key is
unchanged, pinned by `test_long_messages.py`; a raised cap is its own projection, which embeds by the cap its spec
records; a query searches the active projection's vectors only, pinned by `test_generations.py`; a prefetched
embedding is given only to the projection and embedder object it was asked of, `test_prefetch.py`), and fail-open
(`test_query_embedding.py`, `test_vectors.py`: a slow or failed embedder leaves the request lexical, with the reason in
the trace). Replays of recorded requests (an evaluation gives the embedding 5,000 ms) do not show (1)–(2), and the
10,000-message bench chat does not show the real chats; the owner's live bench harness (`~/nmos-eval/three-bench`, the
NMOS lane, the embedder as in production) is where AGE-24's criterion is measured. Phase 27 and the live run on
`e13dee7` that followed are complete: the real-chat target met, the combined no-regression gate not; Phase 28 above
corrects the two state defects it found.

**Phase 23 — NMOS without Docker: approved 2026-10-01, complete 2026-10-02, not released.** Spec `docs/phases/PHASE-23.md`
(AGE-29; the owner pulled it in before 1.0, an exception to R7): a bundle for each PocketRisu portable target
(win-x64, macos-arm64, linux-x64, linux-arm64; Termux later) with a portable PostgreSQL 16, Python, the sidecar and the plugin;
Windows as a zip with `NMOS.exe` in the notification area, macOS as a menu-bar app signed ad hoc and allowed once
with Open Anyway. The spike (`spike/native-bundle`) ran on all four targets. Step 1 (the spec) done. Step 2
(`tools/native/`, `native.yml`): every download pinned by SHA-256 (`sources.json`), the sidecar's packages by
`uv.lock`'s hashes, the Linux libraries a bundle carries by their Ubuntu package versions in a digest-pinned build
image; the launcher refuses a second launcher on the same data, data written by a newer NMOS, and a port in use,
and keeps the data its owner's only (on Windows by ACL). On each target, from a folder named "한글 폴더": first start,
Korean `pg_trgm`, stop, restart and the three refusals; the sidecar suite (783) passes against the bundle's
PostgreSQL on linux-x64, macos-arm64 and win-x64. High risk (AGENTS.md §14): the bundle's stored data. Step 3
(Windows): `NMOS.exe` with the plugin's icon starts a notification-area tray (status, copy the sidecar URL, the plugin
and log folders, start at login through the user's Run key, quit); a failed or interrupted start leaves nothing
running; checked on CI from a Korean folder, a sign-in included by starting the Run entry's command. The Windows
suite's one intermittent failure was the sidecar's clock (fixed in #228: canon facts follow the database's clock).
Step 4 (macOS): `NMOS.app`, a menu-bar item, in a `.dmg`, every binary in it signed ad hoc; data in
`~/Library/Application Support/NMOS/` (App Translocation; the owner's Q3/Q9 exception); checked on CI from the `.dmg`,
sealed while running. Merged after #233 (story facts read up to a request's message follow the request's
transaction start, not the sidecar's clock: the Windows-only replay failures, 9 of 40 before, 0 of 40 after). Step 5:
`/dashboard`, the Inspector's first page with the version and recent job errors added, opened from the tray and the
menu bar. Step 6: `release.yml` builds the four bundles through `native.yml` with the tag's version and attaches them
after their checks; the smoke adds an update (data of the version before starts and migrates, nothing lost, on another
database port: the launcher now passes `NMOS_DB_PORT` at every start, which a changed port needed); README "Without
Docker" and the Korean guide (the shared `.env.example` needs `NMOS_DB_PORT=54390`; updates keep `.env` too);
ADR 0060; `ARCHITECTURE.md` §6. The owner's Windows and macOS checks (2026-10-02, AGE-29): memory injection works,
PostgreSQL shuts down, and data remains after restarting (owner reports; the OS/host versions and bundle builds
were not supplied). The requested small follow-up adds a **Refresh / 새로고침** button to the standalone dashboard's
first page: a read-only GET keeps its token and language and reads the status again. The owner explicitly confirmed
the Mac browser-download / Open Anyway path without Terminal too. The last owner-check boundary is met; Phase 23
is complete, its acceptance criteria checked against `native.yml` run 36855596213 (a second `NMOS.exe` or app's
notice, the worker checked stopped after a quit, and a real sign-out and in are not run in CI: owner accepted).
Bundles ship with the next tagged release; no tag is authorized by these checks.
Refresh follow-up verified locally: the dashboard test submits the rendered GET form, keeps auth and language,
and reads a job's changed status; the embedded panel has no added form. The full sidecar suite passes (898 tests),
`git diff --check` passes, and the diff-scoped self-review found no remaining issue. The native bundles were not
rebuilt for this UI-only follow-up; the owner's checks above concern the bundles they already ran.

**Release `v0.2.0` (2026-09-28), the first milestone (`docs/ROADMAP-1.0.md`), at the owner's request.** Stage 4
(knowledge and secrets, Phase 10) complete, with Stage 5 (Phases 11–12) and Stage 6 so far (Phase 13, Phase 14 steps
1–5) from `main`: secrets and memory modes, open business and causes, relationship pairs, summaries in `<Story>` and
`<Cast>`, owner repairs and the lock, canon sources, names and facts. Extractor `extract-v13`, normalizer `clean-v3`,
packet policy `packet-v8`, migrations 0021–0026. Phase 14 step 6 (canon facts measured, real-host smoke) followed on
`main`, then Phase 15 (complete 2026-09-29): `packet-v9` and a 4,000-token default budget (ADR 0049), M0 +6 cases
needing memory; 70 % of production recalls went without vectors (K34), now shown in the Status tab.

**Phase 20 — A name join shown before it is made: approved and complete 2026-10-01, not released.** Spec
`docs/phases/PHASE-20.md` (C7 of `docs/proposals/IDEA-SURVEY-2026-09-29.md`, Stage 6's remaining items): a preview
of what a join, a split or an undo changes in the chat's memory, a check that memory did not change since, and the
re-extraction of turns extracted while a join held. The owner accepted every proposed answer (Q1–Q10), among them
no side chosen per fact (Q5) and re-extraction of just the turns a join covered, on the owner's click (Q7); no
release. Step 1 (the spec) done. Step 2 (ADR 0055, D65): a preview of a join, a split and the undo of either
(`POST …/entity-links/preview`, `…/entity-links/{link}/remove/preview`, `…/repairs/preview`,
`…/repairs/{repair}/remove/preview`), the difference of two reads of the head, nothing written; the action answers
409 with a fresh preview when its `expect` fingerprint no longer matches. Step 3: after an
undo, `POST …/entity-links/{link}/reextract` discards the extractions of the turns extracted while the join held
(their hints list the two names as one) and queues just those turns; the undo's preview counts them. Step 4: the
panel shows the preview in place before a join, a split, or the undo of either (warnings first; a 409 shows the new
preview), and an undo of a join offers the re-extraction as a box, off by default. On an isolated PocketRisu v1.13.0
(stub models): a join previewed and made, then undone with its three covered turns re-extracted, none left joined.
A new plugin build. Step 5 (`docs/perf/join-preview.md`): on the restored copies each of the owner's seven joins,
undone and joined again, did exactly what its preview said (14 of 14); four change nothing, two replace a current fact;
125 turns would be re-extracted by their undos (the spec's 72 read only the active generation); a preview takes at most
35.4 ms on the 147-message chat. Phase 20 complete.

**Phase 19 — One extractor generation, `extract-v14`: approved 2026-09-30, complete 2026-10-01, not released.** Spec `docs/phases/PHASE-19.md`:
the changes queued for the next extractor generation (below) and a shorter context shipped together, so each chat's
re-extraction is paid once: each context message cut at 1,000 characters instead of 2,000 (measured before the spec:
17 % fewer input tokens, as many ledger facts found), the prompt's examples from the owner's chat replaced by
synthetic ones, and a turn extraction's assertion parked when its quote (12 characters or more) is not in the target
turn. Offline measurements first, then a paid evaluation from the implementation branch after the owner's OK for its
estimate; the implementation merges only when that evaluation meets the criteria. The owner accepted every proposed
answer (Q1–Q6); no release. Step 1 (the spec) done. Step 2 (`docs/perf/extract-v14.md`, no model call): the
evidence check would park 0.5 % (`deepseek`) and 5.0 % (`gemma`) of the evaluation copies' valid `extract-v13` rows,
55 of 66 quoting a context turn; six of them are placed in passed M0 v2 packets and answer none, and leaving them all
out loses one case (`gemma`, main chat, through a thread a misplaced `resolved` closed), which the owner accepted as
the criterion (at most one case per run); the shorter context repeats a pair's current value no more often. Step 3
(ADR 0054, D64): `extract-v14` implemented on its branch (context messages at 1,000 characters, synthetic examples, a
quote not in the target turn parks its row; the canon generation changes through the `addresses` description), with
`tools/eval_extract_sample.py` for step 4. Step 4 (`docs/perf/extract-v14.md`, 880 paid calls, about 7.9M input
and 2.9M output tokens): on sampled turns `extract-v14` found more ledger facts (mean 115 against 106–109) with 16 %
less input, the check parking 0.4–0.9 % of valid rows and no fact; re-extracted, `gemma4:31b` kept the M0 cases within
one per run and the synthetic cuts passed one more, but `deepseek-v4.1-flash` passed two fewer M0 cases on three runs
(K41), not through the check. The owner accepted `extract-v14` (2026-09-30). Step 5: README, the Korean guide and the
CHANGELOG say what an upgrade re-extracts and what a pending fact is. Phase 19 complete.

**Phase 17 — Model-call cost and fallback outcomes: approved 2026-09-29, complete 2026-09-30, not released.** Spec
`docs/phases/PHASE-17.md` (C4 and C5 of `docs/proposals/IDEA-SURVEY-2026-09-29.md`): the tokens each model call of
the worker used (extraction, summaries, canon reads; embeddings as input tokens), as the provider reports them and
never estimated, stored with the row they produced; totals per chat and generation in the Inspector and one line in
the Status tab, no money; the HUD tells "injected, lexical only" (K34) and "injected (reused)" apart and says what
background work produced. One migration. The owner accepted every proposed answer (Q1–Q7), and moved the embeddings'
usage from the job (pruned after 7 days) to each embedded chunk; no release. Step 2 (ADR 0051, D61, migration
0027): `ChatModel.complete_metered` and `Embedder.embed_metered` read the response's `usage`; each extraction, canon
read, summary and embedded chunk keeps its call's usage (NULL before the migration, `{"calls": 0}` without a call);
the archive carries it. Nothing is shown yet (step 3). The hosted check (Q7, `gemma4:31b-cloud` through Ollama, the owner's choice): three
calls recorded the input and output tokens of each response's `usage` exactly, and Ollama's own count of the same
prompts agreed (46/51, 50/86, 55/150); the provider names the model `gemma4:31b`. The local embedding check waits
for a model that is not production's request-path embedder. Step 3: `GET /v1/conversations/{id}/coverage?usage=true`
totals the chat's usage per generation (calls, calls reported, input / output / cached / reasoning tokens, results
from before recording), discarded results included; the HUD's polls leave it out. A "Model usage" section on the
Inspector's conversation page, and one line in the panel's "This chat" card. A new plugin build. Step 4: the HUD
says "· lexical only" when the recall's vectors fell back (K34) and "· reused" for a cached packet, in the injected
style; background work that added facts or summaries ends with "✓ facts +N · summaries +M" (the coverage view's new
`produced` counts, compared from when the work was first seen), else "✓ Processing done". On the isolated PocketRisu
v1.13.0 (stub models; the query embedding held past a 150 ms timeout): "✓ 기억 주입 (639자) · 어휘 검색만", on the
second reroll "… · 재사용 · 어휘 검색만", "✓ 사실 1개 추가" after a turn's extraction, and the Status-tab and Inspector
usage. A new plugin build. Step 5 (`docs/perf/model-usage.md`): recorded usage equals the provider's on a local
model too (an isolated CPU Ollama: `qwen2.5:0.5b`, cached input included, and `all-minilm` embeddings); request-path
latency at 10,000 messages unchanged (p50 301.6 → 301.1 ms); an evaluation copy at schema 0025 restores through
migration 0027 with usage "not recorded" and round-trips byte for byte. Phase 17 complete.

**Phase 18 — Recall by the words that matter: approved and complete 2026-09-30, not released.** Spec
`docs/phases/PHASE-18.md`: a keyword lexical route beside the whole-message one (ADR 0052, D15 amended, D62) and
`packet-v10` excerpts that grow from their best sentence (ADR 0053, D63; before, two sentences, a median of 69
characters at every budget). Step 2 done: lexical recall found a candidate for 30 % of evaluation queries. Step 3: the
keyword route (up to four words, each looked up alone, a word in more than 200 messages or half the chat dropped,
25 ms a word within the lexical budget; keyword-only excerpts that repeat a secret left out). Step 4: `packet-v10`,
the default, grows an excerpt by up to four sentences within its length; at 4,000 on M0 v2, +6 cases needing
memory without vectors and a median excerpt of 98 characters. Step 5: on 34 of the owner's recorded
requests (read-only, counts only) it placed 24 excerpts without vectors where `packet-v9` placed none, and no secret
or thread `packet-v9` would not; the isolated PocketRisu v1.13.0 injected a grown excerpt the keyword route found;
latency +11.9 ms p50 at 10,000 messages (+29 ms for a question of four common keywords alone, accepted); K39 (grown
excerpts carry replaced values) and K40 (a short keyword with a particle attached is not found) recorded
(`docs/perf/lexical-recall.md`).

**Phase 16 — Export and restore (Stage 6, part 3): approved and complete 2026-09-29, not released; the owner's iPhone check done 2026-10-01 (K38).** Spec
`docs/phases/PHASE-16.md`: an "NMOS Archive" (`.nmos.zip`: a manifest and one JSON Lines file per table) of the
whole install or chosen chats, with the ledger, canon, the owner's input, recorded requests and settings without
secrets, by default the model's work too (embeddings optional); restore into an install without those chats, same or
newer NMOS, never merged; export from the panel as well as a command, restore a command. Host evidence first (can the
plugin's frame save a file). The owner accepted every proposed answer; no release. Step 2 done (`docs/HOST-FACTS.md`
"Saving a file from the plugin frame", H21): on v1.13.0 the frame saves a Blob (Chromium and Firefox in that probe;
the owner's iPhone checked later, K38) and `nativeFetch` carries a 30 MB binary body whole on both routes; a link to the file breaks the panel, so
Export saves a Blob. Step 3 (ADR 0050, D60): the NMOS Archive and its export: `GET /v1/archive`, `python -m
nmos_sidecar.archive export`, and the panel's **Export this chat** (Inspector) and **Export everything** (Settings);
one read-only snapshot, the ledger, canon, the owner's input, recorded requests and generations always, settings
for the whole install, the model's work by default, embeddings when asked; any credential refuses the export. A new
plugin build; no migration. Step 4 (ADR 0050 amendment 1): `python -m nmos_sidecar.archive restore [--check]`: every
file checked first; refused for a newer archive or a conversation already here (never merged); the archive's schema
built in a scratch schema, rows loaded, later migrations applied, copied in with ids and timestamps kept (shared
sequenced ids moved past the install's own when taken, with the recorded requests' refs); a whole install restored
into a fresh one re-exports to the same bytes and replays the same; a Phase 13 archive restores as the upgrade would.
Step 5 (`docs/perf/archive.md`): on copies of the two measured chats (schema 0025, migrated on restore) every table
equal, every recorded request compiled the same, M0 and the secret gate identical, rebuilds equal; the production-sized
copy exports in 2.6 s (15.3 MB with embeddings, 2.1 MB without) and restores in 2.9 s; a real-host smoke of both
Export buttons on v1.13.0. On the owner's iPhone (2026-10-01) **Export everything** saved its file, and the host then
showed its own reload alert (K38).

**Phase 14 — Verification and Repair, part 2: canon sources (Stage 6): approved 2026-09-28, complete 2026-09-29.** Spec
`docs/phases/PHASE-14.md`: the character card, the lorebooks, the persona and the author's note as
immutable sources of each chat; names from canon; canon facts read by the extraction model as their own projection
(the message extractor unchanged), superseded by the story from the turn it says something new; contradictions in
"Needs attention"; a canon lock. Host evidence first, on the owner's PocketRisu v1.13.0. Export/restore is Phase 16 (Q0; renumbered 2026-09-29).
The owner accepted every proposed answer; no release. Step 2 done (`docs/HOST-FACTS.md` "Canon sources", H19,
`docs/perf/canon.md`): every canon source is readable on v1.13.0, the card only off the request path (reading it
clones the chat, 82–93 ms at 10,000 messages); sample 2's lorebook keys cover six given names (K31). Step 3 (ADR 0045,
D55, migration 0025): canon kept per chat as immutable revisions and manifests, a request recording its manifest
and the keys its prompt held (it replays with its own canon), uploads in the background, a "Canon" section in the
Inspector; a new plugin build. Step 4 (ADR 0046, D56): a lorebook entry's keys become aliases of the one
character they name (K31); on sample 2 with its canon the given-name probes find their fact 2 of 3 (0 before), M0
unchanged. Step 5 (ADR 0047, D57, migration 0026): a `canon` generation reads the card, the persona, the note and each
lorebook entry once a prompt held it; its facts are before turn 0 and the story supersedes them; a story that changes
who someone is or how two stand is listed in "Needs attention" with the owner's choices; `fact_lock` keeps a canon fact
or a correction current; a canon fact whose text the prompt held is not sent again; a new plugin build (the switch,
the lock button, macro-aware "held"). Step 6 (`docs/perf/canon.md`, "Evaluation"; ADR 0047 amendment 1): on both
measured chats with their canon, M0 and the secret gate unchanged case by case; canon took 12 and 66 model calls (26 on
production); only relationships are listed as conflicts with canon now (the owner's choice: the identities listed were
the same one in two languages, K37); latency with a 200-entry lorebook read whole +33.7 ms, accepted (K36); an upgrade
fixture from Phase 13 `main`; a real-host smoke on v1.13.0 passed and found an Inspector display bug (fixed).

**Owner request (2026-09-28), outside the Phase 14 steps: NMOS off for one chat** (ADR 0048, D58). The plugin arg
`disabled_chats` lists chats whose requests pass through untouched (nothing synced, uploaded or retrieved; what NMOS
keeps stays). Switched from the chat input's ☰ menu and a "This chat" card at the top of the panel's Status tab; the
panel also opens from the sidebar's ☰ menu. A new plugin build; no migration. Plugin tests pass; the real-host smoke
(the two menus, the arg surviving a reload and an update) is not yet run.

**Owner request (2026-09-28): a new icon.** NMOS's own SVG line icon (an N with a memory node, `src/icon.ts`) replaces
🧠 in the three menus and before "Recalling memory…" in the progress display. A new plugin build. Source reading and
a local DOMPurify check say the host keeps it (`docs/HOST-FACTS.md` "Plugin icons"); the real-host look is not yet
checked.

**Phase 13 — Verification and Repair, part 1 (Stage 6): complete (2026-09-28), not released.** Spec
`docs/phases/PHASE-13.md`: the owner repairs memory in the panel (close or reopen a thread, retract or correct a
fact, mark a secret found out, split two names), stored as owner input that survives rebuilds and new extractor
generations and finds its target by what it says; a "Needs attention" queue per chat. Canon sources are Phase 14
and export/restore Phase 15. The owner answered every question with the recommended answer; no release. Step 2 done
(`docs/perf/repair.md`): the owner confirmed NMOS's lists (50 of 59 open threads ended, 6 of 14 kept secrets found out,
2 never kept); on `main` all 40 M0 packets carry a thread the owner closed. Step 3 (ADR 0044, D54, migration 0024):
owner repairs as owner input, found by what their target says; threads closed or reopened and secrets found out or
kept, through the API, listed in the Inspector. Step 4: facts retracted or corrected, two names split (K8). Step 5:
the panel's repair buttons (bulk close, undo, splits on an entity page) and each chat's "Needs attention" list; the
plugin build changed. Step 6 (`docs/perf/repair.md`): with the owner's decisions made as repairs, no thread the
owner closed reaches a packet on either measured chat (113 lines in 40 packets and 45 in 17 before); M0 27 of 28
(one more) and 5 of 12, the second chat's 17 cases unchanged; the secret gate 6 of 6 with `<Story>` back in all six
scenes, judged by the owner's list (the owner's decision: words of a secret the character found out are told, not
forbidden); an upgrade from every fixture and a real-host smoke pass (a thread closed in the panel leaves the next
packet, undo brings it back). K8 and K23 are rewritten to what remains. One criterion is missed and the owner
accepted it: retrieve at 10,000 messages is +7.0 ms p50 over Phase 12 `main` with 100 fact repairs (the spec allows
+5; +1.7 with none, about +2 with the owner's own mix). A first run was +66 ms; the fact repairs' reads were fixed.

**Phase 12 — Narrative Engine, part 2 (Stage 5): complete (2026-09-28), not released.** Spec
`docs/phases/PHASE-12.md`: scene summaries of 8-turn windows and a story so far, as a rebuildable `summarize`
projection written by the extraction model; secrets left out and checked, no `<Story>` in narrator mode; a `<Cast>`
block of each scene character's state from facts; `packet-v8` with `<Story>` in at most 30% of the budget; new M0
cases whose answers lie outside the prompt window. The owner answered every question with the recommended answer;
no release is decided. Done: step 1 (spec); step 2, 12 owner-confirmed M0 cases whose answers lie outside the
prompt window, 2 of 12 on `main` (`docs/perf/m0-baseline.md`); step 3, the summary projection (ADR 0042, migration
0023), off by default and not yet in packets; step 4, secrets in the summary prompt and a read-time check
(`docs/perf/summaries.md`: `gemma4` 18/24, `deepseek` 24/24; `gemma4` wrote a secret twice, both held by the
read-time check); step 5, `packet-v8` with `<Story>` and `<Cast>` (ADR 0043), summaries on by default and the default
memory budget 2,000 (owner: the story did not fit 30 % of 800). M0 with `gemma4` extraction: 2 → 5 of the 12 new cases,
26 of 28 as before, nothing forbidden placed. Two faults found on the owner's chat and fixed: a finished goal in an
unrelated packet, and a secret stated after its summary (ADR 0042 amendment 2). The secret gate passes 6 of 6 with a
stricter check in front of the character a secret is kept from (amendment 3). Step 6: the Inspector shows each
summary's state and why one is not used, and a character's `<Cast>` state and open goals. Step 7: the deterministic
cases, an upgrade from Phase 11 `main` and a real-host smoke pass (`docs/perf/summaries.md`, "Acceptance"); two faults
found and fixed (ADR 0042 amendment 4: a long append left the story unwritten; a request's `<Story>` read cost about
180 ms at 10,000 messages, now about 10). One criterion is not met, and the owner accepted it: retrieve at 10,000
messages is +13.1 ms p50 over Phase 11 `main` with a summary for each of 624 windows (the spec allows +10). With
Phases 11 and 12, Stage 5 of the roadmap is done on `main`. The owner decided no release for now and chose Stage 6
next: Phase 13 is current (below).

**Phase 11 — Narrative Engine, part 1 (Stage 5): complete (2026-09-28), not released.** Spec
`docs/phases/PHASE-11.md`: the M0 evaluation on real chats (a restored backup, read-only), relationship history
per pair (K24), goal, question, threat and debt threads with a lifecycle, and explicit links, in one extractor
generation (`extract-v13`). The owner answered every question with the recommended answer; no release is decided.
Part 2 (summaries, character state) is Phase 12. Done: steps 1–3 (spec; M0 on a restored backup,
`docs/perf/m0-baseline.md`; relationship pairs, the persona's full name and `packet-v5`, ADR 0038, K24's direction
case closed). M0: 5 → 7 of 12; on the 28 cases the owner confirmed later, 13 → 15. Steps 4–5 (`extract-v13`,
ADR 0039, migration 0022; one pull request, since the prompt's OPEN THREADS need the read side): synthetic tier
`gemma4` 41/42, `deepseek` 42/42; M0 on the copy re-extracted with it 17 of 28, no category worse than the baseline
(`docs/perf/extract-v13.md`). The first 12 cases had stopped it on one wording; the owner then confirmed 28.
Step 6 (ADR 0040, `packet-v6`): stated causes in the packet and linked in the Inspector. M0's scoring now counts
answers the prompt's own last messages hold (`docs/perf/m0-baseline.md`): 23 → 26 of 28, and of the 9 cases that
need memory 5 → 7. Step 7: the Inspector's Relationships section per pair and threads by kind. Step 8: every
thread kind opened, ended, deleted and edited back in the memory evaluation (53 of 53), a real-host smoke on
PocketRisu v1.13.0, an upgrade from Phase 10 `main`, retrieve +1.2 to +4.7 ms p50 at 10k. One criterion is partly
met, and the owner accepted it: goals end (9 of 48 on the owner's chat) but 37 stay open (K23; closing a thread by
hand is Stage 6, `docs/perf/extract-v13.md`).

Outside the phase (found in the Phase 11 real-host smoke; owner decision 2026-09-28): `packet-v7`, the default, numbers
an excerpt's `turn` and a state item's `as_of_turn` by the turn of their message, as facts and threads are numbered
(ADR 0041, D51); earlier policies and their traces are unchanged. The compose files pass the packet policy empty, so a
compose install gets the sidecar's default (they had pinned `packet-v4`).

**Phase 10 — Knowledge and Secrets (Stage 4): complete (2026-09-27), not released (owner).** Spec
`docs/phases/PHASE-10.md` (every acceptance criterion met), ADRs 0033–0037, D43–D47, migration 0021. A secret is
what the story keeps from someone and ends when they find it out (`extract-v12`); what someone in the scene does
not know goes in a `<Private>` section with a rule; a chat can choose strict or a first-person narrator; the
Inspector shows a chat's secrets. Along the way, by the owner's requests: the default reserve 800, a Status-tab
notice with the budget that holds what was left out and `packet-v4` (ADR 0036), and the plugin build check (ADR
0037, K19). Evidence: `docs/perf/secrets-eval.md` — on the owner's real scenes, 48 replies of Opus 5.5 and Gemini
3.1 Pro with no leak, the holder remembering the secret as often as the pilot's best condition once a thread
ranking fault was fixed (ADR 0019 amendment 1). Released in `v0.2.0` (2026-09-28).

**Phase 9 — Accountable Packets: complete (2026-09-26), released in `v0.1.0-beta.19`.** The owner asked for
the work on a new branch and approved the merge after review. Spec `docs/phases/PHASE-9.md` (Track B, B6
narrowed to recording and budgeting what the packet holds), ADR 0027, D39, migration 0020. Every request
records a ledger of what its packet offered and held, with provenance. `packet-v1` keeps room for the
best excerpt. A recorded request replays as of its time (story position and knowledge time), and
`tools/replay_packets.py` compares policies offline. Echo reports what the next reply reused. Evidence:
`docs/perf/phase9-packets.md`, including a real-host smoke and an answer probe with two response models.
Every acceptance criterion is met. No phase is current.

**Phase 8 — Event Participants: complete (2026-09-24), released in `v0.1.0-beta.15`.** Spec
`docs/phases/PHASE-8.md` (Track B, B3 narrowed to typed participants of `event`, `goal`, `knows`,
`destroyed`), approved with the recommended answer to every question (Q1–Q5). Typed participants
(ADR 0021, D33), `extract-v8`, migration 0017, `resolve-v2`, Inspector "With" and "Takes part in".
Evidence: `docs/perf/phase8-extraction.md`. Every acceptance criterion met; the Phase 7 minor-event
scene "chores" (1/3 with `extract-v8`, no event extracted; ten more runs: v7 3/10, v8 4/10) was accepted
by the owner as not a regression. No phase is current. Next: the rest of Track B, B3, not authorized.

**Phase 7 — Promise Threads and Event Salience: complete (2026-09-24), released in
`v0.1.0-beta.14`.** Spec `docs/phases/PHASE-7.md` (Track B, B3 narrowed to promise threads and event salience),
approved with the recommended answer to every question (Q1–Q5). Promise threads (ADR 0019), event cap
and salience (ADR 0020), `extract-v7` with `fulfilled` and OPEN PROMISES, migration 0016, D32, Inspector
promises. Evidence: `docs/perf/phase7-extraction.md` (real-model tier, fact-read latency, real-host
smoke, upgrade from a `v0.1.0-beta.13` database).

**Phase 6 — Item Transitions and Conflicts: complete (2026-09-24), released in `v0.1.0-beta.13`.**
Spec `docs/phases/PHASE-6.md` (Track B, B2), approved 2026-09-24 with the recommended answer to every
question (Q1–Q5). One whereabouts per item (ADR 0016), `destroyed` with `extract-v6` and
`disputed="true"` (ADR 0017), D30, Inspector item timelines and conflicts. Every acceptance criterion
met: `docs/perf/phase6-extraction.md` (real-model tier, fact-read latency, real-host smoke, upgrade from
a `v0.1.0-beta.12` database).

**Phase 5 — Entity Identity and Semantic Assertions: complete (2026-09-24), released in
`v0.1.0-beta.12`.** Spec `docs/phases/PHASE-5.md`, ADRs 0012–0014 (0012/0013 amended by the owner after
the real-model tier), D26/D27, D7/D20 amended. Every acceptance criterion met: deterministic cases in
CI, the real-model tier on the release candidate and a real-host smoke (`docs/perf/phase5-extraction.md`),
latency (`docs/perf/scale.md`), a real upgrade from a `v0.1.0-beta.10` database. Next: Track B, B2
(transition verifier), not authorized yet.
Outside the phase (owner decision 2026-09-24, D28): an optional progress display on the chat screen,
released in `v0.1.0-beta.12`.
Outside the phase (owner-reported bug 2026-09-24, ADR 0023, D34, released in `v0.1.0-beta.16`): the persona's name as
the host reports it is the persona, so `{{user}}` and a named persona are one entity; the plugin
reads it with the host's "db" permission, asked at load (real-host check: `docs/HOST-FACTS.md`, "Persona
name"). Migration 0018, `resolve-v3`.
Outside the phase (owner report 2026-09-25, ADRs 0024 and 0025, D35 and D36, released in `v0.1.0-beta.17`): `extract-v9` labels an
event major by what it changes, in action or in words (admissions, speech-level and address changes, a relationship
allowed, an incident others must deal with), names a character shown without a name by a `?` description and links
it when a later turn reveals the name; the owner can join two names of a chat by hand in the panel (migration 0019,
`resolve-v4`). Evidence: `docs/perf/extract-v9.md`.
Outside the phase (owner request 2026-09-24, ADR 0022): Google Vertex AI service-account keys for the
extraction LLM, released in `v0.1.0-beta.15`. Mocked token exchange in CI; verified against real Vertex on
2026-09-26 with the owner's key (`google/gemini-3.8-flash`: connection test, extraction, recall; ADR 0022).
Amendment 1 (owner request 2026-10-04, unreleased): **Load key file** in the panel and a model list from Vertex's
publisher-model catalog. Mocked in CI; the catalog checked against real Vertex with the owner's key (global host, 14
chat models kept of 26); the picker checked in a real PocketRisu v1.13.0 (Chromium; HOST-FACTS); Safari/iPhone not
yet checked.
Outside the phase (owner report 2026-09-26, ADR 0026, D37, released in `v0.1.0-beta.19`): characters forgot settled things (a 반말 agreement
went back to 존댓말). Reproduced read-only on the owner's database: in a crowded scene the fact ranking was decided by
`known_by` lists, so trivia took the four facts a 600-token packet holds. Now how the cast stand with each other
(`relationship`, `feels_toward`) and major events come first among equal mentions, standing facts take the budget before
threads, and the trace and Inspector show how many facts fit. Read side only.
Outside the phase (owner decision 2026-09-26 on `docs/proposals/SPEECH-AND-ADDRESS.md`, recommended answers; ADR 0028,
D38, released in `v0.1.0-beta.19`): `extract-v10` adds `addresses`, how one character speaks to and calls another, per direction, only when
the story settles it (a slip is not recorded); it ranks with relationships. Evidence: `docs/perf/extract-v10.md`
(owner's model on the owner's chat: 18/18 settled turns, 0/3 on the slip, 0/12 routine; synthetic 21/21 on two models;
isolated real host).
Outside the phase (owner request 2026-09-25, released in `v0.1.0-beta.18`): the Status tab shows the exact text the last request
injected ("Show the injected memory"), held in the plugin's memory only. Real-host check on
`ghcr.io/pocketrisu/pocketrisu:latest` at 1280 px and 390 px; the text matched what the stub model received.

Outside the phase (owner decision 2026-09-27, unreleased): `extract-v11`, made before its milestone at the owner's
request. It carries the two queued audit items: the prompt says notes outside the story are not evidence (A-12;
an OOC note in a reply 0/3 → 3/3 ignored, the control kept 3/3) and the registry drops `Predicate.epistemic`
(A-14). Evidence: `docs/perf/extract-v11.md`. Memory-shaped markup still became a fact, because the normalizer
stripped the tag and kept the text; the owner then chose a normalizer generation (2026-09-27, unreleased):
`clean-v3` drops NMOS's own memory markup with its content (K27; `docs/perf/memory-poisoning.md`).

Outside the phase (owner decision on K26, 2026-09-26, ADR 0032, D42, unreleased): the default packet policy
is `packet-v2`, which estimates Korean at 1.2 tokens a character instead of 1.5, so more of the reserve is
used. Evidence: `docs/perf/token-estimate.md` (three tokenizers, a replay of the owner's recorded requests,
an answer probe with two response models).

**Phase 0 — complete (2026-09-22).** Phase 0A exit criteria and all Phase 0B acceptance criteria are met.

**Public beta `v0.1.0-beta.21` (2026-09-26), public repository and image.** The rest of the 2026-09-26
audit: deadline warnings in the plugin, a host check without a token (ADR 0030), the per-message extraction
window retired (ADR 0031), startup backfills committed step by step, one environment for sidecar and worker,
upgrade tests from beta.7/beta.16 databases, Vertex AI verified; no schema or generation change.
`v0.1.0-beta.20` (2026-09-26): Three fixes from the
2026-09-26 audit: a broken emoji no longer stops a chat's sync (A-01, ADR 0029), a reply quoting the
memory tag no longer turns memory off (A-02), and one bad job no longer stops the worker (A-04).
`v0.1.0-beta.19` (2026-09-26): Phase 9 (accountable
packets: packet ledger, `packet-v1`, echo, as-of replay), standing facts first (ADR 0026) and speech
level and forms of address (`extract-v10`, ADR 0028); migration 0020.
`v0.1.0-beta.18` (2026-09-25): The Status tab shows the
memory the last request injected (plugin only).
`v0.1.0-beta.17` (2026-09-25): `extract-v9` (salience by
what an event changes, unnamed characters and revealed names, ADR 0024) and owner entity links (ADR
0025); migration 0019.
`v0.1.0-beta.16` (2026-09-24): Bug fix: a named persona is
the persona (ADR 0023, above); migration 0018.
`v0.1.0-beta.15` (2026-09-24): Phase 8 (above), Google
Vertex AI keys for extraction (ADR 0022), an Inspector status-window example; migration 0017.
`v0.1.0-beta.14` (2026-09-24): Phase 7 (above); migration
0016. `v0.1.0-beta.13` (2026-09-24): Phase 6 (above) and O5
resolved: superseded vectors pruned (ADR 0015), full-manifest host observations compacted losslessly
(ADR 0018); migration 0015. `v0.1.0-beta.12` (2026-09-24): Phase 5 (above), `clean-v2`
normalizer (inline images no longer read as story), optional progress display (D28); migration 0014.
`v0.1.0-beta.11` (2026-09-24): Phase 5 step 1: a new LLM
model re-extracts only each chat's recent window and older turns keep the previous model's facts (ADR
0014, D20 amended); fact and state reads no longer stall for seconds after an edit, reroll or swipe in a
long chat. No schema change. `v0.1.0-beta.10` (2026-09-23): Track A stabilization:
verified append fast path and incremental plugin manifest (ADR 0010, migration 0013), default request
deadline 3 s after a real-host check at 5k/10k/15k messages (D24), one current holder per item (ADR
0011, D25), broad lexical queries stopped at 200 matches, and a deterministic memory evaluation
(`docs/perf/eval-baseline.md`). Evidence: `docs/perf/scale.md`. `v0.1.0-beta.9` (2026-09-23): the owner can delete a
conversation from the panel's Inspector, raw messages included (ADR 0009, D23, invariant 1 amended;
migration 0012). Evidence: `docs/perf/scale.md` (delete timings, sync A/B), real-UI host check in
ADR 0009. `v0.1.0-beta.8` (2026-09-23): facts are extracted per turn
(user message + reply) with turn-counted backfill, and each chat has "extract all history" and
"rebuild memory" in the Inspector (ADR 0008, D7/D17 revised, D22; migration 0011). Evidence:
`docs/perf/turn-extraction.md` (model comparison, real-UI host check), `docs/perf/scale.md` re-check.
`v0.1.0-beta.7` (2026-09-23): main-generation gating no
longer assumes a preset layout (ADR 0001 amendment 2): presets that add instructions after the user's
turn got no memory in beta.6 and earlier. `v0.1.0-beta.6` (2026-09-23): the Inspector opens inside
the NMOS panel (Status | Inspector | Settings tabs): PocketRisu sandboxes plugins without
`allow-popups`, so the beta.5 link could not open a tab (ARCHITECTURE H15). One PocketRisu settings
entry. `v0.1.0-beta.5` (2026-09-23) was a packaging release: multi-arch image (`linux/amd64`,
`linux/arm64`), `:latest` tag on every release, Inspector "—" for never-enabled features, README
screenshots. `v0.1.0-beta.4` (2026-09-23) was the
stabilization release (issues #6–#19) and UI review on top of `v0.1.0-beta.3` (2026-09-22). Phases 1–3 complete. Phase 4 soft
subset complete (knowledge scope `public` / `limited` / `unknown`, D19, `docs/phases/PHASE-4.md`).
Plugin settings panel configures providers, embeddings, tuning and parser rules. Validated with a
real RisuRealm sim bot and a fresh install from release assets. Still outside the beta: hard
character-POV isolation, threads/causal links, verifier, MCP (Phase 5+; not authorized).

**beta.4 contents.** Projection generations and coverage (D20, ADR 0006), normalized text (D21),
knowledge scope (ADR 0007), CORS PUT, large-chat envelope (`docs/perf/scale.md`), release gate, no
search of unverifiable beta.3 vectors (#17), immediate provider disable (#18), strict config types
(#19), one NMOS panel (status/settings tabs, chat-menu entry, Korean/English), Inspector labels.
Known issues (current list): `docs/KNOWN-ISSUES.md`.

## What exists

| Part | Where | State |
|---|---|---|
| Host evidence | `docs/HOST-FACTS.md`, `fixtures/host/a14c911-2026-09-22/` | S1–S14 (S13 N/A), Q1–Q8, 0B runtime findings |
| Architecture | `ARCHITECTURE.md` | H1–H22, D1–D73, O1/O2/O3/O4/O5 resolved |
| Sidecar + worker | `apps/sidecar` (Python 3.12, FastAPI, psycopg 3, httpx) | sync, hybrid recall, state, facts, inspector; `nmos-worker` jobs |
| Schema | `migrations/0001`–`0027` | source layer, state, extraction/jobs, embeddings, config, knowledge, normalized text, projection generations, knowledge scope, conversation labels, turn extraction, conversation delete, append rows, assertion semantics, observation compaction, event salience, assertion participants, conversation persona, owner entity links, packet ledger, conversation memory mode, thread outcome and cause, summaries, owner repairs, canon, canon facts and lock, model-call usage |
| Plugin | `adapters/pocketrisu-plugin` → `dist/nmos-pocketrisu.js` | gating (D13), manifest, sync, recall injection, fail-open |
| Deployment | `docker-compose.yml`, `docker/sidecar.Dockerfile`, `.env.example` | postgres 16 + sidecar |
| Tests | `apps/sidecar/tests` (754), `adapters/pocketrisu-plugin/test` (193; DOM code under `happy-dom`) | all passing; the M0 real-chat evaluation is `docs/perf/m0-baseline.md` (28 owner-confirmed cases; 9 need memory: 5 before Phase 11, 7 now) and, on a second chat, `docs/perf/m0-sample2.md` (17 cases; 8 of the 13 that need memory); deterministic memory evaluation `docs/perf/eval-baseline.md` (with budget pressure since Phase 9) |
| Performance | `docs/perf/phase0.md`, `docs/perf/scale.md` | Phase 0 targets met. Since beta.10: sidecar append 715 → 156 ms and plugin manifest 175 → 17 ms at 10k (ADR 0010). Real host (PocketRisu v1.12.0): ≈1.5 s at 5k, ≈2.7 s at 10k, ≈4.1 s at 15k per warm generation (host stall after `getChatFromIndex`); default deadline 3 s covers up to ≈10k without extraction and embeddings (D24); with both on (15k facts, 15k vectors) 10k takes ≈3.2 s (A-09); K3 on the real host (2026-09-27): rerolls and last-reply swipes stay on the fast path, an edit of an older message at 10k takes 3.6–3.8 s |
| Known issues | `docs/KNOWN-ISSUES.md` | K1–K42 (K10 resolved; K33–K38 recorded 2026-09-29, K39–K40 in Phase 18, K41 in Phase 19, K42 in Phase 21 and resolved on `main`) current as of `v0.2.0` and Phase 20, each with workaround and tracking (host, Track B stage); resolved limitations listed |
| Next work | `docs/ROADMAP-1.0.md`, `docs/proposals/` | Road to 1.0: stages 4–7 of the original roadmap, one release each (R7, 2026-10-01: Stage 8 after 1.0, Stage 6 ends with Phase 20, new phases only for Stage 7; R1, R5, R7 decided, R2–R4 open). Track A (stabilization) A1–A5 done; Track B B1 = Phase 5, B2 = Phase 6 (complete); B3 narrowed = Phase 7 (complete); the rest of B3 and B4–B7 not authorized |
| Decisions | `docs/adr/0001`–`0064` | gating, branches, token (optional), recall scoring, hybrid tuning, projection generations, knowledge scope, turn extraction, conversation delete, append fast path, item holder; Phase 5: entity identity, assertion semantics, generation fallback; superseded projection retention; Phase 6: item whereabouts, item end; observation compaction; Phase 7: promise threads, event salience; Phase 8: typed participants; Vertex AI service-account keys; persona name; salience by change and revealed names; owner entity links; standing facts first; speech level and address; text PostgreSQL cannot store; host check without a token; per-message window retired; Korean token estimate; Phase 10: secrets, private section, memory mode, budget pressure; plugin build check; Phase 11: relationship pairs, open business, stated causes; Phase 12: scene summaries, story and cast; Phase 13: owner repair; Phase 14: canon sources, names from canon, canon facts and lock; NMOS off for one chat; Phase 15: a packet that fills its budget; Phase 16: NMOS Archive; Phase 17: model-call usage; Phase 18: keyword lexical recall, excerpts that fill their length; Phase 19: `extract-v14`; Phase 20: join preview; Phase 21: first cue; Phase 22: reveal checks; Phase 24: name variants; Phase 25: `role_toward`; Phase 23: portable bundles; the query embedded while recall reads (K34); the chunk cap a setting of the projection (K13); Phase 27: `packet-v11`, the excerpt lands on the answer; Phase 28 (proposed): `extract-v16`, CURRENT ROLES and a name said two ways |
| Phase specs | `docs/phases/PHASE-0.md`–`PHASE-28.md` | 0–3 met; 4 soft subset met; 5–10 met; 11 met but one criterion partly (owner accepted); 12 met but the latency criterion missed by 3 ms (owner accepted); 13 met but the latency criterion missed by 2 ms (owner accepted); 14 met but the latency criterion missed by 29 ms with a 200-entry lorebook read whole (owner accepted); 15 met (packet fill); 16 met (the owner's iPhone check 2026-10-01; the host's alert is K38); 17 met; 18 met (latency measured over the benchmark's questions, owner accepted); 19 met but for `deepseek-v4.1-flash`'s M0 criterion (owner accepted, K41); 20 met; 21 met; 22 met but the paid run's reveal count missed by one (owner accepted); 23 met (owner Windows and Mac checks 2026-10-02; a second start's notice, the worker after a quit and a real sign-in not run in CI, owner accepted); 24 met; 25 met (the paid run's output tokens 43 % above the estimate, owner accepted); 26 stopped (not merged; Stage 6's criterion reworded); 27 complete (2026-10-02; Q1b the keywords anchor and Q5's bound one-sided by the owner on the measurement); 28 approved (2026-10-03), step 2 in review (#251) |
| Retro | `docs/phases/PHASE-0-RETRO.md` | |
| Audits | `docs/audits/NMOS-AUDIT-2026-09-26.md` + `-REVIEW.md` | A-01 (ADR 0029, D40), A-02, A-04 fixed in `v0.1.0-beta.20`; A-03, A-05 (ADR 0030), A-06, A-07, A-08, A-10 (verified), A-15 (ADR 0031), A-16 fixed, A-09 measured with deadline warnings, A-12 measured (K27), in `v0.1.0-beta.21`; after it, A-11 fixed (access log), A-13 documented (K28), A-18 documented (K21), A-19 fixed (plugin tests); A-17 is a caution (K15), not a defect; A-12's prompt line and A-14 in `extract-v11`, and A-12's markup half in `clean-v3` (both unreleased) |

## Evidence status (Phase 0A)

| Scenario | Status | Fixture/evidence |
|---|---|---|
| S1–S12 | run | `fixtures/host/a14c911-2026-09-22/` (S4b, S8b variants) |
| S13 | not executable on `a14c911` (no group chat); N/A accepted by owner | HOST-FACTS S13 |
| S14 | run (100 / 1,000 messages) | `…/*S14*` |

## Audit follow-up (2026-09-27)

A read-only audit of `69800f0` is recorded in [Original vision → stable](proposals/ORIGINAL-VISION-TO-STABLE-2026-09-27.md) (Korean, at the owner's request; proposal only). Its isolated API/worker probes reproduced a reveal being applied to a different secret after an old source edit (G1), the K29 history-extraction workaround queuing no work for already compiled turns (G2), and malformed assertion output being recorded as complete (G3). The 421 sidecar and 104 plugin tests that existed then passed and did not cover these cases.

- **Fixed on `main` (unreleased):**
  - G1: a reveal links to its listed turn only while that turn reads as it did (ADR 0033 amendment 2).
  - G2: "Extract all history" also extracts again the turns extracted before an earlier turn's secret, so K29's workaround works (amendment 2).
  - G3: an answer without an `assertions` list fails the job (retried, then counted failed) instead of counting as compiled.
  - Each is covered in `test_secrets.py` / `test_extraction.py`; they were strict xfails before the fix.
- Exposure before the fix: G1 and G2 came with Phase 10, which production runs from `:edge`; no tag has them. G3 dates from `e21e9cd` (Phase 2) and is in every release up to `v0.1.0-beta.21`.
- No extractor generation change: the prompt, registry and normalizer are unchanged; the listed turn's hash is stored with the hints only. Reveals extracted before the fix carry no hash and keep the old linking.

The audit's other findings (G4–G17) stay proposals. No phase authorization or release decision was made.

A second analysis the same day (an external document the owner shared, not in the repository) was reviewed against
the code. Its confirmed defects are fixed on `main` as bug fixes (CHANGELOG, Unreleased): a saved API key is sent
only to the host it was saved for, the plugin's host reads count against the request deadline and its budget and
deadline arguments are capped, the worker waits for the sidecar's migrations, a recall reads the chat as its
request had it, and the plugin's DOM code has tests (`happy-dom`, owner-approved dev dependency). Not adopted: its
advice to tag `0.2.0` now (it missed G1–G3), a Dockerfile `HEALTHCHECK` (the worker runs the same image),
removing the assertion's `epistemic` field (it is live: `certainty="implied"`; A-14 removed only
`Predicate.epistemic`), and a plugin update channel (on hold by the owner; the host offers an update only for a
higher `//@version`). Its Stage 5–8 items remain phase work; next, once G1–G3 were fixed: M0 and Stage 5 (owner,
2026-09-28).

## Anonymous design survey (2026-10-03)

The owner's requested [anonymous comparison](proposals/IDEA-SURVEY-2026-10-03.md) records current NMOS behavior,
approaches observed in other projects and possible follow-up measurements. Static source reading only: no runtime
comparison, model calls or claimed recall gains. Current NMO-24 (formerly AGE-24) help is limited to the existing
Phase 28 role-ending checks and diagnosis; support retrieval, route coverage and story selection wait for corrected
state and separate scope approval. Optional UI feedback remains a proposal. No new phase or release gate is added.
The [earlier survey](proposals/IDEA-SURVEY-2026-09-29.md#7-follow-up-2026-10-03) now marks completed candidates and
later deferrals. External project identities and identifying source references are omitted at the owner's request.

## Open owner decisions

- Phase 26 (a repair whose item is gone suggests where it belongs now; Stage 6, AGE-23) — approved 2026-10-01, then
  stopped by the owner the same day after the review on the copy (`docs/phases/PHASE-26.md`, "Outcome"); Stage 6's
  criterion reworded and met.
- O1 — resolved 2026-09-30: NMOS is an independent project, no longer related to MIRRA or VEIL
  (owner decision [NMO-16](https://linear.app/sallos725/issue/NMO-16); Git record aligned by NMO-32,
  `ARCHITECTURE.md` §9).
- O5 — resolved 2026-09-24: superseded vectors and text pruned (ADR 0015, D29), full-manifest host
  observations compacted losslessly (ADR 0018, D31), everything else on abandoned worldlines kept.
- Phase 9 (accountable packets): complete, released in `v0.1.0-beta.19`.
- Phase 11 (Stage 5, part 1): approved 2026-09-28 with the recommended answers (Q0–Q8); complete 2026-09-28, the
  goal pile-up criterion partly met and accepted (owner); release on hold.
- Phase 12 (Stage 5, part 2: summaries, character state): approved 2026-09-28 with the recommended answers
  (Q1–Q9, `docs/phases/PHASE-12.md`); complete 2026-09-28, the latency criterion missed by 3 ms and accepted
  (owner). No release for now (owner, 2026-09-28).
- Phase 13 (Stage 6, part 1: owner repair and a needs-attention queue): approved 2026-09-28 with the recommended
  answers (Q0–Q9, `docs/phases/PHASE-13.md`); complete 2026-09-28, the latency criterion missed by 2 ms and accepted
  (owner); no release.
- Phase 14 (Stage 6, part 2: canon sources): approved 2026-09-28 with every proposed answer (Q0–Q10,
  `docs/phases/PHASE-14.md`); export/restore is Phase 16 (Q0; renumbered 2026-09-29); complete 2026-09-29, the latency
  criterion missed (+33.7 ms with a 200-entry lorebook read whole) and accepted (owner); no release.
- Phase 15 (a packet that fills its budget; P1 of `docs/proposals/PUBLIC-RELEASE-AND-BENCHMARK.md`): approved
  2026-09-29 with the proposed answers (Q0–Q8, `docs/phases/PHASE-15.md`); before export/restore, after Phase 14
  step 6; default budget 4,000, fixed; no release.
- Phase 16 (Stage 6, part 3: export and restore): approved 2026-09-29 with every proposed answer (Q0–Q9,
  `docs/phases/PHASE-16.md`); an Export button in the panel too (owner); complete 2026-09-29; no release.
- Phase 17 (model-call cost and fallback outcomes; C4 and C5 of `docs/proposals/IDEA-SURVEY-2026-09-29.md`): the
  owner chose 2026-09-29 to run it after Phase 16; approved 2026-09-29 with every proposed answer (Q1–Q7,
  `docs/phases/PHASE-17.md`); complete 2026-09-30 (`docs/perf/model-usage.md`); no release.
- Phase 18 (recall by the words that matter): approved 2026-09-30, complete 2026-09-30
  (`docs/perf/lexical-recall.md`); no release. The owner accepted the latency criterion as measured over the
  benchmark's questions and chose to measure a lower keyword threshold (K40) separately: measured 2026-09-30, 0.65 found less and 0.7 differed only by run-to-run noise; 0.8 kept.
- Phase 19 (one extractor generation, `extract-v14`; the queue below and a shorter context): approved
  2026-09-30 with every proposed answer (Q1–Q6, `docs/phases/PHASE-19.md`); every paid run after the owner's OK for
  its estimate; the step-2 criterion amended and `deepseek`'s M0 miss accepted (K41) by the owner; complete 2026-10-01;
  no release.
- Phase 20 (a name join shown before it is made; C7, Stage 6's remaining items): approved 2026-10-01 with every
  proposed answer (Q1–Q10, `docs/phases/PHASE-20.md`); the owner kept Q7 knowing its limit; complete 2026-10-01; no
  release.
- Phase 21 ("at first": how it started, when the message asks; AGE-26): approved 2026-10-01 with every proposed
  answer (Q1–Q6, `docs/phases/PHASE-21.md`); a model call classifying the message (Q1's alternative) to be reviewed
  later, outside this phase (owner); complete 2026-10-01 (`docs/perf/first-cue.md`); K42, found in its review, fixed at
  the owner's request (ADR 0038 amendment 1); no release.
- Phase 22 (a re-extraction that keeps what it found: a reveal check instead of K29's re-extraction, and the narrated
  facts a re-extraction dropped, with a Restore repair; AGE-25, urgent): the owner chose the direction 2026-10-01
  (AGE-25); approved 2026-10-01 with every proposed answer (Q2–Q8, `docs/phases/PHASE-22.md`); complete 2026-10-01
  (`docs/perf/reextract-loss.md`), the paid run's reveal count missed by one (owner accepted); option 3 (keeping dropped
  facts automatically) not now; no release.
- Phase 23 (NMOS without Docker: a bundle for each PocketRisu portable target; AGE-29): the owner pulled it in before 1.0
  (2026-10-01, an exception to R7) and chose zip + `NMOS.exe` for Windows; a spike on `spike/native-bundle` ran on all
  four targets; approved 2026-10-01 with every proposed answer but Q6, where the owner chose ad hoc signing and
  "Open Anyway" over `xattr -cr`; Windows and Mac checked by the owner, including the Mac browser-download /
  Open Anyway path without Terminal, complete 2026-10-02 (`docs/phases/PHASE-23.md`); no release.
- Phase 24 (a name as the story says it: a given name alone, and a Hangul word for a character held under a romanized
  name; AGE-28 under AGE-24, one of the fixes `0.3.0` waits for): approved 2026-10-01 with every proposed answer
  (`docs/phases/PHASE-24.md`); the owner noted that the fixes keep adding rules for small gains (every rule behind a
  recorded option, no set may get worse); Q3 widened in the spec's review to every place a message is matched against
  names; K32 measured with it and left out; complete 2026-10-01 (`docs/perf/name-variants.md`); no release.
- Phase 25 (`extract-v15`: a role between two people, its own fact; AGE-27 under AGE-24, the last fix `0.3.0` waits
  for): approved 2026-10-01 (`docs/phases/PHASE-25.md`); the owner chose Q1's alternative, a new predicate
  `role_toward`, over widening `relationship` ("quality before time"), the rest as proposed; the paid run's estimate
  (about 450 calls, ≈3.8M input tokens) is part of the spec; complete 2026-10-01 (449 calls, 3.90M input and 0.57M
  output tokens, the output above the estimate, owner accepted). Phase 26+ (Stages 7–8): not authorized.
- K26 — decided 2026-09-26: change the estimate (1.5 → 1.2 tokens per non-ASCII character, `packet-v2`,
  ADR 0032, D42); the default reserve stays 600. Raised to 800 on 2026-09-27 (owner; ADR 0035).
- Release cadence — decided 2026-09-26, revised 2026-09-27: one release per roadmap stage, urgent patches
  only in between, `:edge` built from every `main` merge (`AGENTS.md` §13).
- Roadmap to 1.0 — decided 2026-09-27: not stable until stages 4–8 of the original roadmap are done
  (`docs/ROADMAP-1.0.md`). Open: R2 public benchmark, R3 and R4 stage scope.
- R1 and R5 — decided 2026-10-01: Stage 7 (forensic recall) before Stage 8 (PocketRisu bridge); read-only MCP leaves
  the 1.0 scope. Stage 6's K8 and K23 are closed: the owner's repair in the panel is the fix (automatic
  detection not planned).
- R7 — decided 2026-10-01: 1.0 needs stages 4–7. Stage 8 (PocketRisu bridge; R6 moot) and Stage 6's transition
  rules and conflict queue move after 1.0; Stage 6 ends with Phase 20. Until 1.0 a new phase is a Stage 7 item,
  urgent fixes excepted; C10 (deleted-chat memory, AGE-4) waits until after 1.0 unless the owner pulls it in.
- `0.3.0` after AGE-24 — decided 2026-10-01: `0.3.0` waits for the urgent AGE-24 fixes (AGE-26 first cue,
  AGE-28 given names, AGE-27 role relationships), so the release does not ship the real-chat recall gaps it
  knows about. AGE-27 needs `extract-v15`; it replaces the unreleased `extract-v14` before the tag (the
  one-generation rule counts what a release carries, `AGENTS.md` §13), so `0.3.0` moves from `extract-v13` to
  `extract-v15` and its users re-extract once. Cost accepted: the owner's production chats, rebuilt with
  `extract-v14`, are rebuilt again, and Stage 6's repair-survival check (40/68 on `extract-v14`) is measured
  again on an `extract-v15` rebuild before the tag. `extract-v15` is on `main` (Phase 25, complete
  2026-10-01). Order: AGE-26 → AGE-28 (with K32) → AGE-27 → production rebuild and Stage 6 re-check →
  AGE-23 → `0.3.0` (AGE-7).
- Stage 4 — decided 2026-09-27: first milestone (R1); recommended answers to Q1–Q5; no release yet. Spec
  `docs/phases/PHASE-10.md`, approved 2026-09-27. Tentative: a holder's own slip is direction, not a leak.

## Queued for the next extractor generation

A change to the extraction prompt or registry makes a new generation and re-extracts each chat's recent
window at the provider's cost (ADR 0006, 0014). Owner-approved changes wait for the next one, so the cost is
paid once (owner decision 2026-09-26). A-12 and A-14 shipped in `extract-v11` (owner decision 2026-09-27,
`docs/perf/extract-v11.md`). The synthetic prompt examples (owner decision 2026-09-28, PR #149) and evidence
found in the turn for every assertion (owner decision 2026-09-29, C2 of `docs/proposals/IDEA-SURVEY-2026-09-29.md`)
shipped in `extract-v14` with a shorter context (Phase 19, ADR 0054, `docs/perf/extract-v14.md`). AGE-27, a role
between two people, shipped in `extract-v15` (Phase 25, ADR 0059, `docs/perf/extract-v15.md`), which replaces the
unreleased `extract-v14` before `0.3.0` (owner decision 2026-10-01, Decisions above). Queued: nothing.

## Public release checklist (done 2026-09-23)

| Item | State |
|---|---|
| Security notice (plain-text API keys in `app_config`, no internet exposure, token for LAN/Tailscale) | done — README "Security", guide.ko "보안 주의" |
| README/guide claims scoped to the tested PocketRisu build | done |
| Private IP in experiment notes generalized (`192.168.x.x`) | done |
| Outdated agent docs (`CODEX-PROMPT.md`, `STARTER-CONTENTS.md`) archived to `docs/reference/`; `AGENTS.md` current; `PHASE-4.md` added | done |
| Commit author email in git history | done — `main` and tags `v0.1.0-beta.1`–`3` rewritten to the GitHub noreply address; later commits use it |
| Repository description/topics | done |
| Repository visibility → Public | done 2026-09-23 (after `v0.1.0-beta.4`) |
| GHCR `nmos-sidecar` package visibility → Public | done 2026-09-23 (owner) |
| Anonymous `docker pull` + fresh install from release assets | done 2026-09-23 — `0.1.0-beta.4` and `beta` pulled without login (same image); release compose file up with migrations 0001–0010; release plugin file installed in PocketRisu `a14c911`, synced a 37-message chat, Inspector showed it as *bot · chat* in Korean |
| README screenshot (settings panel or Inspector) | done 2026-09-23 — `docs/images/` (panel Status tab, Inspector), taken on the `v0.1.0-beta.4` release stack |
