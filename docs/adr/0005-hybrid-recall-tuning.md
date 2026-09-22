# 0005 — Hybrid recall tuning (Korean real-model run)

Status: accepted, 2026-09-22.

## Context

Real run: PocketRisu `a14c911`, 120-message Korean chat, `qwen3-embedding:0.6b` via Ollama,
`deepseek-v4-flash:cloud` extraction. Two failures were found:

1. Without a query instruction, Qwen3-Embedding ranked the user's *other earlier questions* above the
   passage that answers the question. Answer passages scored 0.36–0.42, filler ≤0.35, earlier
   questions 0.46–0.49.
2. The plugin's in-context detection let old duplicate filler lines "match" the prompt. The in-context
   window grew backwards, and out-of-context fact sources were treated as already present.

## Decision

- Queries (not documents) get an instruction prefix. `NMOS_EMBED_QUERY_INSTRUCTION=auto` applies the
  Qwen3-Embedding format when the model name contains `qwen3-embedding`; any other value is used as the
  instruction text, and `none` disables it. With it, answer passages scored 0.44–0.54, filler ≤0.35,
  and other questions ≈0.25.
- `NMOS_VECTOR_MIN_SIM` default 0.42.
- In-context detection matches host messages newest→oldest against prompt messages newest→oldest with
  a moving pointer, so an older duplicate cannot claim a prompt slot.

## Result

Five paraphrased questions ("그때 반짝이던 그거, 어디에 숨겨 놨었지?", "카이토는 어디서 일한다고?", …)
each got the correct out-of-context excerpt and/or facts, with no filler. Added latency was 107–155 ms.
