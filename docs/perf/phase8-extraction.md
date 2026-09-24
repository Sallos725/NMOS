# Phase 8 evidence (2026-09-24)

Evidence for the acceptance criteria of `docs/phases/PHASE-8.md` that need a real model, a real host
or a measurement. It is not a CI gate: the model results come from one model on one day.

## Real-model tier

### Setup

- **Model:** `deepseek-v4.1-flash:cloud` through the local Ollama (OpenAI-compatible
  `/v1/chat/completions`, `response_format: json_object`, temperature 0), the model of the Phase 5–7
  tiers.
- **Code:** Phase 8 steps 1–4 (`636650a`, `extract-v8`). The runner `tools/eval_phase8_model.py`
  calls the sidecar's own `SYSTEM_PROMPT`, `build_prompt` and `normalize`.
- **Scenes:** 18 short Korean scenes written for this evaluation (synthetic test data, not a user's
  chat):
  - 10 positive scenes, each naming the people an assertion must cover and the participants' types:
    - giving ×2, an attack, confessions ×2, a rescue;
    - a group attack (산적들 on 하나 and 카이토);
    - a goal, a knowledge fact and a destroyed item about another character;
  - 4 controls that must produce no participant: a solo walk, cooking, passing someone's house while
    they are away, and "동전이 하나도 없었다" with no character 하나;
  - the secret about a shared event, modeled on the owner's report (new text);
  - 3 relationship scenes (report only), each with the relationship fact that held before.

  Each ran three times (54 calls). The Phase 6 scenes (39 calls) and the Phase 7 scenes (66 calls)
  ran again with `extract-v8`. The four Phase 5 control scenes ran once with `extract-v7` and once
  with `extract-v8` for tokens (8 calls). No call failed.
- **Record:** `fixtures/model/phase8/2026-09-24-deepseek-v4.1-flash/` (`runs.jsonl`, `summary.json`).
  `minor-repeat.jsonl` holds the follow-up below.

### Acceptance bars

| Bar (PHASE-8) | Result | Met |
|---|---|---|
| Two-person and group scenes: the other participant(s) in `with` in ≥ 2 of 3 runs | 3/3 in all seven, with the right types (산적들 as a group) | yes |
| Goal, knowledge and destroyed-item scenes: the other character in `with`, right type, ≥ 2 of 3 | 3/3, 3/3, 3/3 | yes |
| Controls: every solo, absent-householder and "하나도" run has an empty `with` | 12 of 12 runs | yes |
| Every participant emitted in a positive scene is named in the TARGET turn | no exception in 54 runs | yes |
| Secret about a shared event: C (마키 선생님) in `with` ≥ 2 of 3, and never in `known_by` | in `with` 3/3, in `known_by` 0/3 (and in `hidden_from` 3/3, reported without a bar) | yes |
| Phase 5 bar with `extract-v8` (≤ 10 % of actual events in control scenes labeled non-actual) | 0 of 31 | yes |
| Phase 6 bars with `extract-v8` | end 3/3 ×4, damaged-intact 3/3 ×2, whereabouts 3/3 ×2; no `destroyed` in the control or damaged scenes | yes |
| Phase 7 bars with `extract-v8` | promises opened, kept, broken, released 3/3 in all nine scenes; controls 3/3 ×4; reported 3/3 ×2; major 3/3 ×4; minor walk 3/3, meal 3/3, **chores 1/3** | **not as written** (below) |

### The Phase 7 minor-event bar

With `extract-v8`, "minor: chores" passed 1 of 3 runs. Both failing runs extracted no event at all. No
minor scene had a `major` label in any run. The same scene with `extract-v7` had passed 2 of 3 in the
Phase 7 tier with one empty run. To tell a regression from variance, `tools/eval_phase8_minor_repeat.py`
ran each Phase 7 minor scene ten more times with both prompts:

| Scene | `extract-v7` | `extract-v8` |
|---|---:|---:|
| minor: walk | 9/10 (1 empty) | 8/10 (2 empty) |
| minor: meal | 8/10 (2 empty) | 10/10 (0 empty) |
| minor: chores | 3/10 (7 empty) | 4/10 (6 empty) |

The chores scene fails mostly by extracting nothing with either prompt; v8 is not worse. The Phase 7
tier's 2/3 on that scene was a favorable draw. The bar as written ("labeled `minor` in at least two of
three runs") is not met in this run. This is recorded for the owner's decision and is not marked done.

### Reported, no bar

| What | Result |
|---|---|
| Participants per valid assertion (all `extract-v8` runs) | 0.356 |
| Phase 6 scenes with participants | 29 assertions (mostly who ate, drank or burned an item) |
| Agreement with a manual review (scope audit, 87 assertions of the Phase 8 runs) | 83 of 87. The four differences: 카이토 added to 하나's fall into the river; 마키 선생님 missed on a `knows` twice (유이, the listener, given instead); "엄마" (마키 선생님) missed on 유이's goal. |
| Lost map (Phase 6 loss scene) | 2/3 as a loss; one run said `destroyed`, as in the Phase 6 tier |

### Relationship report (no extraction-rate bar)

Each scene had one relationship fact from an earlier turn. The new one was read with the fact fold.

| Scene | Extracted | Earlier fact superseded |
|---|---|---|
| friends → rivals | `relationship: 경쟁자` 3/3 (both directions each time) | 3/3 |
| confession accepted | `relationship: 연인` 3/3 | 2/3. One run recorded it as 카이토 → 유이, the opposite direction of the earlier 유이 → 카이토, so "같은 반 친구" stayed current beside it |
| reconciliation | 3/3 (`feels_toward` 2/3, `relationship` only 1/3) | 2/3. When only `relationship` was recorded, the earlier `feels_toward: 분노` stayed current |

Relationship changes were extracted in 9 of 9 runs. In 2 of 9 an older state stayed current, once
through direction (no inverse or symmetry rule) and once through the choice between `relationship`
and `feels_toward`. Neither is caused by Phase 8, and Phase 8 does not change relationships. Both
are recorded in `docs/KNOWN-ISSUES.md` (K24) as input for a later decision.

### Prompt and completion tokens

Mean on the four Phase 5 control scenes, one call each (`usage` from the endpoint):

| Prompt | Prompt tokens | Completion tokens |
|---|---:|---:|
| `extract-v7` (system prompt and registry at `23b13a8`, `v0.1.0-beta.14`) | 1,663 | 2,656 |
| `extract-v8` | 1,824 (+9.7 %) | 2,852 (+7.4 %) |

The `with` rule and answer field cost ≈161 prompt tokens per call. The spec estimated +2–4 %; this
measurement replaces it. Completion tokens are one call per scene, mostly reasoning, and vary between
runs.

## Scope audit

`fixtures/model/phase8/scope-audit.json` now also lists the 87 `event`, `destroyed`, `goal`, `knows`
and `fulfilled` assertions of the Phase 8 runs. Each entry records the model's own `with`
(`model_participants`) beside the manual review and whether they agree. Participants the value does
not name but the TARGET turn does are marked `implied`: the one who burned the diary, and the person a
nod answered. `python3 tools/check_phase8_scope_audit.py` checks them against the run file too. The
Phase 5–7 scope counts are unchanged (78 usable assertions in 18 scenes).

## Fact-read latency

`tools/bench_facts.py --phase7`, the Phase 7 facts tier. On a Phase 8 schema, half of the events also
name another character as a typed participant: 2,500 of 15,666 assertions at 10,000 messages (the
recorded `extract-v8` runs average 0.356 participants per valid assertion). Phase 8 and `v0.1.0-beta.14` (`23b13a8`, a git worktree)
ran alternately at 10,000 messages.

Final code, each database built by its own code and read in alternation (six pairs):

| Pair | Phase 8 p50 | beta.14 p50 | Difference |
|---|---:|---:|---:|
| 1 | 314.2 ms | 311.3 ms | +2.9 |
| 2 | 317.0 ms | 307.9 ms | +9.1 |
| 3 | 309.0 ms | 307.3 ms | +1.7 |
| 4 | 314.5 ms | 306.9 ms | +7.6 |
| 5 | 313.3 ms | 315.3 ms | −2.0 |
| 6 | 313.4 ms | 305.3 ms | +8.1 |

The median difference is +5.3 ms, within the PHASE-8 bound of +15 ms p50. Two fixed databases (one
per version), read in seven interleaved rounds, gave a median of +7.0 ms. At 1,000 and 5,000 messages
(one run each, before the last two changes below): 25.6 against 24.3 ms and 148.6 against 137.2 ms.
Single runs on this machine vary by about ±10 ms (reading one database with one code version several
times), so only medians over several pairs are reported.

**How the cost was brought down.** The first Phase 8 read cost ≈+25 ms more than beta.14 on the same
database. Five changes brought it down:

- Participants are fetched as text, not jsonb. Decoding every value through the driver's jsonb loader
  cost ≈10 ms.
- The text is parsed once per distinct stored list and cached. Rows never change, so a read after the
  first costs no parsing (`json.loads` of 2,500 lists was ≈4 ms).
- `entities.node()` is cached: the resolver's second pass and the persona check call it for every
  participant.
- Only rows that have participants are processed.
- The participants' entities for display are resolved on the Inspector's paths only. A fact read for
  recall resolves just the names it needs.

**A benchmark artifact, found and fixed.** The benchmark first filled participants with an `UPDATE`
after inserting the rows, and only on the Phase 8 schema. The dead rows it left made the Phase 8
database slower to read than the beta.14 one: +19.7 ms median over eight pairs of an earlier version of
the code. A real database writes participants with the row, so the benchmark now runs `VACUUM` after
that `UPDATE`. With `VACUUM`, and before the parse cache and the Inspector-only resolution, the median
was +18.2 ms over six pairs; the last two changes brought it to the table above.

## Real-host smoke (PocketRisu v1.12.0)

- **Environment:**
  - an isolated `ghcr.io/pocketrisu/pocketrisu:latest` on its own port and save directory;
  - the plugin file from `adapters/pocketrisu-plugin/dist/` (`0.1.0-beta.14`; Phase 8 does not change
    it);
  - this code's sidecar and worker on a scratch database;
  - the stub chat model (`tools/spike_stub_llm.py`);
  - a deterministic extraction stub: "X는 Y를 배신했다." → a major event with `with: [Y]`, and "X는 Y
    일을 했다." → a minor event;
  - a preset whose chat range keeps the last three messages.
- **Messages:** "하나는 카이토를 배신했다.", three chores by 하나, three filler messages, then
  "카이토야, 오랜만이야.".
- **Packet:** the stub model received this packet (test data only):

```xml
<NarrativeMemory version="0" source="nmos">
  <Note>…</Note>
  <Facts>
    <Fact kind="event" turn="0">하나 event: 카이토를 배신함</Fact>
  </Facts>
</NarrativeMemory>
```

  The event came back from turn 0, far outside the prompt window, by addressing its participant, not
  its subject. The query shares nothing with the fact but the name. No chore came back.
- **Inspector:**
  - the facts table's "함께한 인물" column showed 카이토 on the betrayal;
  - 카이토's page listed it under "참여한 일";
  - the character picker listed 하나 and 카이토.
- **Plugin cost:** 49 and 31 ms in the plugin for the last two generations (the only ones logged). No
  plugin change was needed.

## Upgrade from `v0.1.0-beta.14`

The `v0.1.0-beta.14` code (`23b13a8`, a git worktree) set up a new database (migrations 0001–0016)
and wrote an 11-turn chat with the memory-evaluation stub extractor, extraction backfill 100:

- turn 0: "Hana betrayed Kaito.";
- 8 filler turns;
- turn 9: "Hana betrayed Mina.";
- turn 10: a chore.

Neither "Kaito, long time no see." nor "Mina, long time no see." brought a betrayal back (the last two
messages in context). This code then opened the same database with backfill 4:

- migration 0017 applied (only it);
- 4 extraction jobs queued (the recent window); coverage under `extract-v8`: compiled 0, served by the
  older generation 11, pending 4;
- before any re-extraction: neither betrayal came back (older rows have no participants, Q5);
- the entity id of Hana changed once (`resolve-v1` → `resolve-v2`), as the upgrade notes say;
- after the 4 jobs: "Mina" brought back `Hana event: betrayed Mina` (turn 9, re-extracted with
  participants). "Kaito" still did not (turn 0, still served by `extract-v7`). Mina appeared in the
  Inspector's character picker as a participant-only entity;
- the `extract-v7` assertion rows were unchanged (3 rows, no participants).

The scripts were scratch code (`up_write.py`, `up_check.py`), in the shape of the Phase 7 check.
