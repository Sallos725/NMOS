# Fresh S1 on 8fe66d1 (2026-10-04)

**Complete, 240/240 turns, with one failed gate: names 2/3.** Every declared role scene passes (7/7),
including the turn-233 resignation in both directions; no wrong automatic ending, no false join. The
turn-200 wrong alias `윤하람 → 도도` recurs (NMO-35 type, both names in the turn), leaving 윤하람
ambiguous, so 윤하람/하람 is not joined at 239. Not a release or default-switch verdict;
`extract-v15` remains the default.

**High risk:** current/historical role state, entity identity, provenance and extraction generations.
The measured product code is unchanged by this report.

## Target and method

- Product: `8fe66d1b6a4a420e2b08d2228d16d20861d5a487` (PR #251: 4cc7ddd plus the trailing-comma parse fix), `NMOS_EXTRACT_COMPILER=extract-v16`.
- Generation: `extract-ba2d952e57b5e468cef813c6e6f52273`, the same as on 4cc7ddd (the fix changes no
  fingerprint); v3 confirmation system SHA-256 `c5fe766a…` unchanged.
- Owner's approval (2026-10-04): another run after the cause of the 4cc7ddd stop (turn 62, a trailing
  comma; `extract-v16-4cc7ddd-sequential.md`) was found and fixed. A new restore of the preserved S1 baseline (SHA-256 `b8910225…`); the stopped
  4cc7ddd database was not resumed. One worker, no retries.
- Envelope, gold, verdicts, review and stop rules are those of the 4cc7ddd run, fixed before it: main
  `max_tokens` 8,192 (production sends none), confirmation 512, 240 main / 64 confirmation calls, input
  stop 4.2M, output budget 360,000; the grader counts a doubt held after a confirmation yes as held, and
  a failed 233 continues to 239. The only changed condition is the product commit (PLAN SHA-256
  `2209e99d4cd5392e8157c1373f10bb7f7ef4ca850fa36820afd555b382b52045`).
- Before the run: 25 instrumentation tests and the full sidecar suite (1,033) passed on 8fe66d1.

## Verdicts (fixed before the run)

| Scene | Expected | Observed | Verdict |
|---|---|---|---|
| 74 mentorship | kept | kept | pass |
| 86 eve of the move | kept | kept | pass |
| 87 move | inn stay ends | applied after a confirmation yes | pass |
| 88 settling in | new residence kept | kept; the main reply ended it, the confirmation said no, the ending held | pass (one spurious held item) |
| 99 promotion elsewhere | inn role kept | kept | pass |
| 144 shop closure | residence kept | kept | pass |
| 233 resignation | both directions applied, or held and listed | both named `now`, both confirmed and applied | pass |
| Wrong automatic endings | ≤ 1, new kind stops | 0 (no ending at 227) | pass |
| False joins | none | none | pass |
| Names at 239 | 3/3 | 강무진/무진 and 백이안/이안 joined; **윤하람/하람 not** (윤하람 ambiguous: 하람, 람이, 도도) | **fail** |

The 233 doubts this commit's base adds were not needed: the main reply named both roles ending now.
One doubt arose elsewhere, at turn 158: the move-out was reported `planned` (a promise to vacate by the
month's end); the confirmation said no and it was dropped, and the actual ending at 159 was applied.
The doubt path is therefore exercised once in this run (a correct drop), and its held branch only in
the deterministic tests.

## Endings and confirmations

| Turn | Role | Path | Confirmation | Stored | Review |
|---|---|---|---|---|---|
| 87 | 서도윤 → 오봉순, inn guest | listed, now | yes (quote Weak alone) | applied | correct ending |
| 88 | 서도윤 → 추오월, attic resident | listed, now | no | held (`role ending not confirmed: no`) | correct hold |
| 134 | 곽은비 → 서도윤, sponsor and client | listed, now | yes | applied | correct ending |
| 158 | 서도윤 → 추오월, attic resident | listed, **planned** (doubt) | no | dropped, no row | correct drop |
| 159 | 서도윤 → 추오월, attic resident | listed, now | yes | applied | correct ending |
| 219 | 윤하람 → 오봉순, inn dining help | listed, now | yes (quote Weak alone) | applied | correct ending |
| 233 | 서도윤 → 강무진, navigator | listed, now | yes | applied | correct ending |
| 233 | 강무진 → 서도윤, employer | listed, now | yes | applied | correct ending |
| 234 | 서도윤 → 강무진, "항해사 (그만둠)" | free negative, not listed | none | valid; ends no current fact | restates 233 |

Applied 6, held 1, dropped doubt 1, wrong 0. The Inspector on a clone of the final state (`en`, `ko`)
lists the three automatic endings within 30 turns of 239 (233 × 2, 219), each with its retraction, and
no held ending: the turn-88 hold's role ended at 159, and a held role no longer current is not listed
(by design). Read at earlier prefixes, `endings.held` lists the hold at 88, 120 and 157 and not at 159
(`held-by-prefix.json`). No repair was run.

## Every also_called row

“Served” means the resolver used the row; a pending row is kept with its reason and serves nothing.

| Turn | Stored ID | Subject | Object | Value | Stored / served outcome |
|---|---:|---|---|---|---|
| 0 | 1147 | `서도윤` | `도윤` | `도윤` | valid; newly joined, correct |
| 1 | 1159 | `오봉순` | `null` | `오 사장` | valid; newly joined, correct |
| 3 | 1171 | `?검은 고양이` | `null` | `먹물` | pending; alias not stated in the turn |
| 10 | 1212 | `서정호` | `null` | `정호` | valid; newly joined, correct |
| 18 | 1251 | `강무진` | `null` | `무진` | valid; newly joined, correct |
| 24 | 1278 | `백이안` | `null` | `이안` | valid; newly joined, correct |
| 25 | 1279 | `나무 오리 인형` | `null` | `특별상` | valid; newly joined, correct (an item) |
| 33 | 1315 | `윤하람` | `null` | `하람` | valid; newly joined, correct |
| 43 | 1361 | `서도윤` | `null` | `도윤` | valid; already joined |
| 81 | 1512 | `백이안` | `null` | `곽 조합장` | pending; alias not stated in the turn |
| 104 | 1600 | `조개껍데기 부적` | `null` | `부적` | pending; alias not stated in the turn |
| 143 | 1777 | `추오월` | `null` | `오월` | valid; newly joined, correct |
| 160 | 1856 | `윤하람` | `람이` | `람이` | valid; newly joined, correct |
| 182 | 1955 | `서도윤` | `도도` | `도도` | pending; alias not stated in the turn |
| 185 | 1970 | `서도윤` | `도도` | `도도` | pending; alias not stated in the turn |
| 200 | 2064 | `윤하람` | `도도` | `도도` | valid; **wrong attribution**, served, subject becomes ambiguous |
| 203 | 2075 | `서도윤` | `서정호 아들` | `서정호 아들` | pending; alias not stated in the turn |

Turn 200: 하람 addresses 도윤 as 도도 (`"도도, 술 마셨지."`); both names are in the turn, so the presence
check admits the row. The resolver joins no two people; it makes 윤하람 ambiguous among 하람, 람이 and
도도, which fails the name gate. The same row and outcome occurred in the c0b0a5b run. This is NMO-35's
scope (a confirmation for an alias whose two names both occur in the turn), reported as a failure and
not a stop under the owner's rule. The 182/185 `서도윤 → 도도` rows, which would be correct, are held as
not stated in their turns.

## The trailing-comma fix in this run

No reply in this run needed it: all 248 replies parse strictly. Turn 62's input differed from the
4cc7ddd run's (prompt `f6095974…` vs `bff9a5c1…`, earlier stored state differs) and its reply was valid.
So this completion does not demonstrate the fix; its evidence is the offline replay of the preserved
replies (1,323 parse as before, the five turn-62 replies now parse, one cut by the cap still fails) and
its tests.

## Time and cost

| Lane | Calls | Input tokens | Output tokens | Cached input reported | HTTP time |
|---|---:|---:|---:|---:|---:|
| Main | 240 | 2,869,303 | 255,086 | 1,403,424 | 939.384 s |
| Confirmation | 8 | 37,141 | 263 | 4,608 | 13.565 s |
| Total | 248 | 2,906,444 | 255,349 | 1,408,032 | 952.949 s |

Started 09:23:27 KST, finished 09:41:47 KST: **1,100.4 s** (18 min 20 s), including 125.0 s of local
review waits. Main median 3,593 ms, maximum 11,697 ms; confirmation median 820 ms, maximum 7,920 ms (the
turn-158 doubt). Maximum output 3,204 main / 45 confirmation tokens: the 8,192 cap was never reached.
Uncached estimate at the owner's rates ($0.14 / $0.40 per million): **$0.50904176**, within the expected
$0.5–0.6. Not an invoice. Facts API through TestClient on the final clone: 65.4 ms median, 84.5 ms p95
(20 reads after 3 warmups; not the 10k gate).

A new read-only connection reconciles all 240 stored extractions: raw replies, usage and assertion
lists equal the captured evidence; HTTP totals equal stored usage, and the confirmation usage kept
apart under `confirm` equals the eight confirmation calls. Jobs: 240 done, each one attempt.

## Evidence and limits

Owner-local root: `/home/grantkim725/nmos-eval/pr251/2026-10-04/sequential-8fe66d1/` — PLAN, approval,
frozen run/source hashes, every request and reply, per-turn audits and reviews, and:

- final archive `s1-backfill-1/stopped.nmos.zip` (written by the name-gate stop after all 240 turns),
  SHA-256 `cf22199a31a4a763264e097469fe719d19351c90c58ddd70f82311a56d936804`;
- `fresh-readback-summary.json` (`48e4e798…`) / `verify_fresh_readback.py`: preservation verified,
  evidence verdict `defect` (the name gate);
- `semantic-summary.json` (`195082ba…`) / `post_audit.py`: every alias, ending and confirmation, 17
  fresh prefix reads;
- `ui-readback-summary.json` (`39be9ab2…`), `inspector-readback-{en,ko}.html` / `verify_ui.py`;
  `held-by-prefix.json`.

Not verified: the 233 held-doubt path in a sequential run, first connection, the 1,440-call comparison,
the 10k latency gate and live acceptance. One run only; the c0b0a5b run's 233 failure and this run's
pass are single samples. NMO-35 (turn 200) remains open and blocks the 3/3 name gate.
