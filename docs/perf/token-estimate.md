# Token estimate for Korean: `packet-v2` (K26, ADR 0032)

2026-09-26. The packet's budget is filled against an estimate, not a tokenizer: 3.5 ASCII characters a
token, and 1.5 tokens for every other character. Phase 9 measured that this over-counts Korean
(`docs/perf/phase9-packets.md` §2), so part of the reserve went unused (K26). The owner chose to lower the
non-ASCII rate to 1.2 (ADR 0032). This file is the evidence for that rate.

All text sent to a tokenizer or a response model here is synthetic (the committed fixtures). The owner's
database was read only as a local restore of their backup, and only aggregates are reported.

## 1. The estimate against three tokenizers

`tools/measure_token_estimate.py`. Samples come from the committed real-model fixtures
(`fixtures/model/**/runs.jsonl`): fact lines rendered from the recorded assertions exactly as the packet
renders them, in packets of eight with the packet's frame and Note; excerpt lines (two sentences of a
scene's reply); prose (a reply, up to 480 characters); and mixed packets (six facts and one excerpt).
There are 16 samples per set. Counts are Ollama's `prompt_eval_count` minus a one-character baseline.
The tokenizers are qwen3-embedding:0.6b (local), gemma4:31b-cloud (Gemini family, the family of the
owner's response model) and deepseek-v4.1-flash:cloud.

Estimate / actual, over the whole set (worst single sample in brackets). Below 1 means the estimate
under-counts.

| Set (non-ASCII share) | Tokenizer | `packet-v1` (1.5) | `packet-v2` (1.2) |
|---|---|---:|---:|
| fact packets (12 %) | qwen3-embedding | 1.17 (1.13) | 1.08 (1.03) |
| | gemma4 | 1.21 (1.10) | 1.11 (1.04) |
| | deepseek-v4.1-flash | 1.18 (1.10) | 1.08 (1.01) |
| excerpt lines (39 %) | qwen3-embedding | 1.30 (1.17) | 1.10 (1.00) |
| | gemma4 | 1.63 (1.43) | 1.38 (1.21) |
| | deepseek-v4.1-flash | 1.30 (1.15) | 1.10 (**0.97**) |
| prose (69 %) | qwen3-embedding | 1.45 (1.27) | 1.19 (1.04) |
| | gemma4 | 1.78 (1.49) | 1.46 (1.22) |
| | deepseek-v4.1-flash | 1.44 (1.18) | 1.18 (**0.97**) |
| mixed packets (13 %) | qwen3-embedding | 1.19 (1.15) | 1.09 (1.06) |
| | gemma4 | 1.24 (1.15) | 1.14 (1.06) |
| | deepseek-v4.1-flash | 1.20 (1.12) | 1.09 (1.03) |

- No whole packet is under-counted by either rate.
- With 1.2, one excerpt line and one prose passage of 16 are 3 % under on deepseek. The budget holds
  whole packets, and in a packet the frame and fact lines carry the margin.
- On the owner's model family (gemma4), `packet-v2` still over-counts Korean prose by 46 %.
- ASCII text alone is estimated at 3.5 characters a token, while these tokenizers take 2.95–3.39. The
  frame's English Note is covered by the Korean margin. An all-English packet is not what K26 is about and
  is unchanged.

## 2. Budget-bound packets: the real size

The answer probe (§3) builds Korean scenes whose facts about 하나 fill the 600-token budget. Its packets
are stored with the runs (`fixtures/model/k26/*/runs.jsonl`). Counted by the same tokenizers (8 packets
per policy; the estimate is 575 of 600 for both):

| Tokenizer | `packet-v1` real tokens, mean (max) | `packet-v2` real tokens, mean (max) |
|---|---:|---:|
| qwen3-embedding | 445 (457) | 500 (514) |
| gemma4 | 410 (420) | 459 (472) |
| deepseek-v4.1-flash | 452 (463) | 508 (523) |

A full `packet-v1` used 68–75 % of the reserve in real tokens, `packet-v2` 76–85 %. The largest packet is 77
tokens under the budget.

## 3. Answer probe: `packet-v2` against `packet-v1`

`tools/eval_packet_answers.py --policies packet-v1` (now labels packets by the policy that recorded them).
It uses Phase 9's eight synthetic probes, three runs per policy, and two response models. Fixtures:
`fixtures/model/k26/`.

| Response model | kind | `packet-v2` answered | `packet-v1` answered | answer in packet (v2 / v1) | lines placed (v2 / v1) |
|---|---|---:|---:|---:|---:|
| gemma4:31b-cloud | quote | 6/12 | 6/12 | 6 / 6 | 102 / 84 |
| | fact | 3/12 | 3/12 | 12 / 12 | 96 / 84 |
| deepseek-v4.1-flash | quote | 6/12 | 6/12 | 6 / 6 | 102 / 84 |
| | fact | 3/12 | 4/12 | 12 / 12 | 96 / 84 |

- `packet-v2` holds about 1.5 more lines per packet: 8.5 instead of 7 for quote probes, 8 instead of 7 for
  fact probes.
- The same probes carry their answer under both policies. Answers match, except one deepseek run of one
  fact probe ("hidden sweets", 1/3 under v1 and 0/3 under v2, with the answer in both packets). At n = 3
  that is noise, not a difference.
- The two quote probes whose answer is in neither packet ("meeting", "last words") were missed the
  same way in Phase 9: their excerpt is not the best-ranked one. The extra room goes to fact lines
  first, as ADR 0026 orders them.
- Mean prompt tokens per request, as the provider reported them: gemma4 610 → 659, deepseek 672 → 728.

## 4. The owner's recorded requests (replay)

A local restore of the owner's backup of 2026-09-26 (`nmos-2026-09-26-pre-beta21.dump`) was replayed with
`tools/replay_packets.py --policies packet-v1,packet-v2`. The embeddings were computed by the same model
on local Ollama. 12 requests carry a ledger (since migration 0020); 3 were skipped because the story
before them changed.

| Policy | packets | mean estimated tokens | placed |
|---|---:|---:|---|
| `packet-v1` | 9 | 263 | excerpt 4, fact 29, thread 5 |
| `packet-v2` | 9 | 250 | excerpt 4, fact 29, thread 6 |

These recent requests used under half the budget, so the rate changes little there: one more thread line,
13 fewer estimated tokens. K26 is about budget-bound requests. Before the ledger, the owner's 168 fresh
requests of 2026-09-23 to 09-25 had a median packet of 566 estimated tokens (`docs/perf/phase9-packets.md`
§1), but those carry no ledger and cannot be replayed.

## 5. What this does not show

- Tokenizers that were not measured (for example Claude's or GPT's) may count Korean higher. A packet
  would then be larger than the reserve by the difference. The worst case measured is 3 % on a single
  excerpt line.
- The answer probe is small and synthetic: 8 probes, 3 runs, 2 response models.
- The deterministic evaluation (`docs/perf/eval-baseline.md`) is the same under both policies: its cases
  are mostly English.
