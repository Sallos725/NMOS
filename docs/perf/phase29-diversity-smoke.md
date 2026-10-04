# New scenarios through the worker on 9aa7c57 (2026-10-04)

**12 of 13 pass the expectations fixed before the run; the 13th (R04) fails by a naming error in those
expectations, and passes when regraded with the names the scenario writes.** Thirteen independent synthetic
scenarios that no earlier measurement used ran through the real extraction worker at `9aa7c57`
(`extract-b88669ca66664b77df6ac117d741ea8e`): role endings (R01–R04), names (I01–I04), English (E01–E04) and an alias
with a secret (K01). No wrong role ending, no false join. This is a smoke check of short scenes, not the 1,440-call
comparison or a live gate.

**High risk:** identity and provenance, current/historical role state, extraction generations.

## Inputs and method

- Pack: the owner's `~/nmos-bench/NMO-24-diversity-2026-10-03` (authored 2026-10-03, synthetic, never run before;
  its SHA256SUMS hashed in the run's PLAN). Each scenario is three user/character turns; the persona is 이도현 (Korean)
  or Alex Rowan (English).
- Live lane: each scenario in a fresh database, turns synced one at a time as a user chatting would, so each turn is
  extracted in story order; a short closing user message makes the last turn eligible (a turn is extracted once the
  user continues). First connection (the whole chat at once, newest turn first) was not measured.
- Expectations were written from the scenario texts and `oracle.json` before any call and hashed: per scenario, which
  roles are current or ended after the last turn (matched by the two people and a keyword of the role) and which name
  pairs must or must not be one entity. The pack's questions were not asked; this checks the stored state.
- Envelope: main `max_tokens` 8,192, confirmations 512, at most 120 calls, no retries; owner-approved.

## Results

| Scenario | What it checks | Result |
|---|---|---|
| R01 | an interpreting delegation ends; the friendship stays | ended, confirmation yes: pass |
| R02 | leaving to do the delegated task is not an ending | kept: pass |
| R03 | a dismissal read in a role-play drill is not real | kept: pass |
| R04 | two independent delegations, one revoked | **fail as graded** (see below); product: the revoked one ended (yes), the other's reverse doubt answered no and dropped, so it stayed |
| I01 | full and given name, a change of address | 오서린 = 서린 (alias confirmation yes): pass |
| I02 | two people with the same given name | 윤태민 and 박태민 apart: pass |
| I03 | a separate visitor named 서린 is not 오서린 | apart: pass (NAME PAIRS listed the pair in two turns; the model did not confirm it) |
| I04 | a real nickname joins, a stage role name does not | 오서린 = 달새 (yes); 세린 apart: pass |
| E01 | English full and first name | Nora Keene = Nora (yes): pass |
| E02 | leaving the room is not leaving the job | kept: pass |
| E03 | a resignation without the old title; friendship continues | both directions ended (yes, yes): pass |
| E04 | two people sharing a first name | Nora Keene and Nora Vale apart (each joined to its own surname only): pass |
| K01 | a call sign is a real alias | 최해온 = 해온 (NAME PAIRS), = 파도 (yes): pass |

**R04.** The frozen expectation named both roles by the full names 정유라 and 서은재, which R04 never writes (it writes
유라 and 은재 only), so the grader found no role for those names and reported "not extracted". The stored state is
correct: 유라 → 은재 (book delegation) ended after a confirmation yes, and 은재 → 유라 (mail delegation), asked as the
reverse of that ending, was answered no ("유라가 은재에게 맡긴 우편물 수령 위임은 그대로 유지됐다.") and stayed current. A
read-only regrade with the names R04 writes passes both checks (`r04-posthoc-regrade.json`). The recorded verdict
stays a fail of the frozen expectations; the regrade is post hoc.

Sixteen confirmations in all: 11 alias confirmations, all yes (each a true alias by review), and 5 role confirmations,
yes for the four real endings and no for R04's reverse doubt. No alias was held, so this run does not exercise a held
alias. Two odd but harmless rows: an item alias (`Alder-84 → locker label`, E01) and an alias held as not stated in its
turn (R01 `임건우 → 건우`).

## Cost and time

55 calls (39 main, 16 confirmation); input 268,328 (cached 223,616), output 28,348; **$0.04890512** at $0.14 / $0.40
per million, uncached. No technical error, retry or truncated reply.

## Evidence and limits

Owner-local: `/home/grantkim725/nmos-eval/pr251/2026-10-04/diversity-9aa7c57/` — `PLAN.json` (`46dffa31…`),
`expectations.json` (`05b6533d…`), `run_diversity.py` (`ae4f95be…`), every request, HTTP body and final state per
scenario under `results/`, `summary.json` (`e952b0b2…`), `r04-posthoc-regrade.json` (`063ee5d1…`); databases
`div9_*` on the bench Postgres.

One run each of three-turn scenes written to test these features, by a model session (not the owner's chats). The
expectations were written by the implementer; R04 shows they can be wrong. Not measured: first connection, longer
chats (the pack's 120-turn variants), the pack's questions against packets, M and T groups.

## R01, the 120-turn variant (owner-approved, the same day)

The pack's long R01 (the delegation at turn 0, its ending at turn 32, dinner as friends at turn 64, everyday filler
elsewhere) through the worker on `9aa7c57`, live lane: **pass**. The interpreting role is current at turn 31 after 31
filler turns (a prefix read), ended at turn 32 after a confirmation yes, and stays ended to turn 119; 임건우 and 정유라
stay apart; the friendship rows stay. No other role ending in 117 filler turns. 122 calls (120 main, 2 confirmation),
input 876,796 (cached 692,224), output 31,203, **$0.13523264**, about 2.5 minutes; no technical error. Evidence:
`/home/grantkim725/nmos-eval/pr251/2026-10-04/long-r01-9aa7c57/` (`expectations.json` fixed before the run, including
the turn-31 check).
