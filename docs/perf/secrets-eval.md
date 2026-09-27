# Phase 10 evaluation: secrets — evidence

Date: 2026-09-27. Phase 10 step 7 (`docs/phases/PHASE-10.md`). This file collects the phase's acceptance
evidence; the response-model tier is added when it has run (it needs the owner's budget first).

## 1. Deterministic tier (CI)

Seven synthetic cases in the memory evaluation (`apps/sidecar/tests/memeval.py`, table in
`docs/perf/eval-baseline.md`), run in `full` and `full-v0`:

| Case | What it checks | `full` |
|---|---|---|
| a secret in front of the one it is kept from | the Private section, the marks and the rule | yes |
| away is not kept from | someone away is not `hidden_from` | yes |
| a reveal ends it | `hidden_from` drops the character; they now count as knowing it; no Private section | yes |
| an edit restores it | editing the revealing turn brings the secret back | yes |
| strict mode withholds it | a Secret line, no content in facts or excerpts | yes |
| a narrator is not told what they do not know | the narrator's filter and Note | yes |
| a narrator who holds it | the narrator gets their own secret | yes |

Every earlier case still answers, with no stale memory in any mode (42/42 in `full`). `tests/test_secrets.py`,
`tests/test_scene.py`, `tests/test_budget.py` and `tests/test_packet_ledger.py` cover the parts one by one,
including a `packet-v2` trace that still reproduces and a strict request that replays with its own mode.

The cases found two faults, both fixed here:

- **Who found out did not count as knowing it.** A revealed fact kept its extracted `known_by`, so with the
  character who found out in the scene it went to Private (its rule telling them not to act on it), strict
  mode withheld it from them, and as a narrator they were not given it. The read side now adds them to
  `known_by` from the revealing turn on (ADR 0033 amendment 1).
- **A reveal can come before its secret** when turns are extracted together, newest first, as when NMOS first
  sees a chat: the reveal matched nothing. In play turns are extracted one at a time. Known issue K29; the
  two reveal cases extract after every step.

## 2. Extraction tier

`docs/perf/extract-v12.md` (steps 2–3): `gemma4:31b-cloud`, 13 synthetic Korean scenes × 3 runs. Deliberate
secrets 9/9, absence 9/9 (`extract-v11` 8/9), private feelings 6/6, reveals of listed secrets 9/9, controls
6/6: no scene below 2 of 3. On the restored copy of the owner's chat the pilot's revealed secret ends at its
reveal (turn 21, five copies), and the absence noise the pilot saw is gone; one questionable mark and one
missed reveal (turn 52) are listed there.

## 3. Latency

`tools/bench_scale.py 10000` (lexical retrieve after an append), alternately against `v0.1.0-beta.21`:

| Run | retrieve p50 / p95 ms |
|---|---:|
| beta.21, 1 | 10.11 / 308.7 |
| this branch, 1 | 10.65 / 309.3 |
| beta.21, 2 | 9.87 / 314.0 |
| this branch, 2 | 10.53 / 316.5 |

+0.5–0.7 ms p50, within the +5 ms bound. That benchmark has no facts, so it does not reach the scene cast
(1.77 ms over 15,000 facts, `docs/perf/packet-v3.md`) or the budget search (about 1 ms when memory was left
out, `docs/perf/budget.md`).

## 4. Real host (isolated PocketRisu v1.12.0, stub models; step 8)

The plugin of `main` (build `84f4a7f48891`) against the sidecar of `main`:

- A secret kept from a character, with that character named in the user's message: the packet the model
  received (the stub's log) had the `<Private>` section with both facts kept from them, their `known_by` and
  `hidden_from`; the trace recorded the cast of three, `packet-v4` and the default budget 800 (the budget
  argument empty).
- The memory mode set on the Inspector's chat page reached the sidecar and the next trace (step 5,
  `docs/perf/memory-mode.md` §4); the budget notice and its button (`docs/perf/budget.md` §4).
- The Inspector's first page: "플러그인: 사이드카와 같은 빌드 84f4a7f48891 (지금)"; the Status tab: "사이드카와 같음".

## 5. Upgrade (step 8)

`tests/test_upgrade.py` now also restores a database written by `v0.1.0-beta.21` (recorded with
`tools/make_upgrade_fixture.py`), besides beta.7 and beta.16. Each upgrades (migrations to 0021), keeps
working through an append, a recall that replays as recorded and an edit; its recorded packets replay without
error under their own policy; an upgraded chat has the default memory mode and takes another; a recall
reports what the budget left out.

## 6. Response-model tier (the owner's runs, 2026-09-27)

The pilot's scenes (`docs/perf/stage4-leak-pilot.md`), rebuilt with `tools/eval_secrets.py` from the restored copy
with `extract-v12` facts and an 800-token budget. The requests are the pilot's own (Opus: the host's logged
requests; Gemini: host-rendered 누렁이Gemini prompts), with only the packet replaced. C2: the mother asks what the
daughter and the user whispered about (the plan to watch her lecture, kept from her). D1: the user asks the
daughter to go and hug her mother (a promise to hug her, kept from her). In both requests the promise's turn (9)
is older than the transcript the host sent (Opus: turns 46–52; Gemini: turns 30–52), so only the packet holds it. The owner ran every call with their own keys; one reader judged the
replies by the pilot's definitions (a leak is words or actions that tell a character it is kept from; omniscient
narration of thoughts is not; a holder's own slip is reported apart, Q4).

Leak / slip or near miss / the holder shows they remember it, per scene and condition:

| Model, scene | `packet-v2` | `packet-v4` (default) | `packet-v4` strict |
|---|---|---|---|
| Opus 5.5, C2 ×3 | 0 / 1 / 3 | 0 / 2 / 3 | 0 / 0 / 3 |
| Opus 5.5, D1 ×3 | 0 / 2 / 2 | 0 / 2 / 3 | 0 / 0 / **0** |
| Gemini 3.1 Pro, C2 third person ×3 | 0 / 0 / 1 | 0 / 1 / 2 | 0 / 1 / 1 |
| Gemini 3.1 Pro, D1 third person ×3 | 0 / 0 / 1 | 0 / 0 / **0** | 0 / 0 / 0 |
| Gemini 3.1 Pro, D1 user first person ×3 | — | 0 / 0 / 1 | — |

- **No leak in 39 replies**, in any condition. The pilot's `packet-v2` had one Opus leak in D1 (3 runs) when the
  promise had no `hidden_from`; `extract-v12` now marks it, and neither `packet-v2` nor `packet-v4` leaked.
- **Slips are the daughter's**: in D1 she tells the user, loudly in the hallway, that this is their plan; in C2 she
  starts to say the lecture's day or that "it's a secret" and stops. None was the content told to the mother.
  Under `packet-v4` Opus slipped about as often as under `packet-v2` (4 and 3 of 6).
- **Opus remembers under `packet-v4`**: 6 of 6, as the pilot's best condition (A′, 3 of 3 in D1).
- **Strict mode forgets what only the packet held**: Opus D1 0 of 3, as the pilot's B′. C2's plan is in the
  host's own transcript, so the holders recall it anyway (3 of 3).
- **Gemini narrated the holder's memory less than in the pilot**: D1 third person 1 of 3 under `packet-v2` and 0
  of 3 under `packet-v4`, where the pilot saw 2 of 2 under both of its packets; C2 1 and 2 of 3 (pilot 2 of 2).
- **Why, in D1: the promise was not in the packet.** The pilot's packet had it as a promise line ("…, let's hug
  her tight"). With `extract-v12` the girl has more open promises (one extracted in both directions), the three
  newest filled the thread limit, and the packet held only a long conditional goal fact about the hug. Opus
  recalled from that fact; Gemini did not. Under `packet-v4` the promise the user's message is about now comes
  first (ADR 0019 amendment 1), and the rebuilt D1 packet holds it in the Private section; C2's packets are
  unchanged. D1 under `packet-v4` is to be run again.
- Not run: Gemini D1 first person with the narrator mode (3 calls): the token cap was reached first, the D1
  prompts being 158,600 tokens instead of the 125,000 estimated.

An earlier reading of this run blamed the eval tool (the request's own turn, extracted later with its reply,
seemed to close the promise); the promise was open, and the tool's rebuild now stops at the message before the
request anyway, which changed none of these packets.

Cost: Opus 5.5, 18 calls, $3.04 as reported by the gateway (repeat calls cached). Gemini 3.1 Pro (Vertex, global),
21 calls, 3,028,863 prompt and 49,206 output tokens.
