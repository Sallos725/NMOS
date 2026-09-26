# `extract-v10`: `addresses` (speech level and form of address) — evidence

Date: 2026-09-26. Branch `speech-address` (ADR 0028), on top of ADR 0026. Models through Ollama at
`http://127.0.0.1:11434/v1`, temperature 0: `gemma4:31b-cloud` (the owner's extraction model) and
`deepseek-v4.1-flash:cloud` (the model of the Phase 5–8 tiers).

## 1. Synthetic scenes (`tools/eval_v10_model.py`, committed)

New Korean scenes written for this evaluation (not a user's chat), 3 runs each. Raw runs and summaries:
`fixtures/model/v10/2026-09-26-*`. A pass for "settled" is a valid, narrated, actual `addresses` for the
right direction with the expected speech level or form of address in its value. A pass for a control is no
valid `addresses`.

| Scene | gemma | deepseek |
|---|---|---|
| settled: agree informally, 유이 → 카이토 | 3/3 | 3/3 |
| settled: agree informally, 카이토 → 유이 (same turn) | 3/3 | 3/3 |
| settled: form of address asked for and taken up (오빠) | 3/3 | 3/3 |
| settled: change back decided (존댓말, 카이토 씨) | 3/3 | 3/3 |
| control: a reply slips into formal speech, nobody remarks | 3/3 | 3/3 |
| control: speech settled in context continues | 3/3 | 3/3 |
| control: routine | 3/3 | 3/3 |

The `extract-v9` scenes (`tools/eval_v9_model.py`) re-run with the `extract-v10` prompt, against the
`extract-v9` fixtures of 2026-09-25:

| Scene | gemma v9 → v10 | deepseek v9 → v10 |
|---|---|---|
| major: admission | 0/3 → 0/3 | 3/3 → 3/3 |
| major: speech level | 3/3 → 3/3 | 3/3 → 3/3 |
| major: form of address | 0/3 → 3/3 | 3/3 → 2/3 |
| major: relationship allowed | 0/3 → 0/3 | 2/3 → 1/3 |
| major: device explodes | 3/3 → 3/3 | 3/3 → 3/3 |
| routine ×3 (no major event) | 3/3 ×3 → 3/3 ×3 | 3/3 ×3 → 3/3 ×3 |
| unnamed: first sight, reveal, two controls | 3/3 ×4 → 3/3 ×4 | 2/3, 3/3 ×3 → 3/3 ×4 |

deepseek's two scenes lost one run each, within the one-in-three variance the earlier tiers showed.

**Phase 6–8 bars (gemma, `extract-v10` prompt;** `fixtures/model/v10/2026-09-26-gemma4-31b-phase-bars`,
written by `tools/eval_v9_model.py`, whose summary labels the current prompt "v9"): identical to the
`extract-v9` run of 2026-09-25 except Phase 7 "released: letter" 3/3 → 2/3 and Phase 8 "absent
householder" 0/3 → 1/3. The known gemma misses (lost map, daily letters, giving ×2, destroyed by another)
are unchanged.

## 2. The owner's chat (read-only, chat text not committed)

The owner's 69-turn chat was read from the production database with a read-only session and never
changed. A scratch script (not committed) built each prompt as the worker does (`build_prompt` from the
head's normalized messages, 3 context turns, and the KNOWN ENTITIES and OPEN PROMISES stored on that turn's
active `extract-v9` extraction), then sent it with the `extract-v10` prompt, 3 runs per turn. Only counts
are reported here.

| Turns | Runs with a valid `addresses` | Notes |
|---|---|---|
| Speech or address settled (t13, t14, t15, t39, t42, t46) | 18/18 | t46 gave both directions (라디아 → persona 반말, persona → 라디아 반말 and '누나') in 3/3 |
| 라디아's slip into 존댓말 (t63) | 0/3 | the reply the owner corrected |
| The user's correction "누나, 반말." (t64) | 3/3 | restates 라디아 → persona: 반말 |
| Routine (t17, t21, t47, t55) | 0/12 | |

Every `addresses` was narration and actual. Values varied in phrasing (e.g. "해요체, '블랑 씨'라고 부름").

Major events on the six settled turns, same day, same prompt builder:

| Turn | `extract-v9` | `extract-v10` |
|---|---|---|
| t13 | 3/3 | 3/3 |
| t14 | 2/3 | 0/3 |
| t15 | 0/3 | 0/3 |
| t39 | 3/3 | 0/3 |
| t42 | 3/3 | 3/3 |
| t46 | 1/3 | 3/3 |
| total | 12/18 | 12/18 |

On t39 and t14 `extract-v10` records the change as `addresses` and labels the only event, another
character's reaction, minor. A variant that asked for the turning point "itself as a major event" gave 8/18
and was not kept.

## 3. Real host (PocketRisu v1.12.0, isolated)

An isolated PocketRisu (`ghcr.io/pocketrisu/pocketrisu:latest`, own save directory, port 6131), the
branch's sidecar and worker (own database), the released plugin (`0.1.0-beta.18`, unchanged by this
branch), the "short window" preset and a deterministic extraction stub (scratch, not committed) answering
two sentence shapes. The owner's stack was not touched.

- Turn 0 "하나와 레온은 서로 말을 놓기로 했다." gave two valid `addresses` rows (하나 → 레온, 레온 → 하나) and a
  major event; the next eight turns gave `하나 knows: 항구의 비밀 N번` with `known_by="미나, 카이토"`.
- The message "하나와 미나와 카이토가 다시 함께 들어왔다. 레온도 뒤따랐다." reached the stub model with a packet
  whose `<Facts>` opened with both `addresses` lines, then the major event, then five `knows` facts. Before
  ADR 0026 the `known_by` bonus would have ranked the `knows` facts first.
- Inspector → the conversation → Retrievals showed the new column "사실 (넣음/후보)" as `8/8` for that
  request, and the fact list used the label "말투·호칭".

## 4. Prompt cost

Mean prompt tokens on the `extract-v9` scenes: gemma 2,262 → 2,527, deepseek 2,240 → 2,506 (+≈265, +12 %),
from the `addresses` line in the registry and its rule.

## 5. Tests

`apps/sidecar/tests/test_addresses.py` (registry, prompt rules, a change back replaces one direction only,
the packet), `tests/test_fact_ranking.py` (ADR 0026), memory evaluation cases "speech level in a crowded
scene" and "speech level changed back" (`tests/memeval.py`; full mode 33/33, no stale memory).
