# Phase 9 evidence — accountable packets

Phase 9, 2026-09-26. Spec `docs/phases/PHASE-9.md`, ADR 0027. Every number
below comes from a run described here. Synthetic data is labeled as such. No chat text of the owner was
read: the production figures are aggregate SQL over `retrieval_trace` in a read-only session.

## 1. Why: what the budget did on real chats (production, aggregates only)

Owner's production database, `v0.1.0-beta.16`-era sidecar with `packet-v0`, default reserve 600:
168 fresh requests, 2026-09-23 to 09-25, 4 conversations, 226 head messages.

| Measure | Value |
|---|---:|
| packet tokens, median / max (estimate) | 566 / 596 |
| empty packets | 47 |
| fact and claim lines offered per request, mean (8 facts + 4 claims at most) | 7.9 |
| requests that placed an excerpt | 7 (12 excerpts) |
| requests with facts and no excerpt | 114 |
| requests that dropped an eligible excerpt | 42 |
| most common packet: 12 fact/claim lines + 3 promises, no excerpt | 76 requests, 578 tokens mean, 15 eligible excerpt candidates |

The eligible excerpt that was dropped came from a message of 325 characters on average (capped at 480).
At 1.5 estimated tokens per Korean character, a two-sentence Korean excerpt costs about as much as the
whole reserve left after the fact lines. The traces could not say which of the 12 offered lines reached
the model, because only their count was recorded.

## 2. Token estimate against real tokenizers (K26)

`estimate_tokens` against three tokenizers on synthetic Korean text from `fixtures/model` (scene turns
and fact lines rendered as packet lines). Counts come from Ollama `prompt_eval_count`, minus a baseline
request: qwen3-embedding:0.6b (local), gemma4:31b-cloud (a Gemini-family tokenizer), and
deepseek-v4.1-flash:cloud. There were 12 samples of 8 fact lines, 12 short excerpts, and 8 prose passages
of up to 480 characters. The script is kept in the session scratchpad; the samples are the committed
fixtures.

| Tokenizer | fact lines: estimate / actual | short excerpts | prose | fitted tokens per Korean char | ASCII chars per token |
|---|---:|---:|---:|---:|---:|
| qwen3-embedding | 1.14 | 1.51 | 1.42 | 0.96 | 3.13 |
| gemma4 | 1.19 | 1.75 | 1.71 | 0.74 | 2.95 |
| deepseek-v4.1-flash | 1.19 | 1.47 | 1.42 | 0.98 | 3.39 |

The estimate never under-counted, and it over-counts Korean prose by 1.42–1.75×. The answer probe
(§5) is consistent with this: packets estimated at about 580 tokens came to prompts of 612–674 real
tokens in all, system prompt and five chat messages included. Left unchanged (Q4, K26).

## 3. Grounding: measured, then left out

Of the recorded real-model runs (`fixtures/model/phase5`–`v9`, both models), 3,169 assertions are valid.
3,070 of them (96.9 %) quote evidence that occurs verbatim in the normalized target turn. Among the rest,
39 reach ≥ 0.9 and 58 ≥ 0.7 trigram containment. Two reach 0.69, and both are legitimate quotes of
dialogue ("내가 직접 건넬게."). A deterministic "evidence must be in the turn" check would change almost
nothing on this evidence. The known extraction errors (K22) are wrong readings of text that is really
there. Not built.

## 4. Deterministic tier (CI)

`tools/eval_memory.py` after Phase 9 (`docs/perf/eval-baseline.md` has the table per case):

| Mode | gold reached | cases with stale memory | irrelevant packets | mean packet tokens |
|---|---:|---:|---:|---:|
| recent | 0/35 | 0 | — | 0 |
| lexical | 2/35 | 0 | 0/1 | 112 |
| hybrid | 3/35 | 0 | 0/1 | 137 |
| full-v0 | 33/35 | 0 | 0/1 | 197 |
| full | 35/35 | 0 | 0/1 | 190 |

`full-v0` misses exactly the two budget-pressure cases ("quote under a full budget", "one line of a long
message"). Every other case answers the same under both (`test_memory_eval.py`), including the two
standing-facts cases of ADRs 0026 and 0028, which `packet-v1` keeps as lead facts before threads.

`tests/test_packet_ledger.py` (20 tests) covers:
- the ledger and its provenance;
- `packet-v1`'s excerpt room, shortening, repeat skipping and state cap;
- replay reproduction:
  - after the story went on;
  - after facts and vectors were derived, later, for turns already on the head (bitemporal);
  - after a reroll of the reply;
- `changed` after an edit before the request;
- echo, including the particle rule and the leak flag;
- the policy comparison;
- traces from before the ledger;
- the Inspector section;
- the self-recall fix (§7).

Sidecar suite: 327 passed (after the rebase onto ADR 0026/0028).

## 5. Answer probe: a response model on packets from both policies

`tools/eval_packet_answers.py`: eight Korean synthetic probes (labeled synthetic). In each, ten long
traits and two claims of 하나 fill the budget. Fact extraction is deterministic (the memory evaluation's
stub extractor); vectors are real (qwen3-embedding:0.6b, local). One request per probe is recorded with
`packet-v1` and replayed as `packet-v0`: two packets for identical inputs. The response model gets a
Korean role-play system prompt, the packet before the last user message (the plugin's default), the last
five messages and the question, at temperature 0.7, three runs per policy. A reply counts as answered
when it contains the answer string. Fixtures: `fixtures/model/phase9/2026-09-26-*/`.

| Probe kind | Model | `packet-v1` answered (answer in packet) | `packet-v0` answered (answer in packet) |
|---|---|---:|---:|
| quote (answer only in a message's words) | deepseek-v4.1-flash | 6/12 (6/12) | 0/12 (0/12) |
| quote | gemma4:31b | 6/12 (6/12) | 0/12 (0/12) |
| fact (answer in a trait line) | deepseek-v4.1-flash | 3/12 (12/12) | 2/12 (12/12) |
| fact | gemma4:31b | 3/12 (12/12) | 3/12 (12/12) |

- **Quote probes.**
  - Whenever `packet-v1` placed the message that answers ("password", "ship"), both models answered in
    3 of 3 runs. `packet-v0` never placed it, so no reply could answer.
  - For "meeting" and "last words", recall found no candidate carrying the answer under either policy (a
    recall miss at the current bars, outside this phase).
  - `packet-v1` placed one fewer fact line when it placed an excerpt: 6 lines instead of 7.
- **Fact probes: literal scoring under-counts use.**
  - The answer line was in every packet.
  - In "old wound", all 12 replies say the right shoulder aches, but none says "화살", the scored word.
  - In "hidden sweets" and "father's chart", the character hides the thing, as the trait says (몰래,
    누구에게도 보여 주지 않고).
  - Both policies are alike here. That is the point of this kind of probe: `packet-v1` does not cost the
    fact lines that answer.
- **Echo, revised by this run.**
  - The first echo definition (share of a line's trigrams in the reply, bar 0.5) found no echo at all,
    even in replies that answered from the packet. The replies take the key phrase ("보라일곱이야",
    "은빛갈매기호"), not the line.
  - The shipped definition counts a reused 4-character span (or a 4+-letter word) that the request did
    not hold, and ignores a question's word with another particle.
  - With it, the audit of each probe's first `packet-v1` reply found the placed line that was used
    whenever the reply answered.
- **Repeats, found by this run.**
  - Before `packet-v1` skipped repeating excerpts, it placed the trait's own message as an excerpt next
    to the trait fact. The replies' echo counts doubled (12 echoed lines against 5–6 for `packet-v0`), for
    no new content.
  - With the rule, the fact probes' packets equal `packet-v0`'s: 7 facts, and the repeating excerpt is
    listed as `repeats`. Echo counts are equal (6 and 6).
- **Cost.** 96 calls per model (8 probes × 2 policies × 3 runs, plus the recording).
  - deepseek-v4.1-flash: mean 674 prompt and 149 completion tokens, 1.1 s.
  - gemma4:31b: 612 and 26, 0.5 s.
- **Trace size.** 3.7–4.5 KB per trace with its ledger and inputs (6 in-context ids, a short previous
  reply).

## 6. Latency

`tools/bench_scale.py 10000` (lexical retrieve after an append, 15 requests), run alternately against
beta.18's source (`main`), same machine and database server:

| Run | retrieve p50 / p95 ms | append p50 ms |
|---|---:|---:|
| branch 1 | 11.95 / 45.2 | 164.4 |
| main 1 | 11.34 / 45.8 | 160.4 |
| branch 2 | 11.29 / 46.6 | 165.3 |
| main 2 | 8.59 / 44.6 | 159.9 |

Retrieve is +0.6 and +2.7 ms p50, within the +5 ms bound. The retrieve now also writes the ledger and the
request's inputs, reads the head's last position, and computes a one-sentence form per excerpt. Append
differs by +4–5 ms p50. The sync path has no Phase 9 code, so this is taken as run-to-run noise. The fact
read keeps its statement: the as-of variant is a separate statement used only by replay.

## 7. Real host (PocketRisu v1.12.0, isolated)

The run used:
- an isolated PocketRisu (`ghcr.io/pocketrisu/pocketrisu:latest`, own save directory, port 6131);
- the plugin built from the branch (source unchanged since `v0.1.0-beta.18`);
- the branch's sidecar and worker on their own database;
- `tools/spike_stub_llm.py` as the chat model, and a deterministic extraction stub ("X는 Y로 간다." →
  located_in).

The owner's stack was not touched.

- **Ledgers replay exactly.** Seven Korean messages in one chat produced seven traces. Each carries the
  real plugin's in-context ids, and each replays with `reproduced: true` on the code that recorded it.
  Six have their reply on the head (`reply: ok`), and the last is `pending`. After the fix below, the
  same seven lines sent again in that chat, and two in a fresh chat, also replayed exactly. A replay
  compiles with the current code, so a trace recorded before a change to gathering reproduces only while
  that change does not touch it.
- **A bug the ledger showed.**
  - The first request's ledger held one placed excerpt: the user's own current message ("하나는
    도서관으로 간다.", position 0, lexical score 1.0).
  - The plugin anchors in-context detection only on messages of at least 16 characters, so a short
    first message reached the sidecar with no in-context ids and came back as memory of itself (147
    estimated tokens).
  - This is older than Phase 9: `packet-v0` recalls it the same way.
  - Fixed in the sidecar. The head's last message is always treated as in the prompt, since the host
    always sends the latest message and D13 injects only when it is there.
  - After the fix, a fresh chat's short first message gets an empty packet (`in_context` still empty, as
    the plugin sent it), and the trace replays exactly.
- **Timing.** Per request, the plugin logged 43–60 ms in all (sync 26–41 ms, retrieve 12–18 ms) on these
  short chats.

## 8. What this does not show

- No real chat has been replayed: production traces predate migration 0020, and copying the owner's chat
  text for an offline run was not allowed in this session. After a release, `tools/replay_packets.py`
  on the owner's database gives the first real A/B.
- The answer probe is small and synthetic: 8 probes, 3 runs, 2 response models, neither of them the
  owner's (Gemini 3.1 Pro). It shows the mechanism and its direction, not a rate.
- Echo is a surface measure and never ranks anything.
