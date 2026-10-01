# "At first": how it started, when the message asks (Phase 21)

`docs/phases/PHASE-21.md`, ADR 0056, ADR 0038 amendment 1 (K42). Numbers only: the cases stay outside the repository
(the owner's chats are private; the synthetic set is not published yet).

## Setup

- **Replays only, no model call** (Q6): recorded requests compiled again with `audit.replay` (read-only), the probe in
  place of the request's message, packet policy `packet-v10` at 4,000 tokens, **vectors off for every variant** so only
  fact selection differs. `first_cue` off is today's ranking, on is ADR 0056; `history_marks` (ADR 0038 amendment 1)
  on in both. An offline harness outside the repository scores each packet with `tools/eval_rp.py`'s scorer.
- **M0 main**: the owner's M0 main chat on a copy of the 2026-09-30 bench database (`gemma4:31b` extraction,
  `extract-v13`), its 40 cases scored against the packet and the recorded chat window; "needs memory" are the 10 whose
  answer the window does not hold.
- **Restored production copies** (`extract-v13`, and the same copy re-extracted with `extract-v14`): for every chat,
  its latest recorded request with the chat window cut to the last 20 messages (a 32k-token user), and probes generated
  from the chat's own narrated facts whose answer is outside that window — "처음에 A는 B를 뭐라고 불렀지?" / "A랑 B는
  처음에 어떤 사이였지?" (gold: the first version) and "A는 무슨 일을 하는 사람이야?" (gold: the current identity).
  Scored on the packet alone.
- **Synthetic chat** (240 turns, Korean): its 25 cases at the 240 cut and the same 25 after a first connection (scored
  with the window), and 15 new first-cue cases at the 240 cut (first forms of address, a first job, a first
  relationship, money at arrival; scored on the packet alone, since the old values recur later in other senses).

## Results (2026-10-01)

| Set | `first_cue` off | on |
|---|---:|---:|
| M0 main, cases that need memory | 6/10 | **7/10** |
| M0 main, all cases | 35/40 | 36/40 |
| Restored copy `extract-v14`, first-cue probes | 6/8 | **7/8** |
| Restored copy `extract-v13`, first-cue probes | 5/5 | 5/5 |
| Restored copies, who-probes (`v13`, `v14`) | 7/7, 4/4 | 7/7, 4/4 |
| Synthetic, 15 first-cue cases | 4/15 | 5/15 |
| Synthetic, 25 cases at the 240 cut / after a first connection | 23/25, 24/25 | 23/25, 24/25 |
| Forbidden phrases placed (M0 main, synthetic ×2, synthetic first-cue) | 1, 0, 0, 1 | 1, 0, 0, 1 |

Packet size (mean characters, or the probes' median on the copies) changes by −0.9 % to +1.3 % per set; the budget and
the fitter are unchanged (Q5). The `extract-v14` copy's +1.3 % is the earlier versions its standing facts now print.

Every acceptance criterion of `PHASE-21.md` is met: M0 main +1 (at least +1), each copy at least as many as today,
the synthetic 25-case sets unchanged, no new forbidden phrase; the deterministic cases in `test_first_cue.py` and
`test_history_marks.py`; recorded requests without `first_cue` or `history_marks` replay as they were.

## What the measurement changed on the way

- **Events mentioned first by whether, not by the mention's score.** The spec's draft harness ordered events by
  whether they were mentioned; the first implementation used the mention's score, which also carries a secret's bonus
  and the persona's first-person bonus: M0 main stayed at 6/10. Ordered by whether, it passes (ADR 0056 item 2).
- **A canon version the prompt holds does not bring a fact back.** Canon statements have positions below every turn,
  so they always looked older than the window (Copilot on #221). Only a canon version whose key the prompt did not
  hold counts now. The draft's 8/8 on the `extract-v14` copy counted one probe whose first version is the persona card,
  held in that request's prompt: 7/8, and the model has that answer in its prompt.
- **K42.** The same review found that earlier versions were printed under the current version's knowledge marks since
  `packet-v5`; on M0 main a feeling whose three earlier versions only one character knew was printed under its public
  line in every packet. Fixed at the owner's request (ADR 0038 amendment 1): no case of any set changes, every M0 main
  packet names one version fewer.

## Ablation (spec draft, the same sets)

Each half of Q2 fixes only its own cases: without (a) — events oldest first, `minor` without the lexical bar — the
M0 main case fails again; without (b) — history the window does not hold — the `extract-v14` copy stays at 6/8. The
synthetic first-cue set's remaining misses are mostly a given name used without the family name (AGE-28).

## Latency (`tools/bench_story.py`, 10,000 messages)

Retrieve p50 and p95, the median of five rounds, each round running main before step 2 and this branch, without and
with the cue (`BENCH_FIRST=1`: every question starts with "처음에"), in turn; budget 4,000, pinned to two cores.

| | before Phase 21, p50 / p95 | Phase 21 and K42, p50 / p95 | p50 difference |
|---|---:|---:|---:|
| Questions of the bench (one of eight has a cue) | 131.6 / 211.0 ms | 133.5 / 220.8 ms | +1.9 ms |
| Every question with the cue | 142.3 / 196.7 ms | 143.5 / 201.7 ms | +1.2 ms |

The rounds spread by ±5–10 ms; neither difference is measurable. The cue's read of the window's lowest position is one
indexed statement. "처음에" in front of every question costs ≈10 ms on both sides: the longer message's lexical recall,
not the cue.
