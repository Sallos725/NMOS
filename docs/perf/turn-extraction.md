# Per-turn vs per-message extraction (2026-09-23, ADR 0008)

## Setup

- **Chat:** a hand-written synthetic Korean role-play, 19 turns plus a greeting: 38 messages, then a
  final user message. It is test data written for this comparison, not a user's chat. Turns 3 and 9
  are user actions that the reply refuses: taking a key from a locked drawer, and swinging a knife
  that the other character stops. Later turns change earlier facts (an injury heals, a map is given
  back, a secret is told to a second character).
- **Model:** `deepseek-v4.1-flash:cloud` through a local Ollama (OpenAI-compatible,
  `response_format: json_object`, temperature 0). A counting proxy recorded `usage` per call.
- **Code:** `main` at `0a31ce2` (per message, `K = 6` messages, `extract-v3`) and this branch (per
  turn, `K = 3` turns, `extract-v4`). Each ran in-process against a fresh database, with the same chat
  synced once and the queue drained. `NMOS_EXTRACT_BACKFILL = 1000`, so all history was extracted.
- One run each, and both ran at the same time against the same Ollama. Wall-clock time is therefore
  not comparable and is not reported. One per-turn call hit the 120 s client timeout and succeeded on
  retry. Neither run had a dead job.

## Cost

| | per message (`main`) | per turn (branch) | change |
|---|---:|---:|---:|
| Jobs | 38 | 19 turns (+1 retry) | |
| LLM calls (targets under 12 chars are skipped without a call) | 32 | 19 | −41 % |
| Prompt tokens | 32,199 | 20,205 | −37 % |
| Completion tokens | 32,363 | 38,543 | +19 % |
| Total tokens | 64,562 | 58,748 | −9 % |

This model is a reasoning model: most completion tokens are reasoning, and a turn target (two
messages) gets longer reasoning than one message does. With a non-reasoning model the completion side
should matter less, but that was not measured here.

## What was extracted

Assertions: 48 per message vs 45 per turn. Current facts: 44 vs 39. Both runs extracted the same
story facts: identities, the key's location, the injury and its healing, the promise, the secret with
`hidden_from: 카이토` and later `known_by: 카이토`, the friendship, the new star's name, the festival,
the map's final place.

The refused actions differ:

| Turn | Per message (current facts afterwards) | Per turn |
|---|---|---|
| 3 — "나는 몰래 서랍에서 은빛 열쇠를 꺼내 주머니에 넣는다." / "서랍은 잠겨 있었다 … 열쇠는 그대로 서랍 안에 남았다." | `유진 possesses 은빛 열쇠` (from the user message, **false**) and `유진 event: 꺼내려 했으나 실패함` | `유진 event: 몰래 꺼내려 했으나 서랍이 잠겨 실패했다`, `은빛 열쇠 located_in 서랍` |
| 9 — "카이토에게 칼을 휘두른다." / "… 손목을 붙잡았다 … 싸움은 일어나지 않았고 칼은 … 카이토가 주웠다." | `{{user}} event: 카이토에게 칼을 휘둘렀다` (**false**) and `유진 event: 제지당했고 싸움은 일어나지 않았다` | `유진 event: 휘두르려 했으나 카이토가 제지함`, `카이토 possesses 칼` |

Per message, both false facts stay current, because nothing later supersedes them. Per turn, the reply
decides the outcome, so they never appear.

Both runs still share one issue: `유진 possesses 해안 지도` stays current after the map is returned,
next to `하나 possesses 해안 지도`. `possesses` is multi-valued per subject, so giving an item away does
not supersede the old holder. This is independent of the extraction unit.

## Host check (real UI)

Isolated `ghcr.io/pocketrisu/pocketrisu:latest` (v1.12.0), fresh save, `tools/spike_stub_llm.py` as
the chat model, a deterministic extraction stub (one `world_fact` per turn, the user line as value),
this branch's sidecar and worker, `NMOS_EXTRACT_BACKFILL = 2`:

1. Five turns were sent **before** the plugin was installed, and four after. At the first request
   after installation NMOS ingested the whole chat and extracted only the latest 2 complete turns;
   each later request completed one more turn. That makes 5 extraction calls in total. The Inspector
   showed facts `5/8`, `not queued 3`.
2. Panel → Inspector → conversation → **과거 전체 추출** queued 3 turns ("턴 3개 추출과 메시지 0개
   임베딩을 백그라운드에 넣었습니다"). After the worker ran: `8/8`, with facts for turns 0–7.
3. PocketRisu's message trash icon offers "Remove this and following messages (6)". It was used on
   turn 6's user message. At the next request NMOS committed `delete ×5, append ×1`: the host deleted
   6 messages, but the last reply had never been synced. Facts of turns 6–7 disappeared, turns 0–5
   stayed, and nothing was re-queued (`6/6`, pending 0).
4. **기억 재구축**: the first click changes the button to "한 번 더 누르면 재구축합니다", and the
   second click reported "추출 8건을 버리고 턴 6개를 다시 추출합니다". The 8 discarded extractions
   included those of the deleted turns. Coverage went to `0/6` at once, then back to `6/6` after 6
   extraction calls, with the same facts.
