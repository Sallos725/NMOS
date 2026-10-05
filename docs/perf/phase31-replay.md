# Phase 31 step 3: `packet-v12` replayed on the PHASE-28 gate (2026-10-05)

**Result: every replay bar of PHASE-31 Q7 (b) met, with 첫날 added to the history cue (owner, 2026-10-05).** As
first specified (without 첫날), S2's full-history median was 21 (bar 22) and one history question lost its answer.
Zero model calls; the live gate (Q6 c) is next, reduced to S1, S2 and S3 once each (owner).

**High risk:** recall semantics (what the packet carries); `packet-v11` unchanged and still the default.

## Method

Every probe of the 17 runs of the PHASE-28 live gate on `9947d2c` (`phase28-live-gate-9947d2c.md`) is compiled
again from its run's database with `audit.replay`: the facts, summaries and vectors as of the request. The gate's
harness deleted each probe message after asking, so a replay passes the probe as `query`; with the message gone, the
lexical route ranks the story without it, and about a third of the replays differ from the captured packet in an
excerpt or two (the trace each probe came from is the one whose `packet-v11` replay is closest to the captured
packet). Each case is therefore compared within the replay: `packet-v11`, `packet-v12` as specified, and
`packet-v12` with 첫날 as a history cue, three replays each, the majority deciding (the lexical route did not return
the same candidates on every replay of one request; reported separately). The query embedding is the gate's model
(`qwen3-embedding:8b`, the same digest) on the evaluation Ollama; vectors ran on every replay. Scored as the gate
scores (`tools/eval_rp.py` `score`, gold present and forbidden phrases placed, the captured window as the prompt).
S0main and S0s2 are the owner's real chats: aggregates only.

## Results

Cases passed per run (three runs each unless noted).

| Set | Bar (Q7 b) | Gate | `packet-v11` replay | `packet-v12` as specified | `packet-v12` with 첫날 | |
|---|---|---|---|---|---|---|
| S1, turn 240 | median ≥ 21/25 | 18, 19, 19 | 19, 20, 20 | 21, 22, 22 | 21, 22, 22 | met |
| S2, full history | median ≥ 22/25 | 19, 19, 19 | 20, 20, 20 | 21, 22, 21 | 22, 22, 22 | met with 첫날 |
| S2, default window | no worse than v11 − 1 | 20, 20, 19 | 21, 21, 20 | 22, 22, 20 | 22, 22, 21 | met |
| S3 | 6/6 | 5, 5, 5 | 5, 5, 5 | 6, 6, 6 | 6, 6, 6 | met |
| S1, turn 120 | no worse than v11 − 1 | 22, 21, 23 | 22, 21, 23 | 21, 20, 22 | 21, 20, 22 | met (−1) |
| S1, turns 30 and 60 | no worse than v11 − 1 | 25 each | 25 each | 25 each | 25 each | met |
| S5 branch and new chat | no worse than v11 − 1 | 6 each | 6 each | 6 each | 6 each | met |
| S4 (one run) | no worse than v11 − 1 | 3 | 3 | 3 | 3 | met |
| S4b | no worse than v11 − 1 | 3, 3, 3 | 3, 3, 3 | 3, 3, 3 | 3, 3, 3 | met |
| S0main, memory cases (default and all) | no worse than v11 − 1 | 38 each | 38, 37, 38 | = v11 | = v11 | met |
| S0s2 | no worse than v11 − 1 | 15 | 15 | 15 | 15 | met |

Forbidden phrases placed, per run: S1 turn 240 5 → 2 and S2 full history 5 → 2 (v11 replay → v12), S2 default
3 → 2, S1 turn 120 3 → 4; S0main unchanged (1). Total lower in every run. History-cue cases (S1 `early` and `past`,
S0main's): no case worse with 첫날; without it S2's `c240_20_early` ("…윤슬포 첫날 저녁에 먹은 게…") lost its
answer in two or three runs, its excerpt left out as stating the replaced residence.

**What changed, case by case** (every run unless noted): `s3_r4_book` (K43) passes, the excerpt anchoring on the
lending sentence; `c240_02_location` passes, the ended role `투숙객: 갈매기 여관 3호실` no longer printed for "지금";
`c240_08_state` passes, an excerpt of a replaced state left out. One loss: `c120_24_irrelevant` ("따뜻한 차 하나
추천해 줘"), a trap question, now places a forbidden phrase: the one-character word 차 moves its excerpt's anchor to
the sentence with 보리차 (Q3 as designed). S1 turn 240's 03, 05, 06, 19, 21 and 24 still fail (03 and 05 not
diagnosed here; 06, 19, 21 and 24 failed historically too).

## Q1 amended, after the reduced live gate (2026-10-05)

The reduced live gate (`phase31-live-gate.md`) missed S1 turn 240 and S2 full history on 03, 05 and 06, an older
excerpt of a replaced residence or form of address that the span share does not tell. The owner approved telling it by
marks; the rules were narrowed twice on this replay (see PHASE-31 Q1's amendment). Same method, three replays each,
now over the 17 gate databases, the three live databases, and the Phase 27 sets (M0 main and sample 2, the synthetic
cuts; vectors on). "Spans only" is `packet-v12` without the marks; "amended" is the committed rule.

| Set | Bar | `packet-v11` replay | `packet-v12`, spans only | `packet-v12` amended | |
|---|---|---|---|---|---|
| S1, turn 240 (gate DBs) | median ≥ 21 | 19, 20, 20 | 21, 22, 22 | 22, 23, 23 | met |
| S1, turn 240 (live DB) | — | 20 | 22 | 23 | |
| S2, full history (gate DBs) | median ≥ 22 | 20, 20, 20 | 22, 22, 22 | 23, 23, 23 | met |
| S2, full history (live DB) | — | 20 | 22 | 23 | |
| S3 (gate DBs and live DB) | 6/6 | 5 | 6 | 6 | met |
| S1, turn 120 (gate DBs) | v11 − 1 | 22, 21, 23 | 21, 20, 22 | 23, 22, 24 | met |
| S2 default, S4, S4b, S5, S0s2 | v11 − 1 | — | = v11 or better | = v11 or better | met |
| S0main memory cases | v11 − 1 | 38, 37, 38 | = v11 | = v11 | met |
| M0 main (Phase 27 set, 40) | v11 − 1 | 34, 34, 34 | 33, 34, 34 | 34, 34, 34 | met |
| M0 sample 2 (15) | v11 − 1 | 9, 10, 8 | 9, 9, 10 | 10, 10, 9 | met |
| Synthetic cuts 30 / 60 / 120 / 240 | v11 − 1 | 21 / 17 / 13 / 13 | 21 / 17 / 13 / 14 | 21 / 17 / 14 / 14 | met |

Forbidden phrases placed per run, v11 → amended: S1 turn 240 5 → 1, S2 full history 5 → 1, S1 turn 120 3 → 1; the
synthetic cuts 57 → 51 over three runs; M0 unchanged or lower.

**The two narrowings.** With marks on every selected fact and a place's words on every question, M0 main lost two
answers in every run (34 → 32): its characters move between many rooms, and questions about what happened in a kitchen
lost the excerpts naming it; and in the synthetic stories an old '도윤 씨' or '추 영감님' in the dialogue dropped
excerpts from questions about a promise, a key, a birthday or a relationship (no case failed, the answers sat
elsewhere). Marks now judge only the facts the question names, a place's words only for a "where" question, a quoted
form of address only for a "what is … called" question. Separately, "도윤은 왜 여관에서 나왔어?" (synthetic cut 120)
lost its answer by spans: a fact whose old value the question names is no longer judged.

**What the marks drop now.** Reviewed in full on S1, S2 and S3 (synthetic): every dropped excerpt is on a "where" or
"what is … called" question and states an earlier residence or place (다락방, 여관 방, 별빛빵집) or an earlier form
of address ('도윤 씨', '하람 씨', '이안 씨'). S0main: 22 excerpts over 12 cases, scores unchanged (not listed).

## After the Copilot review of #264 (2026-10-05)

Under `packet-v12` a dropped excerpt's slot is now filled by the next candidate (Q1 as specified; before, the
candidates were cut to `top_k` first), ended roles leave the ranked facts before the limit, and no placed form of a kept
excerpt says only an old value. Replayed the same way: S1 turn 240 22, 23, 22 (bar 21); S2 full history 23, 23, 22
(bar 22); S3 6/6; the live run's databases 23 and 23; M0 main 34 = v11; every other set unchanged. One case changed in
two runs: `c240_02_location` now places 3호실 from a refilled excerpt (turn 86, packing in the old room) that no
selected fact's history names by that word (the old place is recorded as 갈매기 여관) — K39's remaining case.

## Not measured here

Generated answers (the gate scores packets); latency (a replay is not a timing test); a chat whose question about
now says 첫날 (it then gets `packet-v11`'s packet). The lexical route's run-to-run difference is a separate finding.

## Evidence

Owner-local: the replay script and per-case JSON (case names, scores, trace ids) in the session scratchpad and
`/home/grantkim725/nmos-eval/age24-v16-9947d2c/`; databases `nmos_age24_9947d2c_*` on the test Postgres, read only.
