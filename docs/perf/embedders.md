# Embedding models compared on the M0 chats (AGE-40)

What recall gains from each embedding model an owner is likely to pick, measured the same way, and the vector
similarity bar each needs. Asked by the owner on 2026-10-05, outside a phase: most people who cannot run Ollama will
use a hosted embedding API, and the bar (`vector_min_sim`, 0.42) was only ever measured with `qwen3-embedding`.

## Setup

- Throwaway copies of the two Phase 25 M0 databases on the test Postgres (`extract-v15` facts), the case sets of
  `docs/perf/lexical-recall.md` (40 cases on the main chat, 15 on sample 2; cases and chats stay outside the
  repository), replayed with `tools/eval_rp.py` on `main` at `83b5490` (the code released as 0.3.0): `--policy packet-v12 --budget 4000 --keywords on`,
  the Phase 25 extractor and summarizer keys.
- **Every model embedded the same messages**: the ones the copies' `qwen3-embedding:8b` projection covers (147
  messages in 435 chunks on main, 69 in 205 on sample 2), cut and stored by the sidecar's own `process_embed`.
- **Voyage through a local cache.** An account with no payment method is limited to 3 requests and 10,000 tokens a
  minute for each model, so the chunks and the 55 query texts were embedded beforehand in paced batches (the request
  body the sidecar sends: `model` and `input`, nothing else) and the sidecar read them from a stand-in endpoint on
  this machine. A batch gives the vectors single calls give. `voyage-context-3` was called at its own endpoint
  (`/v1/contextualizedembeddings`), one message's chunks together, each query alone.
- The qwen3 models ran on the evaluation Ollama (CPU), queries with the qwen3 instruction as in production. A replay
  gives its query embedding 5 s (120 s here when the CPU server had to swap models; a run whose `vectors` column is
  not the whole set was lexical only and is not reported).
- The bar is each request's recorded option; "bar 0.30" replays every request with `vector_min_sim` 0.30.
- Baselines repeated: no vectors and `qwen3-embedding:8b` gave the same counts twice; `voyage-4-large` at 0.30 twice.
  Sample 2 with `voyage-4-lite` gave 7 and 8 of 15 on two identical runs. Read a difference of one case as noise.

## Results (2026-10-05)

Passed cases; in brackets the cases whose answer is outside the prompt window (23 on main, 12 on sample 2).
"Forbidden" counts packets that placed a phrase a case forbids (a replaced value, such as an older form of address).

| Embedding model | Main, of 40 | Main forbidden | Sample 2, of 15 | Sample 2 forbidden |
|---|---:|---:|---:|---:|
| none (lexical only) | 32 (15) | 0 | 7 (4) | 0 |
| `qwen3-embedding:8b`, bar 0.42 | 34 (18) | 1 | 9 (6) | 0 |
| `qwen3-embedding:0.6b`, bar 0.42 | 33 (17) | 1 | 9 (6) | 0 |
| `qwen3-embedding:0.6b`, bar 0.30 | 33 (17) | 1 | 9 (6) | 0 |
| `voyage-4-lite`, bar 0.42 | 30 (15) | 2 | 7–8 (4–5) | 0 |
| `voyage-4-lite`, bar 0.35, 0.30, 0.25, 0.20 | 30 (15) | 2 | 7 (4) | 0 |
| `voyage-4-large`, bar 0.42 | 32 (16) | 1 | 9 (6) | 0 |
| `voyage-4-large`, bar 0.30 | 33 (17) | 1 | 10 (7) | 0 |
| `voyage-4-large`, bar 0.20 | 33 (17) | 1 | 10 (7) | 0 |
| `voyage-context-3`, bar 0.42 | 32 (17) | 2 | 9 (6) | 0 |
| `voyage-context-3`, bar 0.30 | 32 (17) | 2 | 9 (6) | 0 |
| `voyage-context-3`, bar 0.20 | 31 (17) | 3 | 9 (6) | 0 |

Similarity of each query's best chunk on the main copy (55 queries, 15 of them the other chat's, so the low end is
unrelated text): `qwen3-embedding:8b` median 0.66 (quartiles 0.44–0.73), `voyage-4-lite` median 0.51 (0.30–0.61).

## Reading

- **Scores are not on one scale.** Voyage's cosines sit about 0.15 under qwen3's for the same question and chunk, so a
  bar measured with one model does not carry to another.
- **`voyage-4-large` equals qwen3 once its bar is 0.30**: one more case on each chat than at 0.42, and nothing more at
  0.20. At qwen3's bar it gives up a case on main.
- **`voyage-4-lite` is worse than no vectors on main** (30 against 32) at every bar: it finds none of the three
  memory cases qwen3 adds, and brings an older form of address into two packets. Its ranking, not the bar.
- **`voyage-context-3` gains nothing over `voyage-4-large`** and places more forbidden phrases; a chunk's context here
  is only the rest of its own message. It would need a second request shape in the sidecar. Not pursued.
- **`qwen3-embedding:0.6b`, the Ollama preset's model, is within one case of the 8b model** and does not move at 0.30.
- `voyage-4` (between lite and large) and OpenAI's `text-embedding-3-small` were not measured.

## Query latency (2026-10-06)

One short query a request, as the sidecar sends it, from the owner's host (South Korea) to Voyage; 20 calls a model,
22 s apart (the free limit), alternately on a new connection (what the sidecar does: `httpx.post` each call) and on
one connection kept open between its uses.

| Model | New connection: median (range), calls ≤ 400 ms | Kept connection: median (range), calls ≤ 400 ms |
|---|---|---|
| `voyage-4-lite` | 309 ms (291–656), 9 of 10 | 183 ms (178–285), 10 of 10 |
| `voyage-4-large` | 341 ms (301–694), 9 of 10 | 216 ms (196–574), 7 of 10 |

- Recall waits for the query's embedding `embed_timeout_ms` (300) **after its reads**, and the sync that carries the
  message starts the call earlier still (ADR 0061). `docs/perf/query-embedding.md` measured an embedder answering in
  400 ms as vectors on every request and one at 700 ms as on 6–7 of 15, so nine calls in ten of either model are
  inside what a request already allows, and the slow one in ten falls back to lexical recall as any late embedding
  does (K34). No timeout or connection change was made. Not measured inside a live request with Voyage.
- A kept connection saves about 125 ms at the median but `voyage-4-large` still took 350–570 ms on 4 of 10 calls, so
  the saving would not remove the slow calls; requests minutes apart would also outlive an idle connection.
- The settings' connection test through the sidecar: 356 ms, 1,024 dimensions.

## What changed

- The plugin's embedding presets gain **Voyage AI** (`voyage-4-large`), and a preset measured here carries its bar:
  picking it sets "Vector min similarity" (Ollama 0.42, Voyage AI 0.30; OpenAI is left as it is). The field stays
  editable, and nothing changes for a saved configuration until a preset is picked.
- Picking Voyage says that an account with no payment method is limited to 3 requests a minute (the sidecar embeds
  one chunk a request, so the 147-message chat above would take 435 of them), and that Voyage lists no models
  (`GET /v1/models` answers 404).
- Voyage's embedding answer reports `usage.total_tokens` and no `prompt_tokens`; an embedding call now counts a
  total reported alone as its input tokens (`llm.Embedder.embed_metered`).
