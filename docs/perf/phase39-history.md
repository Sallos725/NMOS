# A status window's history in recall: the replay (PHASE-39 step 3b, `packet-v17`)

Measured 2026-10-08 on the trial install's database, read only (`audit.replay` in a read-only session), lexical only
(no embedder is called; both policies replayed the same way), with the owner's two card-bound rules as saved there.

## The recorded requests

The install had 78 recorded requests; 67 replay (11 are of a story changed since). None was recorded with the rules
(they were saved after), so each was replayed under the rules as saved now, once under `packet-v16` and once under
`packet-v17`.

| Requests replayed | Of the two card-bound chats | Packets that differ, v16 → v17 |
|---:|---:|---:|
| 67 | 47 | **0** |

No message the owner sent named a status key and asked how it changed, so `packet-v17` changes none of them.

## Probes

A probe replaces the latest request's message of each card-bound chat (the story before it unchanged).

| Chat | Probe (kind of key) | `<StateHistory>` lines | Placed | Tokens, v16 → v17 |
|---|---|---:|---|---|
| card A | "레벨 언제 올랐어?" (level; the bar writes it in English) | 1 (4 changes) | yes | 2,530 → 2,573 |
| card A | "아이템 언제 생겼지?" (inventory) | 1 (6 changes, long lists) | yes | 2,158 → 2,573 |
| card A | "골드 얼마나 늘었어?" (money) | 1 | yes | 1,726 → 1,828 |
| card A | "HP 언제 이렇게 줄었지?" | 1 | yes | 1,726 → 1,792 |
| card A | "시간이 얼마나 지났지?" (time) | 1 | yes | 1,726 → 2,131 |
| card A | "레벨이 몇이야?" (no change asked) | 0 | — | unchanged |
| card A | "기분 언제 바뀌었어?" (no such key) | 0 | — | unchanged |
| card B | "기분 언제 바뀌었어?", "날씨 언제부터 이랬어?", "시간이 얼마나 지났지?" | 1 each | yes | 0 → 153–176 |
| card B | the four probes of keys it does not have | 0 | — | unchanged |

Card B's latest request placed nothing (an early turn), so its line is the whole packet.

## Reading it

The line comes only when asked: a key named (in the bar's words or the usual Korean and English words for it) and a
cue of change. A list key costs the most (≈400 tokens for six inventories); a number key 40 to 100. The replay found
no request it would have changed. Whether `packet-v17` becomes the default is the owner's decision.
