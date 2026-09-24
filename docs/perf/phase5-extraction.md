# Phase 5 real-model tier (2026-09-24)

Evidence for the real-model acceptance criteria of `docs/phases/PHASE-5.md`. Not a CI gate: it
depends on one model on one day.

## Setup

- **Model:** `deepseek-v4.1-flash:cloud` through the local Ollama (OpenAI-compatible
  `/v1/chat/completions`, `response_format: json_object`, temperature 0), chosen by the owner. It is a
  reasoning model.
- **Code:** `main` at `d64e639` (`extract-v5` prompt, validation and reading as in Phase 5 steps 2–5).
  The runner `tools/eval_extraction_model.py` calls the sidecar's own `SYSTEM_PROMPT`, `build_prompt`
  and `normalize` (the worker's validation), so what is measured is what the worker would store.
- **Scenes:** 18 short Korean scenes written for this evaluation (synthetic test data, not a user's
  chat), 1–2 turns each, in `tools/eval_extraction_model.py`. Three runs per scene (54 calls), plus one
  call per control scene for the token comparison (8 calls). No call failed; one needed a retry.
- **Record:** every prompt, raw reply, token count, normalized assertion and check result is in
  `fixtures/model/phase5/2026-09-24-deepseek-v4.1-flash/` (`runs.jsonl`, `summary.json`).

## Acceptance bars

| Bar (PHASE-5) | Scenes | Result | Met |
|---|---|---|---|
| No hypothetical, dreamed or claimed content becomes a current fact | did not go, plan to meet, condition, dream, daydream, boast, lie (7 × 3 runs) | 0 violations in 21 runs | yes |
| At most 10 % of actual-event assertions in control scenes labeled non-actual | library, key handed over, sprained ankle, promotion (4 × 3) | 1 of 32 (3.1 %): `{{user}} goal "도서관에 가기"` as hypothetical, from the user's "도서관에 가 보자" — arguably right | yes |
| Negation and loss end the right fact in ≥ 2 of 3 runs per scene | lost map, broken sword | 3/3 and 3/3: a negative `possesses` for the same holder and item, which ends the prior holding when read | yes |
| False-merge check: a second item keeps its own name in ≥ 2 of 3 runs, else hints ship off | second map ("해안 지도" hinted; a star map appears), second key ("은빛 열쇠" hinted; a bronze key appears) | 3/3 and 3/3 | yes — hints stay on (default 40) |

"Becomes a current fact" means an assertion that would form state: valid, `modality=actual`,
`source=narration`, positive (ADR 0013). The check is per scene, e.g. nothing places 하나 in the
library in "lie" or 카이토 as the kingdom's best knight in "boast".

## Reported, no bar

| What | Result |
|---|---|
| Hint reuse: "지도" in a turn while "해안 지도" is hinted | 3/3 written as "해안 지도" |
| Stated alias in narration: "하나(Hana)는 … 'Hana'라고 적었다" | 3/3 `also_called` 하나 ↔ Hana, narration. In one run the subject was written "하나(Hana)" (the resolver keys that apart from "하나"). |
| Alias by self-introduction in dialogue: "다들 하루라고 불러 줘" | 0/3 linked. The model found the alias every time (`미나토 하루카 also_called 하루`) but labeled it `character_claim`, correctly: the character says it. ADR 0012 links names only from narration, so this alias is kept and not used. |
| Claims in dialogue | Of 9 claims in "boast" and "lie", 7 were labeled `modality=unknown` (the speaker's truth is unknown) and 2 `actual`. ADR 0013 renders only actual claims as `<Claim>`, so most boasts and lies are stored but not shown to the model. Safe (nothing became a fact), but the claim is lost for the packet. |
| Negations beyond the scenes' targets | "key handed over": the giver's holding ended (3/3). "second map": the star map is no longer in the drawer. "did not go": a negative `event`. |
| Over-inference | "lie", 1 of 3 runs: a narrated negative "하나 located in 도서관" inferred from the sand on her shoes. Not stated by the narration; not a bar failure (it adds no false positive state). |

## Prompt and completion tokens

Mean `prompt_tokens` for the same four control scenes, one call each (`usage` from the endpoint):

| Prompt | Tokens | vs v4 |
|---|---:|---:|
| `extract-v4` (system prompt and registry at `d557496^1`), no hints | 910 | — |
| `extract-v5`, no hints (three runs each) | 1,278 | +40 % |
| `extract-v5` with a 40-entity hint list | 1,626 | +79 % |

The new fields' instructions cost ≈370 tokens per call; a full 40-name list ≈350 more (ADR 0012
estimated 200–300 for the list). A chat with fewer known entities sends a shorter list. Mean
completion tokens per `extract-v5` call: 2,494 (mostly reasoning; not compared with v4, which this run
did not measure for completions). Per call the total therefore grows by roughly 10–20 % with this
reasoning model.

## Real-host smoke (PocketRisu v1.12.0)

Isolated `ghcr.io/pocketrisu/pocketrisu:latest` on its own port and save directory, the release plugin
file (`0.1.0-beta.11`, unchanged by Phase 5), this code's sidecar and worker on a scratch database, the
stub chat model (`tools/spike_stub_llm.py`), a deterministic extraction stub, and a preset whose chat
range keeps only the last three messages. Ten user messages; the last one asks about the map and
Kaito. The stub model received this packet (test data only):

```xml
<NarrativeMemory version="0" source="nmos">
  <Note>… negated="true" marks something explicitly not, or no longer, true. A Claim is what that character said, not established truth.</Note>
  <Facts>
    <Fact kind="possesses" turn="4" negated="true">하나 possesses 해안 지도</Fact>
    <Fact kind="identity" turn="1">카이토 identity: 견습 기사</Fact>
    <Claim by="카이토" kind="identity" turn="5">카이토 identity: 왕국 최고의 기사</Claim>
  </Facts>
</NarrativeMemory>
```

Every generation added 32–42 ms in the plugin. No plugin change was needed.
