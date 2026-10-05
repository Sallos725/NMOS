# Fresh S1 on 9aa7c57 (2026-10-04): Phase 29 (c)

**Complete and passing: 240/240 turns, names 3/3, role scenes 7/7.** The first fresh sequential S1 of PR #251 to pass
every declared gate. At turn 200 the main reply wrote `윤하람 → 도도` again (the NMO-35 row, in its fourth run); the
alias confirmation answered no and held it, so 윤하람 stayed resolved and the name gate passed. No wrong automatic
ending, no false join. Not a release or default-switch verdict; `extract-v15` remains the default.

**High risk:** identity and provenance, current/historical role state, knowledge boundaries through an alias,
extraction generations. The measured product code is unchanged by this report.

## Target and method

- Product: `9aa7c57cd051308c1b5420536aedd23b3ed64cfa` (PR #251: Phase 28 step 2 with the Phase 29 alias
  confirmation, the owner link from Needs attention and the word-level presence check), generation
  **`extract-b88669ca66664b77df6ac117d741ea8e`**; `extract-v15`'s key unchanged (`extract-5a714c5f…`).
- Owner-approved (2026-10-04). A new restore of the preserved S1 baseline (SHA-256 `b8910225…`), one worker, no retries.
  Envelope as in the 8fe66d1 run: main `max_tokens` 8,192 (production sends none), confirmation 512, 240 main / 64
  confirmation calls (role and alias confirmations together), input stop 4.2M, output 360,000.
- Changed conditions vs the 8fe66d1 run (PLAN SHA-256 `340b0bfd…`): the product; alias confirmations counted as
  confirmation calls; the semantic review also paused on every held alias. Gold, verdicts and stop rules unchanged.

## Verdicts (fixed before the run)

| Scene | Observed | Verdict |
|---|---|---|
| 74 mentorship, 86 eve of the move, 99 promotion elsewhere, 144 shop closure | role kept | pass |
| 87 move | inn stay ended after a confirmation yes | pass |
| 88 settling in | new residence kept; no ending proposed in this run | pass |
| 233 resignation | navigator role ended after a confirmation yes (only that direction was listed in this run) | pass |
| Wrong automatic endings / false joins | 0 / 0 | pass |
| **Names at 239** | 강무진/무진, 윤하람/하람, 백이안/이안 joined | **3/3, pass** |

## The alias confirmation in the worker

Three aliases met PHASE-29 Q1; every other alias was a NAME PAIRS answer, the persona's, an item's, already joined, or
held by an earlier check.

| Turn | Alias | Confirmation | Stored | Review |
|---|---|---|---|---|
| 1 | `오봉순 → 오 사장` | yes ("다들 오 사장이라고 부르지.") | valid, joined | correct |
| 145 | `윤하람 → 람이` | yes ("오 사장님, 람이. 와 주셨네요." — 도윤 greeting 하람) | valid, joined | correct |
| 200 | `윤하람 → 도도` | **no** ("도도, 술 마셨지. 맥주 냄새 나." — 하람 to 도윤) | **pending, joins nothing** | correct hold |

The turn-145 yes and the turn-200 no are both vocatives: the confirmation told an address to the same person from an
address to another, in the worker as in the probe. The held row is listed in the Inspector (`en`, `ko`) with its
`alias_join` action on a clone of the final state; no repair or link was made.

### Every also_called row

| Turn | Stored ID | Subject | Object | Value | Stored / served outcome |
|---|---:|---|---|---|---|
| 0 | 1147 | `서도윤` | `도윤` | `도윤` | valid; newly joined, correct (persona, not asked) |
| 1 | 1160 | `오봉순` | `null` | `오 사장` | valid after a yes; newly joined, correct |
| 10 | 1212 | `서정호` | `null` | `정호` | valid (NAME PAIRS); newly joined, correct |
| 18 | 1250 | `강무진` | `null` | `무진` | valid (NAME PAIRS); newly joined, correct |
| 24 | 1278 | `백이안` | `null` | `이안` | valid (NAME PAIRS); newly joined, correct |
| 29 | 1298 | `은빛 잉크병` | `null` | `작은 잉크병` | valid (an item, not asked); newly joined, correct |
| 33 | 1315 | `윤하람` | `null` | `하람` | valid (NAME PAIRS); newly joined, correct |
| 43 | 1358 | `추오월` | `null` | `추 영감` | pending; alias not stated in the turn |
| 59 | 1422 | `추오월` | `null` | `오월` | valid (NAME PAIRS); newly joined, correct |
| 104 | 1600 | `조개 부적` | `null` | `부적` | pending; alias not stated in the turn |
| 110 | 1626 | `?쪽배` | `null` | `청새치호에 딸린 쪽배` | pending; alias not stated in the turn |
| 145 | 1772 | `윤하람` | `null` | `람이` | valid after a yes; newly joined, correct |
| 182 | 1952 | `서도윤` | `도도` | `도도` | pending; alias not stated in the turn |
| 185 | 1971 | `서도윤` | `도도` | `도도` | pending; alias not stated in the turn |
| 193 | 2011 | `윤하람` | `람이` | `람이` | valid; already joined |
| 193 | 2012 | `서도윤` | `도도` | `도도` | pending; alias not stated in the turn |
| 200 | 2057 | `윤하람` | `도도` | `도도` | **pending; alias not confirmed: no** |
| 238 | 2235 | `서도윤` | `null` | `도도` | pending; evidence not in the turn |

The persona's `서도윤 → 도도` rows (182, 185, 193, 238) stay held by the earlier checks; the persona is outside this
phase (PHASE-28 Q6).

## Role endings and confirmations

| Turn | Role | Path | Confirmation | Stored | Review |
|---|---|---|---|---|---|
| 87 | 서도윤 → 오봉순, inn guest | listed, now | yes | applied | correct ending |
| 134 | 곽은비 → 서도윤, sponsor | listed, now | yes | applied | correct ending |
| 135 | 서도윤 → 백이안, colleague | listed, now | yes (quote Weak alone) | applied | correct ending (leaves the office after the dismissal) |
| 158 | 서도윤 → 추오월, attic resident | listed, planned (doubt) | no | dropped | correct drop |
| 159 | 서도윤 → 추오월, attic resident | listed, now | yes | applied | correct ending |
| 219 | 윤하람 → 오봉순, inn work | listed, now | yes (quote Weak alone) | applied | correct ending |
| 233 | 서도윤 → 강무진, navigator | listed, now | yes | applied | correct ending |
| 234 | 서도윤 → 강무진, "항해사: 그만둠" | free negative | none | valid; ends no current fact | restates 233 |

At 134 the model also proposed ending the colleague role on the dismissal; no row was stored (the counterpart is not
named in that TARGET), and the next turn ended it.

## Time and cost

| Lane | Calls | Input tokens | Output tokens | Cached input reported | HTTP time |
|---|---:|---:|---:|---:|---:|
| Main | 240 | 2,861,287 | 255,122 | 1,397,952 | 980.706 s |
| Confirmations (7 role, 3 alias) | 10 | 43,627 | 402 | 3,968 | 12.142 s |
| Total | 250 | 2,904,914 | 255,524 | 1,401,920 | 992.848 s |

Started 11:20:15 KST, elapsed **1,145.6 s** (19 min 6 s) including 127.0 s of local review waits. Main median 3,600
ms, maximum 14,185 ms; confirmation median 781 ms, maximum 5,317 ms; maximum output 2,769 main / 66 confirmation
tokens. **$0.50889756** uncached at the owner's rates ($0.14 / $0.40 per million); not an invoice. No HTTP error,
format error, retry or truncated reply.

A new read-only connection reconciles all 240 stored extractions (raw, usage, assertions) and the ten confirmations;
HTTP totals equal stored usage. Jobs: 240 done, one attempt each. Facts API on the final clone: 66.6 ms median,
72.6 ms p95 (20 reads after 3 warmups; not the 10k gate).

## Evidence and limits

Owner-local root: `/home/grantkim725/nmos-eval/pr251/2026-10-04/sequential-9aa7c57/` — PLAN, approval, frozen hashes,
every request and reply, per-turn audits and reviews, and the final archive `s1-backfill-1/result.nmos.zip`
(SHA-256 `73cf2f80ca3f4df15f7abf71639375b562f91c94db3a9c4d31755e1a9a938d23`); `fresh-readback-summary.json`
(`41ed5edf…`, verified), `semantic-summary.json` (`61e7050c…`), `ui-readback-summary.json` (`97239fd5…`).

One run of one development story (S1). The rules were shaped on S1, so this does not show they hold on other stories:
S2, the independent glass-garden probe and the 1,440-call comparison (PHASE-28 Q5 (c)) remain, as do first
connection, the 10k latency gate and the live runs (Q5 (d)). The 233 doubt path held nothing in this run.
