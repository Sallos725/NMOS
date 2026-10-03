# Fresh S1 on c0b0a5b (2026-10-04)

**First run: defect, stopped at turn 233 after 234/240 jobs and 239 calls.**
The normal resignation was classified `planned` for one direction, with the reverse
omitted. Neither directed employment role ended. A separate wrong alias at turn 200
made 윤하람 ambiguous; the three name pairs resolve 2/3 at the last measured turn.
The owner requested one fresh repeat after this result; its evidence is kept separately.
This report is not a release or default-switch verdict. `extract-v15` remains default.

**High risk:** current/historical role state, entity identity, provenance and extraction
generations. The measured product code is unchanged; this is an evidence report.

## Target and method

- Product: `c0b0a5ba38ffb27ce939fad249169340517f0ce2` (PR #251).
- Generation: `extract-e9b9db7bfa4921c0e758fb3718f397fb`; v3 confirmation system
  SHA-256 `c5fe766ad7541573ce74e09f6f5282b8d6f4592602bd933f5bd331c85f986413`.
- One fresh copy of the preserved synthetic S1 baseline, 481 source messages; actual
  sequential extraction worker, turns 0–239 planned. Baseline archive SHA-256
  `b89102254a34ed84c8c5f7618281e6a42f7c42c7c203091cc3e64b82586a3597`.
- Same authorized envelope as `4e76c70`: at most 240 main + 32 confirmation calls,
  one worker, no retries, input stop threshold 4.2M, output budget 336,384;
  `max_tokens=4096` main / `512` confirmation. Production remains uncapped.
- Every newly served alias and every negative role assertion pauses for local source
  review before the next call. All aliases, including rejected and redundant rows,
  are preserved. These review pauses are measurement overhead, not product latency.
- Frozen declared role cases are unchanged. A confirmation-held normal ending is a
  reported cost and may continue; missing extraction or a `planned` classification
  without a matching pending ending still fails. False joins, a new wrong-ending kind,
  or more than one wrong automatic ending stop. The known 227 class is counted.
- 94 scoped repository tests passed before execution; 20 instrumentation controls
  passed, including rejection of a preserved wrong stored residence and a mutation
  with only reverse mentorship. Claude's full-suite count is not substituted for
  this run's checks.

## First run: stored outcomes

| Check | Observed result |
|---|---|
| Declared role scenes | 6/7; stop at 233 |
| 74 mentorship, 86 preparation, 99 other employer, 144 closure | Existing role retained |
| 87 move | Old inn role ended, confirmation yes |
| 88 settling in | New residence retained; **no ending proposed**, no confirmation called |
| 233 resignation | Both current employment roles remain; R1 `planned`, R2 omitted |
| Frozen normal endings | Applied 1/2 scenes, 1/3 directed roles; held 0/2 scenes, 0/3 roles; missed 1 scene / 2 roles |
| All confirmation candidates | Applied 5, held 0, wrong applied 0 by local whole-scene review |
| Invalid free negative role row | One at 135, registry-rejected (`object_type must be character`); not a confirmation hold |
| Names at turn 233 | 강무진/무진 and 백이안/이안 joined; 윤하람/하람 not joined (2/3) |
| Final turn-239 identity / turn 237 | Not run; turns 234–239 unmeasured |

The five confirmed endings are the inn move (87), dismissal and explicit cancellation
of sponsorship (two roles at 134), attic departure (159), and departure to school (219).
Their confirmation quotations are separately rated **Supports 3 / Weak 2 / Uncertain 0 /
Contradicts 0 / Missing 0**. These are unblinded local judgments: the move and school
boarding quotations require the rest of TARGET to establish a completed change.
All five yes replies pass the existing quote/LATER contract. Zero held normal endings
is not full normal-ending recall: the missed resignation never reached confirmation.

At 227 there is no ending proposal. Sponsorship already ended on an explicit
cancellation at 134; this run **does not demonstrate that confirmation fixed 227**.
Likewise, unlike the `4e76c70` run, 88 does not exercise a wrong-candidate rejection.

### Two independently preserved failures

**Turn 200, alias attribution.** The model emits `subject=윤하람`, `object=null`,
`value=도도`, quoting `"도도, 술 마셨지."`. 하람 is speaking to 도윤, so this is a
wrong alias. KNOWN ENTITIES contains `윤하람` with `also=[하람, 람이]`; TARGET names
하람 and 도도. The presence check therefore admits the row as written. This is a
limit of presence checking, not evidence that the implemented absence rule failed
its own contract. The stored row is valid/served, but the resolver leaves 윤하람
ambiguous between 하람, 람이 and 도도 rather than joining the two entities. A fresh
prefix read reproduces it; removing only assertion 2077 from the in-memory resolver
input restores 윤하람/하람/람이. No database repair or downstream replay was performed.

The legitimate triple had joined at **185**, retained through 199. At 182 this run
instead emits the wrong `백이안 → 도도`, which is correctly held. Turn 81 emits no
bad alias, so it cannot be counted as an observed block. The previous run's specific
81/182/200 model outputs must not be treated as fixed inputs of this sequential run.

**Turn 233, missing completed resignation.** CURRENT ROLES contains both
`R1 {{user}} → 강무진` (navigator) and `R2 강무진 → {{user}}` (employer), both from
149. The raw reply contains only:

```json
{"role":"R1","when":"planned","evidence":"이제 항해사 일은 그만둬야 한다고."}
```

No confirmation is dispatched and no negative or pending role assertion is created.
The returned event does record announcing resignation. Both directed roles remain
current on fresh readback. This differs from the old full/given-name counterpart
rejection and from a confirmation no: the decision is already in the main model's
reply. The frozen resignation gold fails; it was not relabeled after the response.

## First-run time and cost

| Lane | Calls | Input tokens | Output tokens | Cached input reported | HTTP time |
|---|---:|---:|---:|---:|---:|
| Main | 234 | 2,776,138 | 251,616 | 1,358,144 | 1,075.802 s |
| Confirmation | 5 | 23,013 | 190 | 640 | 3.400 s |
| Total | 239 | 2,799,151 | 251,806 | 1,358,784 | 1,079.202 s |

Terminal status: **01:26:10 KST**, elapsed **2,139.994 s (35 min 40 s)** including
**1,038.178 s** of local semantic review waits. Excluding those waits gives 1,101.816 s
(18 min 22 s); the remaining difference from summed HTTP time includes worker/DB/audit
work. Confirmation median **680 ms**, maximum **734 ms**; main median 3,939 ms,
maximum 29,974 ms. This is catch-up work in the worker, not time added to every chat
request. Five confirmations add 2.14% to the call count and 0.32% to summed HTTP time.

HTTP/format/usage errors, retries and truncated outputs: **0**. Maximum output
4,015 main / 45 confirmation, both below the experiment caps. All 234 stored raw
records and assertion lists match captured evidence through a new read-only connection;
HTTP totals equal stored input/output/cached tokens and separate `usage.confirm`.
Duration counters use different timing boundaries and are not asserted identical.

Owner-provided per-million rates ($0.14 input / $0.40 output), ignoring cache discounts:
**$0.49260354** total, including **$0.00329782** confirmation. This is an estimate,
not a provider invoice or current account balance.

## Zero-call read latency and Inspector readback

The same stopped database and measured prefix (through 233, 468 messages, 1,049 served
assertions) were read with both code snapshots. Each used a fresh read-only connection,
three warmups and 30 timed `facts.memory_view` calls, in baseline-then-candidate order.

| Code reading the same stored data | Median | p95, nearest rank | Range |
|---|---:|---:|---:|
| `4e76c70` | 31.00 ms | 45.59 ms | 28.87–47.57 ms |
| `c0b0a5b` | 30.26 ms | 45.19 ms | 28.62–47.36 ms |

No slowdown is apparent in this small diagnostic. It is not an equivalence test or
Phase 28's 10,000-message `/context`/live-host latency gate. The row set is identical;
the older resolver can interpret it differently. Network and query embeddings are
outside this component measurement.

On a separate clone, the actual facts HTTP endpoint through TestClient took **67.02 ms
median / 84.61 ms p95** (three warmups, 20 reads). This has no old-code HTTP comparator
and the full head includes older-generation fallback for six unmeasured turns. The
Inspector returns 200 and lists the recent automatic ending at 219 with its
`fact_retract` action. No repairs were executed; no held ending existed to inspect.
External HTTP was guarded to raise, and extraction count was unchanged: **0 model calls**.

## Evidence and limits

Owner-local root: `/home/grantkim725/nmos-eval/pr251/2026-10-04/sequential-c0b0a5b/`.
First-run PLAN SHA-256: `0ba54a59eca14c60ba1532c11beb657893228e18268d3eb10371f1324b8f663f`.
It contains approval, frozen source/run hashes, every request/reply, source context,
all per-turn semantic reports/reviews, the stopped archive and these zero-call outputs:

- `fresh-readback-summary.json` / `verify_fresh_readback.py` (exit 0: verifies preservation
  and reproduces the defect, not an overall pass);
- `semantic-summary.json` / `post_audit.py` (all aliases, endings, fresh prefix reads,
  and the single-row counterfactual);
- `latency-baseline.json`, `latency-candidate.json` / `measure_reads.py`;
- `ui-readback-summary.json`, `inspector-readback.html` / `verify_ui.py`.

No product/default/generation change, first-connection run, full 1,440-call comparison,
10k latency gate or live gate follows automatically. NMO-24 and NMO-35 remain open.

## Every first-run also_called row

The resolver uses subject/value; the raw object is retained separately. “No effect”
means the row was not a served alias, not that it was semantically correct. Every one
of the nine newly joined pairs was source-reviewed; no false join was observed in
the measured prefix. One served wrong alias instead introduced ambiguity.

| Turn | Stored ID | Subject | Object | Value | Stored / served outcome |
|---|---:|---|---|---|---|
| 0 | 1147 | `서도윤` | `도윤` | `도윤` | valid; newly joined, correct |
| 1 | 1160 | `오봉순` | `null` | `오 사장` | valid; newly joined, correct |
| 3 | 1171 | `?검은 고양이` | `null` | `먹물` | pending; alias not stated in the turn |
| 10 | 1215 | `서정호` | `null` | `정호` | valid; newly joined, correct |
| 18 | 1250 | `강무진` | `null` | `무진` | valid; newly joined, correct |
| 24 | 1278 | `백이안` | `null` | `이안` | valid; newly joined, correct |
| 33 | 1314 | `윤하람` | `null` | `하람` | valid; newly joined, correct |
| 53 | 1396 | `서정호` | `null` | `미친 해도쟁이` | valid; no served alias (character claim about another name) |
| 59 | 1420 | `추오월` | `null` | `오월` | valid; newly joined, correct |
| 104 | 1604 | `조개 부적` | `null` | `부적` | pending; alias not stated in the turn |
| 110 | 1627 | `?쪽배` | `null` | `청새치호에 딸린 쪽배` | pending; alias not stated in the turn |
| 133 | 1737 | `항만청장` | `null` | `청장` | valid; newly joined, correct |
| 182 | 1958 | `백이안` | `도도` | `도도` | pending; alias not stated in the turn |
| 185 | 1977 | `윤하람` | `null` | `람이` | valid; newly joined, correct |
| 185 | 1978 | `{{user}}` | `null` | `도도` | pending; alias not stated in the turn |
| 193 | 2020 | `윤하람` | `람이` | `람이` | valid; already joined |
| 193 | 2021 | `{{user}}` | `도도` | `도도` | pending; alias not stated in the turn |
| 200 | 2077 | `윤하람` | `null` | `도도` | valid; wrong attribution, subject becomes ambiguous |
| 206 | 2100 | `람이` | `윤하람` | `람이` | pending; alias not stated in the turn |
| 217 | 2155 | `윤하람` | `람이` | `람이` | pending; alias not stated in the turn |
| 217 | 2156 | `{{user}}` | `도도` | `도도` | pending; alias not stated in the turn |
