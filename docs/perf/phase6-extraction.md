# Phase 6 evidence (2026-09-24)

Evidence for the acceptance criteria of `docs/phases/PHASE-6.md` that need a real model, a real host
or a measurement. It is not a CI gate: the model results come from one model on one day.

## Real-model tier

### Setup

- **Model:** `deepseek-v4.1-flash:cloud` through the local Ollama (OpenAI-compatible
  `/v1/chat/completions`, `response_format: json_object`, temperature 0). This is the model the owner
  chose for Phase 5.
- **Code:** Phase 6 steps 1–4 (`2bfd76c`, `extract-v6`). The runner `tools/eval_phase6_model.py`
  calls the sidecar's own `SYSTEM_PROMPT`, `build_prompt` and `normalize`. It then reads the extracted
  assertions together with each scene's earlier facts through the fact fold (`facts._versions`), so
  the check sees what a request would.
- **Scenes:** 13 short Korean scenes written for this evaluation (synthetic test data, not a user's
  chat):
  - 4 where an item stops existing;
  - 2 where an item is damaged but intact;
  - put down and picked up;
  - a loss (the Phase 5 "lost map" scene);
  - the 4 Phase 5 control scenes.

  Each scene ran three times (39 calls), plus one `extract-v5` call per control scene for the token
  comparison (4 calls). No call failed.
- **Record:** every prompt, raw reply, token count, normalized assertion and check result is in
  `fixtures/model/phase6/2026-09-24-deepseek-v4.1-flash/` (`runs.jsonl`, `summary.json`).

### Acceptance bars

| Bar (PHASE-6) | Scenes | Result | Met |
|---|---|---|---|
| Destroyed, eaten or used-up items end their whereabouts in ≥ 2 of 3 runs per scene | burned letter, eaten apple, drunk potion, last match | 3/3, 3/3, 3/3, 3/3 | yes |
| Damaged-but-intact controls: no `destroyed` in any run | cracked sword, torn cloak | 0 of 6 runs; the holder stays 3/3, 3/3 | yes |
| Control scenes: no `destroyed` for an item that still exists | library, key handed over, sprained ankle, promotion | 0 of 12 runs | yes |
| Control scenes: at most 10 % of actual-event assertions labeled non-actual (Phase 5 bar) | same | 0 of 35 | yes |
| Put down / picked up end with the stated whereabouts in ≥ 2 of 3 runs | put down, picked up | 3/3, 3/3 | yes |

### Reported, no bar

| What | Result |
|---|---|
| A loss stays a loss | "lost map" (the map is blown into the sea and vanishes under the waves): 2 of 3 runs give `하나 possesses 해안 지도, negative`. In 1 run the model gave `해안 지도 destroyed: 바람에 날려 바다로 떨어져 파도 속으로 사라짐` ("blown into the sea and vanished under the waves"). Hana's holding ends either way. The fact reads "destroyed" rather than "lost", which is arguable for a paper map lost at sea. |
| Same-turn multi-value (two different values for one single-valued key in one turn) | 2 of 39 runs, both "sprained ankle": `has_status` "sprained" and "bandaged" in one turn. These are compatible statuses, not a contradiction; the later one is read as current. No item key. This does not justify a same-turn conflict rule (the rule stays out of scope). |

### Prompt and completion tokens

Mean `prompt_tokens` on the four control scenes (`usage` from the endpoint):

| Prompt | Tokens | vs v5 |
|---|---:|---:|
| `extract-v5` (system prompt and registry at `acd0b82`) | 1,328 | — |
| `extract-v6` | 1,424 | +7.2 % |

The `destroyed` registry line and rule cost ≈96 prompt tokens per call. The spec estimated +3–5 %;
this measurement replaces that estimate. Mean completion tokens per `extract-v6` call: 1,478 (mostly
reasoning).

## Fact-read latency

`tools/bench_facts.py`: a `bench_scale.py` chat with one stub extraction per turn, each with two
assertions (a character's place, and an item's holder, place or end, cycling over 60 items). It times
`fact_versions` (15 reads, p50). Phase 6 (`2bfd76c`) and `main` before Phase 6 (`2d71686`, a git
worktree) ran alternately on the same machine at 10,000 messages (10,000 assertions):

| Run | Phase 6 p50 | before p50 | Difference |
|---|---:|---:|---:|
| 1 | 167.9 ms | 157.6 ms | +10.3 |
| 2 | 179.3 ms | 152.7 ms | +26.6 |
| 3 | 163.9 ms | 139.8 ms | +24.1 |
| 4 | 167.0 ms | 149.9 ms | +17.1 |
| 5 | 167.1 ms | 143.9 ms | +23.2 |

The median difference is +23 ms, within the PHASE-6 bound of +30 ms p50. At 1,000 messages the
difference was +2 to +3 ms (16.0 / 16.5 against 14.1 / 13.9 ms). The code before Phase 6 ignores
`destroyed` rows, which are not in its registry, and returns more facts (160 against 100), because
holder and place were separate keys.

## Real-host smoke (PocketRisu v1.12.0)

- **Environment:**
  - an isolated `ghcr.io/pocketrisu/pocketrisu:latest` on its own port and save directory;
  - the release plugin file (`0.1.0-beta.12`), which Phase 6 does not change;
  - this code's sidecar and worker on a scratch database;
  - the stub chat model (`tools/spike_stub_llm.py`);
  - a deterministic extraction stub ("X는 Y를 가지고 있다." → `possesses`, "X는 Y를 불태웠다." →
    `destroyed`);
  - a preset whose chat range keeps only the last three messages.
- **Messages:** eleven user messages. 하나 holds a letter, burns it, and later holds it again.
  카이토 holds a ring, then burns it. The last message asks where the letter and the ring are.
- **Packet:** the stub model received this packet (test data only):

```xml
<NarrativeMemory version="0" source="nmos">
  <Note>… disputed="true" marks a place where the story contradicts itself; neither side is certain.</Note>
  <Facts>
    <Fact kind="destroyed" turn="6">반지 destroyed: 불탐</Fact>
    <Fact kind="possesses" turn="4" disputed="true">하나 possesses 편지; but turn 2: 편지 destroyed: 불탐</Fact>
  </Facts>
</NarrativeMemory>
```

- **Inspector:** the same run's Inspector listed the conflict (`하나 possesses 편지`, turn 4, against
  `편지 destroyed: 불탐`, turn 2) and the timelines:
  - 반지: 카이토 보유 *끝남* → 소멸 *현재*
  - 편지: 하나 보유 *끝남* → 소멸 *충돌* → 하나 보유 *현재*
- **Plugin cost:** every generation added 34–44 ms in the plugin. No plugin change was needed.

## Upgrade from `v0.1.0-beta.12`

The `v0.1.0-beta.12` code (`2d71686`, a git worktree) wrote a 14-turn chat with a stub extractor and
extraction backfill 100. Turn 0 was "Hana has the map.", turn 1 "Hana puts the map on the table.",
then filler and "Mina is in the harbor.". That code read `Hana possesses map` and
`map located_in table` as current together (K10). This code then opened the same database with
backfill 4:

- 4 extraction jobs queued (the recent window only); coverage `compiled 0, older generation 13,
  pending 4` under `extract-v6`;
- before any re-extraction: `Mina located_in harbor` and `map located_in table`, both served by
  `extract-v5`. The whereabouts rule applied to the older generation's facts at once, so
  `Hana possesses map` is no longer current;
- after the 4 jobs: `Mina located_in harbor` from `extract-v6`, `map located_in table` still from
  `extract-v5`.

The scripts were scratch code (`up_write.py`, `up_check.py` with a stub extractor), in the same shape
as the Phase 5 upgrade check.
