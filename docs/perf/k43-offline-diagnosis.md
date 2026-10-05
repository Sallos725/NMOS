# K43: offline stage diagnosis, 2026-10-05

Base: `main` `9947d2c0668e0a6708e4e17fe806c832b57dbd28` (verified by Git clone and GitHub tree).
Scope: NMO-37's measured **lent book** case, `s3_r4_book`. No gift cases, extraction changes,
new predicates, model calls, packet policy changes, or runtime fixes.

## Evidence boundaries

- [NMO-37](https://linear.app/sallos725/issue/NMO-37) remains Backlog. Its October 4 comment reports S3
  5/6 in all three focused-v16 runs, the same book failure; the other S3 cases and S5 passed.
  The issue reports the same failure on v15. These are owner's measurements, not new measurements here.
- [PR #263](https://github.com/Sallos725/NMOS/pull/263) is open, not merged, head `b943cfec`.
  It changes KNOWN-ISSUES and STATUS only. Its second revision explicitly says gifts were not measured.
  It records a likely cause, not an established stage diagnosis.
- PHASE-28 Q6 excludes excerpt, sentence-anchor, fact-ranking and packet-policy changes from Phase 28;
  they must be re-scoped after measurement on corrected state. This diagnostic does not implement those changes.
- NMO-24's corrected read-only comment invalidates the pair-relation extraction omission hypothesis:
  names in `value` were missed by an object-only detector; information already existed under
  `knows`, `goal`, and `event`. The diagnostic searches subject, object **and value**. No extract-v17 proposal.
- Original gate DBs, captured requests and result files are outside this workspace and repository.
  The recorded locations are `~/nmos-eval/age24-v16-9947d2c/run/S3-1/` and
  `/tmp/nmos-age24-e13dee7/run/S3-1/`. No host connection was available here.
  Thus the actual S3 passage's first failing stage was **unconfirmed** when this note was written; it was then
  measured on the gate's own database (below, "Result on the gate database").

## Confirmed code path, separately from the live case

1. `facts.version_key` puts both positive possessions under one whereabouts key per resolved item
   (ADR 0016). `facts._versions` keeps the later holder current and preserves the earlier holder in history.
2. `memory_view` supplies current facts to `retrieval.gather`. `_annotate` adds current subject/object
   names and participants, not every historical holder's name.
3. `relevant_facts` scores current text/names, previous reply, variants, and first-person cues;
   it does not independently admit historical possession rows or search their text.
   A synthetic two-holder example loses the old holder's name route immediately after transfer.
   Previous reply, current scene, knowledge marks, repairs and other actual rows can change the live result.
4. Even when an item-name query admits the current possession, `fact_line(before=True)` does not print
   its old holder: `_prior` is restricted to `STANDING`, which excludes `possesses`.
   Printing current ownership alone would not establish **who lent** the item anyway.
5. Facts and passages are distinct routes: lexical/keyword/vector routes retrieve **source revisions**,
   then `fuse` applies RRF and admission bars. In-context revisions are excluded before `top_k`.
   `filled` can increase top_k/fact slots with budget before selection.
6. `packet-v11` chooses a qualifying vector's chunk even for lexical/keyword hits. It then grows from
   the best sentence; the actual query has no why/contents cue, so it retains the four-sentence cap.
   Mode/keyword secrecy checks can withhold it before the fitter. `compile_gathered` subsequently
   budgets, deduplicates and may shorten an offered excerpt.

| Path | What can be concluded now | What needs the original capture |
|---|---|---|
| Old possession | Preserved in history, not an independent current-fact candidate or historical possession rendering | Whether the two reported rows actually serve this request's generation/time and resolve to the same item |
| Current possession | Can be admitted by item/current-holder cues; no lender inferred | Admission, limits, Cast transfer, secrecy/mode and actual ledger placement |
| Lending passage | Independent route can answer despite fact gap | Source eligibility; lexical/keyword modes; vector availability/span; RRF rank; top_k; selected excerpt; fitter ledger |

Neither “increase budget” nor “add every past holder” is justified by the packet's missing title alone.

## Minimal diagnostic

`tools/diagnose_k43.py` uses existing `audit.replay`, observes its actual production readers and compiler,
and emits a private JSON capture. Database capture runs a **repeatable-read, read-only transaction**;
it never calls `retrieve`, starts a worker, enqueues extraction or writes retrieval traces.
The only embedder implementation is a supplied frozen vector; it has no network client.
It rejects vectors with a different projection/query prefix/query, and non-finite vectors.
No model endpoint or API key argument exists.

The capture records:

- Original trace, generations, recorded input/context, timestamps, options and original candidate/line ledger.
- Stored title-bearing assertions versus assertions served at the recorded time; folded current facts and history.
- Fact rank input/output and a full-limit diagnostic ranking under the same relevance/event rules.
- Raw lexical, keyword and vector output, route modes, fusion result, context exclusions and effective limits.
- Title-bearing head revisions, selected excerpt text/short form, mode/secrecy counters and compiled ledger/text.

`report.passage_paths` distinguishes route-output absence, fusion abstention, in-context exclusion,
top_k truncation, pre-fitter withholding, span/anchor/growth loss, and fitter decisions.
Route-output absence alone does not identify *why* SQL excluded a source: inspect source lifecycle/metadata,
cuts, normalization, route bars, broad-query/timeouts, and the per-route 50-candidate cap.
Ledger text is capped at 400 characters; shortened placed forms require inspecting the exact packet text.
No history entry or title match is itself proof of a lending action.

On the machine holding the preserved S3 database, use a restored copy of **one failed run** first.
Select the request whose query equals `이안이 빌려준 책 제목이 뭐였지?`; retain its trace ID, original
`rows-s3.json`, `texts-s3/s3_r4_book.txt`, request input and generation identifiers together.
The title-bearing passage must be checked against its actual lending scene, not just a later mention of the title.

```sql
-- Read only, on that run's database; if several traces match, keep each run's identity distinct.
SELECT id, created_at, query, policy, budget_tokens, extractor_key,
       embed_projection, recall_options, latency_ms, candidates, lines
FROM retrieval_trace
WHERE query = '이안이 빌려준 책 제목이 뭐였지?'
ORDER BY created_at;
```

```bash
cd apps/sidecar
# Set NMOS_DIAG_DATABASE_URL to the restored evaluation DB privately.
uv run python ../../tools/diagnose_k43.py --trace TRACE_UUID \
  --lexical-only --output /tmp/k43-s3-1-lexical.json
```

Lexical-only diagnoses the fact path and word routes; it **does not reproduce** an originally vector-enabled
gate request. Trace query vectors are not stored in `retrieval_trace`. If an exact query vector was already
preserved, supply it in a private file, with the original full projection key and exact prefixed query text:

```json
{"projection": "EXACT_TRACE_PROJECTION_KEY", "text": "EXACT_PREFIX_AND_QUERY", "vector": [0.1, 0.2]}
```

The numbers above are schema examples, **not usable measured embeddings**. Never fabricate an S3 vector.
If no such vector exists, an independent free local embedding with the original model/settings can support
a new vector replay, labelled as newly computed; do not pretend it reproduces the original timeout/fallback.
This tool itself makes no such call. A vector capture is run as follows:

```bash
uv run python ../../tools/diagnose_k43.py --trace TRACE_UUID \
  --vector /tmp/k43-original-query-vector.json --output /tmp/k43-s3-1-vector.json
# Recompute the stage report from the captured evidence, with no DB or model:
uv run python ../../tools/diagnose_k43.py --snapshot /tmp/k43-s3-1-vector.json \
  --output /tmp/k43-s3-1-report.json
```

Snapshot mode recomputes the **diagnostic report**, not SQL retrieval or a newly ranked packet.
On vector runs, inspect `replay.reproduced`, notes and original route modes before treating ranks as evidence.
Frozen-vector replay bypasses original embedding latency: a request that originally fell back is not the same
as a replay now forced to use vectors, even if a packet happens to match.
Changed-prefix, missing-trace or unrecorded requests yield no cause conclusion.
Capture outputs contain private story text; keep them outside the repo and do not publish them automatically.
Output paths use exclusive creation so earlier evidence is not overwritten.

## Verification performed here

`apps/sidecar/tests/test_k43_diagnosis.py`: **16 passed**, synthetic inputs only. Cases pin:
the two-holder history/current split; given-name candidate loss; absent historical possession rendering;
fusion bars versus top_k; a vector span excluding the title before fitting; a correct excerpt lost to budget;
stage report classification; value-text matching; frozen-vector provenance validation; an invalid replay;
the real `audit.replay` → `gather` → compiler chain with frozen vector and HTTP calls forbidden.

Scoped suite: **139 passed, 47 skipped** (Postgres unavailable), two dependency deprecation warnings.
No production DB, actual S3 replay, live host, real vector index or paid model was exercised.

```bash
uv run pytest tests/test_k43_diagnosis.py tests/test_transitions.py \
  tests/test_first_cue.py tests/test_packet_v10.py tests/test_packet_v11.py \
  tests/test_packet_ledger.py tests/test_packet_fill.py \
  tests/test_keyword_recall.py tests/test_keywords.py -q
```

Self-review: changes are diagnostic tooling, synthetic tests and documentation only. Observers call the original
functions and do not replace selection results; the full-limit fact call is diagnostic, not injected.
No schema, prompt, generation, policy, default, worker or plugin changes. Future retrieval changes would be
**high risk** for current/history correctness, provenance, knowledge isolation, replay and fail-open behavior.

## Result on the gate database (2026-10-05, read-only, no model call)

Run by Claude on the owner's machine with this tool (`9947d2c`, the gate's S3 run 1, `nmos_age24_9947d2c_s3_1`, the
main chat's trace of the book question; the same question also appears in S5's branch and new chat, where the new chat
correctly knows nothing). Two fixes were needed first: the gate sends each probe and deletes it, so a plain replay
reads `changed`; the tool now retries as the probe (`query`, audit.replay's PHASE-18 path). Lexical-only (the trace's
query vector is not stored).

| Stage | Result |
|---|---|
| Stored / served | `백이안 possesses 『북해 조류 일지』` and `서도윤 possesses …`, both turn 74, both served |
| Folded | 서도윤's possession current; 백이안's in its history (superseded) |
| Fact ranking | the current possession is an input and scores nothing: 0 of 1 kept even at the full limit (194) |
| Passage | the lending message (turn 74) is found and ranked 3rd; its excerpt misses the title: **excerpt span/anchor/growth** |

The recorded request (with vectors) placed the same excerpt: it ends at "…그의 입가에 아주 옅은 미소가 걸렸다. "서 선생.…".
The title sentence is the message's last, after a status block: "백이안이 책 한 권을 건넸다. 표지에는 『북해 조류 일지』라고
적혀 있었다." The query writes the given name (이안); the anchor sentence it picks holds "이안이", the title sentence
holds the full name "백이안이". **The first loss is the excerpt span**; the likely reason, to be confirmed by
Phase 31's deterministic case, is that the anchor does not read a known name's variants (ADR 0058 widens fact
mentions, not the excerpt anchor). The fact route loses too, as described above. Capture:
`/home/grantkim725/nmos-eval/k43-diag/s3-1-main-lexical-v2.json` (owner-local, private text).

## Decision boundary

**No runtime modification is proposed yet.** Once an original failed trace identifies the first loss,
choose one change at that stage rather than combining history expansion, RRF boosts, span changes and budget changes.
The old-holder fact gap alone does not establish the minimal sufficient fix for the actual lending question.
Do not add a gift scenario or claim the recorded workaround is newly verified.

After that identification, derive the smallest replay regression scope from the changed stage:
the failed `s3_r4_book` trace and its wrong-book forbidden check, other measured S3 cases, and the preserved S5
branch/new-chat traces, while retaining inactive-source, history/knowledge and replay checks. Broader measured
sets are needed only if the eventual change alters a shared ranker/policy. Report each replay/run separately.
The requested S3 live median 6/6 remains unverified; free deterministic checks do not complete NMO-37's live DoD.
