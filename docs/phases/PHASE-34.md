# Phase 34 — Forensic recall, part 2 (Stage 7): what a line is for, and memory that stops repeating itself

> **Status: approved 2026-10-07 (the owner: every question as proposed; the live run (Q8 d) after a cost estimate),
> the current phase; steps 2–4 done (#278: labels, the rest, the threshold, the Inspector; S1 replayed: supportive
> repeats −24 %, stale tokens −76 %, the bench and the quote set as `packet-v13`; latency +0.7 ms at 10,000 messages),
> step 5 under way: `packet-v14` on the owner's trial environment since 2026-10-07; the default decision and Q8 (d)
> open.** Stage 7 of `docs/ROADMAP-1.0.md` ("Forensic recall"; original
> §48–50, §53; Track B, B6), part 2 of 2 (PHASE-33 Q0). Under AGE-10. Follows Phase 33 (`packet-v13`, ADR 0067, PRs
> #273, #274, #276); `0.4.0` follows this phase (R7).

## Why now

Phase 33 measured the overuse baseline (`docs/perf/phase33-baseline.md`, Q8). In live play (S1, 240 turns, 340
requests) **61 % of a packet's lines were placed in the request before it too**, and **38 % of its tokens went to
lines placed in each of the three requests before it**. The same memories hold the packet request after request: the
original's "a character should not constantly bring up old events" (§49). *(Corrected 2026-10-07: this paragraph
also cited the bench's echo, 10.6 % for repeated lines against 24.6 % for new ones, as the reply using repeated memory
less; the bench's replies are scripted, so those figures are the script's overlap with memory, not a model's use of it.
Whether a model uses repeated memory less is measured on real replies, Q8 d.)*

Today nothing looks across requests: each packet is chosen from scratch (`retrieval.gather`; the only state carried
between requests is the prefetched query embedding). Every line is offered by relevance alone, and `audit.py` says of
echo "never used for ranking".

Stage 7's done criteria still open: "overuse is measured by echo before and after" (`docs/ROADMAP-1.0.md`).

## Questions and proposed answers

| # | Question | Proposed answer | Alternatives considered |
|---|---|---|---|
| Q1 | What labels, and who assigns them? | **Four, by rule, at compile time; no model call.** **Required**: what the request cannot do without: State of characters named now, Cast, the story-so-far summary (amended 2026-10-07: the continuity every packet carries; scene summaries stay supportive), Private and Secret lines (knowledge boundaries), facts and threads the question names (mention in the query), `<Quote>` lines on the forensic path, and the first excerpt (the reserved one, ADR 0026). **Supportive**: everything else offered (facts found by overlap or the previous reply alone, other excerpts, Story, threads not named, fill slots). **Risky**: a supportive line that is disputed (`disputed_by`) or contradicts a current fact; offered after the other supportive lines. **Hidden**: what a mode withheld or a secret gate dropped; never placed, recorded only. "Irrelevant" (§48) is what recall already does not offer and gets no label. | A model-assigned label (C8; cost and latency on the request path); labels only in the Inspector (they would change nothing the packet does). |
| Q2 | When is a supportive line overused? | **When the same line (kind and ledger `ref`, as the overuse report keys it) was placed in each of the last `rest_after` requests of the chat (a recorded recall option, `NMOS_REST_AFTER`; 2 by default, amended 2026-10-07 from 3 on step 3's replay, the owner may set it back to 3 on the live run) and none of the replies after them echoed it** (`spans.reuse`, ADR 0027, the measure the report uses). Read at request time from the chat's last 3 traces and the messages after them; a trace the head no longer agrees with (an edit, a reroll) still counts, as the reply the user saw did. | Placement count alone (a line the reply keeps using is not overused); a decay score stored per line (a new stored row, the same signal). |
| Q3 | What does the penalty do? | *Amended 2026-10-07 (the owner, on step 3's replay: moved behind the others, a tired line was placed anyway whenever the budget had room, which on S1 was nearly always; supportive repeats −6 %).* **An overused supportive line is left out while it rests**, and the next candidate takes its slot: for the request after its `rest_after`-th placement in a row and the one after that, then it is a candidate again. It does not rest when the question names it (it is required), when the question's own words found it (an excerpt hit lexically or by keyword), when the question asks about the past or how it started (`HISTORY_CUE`: old memory is the answer), or when a reply used it (Q2). Required lines never rest. The trace counts the lines left out (`rested`). | Offered after every non-resting line (the first answer: no effect when the budget has room); drop it until it is named again (a line can be needed again two turns later); a per-line cooldown counter stored in the database (state that replay would have to rebuild anyway). |
| Q4 | What is the activation threshold for supportive memory (§49)? | **An excerpt after the first needs its fused score at least 0.5 of the best excerpt's, or a mention or keyword hit**; a supportive fact needs a mention or overlap ≥ `LEXICAL_BAR` as now. Below it the excerpt is not offered (ledger: `below_threshold`). The 0.5 is measured on Q8 (b) and may move with the owner. | A fixed absolute score (fusion scores differ by chat size); no threshold (§49 asks for one). |
| Q5 | Does it replay? | **Yes.** The penalty reads only traces recorded before the request and messages on the head as of it, so `audit.replay` reproduces it (ADR 0027). A replay of a single old request uses the traces that were recorded then; the sequential replay (Q8 b) feeds each replayed packet to the next. | A per-chat memory in the plugin (the owner: keep the browser plugin light). |
| Q6 | How does it ship? | **`packet-v14` behind `NMOS_PACKET_POLICY`** (Q1–Q4), on top of `packet-v13`; `packet-v13` and `packet-v12` unchanged and selectable. The labels (Q1) are recorded in the ledger under every policy from `packet-v14` on. The default is the owner's decision on the measurement. | A recall option per rule. |
| Q7 | What does the Inspector show? | **A label chip on each ledger line** (필수, 보조, 위험, 숨김) and `resting` / `below_threshold` as outcomes; the overuse report's numbers for the chat on its conversation page. Server-rendered; no plugin change but the strings. | A separate overuse page (one more place to look). |
| Q8 | How is it measured? | **(a)** Deterministic cases: each label rule, the penalty's start and end, the threshold, required lines never resting, replay. **(b)** A **sequential zero-call replay** of the S1 live run (340 requests in order) under `packet-v13` and `packet-v14`, each request seeing the replayed packets before it: the overuse report (repeat share, stale token share) on both. Echo cannot be judged on replay (the replies were written for the old packets). **(c)** The zero-call replay of the v0.3.0 bench sets (as PHASE-33 Q10 c) and the quote set under `packet-v13` and `packet-v14`, three replays, the majority deciding. **(d)** *Amended 2026-10-07 (a review: the bench's chat model plays scripted replies, so its echo is the script's overlap with memory, not a model's use of it).* Echo on **real replies of the same chat model under comparable conditions**: the owner's trial chat, its requests recorded under `packet-v13` and under `packet-v14` with the same chat model and preset (`tools/overuse_report.py --policy`); a paired run (S1's user turns, replies generated by the same model, once per policy) only if the owner wants a controlled comparison, its cost estimated first. **(e)** Latency at 10,000 messages (`tools/bench_forensic.py`'s method): the trace reads add at most 30 ms at p95. | Echo on replay (meaningless: old replies); the full live gate (an extraction change only). |
| Q9 | What is the bar? | *Amended 2026-10-07 (the owner, on step 2's baseline, `docs/perf/phase34-baseline.md`: required lines are 64 % of the repeats, which the rest does not touch).* On (b), against `packet-v13` in the same sequential replay: **on supportive lines**, the repeat share at least a fifth lower (amended 2026-10-07 from a quarter: the rest starts after `rest_after` placements, so the first repeats stay) and the stale token share at least a third lower; **on the whole packet**, neither higher; and the report says what took a resting line's place (a new line or another repeated one). On (c): every set no worse than `packet-v13` by more than one case; forbidden totals not higher; the quote set at least 20 of 24. On (d) (amended 2026-10-07): of the lines placed again from the request before, the share the real reply echoed is no lower under `packet-v14` than under `packet-v13`, each judged on at least 30 such lines, and the owner's judgement of the play; the bench's scripted 0.106 is no bar. Fewer repeats (b) does not by itself show better use of memory. On (e): +30 ms. | A bar on the whole packet's repeat share (out of reach by construction: the rest acts on supportive lines only); a lower whole-packet target such as −10 % (mixes the rest's effect with the required lines' repeats). |
| Q10 | Release? | **`0.4.0` after this phase** (Stage 7 complete, R7), the defaults decided on (b)–(d). | Release Phase 33 alone (the owner may still choose it). |

## Baseline

`packet-v13` on the Phase 33 branches (#274, #276), the overuse report of `docs/perf/phase33-baseline.md`, and the
v0.3.0 bench databases `nmos_b030_*` on the test Postgres (owner-local evidence
`/home/grantkim725/nmos-eval/bench-v030-0ace76c/`).

## In scope

1. Labels at compile time and in the ledger (Q1).
2. `packet-v14`: the overuse penalty (Q2, Q3) and the activation threshold (Q4), replayable (Q5).
3. The sequential replay in `tools/` (Q8 b), the overuse report run on its output.
4. The Inspector's label chips and the chat's overuse numbers (Q7).
5. An ADR (next free number after 0067) for labels and overuse; ROADMAP's Stage 7 section updated.

## Out of scope

A model call on the request path (C8); a new stored table or migration (stop and ask if one is needed); read-only MCP
(R5); extraction changes; story-day segmentation; any plugin logic beyond strings (the owner, 2026-10-07: keep the
browser plugin light).

## Steps

1. This document, approved; AGENTS §1/§2, STATUS and ROADMAP name Phase 34 as current.
2. Labels in the ledger without changing placement; the sequential replay; the label shares and overuse on S1 under
   `packet-v13` as the step's baseline.
3. `packet-v14` (Q2–Q4) with deterministic cases and the ADR; replays (b) and (c) and their report.
4. The Inspector's chips and numbers (Q7).
5. The owner's default decision; the reduced live run (d) and latency (e); `0.4.0` prepared, released on the owner's word.

## Stop conditions

Stop and ask the owner when: a replayed set gets worse by more than one case; a required line rests or falls below the
threshold in any case; a line the secret gate withheld is placed; `packet-v13`'s or `packet-v12`'s compiled output
changes for any recorded request; the sequential replay cannot reproduce a recorded packet under the policy it was
recorded with; latency exceeds Q9's bar; a migration, a runtime dependency or a model call on the request path would be
needed.

**Known risk.** A resting line can be the one a later question needs without naming it; the threshold and the rest
both drop it to the back, not out, and a mention brings it back. The penalty keys on placement and echo, so a line the
reply uses in its own words (no shared spans) may rest though it was used; the live run (d) measures how often.

**High risk (AGENTS §14):** recall semantics (what a packet carries, now depending on the requests before it) and
replay of recorded requests.
