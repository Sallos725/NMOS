# Model-call usage and fallback outcomes (Phase 17)

`docs/phases/PHASE-17.md`, ADR 0051, D61. What NMOS's own model calls used, kept with each row they produced, and
the progress display telling a reduced or reused packet apart. Measured 2026-09-29 and 2026-09-30.

## Recorded usage against the provider's (Q7)

Each check calls `ChatModel.complete_metered` / `Embedder.embed_metered`, keeps the raw response, and asks the same
prompt again through Ollama's native API, which counts tokens itself (`prompt_eval_count`, `eval_count`). Scripts and
raw results: `~/nmos-eval/phase17-usage/` (outside the repository).

| Endpoint | Model | Calls | Recorded input / output (cached) | Response `usage` | Ollama's own count |
|---|---|---|---|---|---|
| Hosted, through Ollama (owner's choice) | `gemma4:31b-cloud` | 3 chat | 46/51, 50/86, 55/150 (0) | same | same |
| Local, an isolated CPU Ollama | `qwen2.5:0.5b` | 2 chat | 43/27 (0), 48/67 (31) | same | 43/27, 48/67 |
| Local, the same | `all-minilm` | 2 embeddings | 19, 8 | same | 19, 8 |

Every recorded count equals the response's `usage` and Ollama's own count; cached input tokens appear when the
provider reports a prompt-prefix hit (31 of 48 on the second local call). The hosted provider names the model
`gemma4:31b`, not the tag it was asked for; the record keeps the provider's name. Production's Ollama was not used
for the local check (its `qwen3-embedding:8b` is the request-path embedder): a separate container on other cores,
removed after. A response without `usage` records `calls`, `ms` and `model` only (tests).

## On the isolated real host (Q5, Q6)

PocketRisu v1.13.0 (`ghcr.io/pocketrisu/pocketrisu:latest`), a seeded save with a 10,000-message chat, plugin build
`22437aea8160`, stub chat, extraction and embedding models, `NMOS_EMBED_TIMEOUT_MS=150` with the stub holding the
probe query's embedding for 400 ms. The display's text, read every 150 ms:

| Request | Display |
|---|---|
| Probe query (vectors fell back) | `✓ 기억 주입 (639자) · 어휘 검색만` |
| Reroll 1 (a new request: the page had just loaded, so the canon snapshot was new) | `✓ 기억 주입 (755자) · 어휘 검색만` |
| Reroll 2 (the plugin's cached packet) | `✓ 기억 주입 (755자) · 재사용 · 어휘 검색만` |
| A message whose query embedding answered | `✓ 기억 주입 (1606자)` |
| Work that only embedded | `✓ 처리 완료` |
| Work that extracted a fact (the stub held it 4 s, so the display saw it pending) | `추출 102/5034 · 임베딩 2006/10069`, then `✓ 사실 1개 추가` |

All in the injected style, none as a warning. The Status tab's "This chat" card showed `NMOS 모델 사용: 호출 2,744회 ·
입력 883,981 · 출력 14,217 토큰`, and the Inspector's "모델 사용량" section the same totals per generation (canon reads
6, summaries 629, embeddings 2,006, fact extraction 103 calls).

Work that finishes before the display's first coverage poll is not shown at all, as before Phase 17.

## Cost of the new reads

On an evaluation copy (151 messages, 1,511 model-work rows): the Inspector's per-generation totals 2.1 ms; the
coverage view's `produced` counts, which the display's polls read, 0.8–1.0 ms.

## Request-path latency

`tools/bench_story.py 10000` with `BENCH_RECALL=wide BENCH_BUDGET=4000` (as Phase 15), `main` before Phase 17
(842981c) against Phase 17 (steps 2–4), alternated, 5 runs each on two cores: retrieve p50 (median of runs) 301.6 ms
before and 301.1 ms after, p95 494.9 ms and 498.3 ms, the same packets (1,055–1,056 tokens). Unchanged: the request
path writes no usage and its answer is the same; the plugin's two extra event fields are not timed.

## The archive

A copy of the first measured chat (schema 0025) exported, restored into a fresh database (migrations 0026 and 0027
applied on the way: 1,316 extractions, 27 summaries and 764 embedded chunks, every one with usage NULL, "not
recorded"), exported again and restored into another: the second round trip's tables are the same bytes (19 tables).
The tests also carry recorded usage through an archive (`tests/test_model_usage.py`).
