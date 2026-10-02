# The query embedded while recall reads (ADR 0061, K34), and the chunk cap measured (ADR 0062, K13)

What the request path gains when the query's embedding runs beside recall's reads instead of before them, and when the
sync that delivers the user's message asks for it first. The first sections are synthetic (`tools/bench_story.py` at
10,000 messages, a stub embedder); the last two are the owner's measurement on the production host with the real
embedder, from the review of #242. The owner's bench harness (AGE-24) measures the real chats live and stays outside
the repository.

## Setup

- `tools/bench_story.py 10000`, budget 4,000, pinned to two cores of a four-core container (not the homelab machine of
  the other perf pages: compare the columns, not the pages). Each row is the median of three rounds, each round running
  `main` before this change (`cf52cec`) and this branch in turn.
- **Default questions**: no embedder, as the other pages' latency rows. The reads alone: what moving the excerpts after
  the facts costs or saves by itself.
- **`BENCH_RECALL=wide` with `BENCH_EMBED_MS=N`**: every message has a vector near the query's and a stub embedder
  answers after N ms (the same stub times out as httpx does when its call's timeout comes first). N = 250 is an
  embedder just under the 300 ms timeout; N = 400 is the owner's production embedder behind its proxy (280 ms median,
  452 ms at the 95th percentile, `docs/KNOWN-ISSUES.md` K34), over the timeout. `vectors_on` counts the requests of
  15 whose recall had vectors.

## Results (2026-10-02)

| Run (15 requests each) | `main` cf52cec, p50 / p95 | this change, p50 / p95 | p50 difference | requests with vectors, before → after |
|---|---:|---:|---:|---:|
| Default questions, no embedder (the reads alone) | 176.8 / 317.4 ms | 190.2 / 314.9 ms | +13.4 ms (rounds 168–209 and 177–204) | — |
| Wide recall, embedder answering in 250 ms (under the timeout) | 704.5 / 810.1 ms | 466.3 / 552.5 ms | **−238 ms** | 15 → 15 |
| Wide recall, embedder answering in 400 ms (over the timeout) | 644.4 / 714.6 ms | 533.6 / 589.1 ms | **−111 ms** | **0 → 15** |

Packets: the same mean size per run on both sides (571 tokens without an embedder; 1,026–1,056 with vectors; 818 on
`main` at 400 ms, where no run had an excerpt). Raw rounds: `main` default 209.2, 167.9, 176.8; branch 190.2, 176.5,
204.3; `main` 250 ms 704.5, 695.1, 730.4; branch 466.3, 481.8, 452.5; `main` 400 ms 633.0, 652.7, 644.4; branch 532.9,
535.8, 533.6 (p50, ms).

## Reading

- **Without an embedder nothing changes but the order of the reads**: the excerpts are now chosen after the facts.
  The two sides' rounds overlap (168–209 against 177–204 ms); the +13 ms between their medians is inside that spread
  and the three rounds alternate, so it is not a measured cost. The other perf pages' rows (one embedder-less run
  each) are unaffected in kind.
- **An embedder under the timeout costs the request nothing any more.** At 250 ms, `main` paid the whole call after
  lexical recall (≈250 ms of its 704); this change runs it under the reads (facts, vectors' search is after it) and
  waits ≈0 ms: −238 ms, the same packets.
- **An embedder over the timeout now gives vectors, and the request is still faster.** At 400 ms `main` waited its
  300 ms, got nothing, and compiled lexical-only packets (0 of 15 with vectors, 818 tokens); this change has the answer
  by the time the reads are done, so every request had vectors (15 of 15, 1,032–1,056 tokens: ten excerpts each) at
  −111 ms. This is the production shape of K34: a warm embedder behind a proxy at 280–450 ms.
- The wait after the reads is bounded as before (`test_query_embedding.py`: an embedder that never answers costs the
  timeout once, after the reads, and the call ends on its own at twice the timeout), so no request waits longer for
  the embedding than on `main`. The whole request can still be longer when it gains vectors it did not have: the
  vector search and a fuller packet (the 700 ms row below). The sizes above are the whole retrieve as the plugin sees
  it (`/v1/retrieve`, in-process).

## Asked for at the sync (ADR 0061 item 7)

`BENCH_PREFETCH=1`: each request's user message is its question, as the plugin sends it, so the sync that delivers the
message starts its embedding and the retrieve that follows takes it. The same wide recall, three rounds each, `main`
and this branch in turn; `BENCH_EMBED_MS` 400 (production's shape) and 700 (an embedder that misses even the reads'
time plus the timeout).

| Run (15 requests each; the message is the question) | `main` cf52cec, p50 / p95 | this change, p50 / p95 | p50 difference | requests with vectors, before → after |
|---|---:|---:|---:|---:|
| Embedder answering in 400 ms (production's shape) | 660.0 / 747.1 ms | 493.2 / 564.2 ms | **−167 ms** | **0 → 15** |
| Embedder answering in 700 ms (beyond the reads plus the timeout) | 648.7 / 737.4 ms | 636.1 / 809.5 ms | −13 ms | **0 → 6–7** |

Raw rounds (p50, ms): `main` 400 ms 628.8, 660.0, 671.4; branch 468.6, 502.3, 493.2; `main` 700 ms 648.7, 641.2, 664.0;
branch 624.0, 636.1, 647.7 (vectors 6, 6, 7 of 15; packets 909–929 tokens, 4–4.7 excerpts, against `main`'s 818 and
none).

- **At 400 ms the sync's time comes on top of the reads'**: 493 ms p50 against 534 ms when the call starts at recall
  (the table above), −167 ms against `main`, every request with vectors. In this harness the sync is an in-process
  append of a 10,000-message chat (tens of milliseconds); on the real host the plugin's sync takes 0.3–2.5 s at that
  size (`docs/perf/scale.md`), so a production embedder's call is over before the retrieve arrives.
- **At 700 ms the median is unchanged and 6–7 of 15 have vectors**: the sync, the reads and the 300 ms wait cover the
  call where the reads ran long; the rest fall back as before (the wait after the reads is bounded as the call was).
  The requests that gained vectors are slower than on `main`: they run the vector search and compile fuller packets
  (ten excerpts), ≈60 ms at the 95th percentile (809.5 against 737.4 ms), the price of the memory they now carry, not
  of the wait.
- A 700 ms embedder is beyond production's shape (280–450 ms behind a proxy); it shows the bound: what the prefetch
  buys is the sync's time, nothing more, and no request pays for an embedder that never answers.

## On the owner's host: the real embedder (the review of #242, 2026-10-02)

The owner's review ran this branch's head (`806698a`) against `main` (`cf52cec`) on the production machine, through
the sidecar's real sync → retrieve → trace path (FastAPI's `TestClient`, the real Postgres, the real Ollama): the 40
questions of the M0 v2 main set, three rounds a side, the sides' order changed each round, a fresh copy of the database
for each run, the chunk cap at 8, no extraction or summary worker. Two embedder paths: production's current one (Ollama
in Docker reached directly, `NMOS_EMBED_TIMEOUT_MS` 1,000) and the one K34 was measured on (the HTTPS proxy, 300 ms).
Medians of the three rounds' percentiles, `sidecar_total` from the traces.

| Embedder path | `main` p50 → this branch p50 | p95 | fell back, `main` → branch | branch requests that took their sync's embedding |
|---|---:|---:|---:|---:|
| Direct, 1,000 ms (production today) | **226.83 → 163.52 ms** | 254.16 → 193.08 ms | 0/120 → 0/120 | 120/120 |
| Proxy, 300 ms (K34's path) | **322.93 → 176.88 ms** | 389.46 → 201.62 ms | 0/120 → 0/120 | 120/120 |

The branch's `embed_wait` p50 was 0 ms on the direct path and 9.24 ms through the proxy; the sync itself took 15–16 ms
p50 on `main` and 16–18 ms on the branch. The latency gain and the prefetch are confirmed on the real embedder. **The
fallback share is not**: production has moved to the direct path with a 1,000 ms timeout, and in this run `main` fell
back on none of its 120 requests either, so K34's 70 % (141 of 201 recalls, Phase 15, on the proxy path at 300 ms) is a
historical figure this run cannot show shrinking. Sidecar time only: no plugin round trip, no generated answers (the
AGE-24 criterion is the live bench's, which has not run on this branch).

## The chunk cap: no change on the M0 chat (ADR 0062)

The first draft of ADR 0062 raised the default cap from 8 to 24 chunks on the belief that the owner's ≈10,000-character
replies had their second half outside vectors. The same review measured it on the evaluation copy of the M0 v2 main
chat: 147 active messages, 15,621 raw characters at most, **5,481 normalized** (`clean-v3`, the text the chunks are cut
from). No message is cut at 8 chunks; no message's spans differ between 8 and 24. A fresh copy re-embedded under a
24-chunk projection (242 jobs, 709 vectors, 303.74 s; the new vectors at cosine 0.9999999999991362 to the stored ones,
so the same model) compiled, with the same fixed query vectors and `known_at`, the **same 40 packets** as the old
projection, character for character:

| Replay (`packet-v10`, 4,000 tokens, keyword route on) | needing memory | all | forbidden | mean tokens | with vectors |
|---|---:|---:|---:|---:|---:|
| `main`, the old projection (cap 8) | 16/23 | 32/40 | 1 | 3,106.32 | 40/40 |
| this branch, the old projection | 16/23 | 32/40 | 1 | 3,106.32 | 40/40 |
| this branch, the new projection (cap 24) | 16/23 | 32/40 | 1 | 3,106.32 | 40/40 |

The one forbidden phrase is in the baseline too. These are packet-evidence scores, not generated answers. So the
default went back to 8 (the same projection key as before: nothing re-embeds on upgrade) and the cap stayed a setting
of the projection for chats whose normalized messages are longer. The bench chat cannot measure it either: its replies
are 1,200 characters, two chunks under either cap.
