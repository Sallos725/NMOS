# Fresh S1 on 4cc7ddd (2026-10-04)

**Incomplete: a technical stop at turn 62 after 62/240 jobs and 63 calls.** The main reply for turn 62 was
JSON with a trailing comma (`"hidden_from": [],` before `}`); the client raised `ReplyError` and the
experiment, which allows no retry, stopped. This is not an accuracy verdict and not the output cap
(`finish_reason=stop`, 945 output tokens of 8,192). None of the declared role scenes (74 onward), the
turn-233 doubts this commit adds, or the turn-239 name gate was reached. No further call was made.
This report is not a release or default-switch verdict; `extract-v15` remains the default.

**High risk:** current/historical role state, entity identity, provenance and extraction generations.
The measured product code is unchanged; this is an evidence report.

## Target and method

- Product: `4cc7ddd0cf1af6a49f51e87d5552e45063fedf33` (PR #251), `NMOS_EXTRACT_COMPILER=extract-v16`.
- Generation: **`extract-ba2d952e57b5e468cef813c6e6f52273`** (computed on 4cc7ddd before any call; only the
  confirmation fingerprint differs from c0b0a5b's `extract-e9b9db7…`: `DOUBTS`). v3 confirmation system
  SHA-256 `c5fe766ad7541573ce74e09f6f5282b8d6f4592602bd933f5bd331c85f986413`, unchanged.
  `extraction.py` SHA-256 `11637728d854b064bd3c48e05c99a244a8a7d84fe9f80ad0b46632d7f7119983`.
- One new database restored from the preserved synthetic S1 baseline (481 source messages; archive
  SHA-256 `b89102254a34ed84c8c5f7618281e6a42f7c42c7c203091cc3e64b82586a3597`); no earlier database resumed.
  Actual sequential extraction worker, one worker, turns 0–239 planned, no retries.
- The c0b0a5b runner and checks were reused. **Changed conditions** (recorded in the run's PLAN before
  execution, PLAN SHA-256 `06647db39ffa5bf46bae466d15219c4bd0cdb39d39ddbb56be2da78cd60b71cb`):
  - commit and generation as above;
  - main `max_tokens` 4,096 → **8,192** (owner; production sends no cap); confirmation stays 512;
  - call ceiling 240 main / **64** confirmation (was 32); output budget **360,000** (was 336,384);
    input stop threshold unchanged at 4.2M;
  - the grader counts a pending row whose reason ends ", confirmation says ended", with a matching doubt
    confirmation (yes, quote present), as held for the owner, as the owner's turn-233 criterion requires;
    an ordinary held ending and a missing ending are graded as before;
  - a failed turn-233 check is recorded and the run continues to 239 so the name gate is measured;
    every other declared scene still stops on failure.
- Verdicts fixed before the run (74, 86, 87, 88, 99, 144, 233; wrong automatic endings ≤ 1 with the 227
  class counted; any false join stops; names 3/3 at 239). Every newly served alias and every negative
  role row paused for local source review before the next call.
- Before execution: 25 instrumentation tests passed, including four that grade the actual 4cc7ddd
  `ended_roles` / `confirm_endings` output (planned + reverse held after a yes; both dropped after a no;
  now-applied with its reverse held; a doubt confirmation cannot excuse an ordinary held row); 113 scoped
  repository tests at 4cc7ddd passed (role-ending, doubt, review, alias and v16 files; no model call).
  These are not the full suite.

## What was measured

| Check | Observed result |
|---|---|
| Jobs / calls | 62 done / 63 calls (all main); 178 jobs queued, the turn-62 job at 1 attempt with its parse error |
| Stop | turn 62, `ReplyError`: invalid JSON (trailing comma, line 69 col 5), HTTP 200, `finish_reason=stop` |
| Known bad aliases at 30 / 34 / 43 | none recurred (3/3 checks passed) |
| Declared role scenes | none reached (first is 74) |
| Role endings | 0 negative role rows, 0 confirmation calls, 0 doubts, 0 applied, 0 held |
| Wrong automatic endings / false joins | 0 / 0 |
| Names at the last completed turn (61) | 강무진/무진, 윤하람/하람, 백이안/이안 joined (3/3). **Not** the turn-239 gate |
| Turn 88 readback, 233 doubts, Inspector listing of endings | not reached / nothing to list |

Roles current at 61 (fresh prefix read): 윤하람 → 오봉순 (inn dining help), 서도윤 → 추오월 (map-shop
assistant), 서도윤 → 오봉순 (inn guest). Turn 0's prompt hash equals both c0b0a5b runs'
(`f42304da…`); from there the stored state, and so turn 62's input, differs per run (`bff9a5c1…` here,
`62597531…` and `cc6bac7c…` in the c0b0a5b runs, both of which passed turn 62).

### Every also_called row

All eight were served and newly joined; each was reviewed against the TARGET before the next call.

| Turn | Stored ID | Subject | Object | Value | Stored / served outcome |
|---|---:|---|---|---|---|
| 0 | 1147 | `서도윤` | `도윤` | `도윤` | valid; newly joined, correct |
| 1 | 1160 | `오봉순` | `null` | `오 사장` | valid; newly joined, correct (self-introduced title) |
| 10 | 1213 | `서정호` | `null` | `정호` | valid; newly joined, correct |
| 18 | 1254 | `강무진` | `null` | `무진` | valid; newly joined, correct |
| 24 | 1285 | `백이안` | `null` | `이안` | valid; newly joined, correct |
| 25 | 1286 | `나무 오리 인형` | `null` | `특별상` | valid; newly joined, correct (an item: the prize is that figure) |
| 33 | 1317 | `윤하람` | `null` | `하람` | valid; newly joined, correct |
| 59 | 1418 | `추오월` | `null` | `오월` | valid; newly joined, correct |

No pending, rejected or redundant alias row was emitted in 0–61.

## Time and cost

| Lane | Calls | Input tokens | Output tokens | Cached input reported | HTTP time |
|---|---:|---:|---:|---:|---:|
| Main, successful extractions | 62 | 689,484 | 64,354 | 356,032 | 217.264 s |
| Main, failed turn 62 | 1 | 11,559 | 945 | 5,760 | 3.836 s |
| Confirmation | 0 | 0 | 0 | 0 | 0 |
| Total | 63 | 701,043 | 65,299 | 361,792 | 221.146 s |

Started 09:01:16 KST, stopped 09:06:01 KST: **284.2 s** elapsed, including 59.0 s of local review
waits. Main median 3,334 ms, maximum 8,724 ms; maximum output 2,510 tokens (the 8,192 cap was never
approached). Uncached estimate at the owner's rates ($0.14 / $0.40 per million): **$0.12426562**.
Not an invoice.

A new read-only connection reconciles all 62 stored extraction records: raw replies, usage and
assertion lists equal the captured evidence, and stored usage plus the failed call equals the HTTP
totals exactly (inputs, outputs and cached tokens). The failed reply's full body, raw text and usage
are preserved. On an isolated clone the Inspector (`en`, `ko`) and the facts API return 200 with no
automatic or held ending to list (none existed); no repair was run, the external HTTP transport was
guarded to raise, and the extraction count was unchanged (0 model calls).

## Cause (zero-call scan of the preserved replies; no change made here)

Every preserved PR #251 reply under the owner's evaluation root was re-parsed (1,423 HTTP records,
main and confirmation). Apart from two simulated self-test bodies and the c0b0a5b retry's `length`
cut, exactly **four replies with `finish_reason=stop` fail to parse, all at S1 turn 62, all with the
same trailing comma** after the last field of an assertion (`"hidden_from": [],` then `}`):

| Run (owner-local) | Attempt | Error |
|---|---|---|
| `2026-10-03/sequential-alias-v5` | 1 and 2 | Expecting property name, line 69 / 71 |
| `2026-10-03/sequential-alias-v10` | 1 | Expecting property name, line 69 |
| this run (`4cc7ddd`) | 1 | Expecting property name, line 69 |

The prompt already asks for no trailing comma, and `response_format: json_object` is sent, but this
endpoint returns fenced text that is not held to JSON. At temperature 0 a same-input retry repeats the
comma (alias-v5's second attempt), so the product worker's retry does not get past it either: the
turn would stay unextracted. The two c0b0a5b runs passed turn 62 on different stored state (different
prompt hashes). So the stop is a product robustness defect in reply parsing, not something 4cc7ddd
introduced (it changes only the post-processing of `roles_ended`). The fix (`8fe66d1`, `llm.parse_json_object`)
and the fresh run approved by the owner after it follow in `extract-v16-8fe66d1-sequential.md`.

## Evidence and limits

Owner-local root: `/home/grantkim725/nmos-eval/pr251/2026-10-04/sequential-4cc7ddd/` — PLAN, approval,
frozen run/source hashes, every request and reply, per-turn audit and review files, and:

- stopped archive `s1-backfill-1/stopped.nmos.zip`, SHA-256
  `ef505cbf3f68d87bca8f061b6c407c2a6b9cf50d0c0a64597eed58ea2140faa4`;
- `fresh-readback-summary.json` / `verify_fresh_readback.py` (preservation verified, evidence
  unverified/incomplete);
- `semantic-summary.json` / `post_audit.py` (every alias, endings, confirmations, fresh prefix reads);
- `ui-readback-summary.json`, `inspector-readback-{en,ko}.html` / `verify_ui.py`.

Analysis-output SHA-256: `fresh-readback-summary.json` `932c7851…`, `semantic-summary.json` `a25daf23…`,
`ui-readback-summary.json` `2d4eccb5…`.

Not verified: every declared role scene, the 233 doubts and their Inspector listing, the turn-239 name
gate, first connection, the 1,440-call comparison, the 10k latency gate and live acceptance. A resumed
run from this database would not count as a fresh S1; another fresh run needs the owner's approval.
