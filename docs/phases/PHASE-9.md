# Phase 9 — Accountable Packets: Ledger, Excerpt Room, Echo, Replay

> **Status: complete (2026-09-26), released in `v0.1.0-beta.19`.** On
> 2026-09-26 the owner asked for this work on a new branch ("새 브랜치 만들어서 하고싶은대로 해봐"),
> after a written review recommended it as the next step. It is Track B, B6 ("strategic selection"),
> narrowed to recording and budgeting what the packet holds. The questions below were answered with the
> recommended option, as the owner has done for every earlier phase; the owner approved the merge after
> review. ADR 0027, D39. Evidence: `docs/perf/phase9-packets.md`.

## Questions and answers

| # | Question | Answer (recommended) | Alternatives not taken |
|---|---|---|---|
| Q1 | How is the budget split? | **Room for the best excerpt** (30 % of the budget inside the frame; the excerpt shortened to its best sentence, or cut, to fit), **no excerpt that only restates an offered fact** (half its spans in the line's content), and a **cap on parser state** (40 %). Facts and threads keep their order and ranking. | (b) Fixed shares for every section. (c) One score across sections: more tuning, and nothing to tune it on yet. |
| Q2 | Where is the ledger kept? | **On `retrieval_trace`** (jsonb `lines` and the request's inputs), pruned and deleted with the trace. | A `packet_line` table, once something needs to query lines across traces in SQL. |
| Q3 | Measure use? | **Echo, report only**: how much of each line reappears in the next reply. It never changes ranking in this phase. | Leave use unmeasured (B6 later). |
| Q4 | Change the token estimate or the default reserve (600)? | **No. Measure only.** The estimate over-counts Korean by 1.4–1.75× on three tokenizers, but a lower estimate can overflow the reserve on tokenizers that were not measured. This is K26, left for a later decision. | Lower the non-ASCII rate; raise the default reserve. |
| Q5 | Where is the ledger shown? | **The Inspector** ("Last packet", and a column in Recent retrievals) plus read-only API. The plugin is unchanged. | Per-line provenance in the plugin's Status tab (a plugin release); owner repair buttons (B7). |

## Goal

Every request's packet is accountable. What was offered, what went in, what was dropped and why, and
where each line came from are recorded. The same request can be compiled again exactly, or by another
policy, from the immutable ledger. Raw evidence gets room in the budget again.

## Evidence behind the scope

- **Budget saturation on real chats.** The owner's production traces (168 requests, 4 chats,
  2026-09-23–25; aggregate SQL only, no chat text read) show:
  - packets at a median of 566 of 600 estimated tokens;
  - an excerpt placed in 7 requests (12 excerpts);
  - 114 packets with facts and no excerpt, and 42 that dropped an eligible excerpt.
- **No record of what was placed.** Traces counted offered fact lines (up to 12 = 8 facts + 4 claims)
  but not which reached the model. Twelve lines of about 50 tokens exceed the budget, so some were
  dropped without a trace.
- **Evaluation blind to the budget.** Memory-evaluation packets averaged 167 tokens.
- **Token estimate.** On synthetic Korean fixture text, `estimate_tokens` over-counts prose by 1.42–1.75×
  and packet fact lines by 1.14–1.19× (qwen3-embedding, gemma4, deepseek-v4.1-flash tokenizers).
- **Grounding is not the gap.** Of the 3,169 valid assertions in the recorded real-model runs, 96.9 %
  quote evidence found verbatim in the target turn, and none is below 0.69 trigram containment. A
  grounding check would change almost nothing, so it is out of scope.

## In scope

1. Migration 0020: the ledger and request inputs on `retrieval_trace`; `revision_embedding.created_at`.
2. `packet-v1` (Q1), `NMOS_PACKET_POLICY` (default `packet-v1`, `packet-v0` available).
3. Provenance on every line: assertion id for facts, claims and threads; revision id for excerpts; key
   for state. Placed secrets carry `hidden_from`.
4. As-of reads: fact, state, lexical, vector and owner-link reads accept a head position and a knowledge
   time. The request path keeps its statements.
5. Echo and the possible-leak flag (Q3); `GET /v1/trace/{id}/audit`.
6. The answer probe `tools/eval_packet_answers.py`: two packets for one request (recorded `packet-v1`,
   replayed `packet-v0`), answered by a response model, scored and echo-audited.
7. Replay (`GET /v1/trace/{id}/replay?policy=`) and `tools/replay_packets.py` (read-only A/B).
8. Inspector: "Last packet" and the Recent retrievals column (Q5).
9. Memory evaluation: a `full-v0` mode and two Korean budget-pressure cases.

## Out of scope

- Using echo or replay results to rank anything (B6 labels, learned selection).
- Changing extraction, the registry, relevance scoring (`relevant_facts`) or knowledge marks.
- Changing the token estimate or the default reserve (K26).
- Any plugin change; any change to gating, deadline or the request's shape.
- Owner repair from the ledger (B7), MCP (B6), canon (B4), hard POV (B5).

## Acceptance criteria

- [x] Every existing test and memory-evaluation case passes; no stale memory in any mode.
- [x] The two budget-pressure cases answer with `packet-v1` and not with `packet-v0`, and every other
      case answers the same under both (`test_memory_eval.py`).
- [x] Each trace lists every offered line with kind, provenance, cost, outcome and reason. Each fact
      line leads to its assertion and the extractor generation of the trace (`test_packet_ledger.py`).
- [x] Replay with the recorded policy reproduces the recorded ledger and text after the story went on
      and after facts and vectors were derived for turns that were already on the head (bitemporal). A
      change before the request's position makes replay and audit report `changed`. A reroll of the
      reply does not.
- [x] Echo: a reply repeating a placed fact echoes it; a placed secret echoed is flagged.
- [x] Retrieve latency at 10,000 messages within +5 ms p50 of beta.18 (`docs/perf/phase9-packets.md`).
- [x] Inspector shows the last packet's ledger in Korean and English.
- [x] `ARCHITECTURE.md` (D39), ADR 0027, README, the Korean guide, KNOWN-ISSUES (K11, K15, K26), CHANGELOG.
- [x] Real-host smoke with the unchanged plugin: traces from real PocketRisu requests carry a ledger
      that replays as reproduced, and the audit finds their replies (`docs/perf/phase9-packets.md` §7).
      It also surfaced an older bug (a short current message recalled as memory of itself), fixed here.
- [x] Answer probe with two response models on synthetic scenes, recorded under `fixtures/model/phase9/`
      (`docs/perf/phase9-packets.md` §5).

## Stop conditions

Stop and ask the owner when:

- a replay with the recorded policy fails to reproduce for a reason other than those ADR 0027 lists;
- `packet-v1` loses a memory-evaluation gold that `packet-v0` reached;
- the ledger would need chat text beyond what traces already hold (query, previous reply), or a new
  retention rule;
- echo would feed ranking, or the plugin would need to change.
