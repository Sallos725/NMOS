# AGE-24: M0 v2 recall candidate, 2026-10-02

Draft PR #241. Evaluation tooling only, on base `cf52cecad524c1d9c630e2a280760179b1290b3a` in
`codex/age24-recall-improvement`. No production source, extraction generation, facts, schema, scorer,
gold, prompt window or packet budget changed. Phase 23 remains current. **AGE-24 is not complete.**

## Which measurement

The original is the owner's retained `phase25/eval/v15/main-on.json`: M0 v2, main chat,
`extract-v15`, vectors ON, keyword routing ON, `packet-v10`, 4,000 tokens. Its SHA-256 is
`4ffe300ae96fefb22e5612789d7fc5c032e94cda7b6070840ac21cf11e6a0c83`.
It reports 16/23 memory-needed cases, 32/40 overall, one forbidden match.
This is a packet-evidence score, **not generated-answer accuracy**.

The original JSON has no runtime commit SHA or saved candidate/packet text. Its launch script points
to the now-missing `NMOS-p25s2` worktree. The original evaluation commit is therefore **unverified**;
current `main` is not substituted for it. The separate interrupted `age24-a013e2d` run (0/9 complete)
and the 20-call extraction experiment are different measurements and do not supply these seven failures.

New read-only reconstruction uses the retained `nmos_p25_main` copy and fixed generations:

- Extractor: `extract-fe5e340b99f9d2c5979e0192480cee7c`, compiler `extract-v15`; stored model `gemma4:31b`.
- Summary: `summarize-28fd99a5b31bf06478793f99b5ff4513`.
- Embedding projection: `embed-8ff0a8d435c02d61ed4939dcd7b68ff8`, `qwen3-embedding:8b`.
- Reconstruction cutoff: `2026-10-01T09:21:00+00:00`, the retained report's time, not a recovered runtime timestamp.
- Same 40 questions, gold, forbidden phrases, prompt windows, original `eval_rp.score`, budget and options.
  The old trace did not record `first_cue`, `history_marks` or `name_variants`; their replay behavior stays off.
- Query vectors frozen once from the existing local embedding model and reused by every candidate.
  Database connections enforce `default_transaction_read_only=on`.

The reconstructed baseline matches **every original case's score fields and packet token count**.
That corroborates the reconstruction; it does not turn its packets into historical records.
No v15-time retrieval traces were found. Private per-case evidence states that limitation explicitly.

## Candidate and measurements

`tools/recall_candidate.py` is loaded only by the experimental runner:

1. Preserve a qualifying vector match's source span when the same revision also has keyword hits.
2. Anchor the excerpt on the current question's keywords, without the previous reply affecting its tie-break.
3. For why/content questions only, expand contiguous context to at most 320 characters plus ellipses
   instead of stopping after four short sentence fragments. Other questions keep the original growth rule.

Source eligibility, ranking, scene/knowledge filters and the original budget fitter remain in the real
`audit.replay` path. No benchmark name, answer, entity name or case ID is supplied to the candidate.
It is tuned on this known set; there is no held-out validation.

The follow-up `--candidate --answer-spans` adds contiguous, source-offset-backed spans inside the same
retrieved sources: a nearby question-related title anchors an enumerated list; a why question needs
both causal connectives and a topic word (names shared by most candidates do not suffice); Korean
container questions retain the packing action that the four-keyword noun limit may omit. Fallback
remains the first candidate. `--frozen-candidates baseline` fixes the exact original fused candidate pool;
question/gold, source hashes and prompt windows are checked before use. `mode.json` names this mode,
hashes its retained inputs, and saved artifacts distinguish current route observations from replayed
route states. Original memory filters and budget fitting still run after span selection.

| Retained run | Memory-needed pass | All pass | Forbidden matches | Decision |
|---|---:|---:|---:|---|
| Original / reconstructed baseline | 16/23 | 32/40 | 1 | Comparison |
| Remove sentence ceiling for all questions | 14/23 | 30/40 | 1 | Reject: regressions |
| Vector span + current-question anchor | 17/23 | 33/40 | 1 | Improves one case |
| 320-character context for all questions | 18/23 | 33/40 | 3 | Reject: regressions / forbidden growth |
| Locally embedded small passages | 17/23 | 32/40 | 3 | Reject: regressions / forbidden growth |
| Context only for why/content questions | 19/23 | 35/40 | 1 | First selected candidate |
| First candidate, independent process repeat | 19/23 | 35/40 | 1 | Same packets and scores |
| Lists + unconstrained causal spans | 18/23 | 34/40 | 1 | Reject: one prior pass lost |
| Lists + topic-constrained causal spans | 19/23 | 35/40 | 1 | Stronger evidence, same score |
| Above + container-action spans | 20/23 | 36/40 | 1 | One additional pass |
| **Final, baseline candidates frozen** | **20/23** | **36/40** | **1** | Same gains, controlled candidate pool |

Memory score is **69.6% → 87.0%**, +17.4 percentage points; versus the first candidate, 82.6% → 87.0%.
No previously passing case is lost and no case gains a forbidden match. Three memory-needed questions
still fail. One other failure does not need memory and retains the pre-existing forbidden match.

The first 19/23 candidate's document and causal passes were semantically incomplete. The follow-up
places the document's actual 593-character list and the container's 234-character description/action
whole. It also places a 625-character causal passage covering the interaction with a later patch and
its installation, instead of matching an age reference alone. The precise intake/exhaust ordering is
still outside that passage. These checks improve evidence quality; they are not response-model tests.

Final audit found a nuisance variable: one already-passing age question had timed out on whole-message
lexical retrieval in the baseline but succeeded in a later run (50 versus 58 candidates). The score gain
was elsewhere, but the final mode freezes the baseline fused candidates rather than treating those
pools as equal. Candidate IDs/order and all focused source spans are checked against the baseline.
The original and intermediate artifacts are retained, including the timeout difference.

## Seven-failure diagnosis

The private report follows original source → stored assertions → candidates → injected packet for
each of the original seven failures. Three lose exact details during extraction; four retain relevant
facts that selection does not offer. In particular, stored assertion 8566 already satisfies both gold
groups for the document question; its missing full document list is a separate coverage limitation. Five of the seven have an answer-bearing source offered to the
reconstructed packet, but its excerpt misses the required span. These overlap: a later source excerpt
can recover information the structured fact omitted. There is no single confirmed first failure for all seven.

The most repeated observed downstream defect is **answer-bearing source selection without answer-bearing
excerpt selection**. The candidate measures a bounded correction to that behavior. It does not establish
that extractor work is unnecessary; closed historical promises and early-event ordering remain separate.

## Verification and reproducibility

Private artifacts are outside Git at `~/nmos-eval/age24-codex-recall-v1/`:
`protocol.json`, frozen query vectors, each run's per-case candidates and complete packet, helper-source
snapshots, `seven-failures-evidence.json`, `verification.json`, `runtime-status.json`, and `REPORT.md`.
The latest source snapshots are under `candidate-frozen-v2-confirm/`; the old `candidate-confirm/` remains the 19/23 reference. The first PR commit is `9d2f0a7`; snapshots identify the exact uncommitted follow-up implementation measured before its commit.

`tools/check_recall_candidate.py` re-reads every saved packet and runs the unchanged scorer. It refuses
case/scorer hash changes, partial runs, missing vectors, budget violations, lost passing cases, changed
memory denominators and any new forbidden match. The selected run exits 0. The rejected broad-context
run exits 1 for its actual regression and added forbidden matches (negative control).

```bash
PYTHONPATH=apps/sidecar/src:tools python -B tools/check_recall_candidate.py \
  "$HOME/nmos-eval/age24-codex-recall-v1" candidate-frozen-v2-confirm --reference candidate-confirm \
  --cases "$HOME/nmos-eval/phase18/m0v2-main/cases.json"
```

This gate does not call a model or touch the database. The optional replay runner also defaults to
cache-only embeddings. `--allow-local-embeddings` is an explicit local-only preparation mode; no
generation/extraction API exists in these tools. The discarded passage experiment used 911 local
embeddings, with its model isolated from external networking for the GPU portion; its preparation
scripts, vectors and usage are retained privately. It is not required by the selected candidate.

Targeted tests: 50 passed (candidate, source binding, cache and hook failure paths, keywords, packet-v10 pure logic, docs consistency). Verification results and commands are retained in the private report. A diff-scoped self-review covers
all added tools/tests and the retrieval/packet callers. **High risk if promoted to production:** excerpt
selection changes injected memory and can include stale or inappropriate neighboring text. Exact source
provenance, original budget fitting and no new forbidden matches are checked here, but live-host behavior,
all AGE-24 scenarios, held-out chats, generated answers and production latency have not been verified.
Draft PR #241 contains the evaluation tools and documentation. No deployment or production generation change was made.

The contiguous-span experiment above is complete for this fixed set. Remaining work is historical/early-source selection for the three failures and independent-data validation. These are not run here; no production rollout or AGE-24 completion follows from this result.
