# PHASE-28 Q5 (c) on S1, at cc1f6e9 (2026-10-04)

**Fixed-input comparison: 21/21 declared role checks, names 3/3 in every run, no wrong ending, no false join.
First connection: 4/7 and names 1/3, no false join, because with nothing extracted before it no turn sees any role or
name.** Both lanes ran on `cc1f6e9` (the `9aa7c57` product plus the comparison tool confirming aliases), generation
`extract-b88669ca66664b77df6ac117d741ea8e`; owner-approved (option A: S1 × 3, two workers; first connection once).
The backfill lane is the sequential S1 on `9aa7c57` (`extract-v16-9aa7c57-sequential.md`: roles 7/7, names 3/3).
Not a release or default-switch verdict; `extract-v15` remains the default.

**High risk:** current/historical role state, identity and provenance, extraction generations.

## Fixed-input comparison (S1 × 3)

`tools/eval_extract_sample.py run --compiler extract-v16` on the copy `nmos_age24_e13dee7_s1_1` (test Postgres, read
only), every turn's prompt built with the copy's stored `extract-v15` hints (`extract-6a63a892…`), three runs. A driver
capped output (8,192 main, 512 confirmation), kept every request and body, stopped on a main call's error (none), and let
only an HTTP 429 be retried (none occurred). Scored by the earlier comparison's method: the listed v15 role plus the
measured v16 rows through production reconciliation.

| Declared scene | Expected | Runs 1 / 2 / 3 |
|---|---|---|
| 74 mentorship, 86 eve of the move, 88 settling in, 99 promotion elsewhere, 144 shop closure | kept | kept ×3 each |
| 87 move | ended | ended ×3 |
| 233 resignation | ended | ended ×3 (both directions, confirmations yes) |

Names (the copy's v15 aliases plus each run's v16 aliases): 강무진/무진, 윤하람/하람, 백이안/이안 joined in all three
runs. Valid endings: 87, 135 (one run), 159, 219, 233 (both directions) are the story's real endings. 88/89 (the inn
stay) and 234 (the navigation job) end again a role that ended the turn before: the fixed v15 hints still list it,
since v15 never ended it; the sequential lane does not list an ended role. Turn 179 proposed ending the attic residence
(still listed in the v15 hints) on "이제 너는 내 조수가 아니다"; the confirmation said no in two runs and it was held, never
applied. Confirmations: role 28 yes, 2 no, 3 `planned` doubts answered no; alias 3 yes and 3 held.

The three held aliases (`추오월 → ?추 영감님`, turn 29, every run) were held as "quote without the name" after a yes:
a `?description` (ADR 0024) can never be in a quote. That was a defect of the Phase 29 selection, fixed in `cd68657`
(such a reveal keeps its own path; a new generation, `extract-ccb3d153…`); none of the other runs asked one. At turn 200
the main reply did not write `윤하람 → 도도` under these inputs, so this lane does not exercise that confirmation (the
sequential lane does). Rows: v15 stored 1,086; v16 1,171 / 1,159 / 1,175.

759 calls (720 main, 39 confirmation), input 8,748,262 (cached 7,195,872), output 800,484: **$1.54 uncached** (about
19 % over the $1.3 estimate: 12.1k input per main call against the 9.7k calibration), 24 min with two workers. No HTTP
error, length or unparsable reply; every `finish_reason` `stop`.

## First connection (S1 once)

S1 synced at once into a fresh database and extracted by the worker in the product's order, newest turn first. Graded
by prefix reads before and after each declared scene, and the names at the end.

| Declared scene | Result |
|---|---|
| 74, 86, 88, 144 | kept |
| 87 move, 233 resignation | **not ended** |
| 99 promotion elsewhere | **no role before the scene** (the inn role was written as `하람 → 오봉순`, a name not joined to 윤하람) |
| Names at the end | 백이안/이안 joined; **강무진/무진 and 윤하람/하람 not** |

Every turn's extraction showed **no CURRENT ROLES, no NAME PAIRS and no known characters**: newest first, each turn is
extracted before every turn before it, so the hints `extract-v16` builds on are always empty. Endings could only come as
free negative roles in other words, which ADR 0013 does not match (233: `항해사: 청새치호에서 일함` beside the listed
`항해사로 고용됨`). No false join: the persona alias `도윤 → 정호` (turn 129, not asked: the persona's) joins nothing, but
leaves 도윤 ambiguous between 서도윤 and 도도. Alias confirmations 13 yes, 2 no, 1 quote not in the turn; held 서정호 → 정호
(a correct alias), 추오월 → 정호 and 도윤 → 람이 (both wrong). 256 calls (240 main, 16 confirmation), input 2,446,848,
output 307,669: **$0.47 uncached**, 18.6 min, no error.

Switching an existing chat to `extract-v16` re-extracts it oldest first (the backfill lane, which passes); this lane is
a chat NMOS sees for the first time with a long history. PHASE-28 Q2 records the limit; measured, it removes the
corrections entirely for such a chat until later turns are extracted again. Changing the first-sight order is a product
decision, not made here.

## Evidence

Owner-local: `/home/grantkim725/nmos-eval/pr251/2026-10-04/q5c-cc1f6e9/` (`PLAN.json` `0a0971d1…`, `drive.py`
`ed9d59d5…`, `score.py` `181663fe…`, `score.json` `4800e5d7…`, every request and body under `calls/`, per-turn outputs
under `out/v16/`) and `first-s1-cc1f6e9/` (`PLAN.json` `b60e2df5…`, `run_first.py` `8bcf81dd…`, `result.json`
`5424e147…`; database `first_cc1f6e9_s1` on the bench Postgres). `q5c-prep/PLAN-draft.md` holds the options and
calibration the owner chose from.

Limits: one story (S1; S2 is the same text). The fixed v15 hints miss the joins and endings v16 makes itself, so the
comparison measures variance and v16's rows on fixed inputs, not the stored state a user gets. Not run: S3/S4/S4b,
the owner's chats, the 10k latency gate and the live runs (Q5 (d)).
