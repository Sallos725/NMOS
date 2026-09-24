# Phase 7 evidence (2026-09-24)

Evidence for the acceptance criteria of `docs/phases/PHASE-7.md` that need a real model, a real host
or a measurement. It is not a CI gate: the model results come from one model on one day.

## Real-model tier

### Setup

- **Model:** `deepseek-v4.1-flash:cloud` through the local Ollama (OpenAI-compatible
  `/v1/chat/completions`, `response_format: json_object`, temperature 0). This is the model of the
  Phase 5 and Phase 6 tiers.
- **Code:** Phase 7 steps 1–5 (`0c74340`, `extract-v7`, system prompt fingerprint `5d318a30df45a8f0`).
  The runner `tools/eval_phase7_model.py` calls the sidecar's own `SYSTEM_PROMPT`, `build_prompt`
  (with the scene's OPEN PROMISES as the worker lists them) and `normalize`. It then reads the
  extracted assertions together with the scene's earlier promise through the thread fold
  (`threads.fold`), so the check sees what a request would.
- **Scenes:** 22 short Korean scenes written for this evaluation (synthetic test data, not a user's
  chat):
  - 3 where a promise is made (dialogue, narration, conditional);
  - 2 kept, 2 broken or withdrawn, and 2 released by the recipient;
  - 4 controls with an open promise listed: two unrelated turns, and two where the promise is only
    discussed;
  - 2 promises that someone else reports;
  - 4 major events (a confession, a betrayal, a secret revealed, a death) and 3 minor ones (a walk, a
    meal, chores).

  Each scene ran three times (66 calls). The 13 Phase 6 scenes (which include the 4 Phase 5 controls)
  ran three times each with `extract-v7` (39 calls). Each of the 4 Phase 5 control scenes also ran once
  with `extract-v6` and once with `extract-v7` for the token comparison (8 calls). No call failed.
- **Record:** every prompt, raw reply, token count, normalized assertion and check result is in
  `fixtures/model/phase7/2026-09-24-deepseek-v4.1-flash/` (`runs.jsonl`, `summary.json`).
- **Rescored after a fold change.** The run was scored with the step 5 fold. Step 6 then changed how a
  new promise restates an open one (containment instead of 0.9 similarity, for cost; ADR 0019 item 4).
  Every recorded check was re-applied to the stored assertions with the final code, and all 93 kept
  their result. No model call was repeated.

### Acceptance bars

| Bar (PHASE-7) | Scenes | Result | Met |
|---|---|---|---|
| A promise opens a thread in ≥ 2 of 3 runs | dialogue, narration, conditional | 3/3, 3/3, 3/3 | yes |
| Kept, broken and released promises close with the right status in ≥ 2 of 3 runs | kept ×2, broken ×2, released ×2 | 3/3 in all six | yes |
| Controls: no `fulfilled` and no negative `promised` for a promise the turn does not keep or break, in any run | unrelated ×2, discussed ×2 | 0 of 12 runs; the promise stays open 12/12 | yes |
| Reported promises: no thread in any run | rumor, oath | 0 of 6 runs | yes |
| Major-event scenes labeled `major` in ≥ 2 of 3 runs | confession, betrayal, secret revealed, death | 3/3 in all four | yes |
| Minor-event scenes labeled `minor` in ≥ 2 of 3 runs | walk, meal, chores | 2/3, 3/3, 2/3 | yes |
| Phase 6 bars with `extract-v7` | burned letter, eaten apple, drunk potion, last match; cracked sword, torn cloak; put down, picked up | 3/3 in all eight; no `destroyed` outside the end scenes | yes |
| Phase 5 bar with `extract-v7`: at most 10 % of actual-event assertions in control scenes labeled non-actual | library, key handed over, sprained ankle, promotion | 0 of 33 | yes |

The two minor-scene runs that missed the bar extracted no event at all (walk run 0, chores run 2). No
minor scene got a `major` label in any run.

### Reported, no bar

| What | Result |
|---|---|
| Promise modality | 9 of 9 made promises labeled `actual` (dialogue and the conditional promise as the maker's claim, the narrated one as narration). With `extract-v6` the Phase 5 "plan to meet" promise was `hypothetical` in 3 of 6 runs. |
| How a resolution names its promise | All 18 resolutions (kept, broken, released) repeated the listed text exactly, so every match took the equal-text path. The similarity path (a reworded resolution) is covered by the deterministic cases only. |
| No `fulfilled` elsewhere | none in the 39 Phase 6 runs |
| The Phase 6 "lost map" scene | 3/3 as a loss (with `extract-v6`: 2/3, one run said `destroyed`) |
| Event labels, all runs | 28 major, 47 minor, none missing on a valid event |

### Prompt and completion tokens

Mean `prompt_tokens` on the four Phase 5 control scenes (`usage` from the endpoint), no OPEN PROMISES
listed:

| Prompt | Tokens | vs v6 |
|---|---:|---:|
| `extract-v6` (system prompt and registry at `4630c4b`, `v0.1.0-beta.13`) | 1,424 | — |
| `extract-v7` | 1,663 | +16.8 % |

The `fulfilled` registry line, the promise and salience rules and the `salience` field cost ≈239 prompt
tokens per call. The spec estimated +5–8 %; this measurement replaces that estimate. Each listed open
promise adds one line (≈20–40 tokens), and only turns whose prompt names its maker or recipient list it.
Mean completion tokens per call on the same four scenes: 3,063 (v6) and 2,704 (v7); on the 39 Phase 6
scenes with v7, 1,471. Completion tokens are mostly reasoning and vary more between runs than between
prompts.

## Fact-read latency

`tools/bench_facts.py --phase7`: a `bench_scale.py` chat with one stub extraction per turn. Each has a
character's place, an item's holder, place or end, and an event (every seventh `major`). Every tenth
turn adds a promise its maker says, and every thirtieth the fulfilment of the promise made two promises
earlier. Makers are spread over 40 characters, or `--makers 4` puts all 500 promises on four characters
(≈125 each). The bench times `fact_versions` (15 reads, p50). Phase 7 and `v0.1.0-beta.13` (`4630c4b`, a
git worktree) ran alternately on the same machine at 10,000 messages (15,666 assertions, 5,099 facts):

| Run | Makers | Phase 7 p50 | beta.13 p50 | Difference |
|---|---:|---:|---:|---:|
| 1 | 40 | 300.7 ms | 296.7 ms | +4.0 |
| 2 | 40 | 310.4 ms | 303.9 ms | +6.5 |
| 3 | 40 | 305.1 ms | 303.6 ms | +1.5 |
| 4 | 4 | 309.7 ms | 299.7 ms | +10.0 |
| 5 | 4 | 311.1 ms | 295.9 ms | +15.2 |

The median difference is +4 ms with spread makers and +10 to +15 ms with four makers, within the
PHASE-7 bound of +30 ms p50. At 1,000 messages: 22.7 against 22.9 ms. At 5,000: 146.1 against 136.8 ms
(one run each).

The step 5 fold was over the bound in the same comparison with four makers: +107 ms in one run, then
+34, +27 and +29 ms after caching each thread's trigrams. It compared every new promise with every open
promise of its maker by trigram similarity (a restatement check), which cost ≈20 ms per read. Three
changes brought the fold to ≈4 ms per read on the same database (ADR 0019):
restatement by containment, trigrams only when a resolution's text is not equal, and folding only the
`promised` / `fulfilled` rows.

## Real-host smoke (PocketRisu v1.12.0)

- **Environment:**
  - an isolated `ghcr.io/pocketrisu/pocketrisu:latest` on its own port and save directory;
  - the plugin file from `adapters/pocketrisu-plugin/dist/` (`0.1.0-beta.13`; Phase 7 does not change
    it);
  - this code's sidecar and worker on a scratch database;
  - the stub chat model (`tools/spike_stub_llm.py`);
  - a deterministic extraction stub that reads the user's lines:
    - "X는 Y에게 약속했다: Z." → X promised Y: Z (X's claim)
    - "X는 약속을 지켰다: Z." → `fulfilled`
    - "X는 Y에게 고백했다." → a major event
    - "X는 Y 일을 했다." → a minor event
  - a preset whose chat range keeps only the last three messages.
- **Messages:** twelve user messages:
  1. 하나 promises 카이토 to meet at the lighthouse when the rain stops;
  2. 유이 promises 카이토 to deliver a letter;
  3. two chores by 하나;
  4. 유이 keeps her promise;
  5. 하나 confesses to 카이토;
  6. three more chores by 하나;
  7. two filler messages;
  8. the last message: "하나야, 유이야, 오랜만이야."
- **OPEN PROMISES:** every extraction prompt from the second turn on listed 하나's promise. 유이's promise
  was listed too in the three turns after she made it, up to and including the turn that kept it, and
  not after.
- **Packet:** the stub model received this packet (test data only):

```xml
<NarrativeMemory version="0" source="nmos">
  <Note>… A Thread is a promise made in the story and not yet kept or broken.</Note>
  <Threads>
    <Thread kind="promise" by="하나" to="카이토" turn="0">비가 그치면 등대 앞에서 만나기</Thread>
  </Threads>
  <Facts>
    <Fact kind="event" turn="5">하나 event: 카이토에게 고백</Fact>
  </Facts>
</NarrativeMemory>
```

  하나's open promise came back from turn 0; 유이's kept promise did not come back. Of 하나's six events,
  only the major one did: the query names her, but not any chore.
- **Inspector:** the Promises section listed both promises: 유이 → 카이토 *지킴* (kept), closed by
  `유이 fulfilled: 편지를 대신 전해 주기` at turn 4; 하나 → 카이토 *열림* (open). The event facts
  carried their chips: five *사소* (minor) and one *중요* (major).
- **Plugin cost:** every generation added 32–54 ms in the plugin. No plugin change was needed.

## Upgrade from `v0.1.0-beta.13`

The `v0.1.0-beta.13` code (`4630c4b`, a git worktree) set up a new database (migrations 0001–0015)
and wrote a 13-turn chat with the memory-evaluation stub extractor, extraction backfill 100:

- turn 0: 'Hana says to Kaito: "I promise to meet you at the lighthouse."';
- filler;
- "Hana did chore 0." to "Hana did chore 2.";
- "Mina is in the harbor.".

Asked "Hana, long time no see." with the last four messages in context, that code injected two chore
events as facts and the promise as `<Claim by="Hana" kind="promised">`.

This code then opened the same database with backfill 4:

- migration 0016 applied (only it), and `assertion.salience` exists;
- 4 extraction jobs queued (the recent window only); coverage under `extract-v7`: compiled 0, served
  by the older generation 13, pending 4;
- before any re-extraction the same question got `<Thread kind="promise" by="Hana" to="Kaito"
  turn="0">meet you at the lighthouse</Thread>`. The thread fold applied to the older generation's
  promise at once. The chore events were still there: unlabeled events rank as before;
- after the 4 jobs, the chores of the re-extracted turns were labeled `minor`. The packet kept the
  thread and dropped the chores: the question names Hana, not a chore.

The scripts were scratch code (`up_write.py`, `up_check.py`), in the same shape as the Phase 6 upgrade
check.
