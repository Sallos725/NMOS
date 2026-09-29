# NMOS and Archive Center 4.8.0, side by side (2026-09-28/29)

The owner asked how NMOS compares with [Archive Center](https://github.com/Flazer31/archive-center) 4.8.0, another
long-term memory plugin for RisuAI/PocketRisu (a Go backend with MariaDB and ChromaDB, and a V3 plugin). This page
records what was measured: request latency, what happens when a long chat is first connected, and what each one puts
in the prompt for the owner's M0 questions. It also records a what-if on the NMOS packet ("fill") that the comparison
suggested, and two evaluation pitfalls found on the way.

Numbers only. The M0 datasets are the owner's chats (PHASE-11 Q1): no chat text, character or persona name appears here.
Archive Center was run as shipped (its Linux x64 package, `full_local`: MariaDB + ChromaDB), with its defaults except
where noted. It was not tuned; its authors may know settings that change these results.

## Setup

- **Host.** Isolated `ghcr.io/pocketrisu/pocketrisu:latest` (**v1.13.0**), headless Chromium, on the 16-core homelab
  machine; published on loopback only. Not the owner's instance.
- **NMOS.** The sidecar and plugin from `main` of 2026-09-28 (Phase 14 step 4), on fresh or copied test databases.
- **Archive Center.** 4.8.0 (release package, checksums verified), in its own container: backend on loopback,
  MariaDB and ChromaDB as its launcher starts them. Settings: the editor/publisher LLM left empty (its "Go only" mode,
  the default for a new install), the turn HUD off. The critic (its extraction model) and the embedder are set per
  section below.
- **Latency.** The synthetic 5,000-message chat of `docs/perf/scale.md` (≈1,200-character Korean replies), stub chat
  model, click → model request as the stub logs it, one untimed warm-up and five timed sends per row.

Two host facts matter for anyone repeating this on v1.13.0:

- the chat-model request now leaves from the browser (a stub must listen where the browser can reach it), while
  NMOS's requests (V3 `nativeFetch`) went through the PocketRisu server (the sidecar must be reachable from the server);
- writing `enabled: false` into Archive Center's stored settings did not stop its hooks; the plugin's power button did.

## Latency (5,000 messages, stubs)

| Condition | Click → model request, median (range) | Added by the plugin |
|---|---:|---:|
| Both plugins off | 3.09 s (3.06–3.10) | — |
| NMOS, no facts or vectors | 4.13 s (4.07–4.17) | ≈1.0 s |
| NMOS, 7,500 facts and 5,123 vectors (stub extraction of the whole chat) | 3.99 s (3.94–4.09) | ≈0.9 s |
| Archive Center, after its backfill (critic stub, no memory written) | 11.59 s (11.43–11.61) | ≈8.5 s |

NMOS's own `request done` total was 0.8–1.1 s, of it sync ≈0.35–0.65 s and retrieve ≈0.25–0.45 s (on v1.13.0 both calls
cross the PocketRisu server, see above). Archive Center's row is a lower bound for a chat with memory: its critic stub
answered `{}`, so nothing was stored for it to read. A diagnostic run showed two `prepare-turn` round trips per request
and 18–20 s spent in one of them on the owner's 147-message chat (≈0.9 M characters) before its backfill finished.

## First sight of a long chat

| | NMOS | Archive Center |
|---|---|---|
| What starts it | the first request with the plugin on (D22) | the first request with the plugin on |
| Raw history | synced in one request: 7.4 s at 5,000 messages | stored turn by turn from the open page |
| Extraction | the latest 100 turns; the rest only on "Extract all history" | every completed turn, one critic call each |
| Whole history, stub models | 269 s (2,559 extractions, 5,123 embeddings; two workers) | ≈40–45 min of page-open time for ≈2,530 turns, 0.7–1.5 s per turn, slowing as history grew |
| Whole history, `deepseek-v4.1-flash` | main chat: 73 turns in ≈31 min (one worker, a second from the 11th minute; ≈40 s a call on its ≈12,000-character turns); sample 2: 34 turns in ≈13 min | main chat: 73 turns in ≈25 min, one at a time (12–17 s per turn) |

With a paid critic, connecting Archive Center to a long chat sends one critic call per past turn at once (≈2,500
for the 5,000-message chat; each prompt ≈30–35 k characters, ≈30 k of them its fixed instructions). NMOS's default
does ≈100 and leaves the rest to an explicit request.

## What each puts in the prompt (M0)

### Method

- **Cases.** The owner's two M0 datasets: the main chat (73 turns; M0-28 and M0-12 at the request of turn 73, 40 cases)
  and sample 2 (35 turns; the 15 cases on window B; the two isolation cases need other chats and were left out).
  Owner repairs (Phase 13) were not applied, so both sides are fully automatic.
- **Extraction.** Both sides extracted the two chats with `deepseek-v4.1-flash` through the local Ollama. NMOS: a new
  extractor generation over every turn on copies of the test databases, summaries on (same model). Archive Center:
  the chats seeded into a fresh PocketRisu up to each probe's position, backfilled with its critic; its critic must use
  its `ollama` provider (`openai` with a local endpoint is refused by its proxy for DeepSeek models). NMOS was also
  measured on the chats' existing `gemma4:31b-cloud` extraction (`extract-v13`, the production generation).
- **Probes.** Archive Center: each case's question sent as the user message; the stub saved the request and failed it,
  so no probe turn was ever finalized, and the message was removed before the next case. NMOS: `audit.replay` of the
  same traces with the case's question (`tools/eval_rp.py`), `packet-v8`.
- **Vectors.** Both on: Archive Center through ChromaDB with `qwen3-embedding:8b`; NMOS through the chats' own
  `qwen3-embedding:8b` projection (see the first pitfall below).
- **Score.** `tools/eval_rp.py`'s `score` on both sides, with the same prompt window (the trace's recorded
  `in_context`): gold phrases held and forbidden phrases placed. For Archive Center the scored text is its
  `[Archive Center — Auxiliary Context]` system message plus anything it added to the user message; all of it counts
  as current, while NMOS's `<Story>` and "before" parts do not (stricter for Archive Center on forbidden phrases).
  Gold phrases were drafted from NMOS's facts, which can favour NMOS's wording; the cases are few (55). Token sizes
  use NMOS's estimate (`packet-v2` rate) for both.

### Results

Main chat (73 turns, 40 cases, 21 need memory, 16 forbidden phrases):

| | Passed | Needing memory | Gold held | Forbidden placed | Injected (tokens) |
|---|---:|---:|---:|---:|---:|
| Archive Center | 25 | 7 | 25/40 | 1 | ≈17,400 (≈36,000 characters) |
| NMOS, deepseek, budget 2,000 | 30 | 11 | 29/40 | 0 | 1,910 |
| NMOS, gemma4, budget 2,000 | 32 | 13 | 31/40 | 0 | 1,904 |

Sample 2 (35 turns, 15 cases, 13 need memory, 4 forbidden phrases):

| | Passed | Needing memory | Gold held | Forbidden placed | Injected (tokens) |
|---|---:|---:|---:|---:|---:|
| Archive Center | 12 | 11 | 17/19 | 1 | ≈19,800 (≈36,000 characters) |
| NMOS, deepseek, budget 2,000 | 9 | 8 | 14/19 | 1 | 1,755 |
| NMOS, gemma4, budget 2,000 | 10 | 8 | 13/19 | 0 | 1,743 |

Archive Center's block was ≈36,000 characters for every question, and about half of it was the same text for all 40
questions of the main chat (194 of ≈368 lines). On sample 2 (≈114,000 characters in the whole chat) that block holds
about a third of the story; on the main chat (≈918,000 characters) about 4 %. This is where the two results part:
a large fixed block wins on a short chat, and selection wins on a long one.

## What-if: a packet that fills its budget

`packet-v8` stops at ≈2,000–3,000 tokens whatever the budget, because recall has fixed limits (`RecallOptions`:
5 excerpts of at most 480 characters, 8 facts, 3 events, 3 threads). The what-if scales those limits with the budget
(×budget/2,000; excerpts up to 480 × that, at most 2,400 characters), replayed read-only outside the repository.
The owner's current preset has a 150,000-token context and a 50,000-token response; Archive Center's block is
≈12–13 % of that context.

| Chat, extraction | Budget | Passed | Needing memory | Forbidden | Tokens |
|---|---|---:|---:|---:|---:|
| main, deepseek | 2,000 (today) | 30 | 11/21 | 0/16 | 1,910 |
| | 4,000 fill | 32 | 13/21 | 2/16 | 3,424 |
| | 8,000 fill | 33 | 14/21 | 2/16 | 5,865 |
| | 16,000 fill | 32 | 16/21 | 8/16 | 10,507 |
| main, gemma4 | 2,000 (today) | 32 | 13/21 | 0/16 | 1,904 |
| | 4,000 fill | 35 | 16/21 | 1/16 | 3,133 |
| | 8,000 fill | 36 | 18/21 | 2/16 | 5,335 |
| | 16,000 fill | 33 | 17/21 | 10/16 | 9,415 |
| sample 2, deepseek | 2,000 (today) | 9 | 8/13 | 1/4 | 1,755 |
| | 4,000 fill | 12 | 11/13 | 1/4 | 3,897 |
| | 8,000 fill | 12 | 11/13 | 1/4 | 6,656 |
| sample 2, gemma4 | 2,000 (today) | 10 | 8/13 | 0/4 | 1,743 |
| | 4,000 fill | 11 | 9/13 | 0/4 | 2,654 |
| | 8,000 fill | 11 | 9/13 | 0/4 | 4,122 |

Raising the budget without "fill" changed little (main, deepseek: 31 passed at 4,000–20,000, all at ≈2,200 tokens).
With it, NMOS matched Archive Center on sample 2 at ≈3,900 tokens (a fifth of its block) and led on the main chat;
beyond ≈8,000 tokens the extra lines were mostly older facts, and forbidden phrases rose to 8–10 of 16. Stale facts,
not room, are the limit there. Proposed as the next change: `docs/proposals/PUBLIC-RELEASE-AND-BENCHMARK.md`.

## Pitfalls found

- **A replay silently drops vectors** when the trace's recorded embedding projection is not the one the evaluation
  embeds with (`audit.replay`: "vectors of the trace's projection unavailable: lexical only"). The first NMOS numbers
  of this comparison were lexical only for that reason (main 28/40, 9/21; sample 2 6/15, 5/13, deepseek, budget
  2,000) and were replaced by the numbers above. Check `vectors` in the notes of every replayed case.
- **`qwen3-embedding:8b` loads cold in ≈18 s** on the local Ollama; warm, a query embeds in ≈50 ms. The request path
  gives the query embedding 300 ms and falls back to lexical recall (PHASE-3), so a request after the model was
  unloaded recalls without vectors (K34). How often that happens in production was not measured.

## Reproduce

The harness is outside the repository (it seeds the owner's chats): an isolated PocketRisu with the two chats cut at
the probe positions (`database.bin` seeded as in `docs/perf/stage4-leak-pilot.md`), a stub chat model that saves every
request and answers 500, Playwright to send each case and remove it, and `tools/eval_rp.py`'s `score` on the saved
requests. The latency rows reuse the `docs/perf/scale.md` chat and the K3 host script.
