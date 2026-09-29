# Phase 15 — A packet that fills its budget

> **Status: approved 2026-09-29 (owner), complete 2026-09-29.** P1 of `docs/proposals/PUBLIC-RELEASE-AND-BENCHMARK.md`.
> The owner chose on 2026-09-29 to do this before export and restore, which is now Phase 16 (`docs/ROADMAP-1.0.md`,
> `docs/STATUS.md`, AGENTS.md §2). It starts after Phase 14 step 6.
> On 2026-09-29 the owner also chose a fixed default budget over one that follows the host's context (Q3).

## Questions and answers

Each answer in bold was NMOS's proposal; the owner approved the document with them (2026-09-29).

| # | Question | Proposed answer | Alternatives |
|---|---|---|---|
| Q0 | Before or after export/restore? | **Before** (owner, 2026-09-29): small, already measured, and it improves every later measurement. Export and restore becomes Phase 16, still before any install for other users (proposal P4). | Export/restore first. |
| Q1 | What grows with the budget? | **Raw excerpts, in number and length, and facts up to twice today's limit.** Open threads, events, secrets (`<Private>`), `<Cast>` and `<Story>` keep today's limits. Measured: growing everything placed stale threads and secrets above ≈8,000 tokens (forbidden 8–10 of 16 at 16,000). Growing excerpts and facts only held forbidden at 1 of 16 up to 16,000 with the same gains. | Grow every section; excerpts only. |
| Q2 | How much, exactly? | **Scale the request's own limits by `f = min(max(budget / 2,000, 1), 4)`.** These are the panel's 발췌 수 / Excerpts (`recall_top_k`, default 5) and facts (`facts_limit`, default 8) settings, which each request records (ADR 0027). Excerpts become `floor(top_k × f)`, each up to `floor(480 × f)` characters (1,920 at 8,000). Facts become `floor(facts_limit × min(f, 2))`. A limit set to 0 stays 0. Below 2,000, today's limits apply. The candidate pool (`CANDIDATE_LIMIT`, 50) still bounds excerpts. At 2,000, and for every recorded `packet-v8` request, the packet is exactly `packet-v8`'s. The packet still stops at the budget, and ranking decides what fits. | A fixed larger set that ignores the settings; per-section budgets. |
| Q3 | The default budget? | **4,000 tokens (from 2,000), fixed.** Recall stops growing at 8,000 (`f` ≤ 4), the range the measurements cover. A larger budget is still accepted, since the API and stored settings allow up to 20,000 and none of them may start failing. It compiles with the limits of 8,000, and the other sections may use the rest of the room as today. The panel suggests up to 8,000. The host's context size is not followed (owner, 2026-09-29): a share of a 500,000-token preset would be ≈20,000 tokens, past the measured range. The reminder stays: lower the host's max context by the budget (D2). The prompt then keeps its size, and older raw messages give way to memory. | Follow the host's context; keep 2,000. |
| Q4 | New policy or a change to `packet-v8`? | **A new policy, `packet-v9`**, the default once accepted. `packet-v8` stays for replays of recorded requests (ADR 0027), and `tools/replay_packets.py` compares the two on the owner's recorded traces. | Change `packet-v8` in place. |
| Q5 | The cold embedding model (K34)? | **Measure, then decide.** First, how often production requests fell back to lexical recall, counted read-only from the owner's traces with the owner's OK. If it is frequent, add a keep-alive note in the guide and a Status-tab notice when a request recalled without vectors. A worker warm-up ping only if the notice is not enough. | Ignore it; always warm up. |
| Q6 | The evaluation tool? | **Fix it first.** `tools/eval_rp.py` names the embedding projection to search, embeds a warm-up query, and reports per case whether vectors ran. A replay that fell back to lexical is not scored silently (the first numbers of the what-if were lexical-only by accident, `docs/perf/packet-fill.md`). | Keep `--no-vectors` evaluations. |
| Q7 | How is it measured? | **M0 on both chats, with vectors, with both extractions (`gemma4:31b-cloud` `extract-v13` and `deepseek-v4.1-flash`), `packet-v9` at 4,000 against `packet-v8` at 2,000.** Also the owner's recorded traces replayed, retrieve latency at 10,000 messages, a real-host smoke, and a review per AGENTS.md §14. | M0 main chat only. |
| Q8 | Release? | **None until the owner asks**, as for Phases 10–14. | A beta tag after merge. |

## Goal

The memory budget buys memory. A larger budget brings more of what the story said, in its own words, and no more
stale business. Cases a short chat's packet misses today for lack of room are answered.

## Evidence behind the scope

All numbers are from `docs/perf/packet-fill.md` (2026-09-29): the owner's M0 cases, 40 on the main chat and 15 on
sample 2, with vectors on.

- **The packet ignores its budget (K33).** `packet-v8` compiles ≈1,800–2,900 tokens at any budget from 2,000 to
  20,000. Recall's limits stop it first: 5 excerpts of at most 480 characters, 8 facts, 3 events, 3 threads.
- **Scaling every limit** raised the cases needing memory, then stale lines came in:

  | Chat, extraction | 2,000 today | 8,000, all grow | 16,000, all grow |
  |---|---|---|---|
  | main, gemma4 | 13/21, forbidden 0 | 18/21, forbidden 2 | 17/21, forbidden 10 |
  | sample 2, deepseek | 8/13, forbidden 1 | 11/13, forbidden 1 | — |

  At 16,000 (main, gemma4) the 10 forbidden phrases stood in open threads (8 times), secrets (8), claims (3),
  facts (2) and one excerpt; a phrase can stand in more than one.
- **Excerpts and facts only (Q1, Q2)** kept the gains and held forbidden steady:

  | Chat, extraction | 2,000 today | 4,000 | 8,000 | 16,000 |
  |---|---|---|---|---|
  | main, gemma4 | 32/40, memory 13/21, forbidden 0 | 36/40, 17/21, 1 (≈2,900 tokens) | 36/40, 17/21, 1 | 36/40, 17/21, 1 |
  | main, deepseek | 30/40, 11/21, 0 | 31/40, 12/21, 1 | 31/40, 12/21, 1 | 33/40, 14/21, 1 |
  | sample 2, deepseek | 9/15, 8/13, 1 | 12/15, 11/13, 1 (≈3,900 tokens) | 12/15, 11/13, 1 | 12/15, 11/13, 1 |
  | sample 2, gemma4 | 10/15, 8/13, 0 | 11/15, 9/13, 0 | 11/15, 9/13, 0 | 11/15, 9/13, 0 |

- **This matches the position paper.** Distilled facts crowd out the raw words that answer "what exactly was said"
  (`docs/proposals/ACCOUNTABLE-MEMORY.md` §2). Room given to excerpts pays; room given to open business costs.
- **The prompt keeps its size.** The user lowers the host's max context by the budget (D2), so a larger budget trades
  older raw messages for selected memory. It adds no tokens to a request.

## In scope (Phase 15)

1. **This document**, approved; the roadmap, STATUS and AGENTS.md §2 renumber export and restore to Phase 16.
2. **Evaluation tooling (Q6).** `tools/eval_rp.py` searches a named projection, warms the embedder, and reports
   vectors per case. The `packet-v8` baseline is recorded with vectors on both chats and both extractions.
3. **`packet-v9` (Q1, Q2, Q4; ADR 0049, D59).**
   - Excerpt count, excerpt length and the fact limit scale with the budget from the request's own settings (Q2); every
     other section keeps its limits.
   - `packet-v8` stays replayable.
   - The budget-pressure advice (ADR 0036) and `FIT_CAP` follow the new range.
4. **Default budget (Q3).** The plugin's default becomes 4,000 and the panel accepts up to 8,000. The reminder to lower
   the host's max context stays. A new plugin build.
5. **Cold embeddings (Q5).** The production fallback rate, then the note and notice if warranted.
6. **Evaluation (Q7)**, the owner's traces replayed, a real-host smoke, latency, review, and documentation.

## Out of scope (Phase 15)

- Export and restore (Phase 16).
- Following the host's context size (Q3). Reading the preset's context is a later option, as a ceiling only.
- Recall growth past 8,000: larger budgets are accepted and compile with the limits of 8,000 (Q3). A different
  ranking of facts, threads or secrets.
- The story's input cap (K35): recorded, not scheduled.
- Importing another plugin's memory (proposal P4).

## Acceptance criteria

- [x] Every existing test and memory-evaluation case passes; recorded `packet-v8` requests replay as they were.
- [x] Deterministic cases:
  - `packet-v9` at 2,000, and below it, equals `packet-v8`, for default and non-default `recall_top_k` and
    `facts_limit`, and a recorded `packet-v8` request replays as it was;
  - excerpts and facts grow from the configured limits (`floor`, `f` at most 4, a limit of 0 stays 0), and threads,
    events, secrets, `<Cast>` and `<Story>` do not;
  - a budget of 20,000 compiles with the limits of 8,000 and within its budget;
  - the packet never exceeds its budget;
  - an excerpt is cut at its sentence, as today.
- [x] M0 with vectors, `packet-v9` at 4,000 against `packet-v8` at 2,000, on both chats and both extractions:
  - cases needing memory: at least +6 in total over the four runs (the measurements gave +9);
  - forbidden phrases placed: at most +2 in total, none of them from a thread or a secret;
  - no category worse by more than one case.
  Met: +6, +2 (both an old excerpt), address −1 per extraction on the longest chat (`docs/perf/packet-fill.md`).
- [x] The owner's recorded traces replayed with both policies: the lines only `packet-v9` places, by kind, and no
      secret or closed thread among them. Met: facts, claims and excerpts only, on 38 requests.
- [x] Retrieve latency at 10,000 messages within +10 ms p50 of `packet-v8` at 2,000 at 4,000, and within +25 ms at 8,000
      and above (the largest recall, `tools/bench_story.py`). Met: −4.7 and −2.9 ms (`docs/perf/packet-fill.md`).
- [x] Real-host smoke on an isolated PocketRisu v1.13.0: the new default applies, the packet grows to it, and the
      budget advice suggests values inside the range.
- [x] K34 measured on the owner's traces (read-only, with the owner's OK), with the result and any change in
      KNOWN-ISSUES.
- [x] Review per AGENTS.md §14.
- [x] `ARCHITECTURE.md` (D59), ADR 0049, README, the Korean guide, KNOWN-ISSUES (K33, K34), CHANGELOG.

## Steps (one pull request each)

1. This document, approved; the renumbering. **Done** (2026-09-29).
2. Evaluation tooling and the `packet-v8` baseline with vectors. **Done** (`docs/perf/packet-fill.md`, "The
   `packet-v8` baseline with vectors"): `tools/eval_rp.py --projection`, a warm-up, a query timeout for replays, vectors
   reported per case and a run without them refused; `audit.replay` takes the projection and says whether vectors ran.
   The baseline equals the what-if's on both chats and both extractions, every case with vectors.
3. `packet-v9`, ADR 0049, the default budget, and a plugin build. **Done** (ADR 0049, D59): `packet-v9` the default;
   excerpts, their length and facts grow from the request's own limits; `FIT_CAP` 8,000; the plugin's default budget
   4,000, saved up to 8,000 (build 8e38edbf7a82); deterministic tests (`tests/test_packet_fill.py`).
4. Cold embeddings: measure, then the note and notice if warranted. **Done** (owner's OK, 2026-09-29; K34): on the
   owner's production 141 of 201 recalls (70 %) went without vectors, all timeouts, every day. The retrieve answer now
   says `vectors` (on, off, fallback), the Status tab shows a notice after a fallback, and the guide, README and K34
   say how to keep the model loaded and raise `NMOS_EMBED_TIMEOUT_MS`; a new plugin build. No worker warm-up ping:
   warm requests were slow too (280 ms median), so a ping would not have saved most of them.
5. Evaluation, the owner's traces, real-host smoke, latency, review, documentation. **Done**
   (`docs/perf/packet-fill.md`, "Evaluation of `packet-v9`"): M0 +6 needing memory, +2 forbidden (an old excerpt),
   no category worse by more than one case; on 38 recorded requests `packet-v9` adds facts, claims and excerpts only;
   latency within the criteria; the real-host smoke passed and found a display bug in the panel (fixed);
   `tools/bench_story.py` takes `BENCH_BUDGET` and `BENCH_RECALL=wide`. The review of this step (tools, a display
   fix, docs) was scoped self-review; the policy itself had its Codex review in step 3.

Every merge reaches the owner's `:edge`; no tag (AGENTS.md §13).

## Stop conditions

Stop and ask the owner when:

- `packet-v9` places a secret or a closed thread that `packet-v8` would not, on any evaluated case or recorded trace;
- M0 misses the criteria above, or the gain depends on one extraction model only;
- latency exceeds the criterion;
- the owner's traces show the larger packet crowding out lines the replies used (echo, Phase 9).
