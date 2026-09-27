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

## 6. Response-model tier (pending the owner's runs)

`tools/eval_secrets.py` takes a case directory outside the repository (the owner's real requests, the
secrets to watch), compiles each request's packet again per condition (a policy, strict mode or a narrator),
sends each to an OpenAI-compatible endpoint or to Gemini on Vertex AI with hard limits on calls, reported
spend and prompt tokens, and reports numbers only: replies, watched secrets echoed, and the reviewer's labels
(leak, slip, recall, kept). Checked without paid calls: packets rebuilt for the pilot's turn-52 scene on the
restored copy (`packet-v2`, `packet-v4`, strict), a Gemini request body's packet replaced, and two calls to a
local model that stopped at the call limit.
