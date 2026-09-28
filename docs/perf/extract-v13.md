# `extract-v13` — open business (Phase 11 steps 4–5 and 8, ADR 0039, ADR 0040)

Measured 2026-09-28. Goals, questions, threats and debts open threads; `resolved` ends one with an outcome; `because`
keeps a cause the story states.

## Real-model tier (synthetic scenes)

`tools/eval_v13_model.py`, 14 Korean scenes written for this evaluation, 3 runs each, both models through the local
Ollama, 2 workers, no errors. Raw prompts, replies and checks: `fixtures/model/v13/`. Prompt fingerprint
`a0de52e41b72df2c` (the final prompt).

| Category | Scene | `gemma4:31b-cloud` | `deepseek-v4.1-flash` |
|---|---|---:|---:|
| opens | a lasting goal | 3/3 | 3/3 |
| opens | a question or mystery | 2/3 | 3/3 |
| opens | a threat made | 3/3 | 3/3 |
| opens | money borrowed | 3/3 | 3/3 |
| wish | a craving is not a goal | 3/3 | 3/3 |
| wish | the next step is not a goal | 3/3 | 3/3 |
| resolve | a goal achieved | 3/3 | 3/3 |
| resolve | a question answered | 3/3 | 3/3 |
| resolve | a threat averted | 3/3 | 3/3 |
| resolve | a debt paid | 3/3 | 3/3 |
| control | a goal worked on stays open | 3/3 | 3/3 |
| control | a debt mentioned stays open | 3/3 | 3/3 |
| cause | a stated cause is kept | 3/3 | 3/3 |
| cause | no cause is invented | 3/3 | 3/3 |
| **all** | | **41/42** | **42/42** |

The one miss: `gemma4` recorded "who rang the bell" as a goal to find out, not a question; it is an open thread
either way. A first prompt without examples had `gemma4` record a craving ("달달한 게 먹고 싶다") as a goal 3 of 3
times and the next step of a chore 2 of 3; the prompt now names both as not goals, and "wanting to find something out"
as a question. Every scene was run again with the final prompt (the table).

## The owner's chat (M0 copy re-extracted)

The restored backup (PHASE-11 Q1), with `extract-v13` activated on a second copy and the owner's model re-extracting
the M0 chat's 73 turns through the local Ollama (no errors). Counts only. This table is the first re-extraction, with
OPEN THREADS listing the newest named threads; the second, with the listing below, is summarised after it.

| | before (`extract-v12`) | `extract-v13` |
|---|---|---|
| goal assertions in the chat | 93 | 49 goals, 9 questions (restatements and cravings fewer) |
| goals as threads | none (facts, never ended) | 48 goal threads: **11 achieved**, 37 open |
| other threads | 8 promises open, 2 kept | promises unchanged; 1 question answered, 8 open |
| endings matching no open thread | — | 6 |
| facts with a stated cause | — | 66 |
| goal lines in M0's 12 packets | 0 | goals reach the packets as threads |

Two faults found here and fixed before this record: the model gives a `resolved` its owner as `object`, and closes a
goal with `fulfilled`; both matched nothing (11 unmatched). `resolved` now matches by owner and text only, and a
`fulfilled` that matches no promise ends the owner's goal (ADR 0039).

**M0 on the first 12 cases: 5 of 12, as the baseline.** Goals reached the packet but not the owner's two open ones
(newer goals rank first), and the relationship cases fell 2 → 0 because the new extraction words the current feeling
differently ("설렘과 긍정적인 감정" where the gold phrase was "좋아함"). That met a PHASE-11 stop condition. The owner
chose (2026-09-28) to fix it before merging: gold that accepts wordings of the same answer, and more cases.

**What changed before this record.** OPEN THREADS lists what the target turn is about first: a thread can only be
ended while it is listed, and the list had held only the newest threads of the characters named, so an old goal the
story came back to was never listed again. The copy was re-extracted with it (73 turns, no errors): 48 goal threads,
9 achieved; 10 questions, 1 answered and 1 given up; 9 endings match nothing.

**M0 on the 28 owner-confirmed cases** (`docs/perf/m0-baseline.md`):

| Category | cases | `main` (before Phase 11) | step 3 | `extract-v13` |
|---|---:|---:|---:|---:|
| address | 5 | 2 | 4 | 4 |
| goal | 1 | 0 | 0 | 0 |
| irrelevant | 3 | 3 | 3 | 3 |
| past | 3 | 3 | 3 | 3 |
| promise | 3 | 2 | 2 | 2 (forbidden 0, was 1) |
| relationship | 4 | 3 | 3 | 3 |
| secret | 2 | 0 | 0 | 0 |
| state | 5 | 0 | 0 | 2 |
| why | 2 | 0 | 0 | 0 |
| **all** | **28** | **13** | **15** | **17** |

No category is worse than the baseline. The goal case still fails: the owner's two open goals were stated once and
never mentioned again, and newer goals outrank them for three thread slots; 37 goals stay open without a turn saying
they ended (K23). The "why" cases wait for step 6, which reads `because`.

These counts hold a gold answer only when the packet does. With the scoring corrected in step 6 (answers the prompt's
own last messages hold count too, `docs/perf/m0-baseline.md`), the same runs give 23 of 28 before Phase 11 and 26 with
`extract-v13`; of the 9 cases that need memory, 5 and 7.

## Acceptance on the M0 copy (step 8)

Read-only on the restored copies, the current code (`resolve-v5`, the pair fold), every current line counted:

| Longest chat | `extract-v12` (`nmos_m0`) | `extract-v13` (`nmos_m0v13b`) |
|---|---|---|
| goals current | 43 lines: 11 facts, 26 claims, 6 not actual | 37 open goal threads (9 achieved, 1 answered, gone), 2 claims |
| per character (three main characters, A–C) | A 17, B 9, C 4 | B 15, A 14, C 4 |
| pairs with more than one current relationship | 0 of 4 with one | 0 of 5 with one |

Goals now end, but they do not stop piling up: the model ended 9 of 48 goals in 73 turns, and a goal the story
never mentions again stays open (K23). One character holds 15 open goals where the owner counts 2 as still under way. The
PHASE-11 figure "one character holds 40" counted valid assertions over every revision, not current lines. The
packet is less affected than the Inspector: at most three threads, the ones about the people named or the message
(ADR 0019 amendment 1).

## Latency (step 8)

`tools/bench_scale.py 10000` (lexical retrieve after an append, and the fact read), three pairs against Phase 10
`main` (8c790b2), the last in reverse order:

| Pair | retrieve p50 ms, 8c790b2 → this branch | fact read p50 ms |
|---|---:|---:|
| 1 | 11.3 → 12.5 | 97.4 → 102.5 |
| 2 | 9.1 → 13.8 | 111.7 → 102.6 |
| 3 (this branch first) | 12.8 → 14.2 | 99.7 → 100.0 |

+1.2 to +4.7 ms p50 (+2.4 on average), within the +10 ms bound; per query +0 to +5 ms. The fact read shows no
change beyond noise. The bench has no goals or causes, so it does not reach the thread fold or the cause links
(read time, per request with facts).

## Real-host smoke (PocketRisu v1.13.0, step 8)

- **Environment:**
  - an isolated `ghcr.io/pocketrisu/pocketrisu:latest` (v1.13.0) on its own port and save directory, with the
    chat of the Phase 10 smoke;
  - the plugin file from `adapters/pocketrisu-plugin/dist/` (Phase 11 does not change it);
  - this branch's sidecar and worker on a scratch database (migrations to 0022, `extract-v13`, `packet-v6`);
  - the stub chat model (`tools/spike_stub_llm.py --show-packets`);
  - a deterministic extraction stub: "X는 목표를 세웠다: Z." → `goal`, "X는 목표를 이뤘다: Z." → `resolved` with
    outcome `achieved`, "X는 Y에게 화가 났다, 왜냐하면 Z." → `feels_toward` with `because`.
- **Messages:** "하나는 목표를 세웠다: 등대지기의 행방 찾기.", three filler messages, "하나야, 요즘 뭘 하려고 해?",
  the anger with its cause, "하나는 목표를 이뤘다: 등대지기의 행방 찾기.", three filler messages, then "하나야, 왜
  카이토한테 그렇게 굴어? 이제 뭘 하려고 해?".
- **Extraction:** every prompt after the goal listed it under OPEN THREADS
  (`- [goal] 하나: 등대지기의 행방 찾기 (turn 26)`); the stub ended it with the listed text.
- **Packets** the stub model received (test data only; the Note and the chat's earlier secrets shortened):

```xml
<!-- "하나야, 요즘 뭘 하려고 해?" -->
<Threads>
  <Thread kind="goal" by="하나" turn="26">등대지기의 행방 찾기</Thread>
  <Thread kind="promise" by="하나" to="카이토" turn="0">비가 그치면 등대 앞에서 만나기</Thread>
</Threads>
<!-- "하나야, 왜 카이토한테 그렇게 굴어? 이제 뭘 하려고 해?" -->
<Threads>
  <Thread kind="promise" by="하나" to="카이토" turn="0">비가 그치면 등대 앞에서 만나기</Thread>
</Threads>
<Facts>
  <Fact kind="feels_toward" turn="31">하나 feels toward 카이토: 화남; because: 카이토가 등대 축제를 잊었다</Fact>
  …
</Facts>
```

- **Inspector** (the plugin panel, chat page): the thread table shows `목표 · 하나 · 등대지기의 행방 찾기 · 26 · 이룸 ·
  32 · 하나 resolved: 등대지기의 행방 찾기`, and "열림: 약속 1"; the Relationships section shows
  `카이토 ↔ 하나` with `하나 → 카이토: 화남 31 · 원인: 카이토가 등대 축제를 잊었다`.
- Every request took 46–121 ms in the plugin (`[NMOS] request done`).
