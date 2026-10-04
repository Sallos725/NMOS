# Phase 29 — Whose name is it: a confirmation for an alias whose two names are both in the turn

> **Status: approved 2026-10-04 (the owner: Q1 and Q5 as decided, the rest as proposed, the probe's bar as written;
> implementation inside `extract-v16` on #251's branch), current as a correction phase (AGENTS §7 item 5); step 2 next.**
> NMO-35 under AGE-24; a correction found by measurement, not roadmap Stage 7 or 8. It builds on `extract-v16` of
> Phase 28 (#251, not merged) and changes nothing under `extract-v15`.

## Questions and proposed answers

| # | Question | Proposed answer | Alternatives considered |
|---|---|---|---|
| Q1 | Which aliases are confirmed? | *Decided (owner, 2026-10-04): NAME PAIRS not asked.* **A character's `also_called` that the worker would store as valid and that would join two names not already one entity** in the KNOWN ENTITIES the extraction was shown: after the registry, bare-label (ADR 0064 item 2) and presence (`alias_evidenced`) checks have passed, so a row those checks already hold costs no call. Not an alias the model confirmed by number from NAME PAIRS (a full name and its part on its own, ADR 0064 item 2): that is already a second, structured check, and holding it would bring back the split Phase 28 fixed. Not an item's or a place's alias. Not the persona's (PHASE-28 Q6 keeps the persona guard; S1's `서도윤 → 도도` rows stay held as not stated in their turns). | Every `also_called`, NAME PAIRS included (more calls, and a held full/part pair re-splits a person); only aliases whose two names are both in the turn (the presence check's other branch, a known name standing in for a `?description`, also joins two entities and is as exposed); aliases of every entity type (an item's alias reaches no knowledge boundary). |
| Q2 | What is asked, and with what? | **One call per alias, with the two names, the two preceding turns and the TARGET** (the role confirmation's frame, `confirm_prompt`, and its envelope: temperature 0, JSON mode, the extractor's client): "In TARGET, is NAME_B a name for the same person as NAME_A? Answer no when NAME_B is how someone in TARGET addresses, writes to or mentions a different person." The answer is `{"same": "yes" \| "no", "evidence": "<one passage of TARGET>"}`. No other hint, no first answer, no KNOWN ENTITIES list: the confirmation reads the scene, not the extraction's beliefs. | The main prompt's wording again (both failed rows came from the current wording, and prompt-only fixes have failed on this input before); KNOWN ENTITIES in the confirmation (it carries the earlier joins the extraction was misled by); a second model (later, as Q7 of PHASE-28 left it). |
| Q3 | What counts as a yes? | **`same: yes` with a passage that is in TARGET (`quoted_in`) and contains NAME_B.** Anything else holds the alias: a no, a missing or foreign quote, an invalid answer, a failed call. As for role endings, the quote check filters a yes; it does not prove identity. | A yes alone (no evidence contract); requiring both names in the quote (a nickname is often introduced a sentence away from the full name: S1 turns 1 and 160). |
| Q4 | What does a held alias mean? | **A pending row, never served**, reason `alias not confirmed: <outcome>`, with the confirmation (the two names, outcome, whole reply, quote, usage, error) kept beside the extraction's raw reply under its own key. The resolver is unchanged (ADR 0012 and its v16 amendment): a pending row joins nothing and makes nothing ambiguous. A wrongly held alias leaves the two names apart, the defect Phase 28 corrected, so the owner must be able to see it (Q5). | Write the alias and mark it doubtful (the resolver would need a new state); drop the row (loses the evidence, and the raw reply already keeps it). |
| Q5 | How does the owner see a held alias? | *Decided (owner, 2026-10-04): listed; and, amended the same day, with a one-click owner link (option A): the held row's mark opens the join's preview and links the two names naming that held row, so a name mentioned only there can be linked (the link waits for a mention, ADR 0025); a plugin change.* **Listed under the Inspector's "Needs attention", with the existing owner link (PHASE-20: a name join shown before it is made) as its one action.** Read only, off the request path; no new repair kind, no migration. If the owner link cannot express "these two names are one person" for a held row, implementation stops and asks. | No listing (a wrong hold is invisible, as the role holds were before PHASE-28 Q7); a new repair kind (a migration and a new UI flow for one case). |
| Q6 | How does it ship? | **Inside `extract-v16`, behind the same `NMOS_EXTRACT_COMPILER`, off by default.** The confirmation's system text joins the generation fingerprint, so this is a new `extract-v16` generation; `extract-v15`'s key, prompt and every default request are unchanged. Usage: the calls are summed into the extraction's top-level usage and kept apart under `confirm`, as the role confirmations are (ADR 0064 item 4). | A separate compiler (`extract-v17`): one more generation for users to re-extract before 0.3.0, against AGENTS §13's one-per-milestone rule. |
| Q7 | How is it measured? | **Deterministic cases in CI, a fixed-input probe, then one fresh sequential S1** (below, "Measurement"), each with an owner-approved call and token estimate and every result reported. | A sequential run first (one sample, about $0.5, and the two failing inputs appear once each). |
| Q8 | What is not in this phase? | Language or scenario generalization (NMO-34, after 1.0): the confirmation is worded in English for any script and adds no Korean or English word list. The persona's aliases. Role endings (Phase 28). Resolver, ADR 0012 or ADR 0013 changes. A default switch or a release. | — |

## Goal

The S1 identity gate (강무진/무진, 백이안/이안, 윤하람/하람 joined at turn 239) fails because an alias whose two names
are both in the TARGET is given to the wrong person. The presence check cannot catch it: both names are there.

| Run (owner-local evidence) | Turn | Stored alias | What TARGET shows |
|---|---|---|---|
| `4e76c70` (2026-10-03) | 237 | `람이 → 도도` | 하람's letter to 도윤 opens "도도에게." |
| `4e76c70` | 200 | `추오월 → 도도` (object 람이) | 하람 to 도윤: "도도, 술 마셨지." |
| `c0b0a5b` (2026-10-04) | 200 | `윤하람 → 도도` | the same line |
| `8fe66d1` (2026-10-04) | 200 | `윤하람 → 도도` | the same line |

Each row is valid and served; the resolver joins no two people, but 윤하람 becomes ambiguous (하람, 람이, 도도), which fails
the gate (`docs/perf/extract-v16-8fe66d1-sequential.md` in #251: roles 7/7, names 2/3). In
every case the alias is how one character addresses or writes to another. The 4e76c70 turn-200 row (subject 추오월,
absent from the turn) is now held by ADR 0064 item 2, and so is turn 81's `백이안 → 곽 조합장` (re-checked on the stored
TARGETs with `alias_evidenced` at #251's head, no model call; 237 and the later 200 rows pass it). The remaining class is
the one where both names are in the turn. The synthetic excerpts are in `fixtures/model/phase28/2026-10-03-s1-confirmation-review/`
(#251).

## Baseline

`extract-v16` on `8fe66d1` (#251 head), fresh sequential S1 of the synthetic story, one run: 240 turns, 248 calls, about
$0.509 uncached; 17 `also_called` rows, nine newly joined (all correct), one wrong served alias (turn 200), names 2/3.
Under Q1, that run would have asked three confirmations: `오봉순 → 오 사장` (1), `윤하람 → 람이` (160) and the wrong
`윤하람 → 도도` (200). Its other seven joins came through NAME PAIRS (10, 18, 24, 33, 143) or were the persona's (0) or an
item's (25), and are not asked.

## In scope

1. The alias confirmation in `extract-v16` (Q1–Q4, Q6), its record and usage.
2. The Inspector listing of held aliases with the owner link (Q5).
3. Deterministic cases for every branch, and a pin that `extract-v15`'s key and every default request are unchanged.
4. The measurement (Q7) and the decision it supports.

## Out of scope

Q8, and: a migration, a new predicate, a new repair kind, any change to the main extraction prompt's alias rule, NAME
PAIRS or the bare-label set. *Amended 2026-10-04 (owner):* the plugin change Q5 A needs is in scope, and so is one change
to the presence check under extract-v16: a Hangul or Latin name counts only as a word of its own (S1: 람이 was found
inside 하람이), in the generation fingerprint; other scripts as before (NMO-34).

## Measurement

**(a) Zero-call.** Deterministic tests with a stand-in model: which rows are asked (Q1), each outcome (Q3), the pending
row and record (Q4), the listing (Q5), the usage sum, a failed call, `extract-v15` unchanged.

**(b) Fixed-input probe** (the confirmation call alone, preserved inputs, three repeats each), estimate for approval:

| Set | Unique inputs | Source | Expected |
|---|---:|---|---|
| Measured wrong aliases | 2 | S1 200 `윤하람 → 도도` (identical confirmation input in c0b0a5b and 8fe66d1), S1 237 `람이 → 도도` | held |
| Measured correct free aliases | 3 | S1 1 `오봉순 → 오 사장`, 160 and 185 `윤하람 → 람이` (the c0b0a5b and 8fe66d1 runs) | kept |
| Measured NAME PAIRS answers | 7 | S1 10, 18, 24, 33, 59, 133, 143 (full name and part): not asked under Q1; measured for information, they do not gate | kept |
| Authored controls | 8 | Written and frozen before any call, synthetic, reported apart: 4 where the second name addresses, writes to or mentions someone else (vocative in dialogue, a letter's salutation, a name in reported speech, a name on a sign), 4 true aliases (a self-introduction, "everyone calls him …", a nickname used and answered to, a title with the surname) | 4 held, 4 kept |

Turn 0 (the persona's) and turn 25 (an item) are deterministic not-asked cases under (a). 20 × 3 = **60 calls**; at the
role confirmation's measured size (about 4,600 input / 40 output tokens) about 276,000 input / 2,400 output tokens,
**about $0.04** at $0.14 / $0.40 per million. Bar, fixed before the run: measured wrong 6/6 held; authored negatives
12/12 held; measured correct free aliases 9/9 kept; authored positives ≥ 11/12 kept; no technical error. The NAME PAIRS
answers are reported for information only (Q1 decided: not asked). The
single-sample counts (two measured wrong inputs, three correct free ones) are a known limitation, which the authored
controls only partly offset.

**(c) One fresh sequential S1** on the new generation, the 4cc7ddd/8fe66d1 envelope (main `max_tokens` 8,192, 240 main
calls, role confirmations and alias confirmations under one 64-call ceiling, input stop 4.2M, output 360,000; about
$0.52): names 3/3 at 239, role scenes 7/7, every `also_called` row reviewed with its confirmation, held aliases listed in
the Inspector.

**Result of (b), 2026-10-04:** 60/60, every bar met (measured wrong 6/6 held, authored negatives 12/12 held, correct
free aliases 9/9 kept, authored positives 12/12 kept, NAME PAIRS 21/21 kept), no technical error, $0.023; at #251's
`b447843` (`docs/perf/phase29-alias-confirmation-probe.md` in #251).

## Acceptance criteria

- [ ] **Defaults unchanged**: `extract-v15`'s key, prompt and default requests as before (full sidecar suite).
- [ ] **Deterministic** (a): every branch of Q1–Q6.
- [x] **Probe** (b) meets its bar (60/60, 2026-10-04).
- [ ] **Sequential S1** (c): names 3/3, roles 7/7, no false join, every held alias listed.
- [ ] Diff-scoped self-review naming the guarantees at risk; STATUS, ADR 0012/0064 amendments and NMO-35 updated.

## Steps

1. This document, approved; AGENTS §1/§2 and STATUS name Phase 29.
2. Implementation and deterministic cases on #251's branch (owner, 2026-10-04); a new generation key reported.
3. The probe (b) after its estimate is approved.
4. The sequential S1 (c) after its estimate is approved.
5. The decision: kept in `extract-v16` (ADR 0064 amended) or withdrawn.

## Stop conditions

Stop and ask the owner when: a false join on any measured input; a measured or authored wrong alias kept in the probe;
the probe's correct-join bar missed; `extract-v15`'s key or a default request changes; a migration, new repair kind or
runtime dependency would be needed (including Q5's link not fitting); a paid run would exceed its approved estimate.

**Known risk.** The confirmation is the same model reading the same scene (PHASE-28's turn 227: both calls wrong
together). A yes on a wrong alias is not caught by this phase; the Q5 listing shows only held aliases, so the owner
sees a wrong hold but not a wrong keep. Listing every newly served alias as well (as PHASE-28 Q7 lists every applied
ending) is the alternative if the probe shows wrong keeps.

**High risk (AGENTS §14):** identity and provenance (which names are one person), knowledge boundaries reached through
an alias, stored extraction generations.
