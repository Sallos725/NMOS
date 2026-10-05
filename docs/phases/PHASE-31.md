# Phase 31 — Recall that knows what changed: replaced values, ended roles, an item's earlier holder

> **Status: approved 2026-10-05 (the owner: as proposed, Q3 as corrected the same day on the measured anchor), current
> as a correction phase (AGENTS §7 item 5); steps 2–3 done (#264; ADR 0066, D75; replay `docs/perf/phase31-replay.md`); Q1 amended and replayed; the second reduced live gate met every bar (`docs/perf/phase31-live-gate.md`). **Complete; `packet-v12` the default (owner, 2026-10-05).**.** Under AGE-24 and AGE-37 (K43); a correction found by
> measurement, not roadmap Stage 7 or 8. Proposed as a correction phase (AGENTS §7 item 5). It is the "excerpt and
> ranking" work PHASE-28 Q6 left for after the role and name corrections, scoped on the live gate of 2026-10-04/05.
> Extraction is out of scope: `extract-v16` (focused, ADR 0064 item 5) stays as it is.

## Why now

The PHASE-28 live gate on the focused `extract-v16` (`9947d2c`, three runs each) passed everything extraction decides
— the real-chat memory cases 9/10 in every run (`extract-v15`: 8), S4b 3/3 (recovered from 2/3), no false join — and
missed three sets, each for a recall reason the same on `extract-v15` (`e13dee7`):

| Set | Bar (median) | Gate | Failing cases, and where the packet goes wrong |
|---|---|---|---|
| S1, turn 240 | 21/25 | 18, 19, 19 | 02, 03, 05, 06, 19, 24 (as `e13dee7`) |
| S2, full history | 22/25 | 19, 19, 19 | the same six |
| S3 | 6/6 | 5, 5, 5 | `s3_r4_book` (K43) |

Against the historical lane (which passed 02, 03, 05 and the book) the loss is four cases, and the packets show where:

- **A replaced value in an old excerpt (K39 family).** 03 "하람이는 지금 어디 있어?" carries turn 17's "이 여관이 제
  집이에요"; 05 "하람이는 도윤을 뭐라고 불러?" carries turn 21's "도윤 씨라고 불러 주는 대신…". The current fact is in the
  packet each time; the old excerpt is chosen because it holds the question's keywords. Excerpt selection
  (`retrieval.gather`, `packet.grown_excerpt`) never consults fact versions.
- **An ended role in a "now" question.** 02 "도윤 지금 어디 살아?" fails on a fact, not an excerpt: the ended role
  `서도윤 role toward 오봉순: 투숙객: 갈매기 여관 3호실에 묵음` (negated, correctly extracted by `extract-v16`) is printed, and
  "3호실" is a forbidden phrase for a question about where he lives now.
- **An item's earlier holder, and an excerpt that stops short (K43).** "이안이 빌려준 책 제목이 뭐였지?": 『북해 조류 일지』
  moved from 백이안 to 서도윤. A read-only stage diagnosis on the gate's database (`tools/diagnose_k43.py`, from Codex's
  NMO-37 work) found two losses: the current possession scores nothing (백이안's possession survives only in history,
  and the current fact's names do not match "이안"); and the lending message *is* found and placed, but its excerpt
  anchors on a sentence holding "이안이" and stops before the title, which sits in a later sentence holding "백이안이".

06, 19, 21 and 24 also fail but failed on the historical lane too; they are out of scope (Q8).

## Questions and proposed answers

| # | Question | Proposed answer | Alternatives considered |
|---|---|---|---|
| Q1 | What happens to an excerpt that states a value the story has since replaced? | **Under `packet-v12`, it is left out**: an excerpt is dropped when (a) a fact selected for the packet has a superseded version whose value or object the excerpt reuses (the `spans.reuse` measure that already drops excerpts restating withheld lines), (b) the excerpt's turn is earlier than the fact's current version, and (c) the excerpt does not also hold the current value. A question with a history cue (Q4) keeps such excerpts. The freed slot goes to the next candidate, as for any dropped excerpt. *Amended 2026-10-05 on the reduced live gate (owner), then narrowed on the replay: a replaced value is also told by its marks, for the standing facts and places the question names (both of a pair; a place's subject), also when the prompt holds them and the packet leaves them out (S1's and S2's 03, 05, 06). A place's marks are the words of its name (여관, with a particle after it), only when the question asks where (어디); a form of address's are its quoted forms ('서 선생'; not a name alone), only when the question asks what someone is called (부르/불러/호칭); another standing fact's are its quoted forms. A value is mostly a frame ("존댓말, '…'이라고 부름") whose distinctive part is too short for the span share. A fact whose earlier value the question itself names ("왜 여관에서 나왔어?") is not judged, by spans or marks. Prose words are no marks. Measured: marks on every selected fact dropped excerpts holding an old '도윤 씨' from questions about a promise or a key; place words on every question cost the owner's main chat two answers.* | Demote instead of drop (the old excerpt still fills the packet when little else matches); label it `superseded` (the model may still echo it, the old value stays in the packet); trim it to its short form (the old value is often in the anchor sentence). |
| Q2 | What happens to an ended role in a question about now? | **Under `packet-v12`, an ended role is printed only with a history cue (Q4)**, or when no fact about the same pair is current and the question names both people. Otherwise the current facts answer. | Print it as "ended at turn N" without the value (the role's description is the useful part, and the scorer would still see it); leave it (02 keeps failing). |
| Q3 | How does the lent-book question (K43) reach its answer? | *Rewritten 2026-10-05 on the stage diagnosis (`docs/perf/k43-offline-diagnosis.md`, "Result on the gate database"), then corrected on the measured anchor.* **First, the excerpt anchor breaks a tie on the question's one-character words.** The question's keywords are 빌려준, 이안, 제목, 이안이 (`retrieval.keywords` drops one-character words such as 책); three sentences of the lending message hold the name and tie at 2, and the trigram tie-break picks "이안이 고개를 숙이고…", 13 sentences before "백이안이 책 한 권을 건넸다. 표지에는 『북해 조류 일지』…". Under `packet-v12`, a one-character word of the question (any script but a lone Latin letter) is a second key after the keyword count, so 책 picks the lending sentence and the excerpt grows into the title (checked on the gate's message). Retrieval routes are unchanged. The lending message is already found (3rd) and placed; only its anchor missed. **Second, measured after the first and kept only if needed**: the earlier holders in a whereabouts fact's history count as mentions, scored below a direct mention, and the line prints its previous holder ("; before, turn N: 백이안 possesses …") under ADR 0038 amendment 1's knowledge marks. | Earlier holders first (the fact route alone does not say who lent; the diagnosis found the passage route closer); a transfer `event` raised on a lending cue (extractor labels, K22; a cue list); always printing possession history (more K39-style echoes). |
| Q4 | What is a history cue? | **`FIRST_CUE` (ADR 0056) plus "before", "used to", "previously" and their Korean forms (전에, 이전, 예전, 원래 already there)**, kept beside `FIRST_CUE` as `HISTORY_CUE`. The words are few, recorded in the policy, and reported per case in the measurement. *Amended 2026-10-05 on step 3's replay (owner): 첫날 too; `FIRST_CUE` leaves it out with 첫눈, and S2's "첫날 저녁" question lost its answer without it. A cue in a question about now ("오늘이 첫날인데") only gives `packet-v11`'s packet.* | No cue (history questions lose their answers); a model call to classify the question (cost on the request path). |
| Q5 | How does it ship? | **A new packet policy, `packet-v12`, behind `NMOS_PACKET_POLICY`**, `packet-v11` unchanged and still selectable; recorded requests replay as they were (ADR 0027). The default is the owner's decision on the measurement. | A recorded recall option per rule (three options to keep in step). |
| Q6 | How is it measured? | **(a) Deterministic cases** for each rule and its cue exception. **(b) Zero-call replay of the live gate**: every probe request of the 17 runs re-compiled against its preserved database under `packet-v11` and `packet-v12` (`tools/eval_rp.py --policy`, which replays a recorded request as of its time and scores gold and forbidden phrases; a small converter maps each probe to its recorded trace and the gate's gold), no model call; the query embeddings use the gate's embedder (the owner's choice of endpoint, as for the gate) or both policies run `--no-vectors` alike. **(c) The live gate again** after the owner's decision on (b), with the harness pacing fixed. *Amended 2026-10-05 (owner): reduced to S3, S2 and S1 once each, the sets the change is for (AGENTS §7 item 6, a rule for later specs too).* | A live gate first (one night per try); fixed inputs only (no packet context). |
| Q7 | What is the bar? | On (b): S1 turn 240 and S2 full history each at least their historical score (21, 22) in the replayed runs; S3 6/6; every other set no worse by more than one case than `packet-v11` in the same run; forbidden-phrase totals not higher; the history-cue cases (S1 `early`/`first` sets, S0main's history cases) not worse. On (c): the PHASE-28 gate's bars. | — |
| Q8 | What is not in this phase? | Extraction (any prompt or generation change); the cases the historical lane also failed (06 a form of address changed in the excerpt that announces it, 19 a past reason, 21 an early event, 24 an irrelevant question); ranking weights; K22. | — |

## Baseline

The live gate on `9947d2c` (`docs/perf/phase28-live-gate-9947d2c.md`), owner-local evidence
`/home/grantkim725/nmos-eval/age24-v16-9947d2c/` (17 run directories with every probe request, packet text and score,
and their databases `nmos_age24_9947d2c_*` on the test Postgres). `packet-v11`, `excerpt_anchor` "keywords".

## In scope

1. `packet-v12`: Q1–Q4 in `retrieval.gather`, `packet.grown_excerpt`'s anchor, `facts.relevant_facts` and
   `facts.fact_line`; `HISTORY_CUE`.
2. `tools/diagnose_k43.py` (Codex's NMO-37 diagnostic, imported with the probe-replay fix) and its tests; the stage
   diagnosis it gives is the evidence for Q3, and it is rerun on the changed stage after step 2.
3. Deterministic cases; a pin that `packet-v11` compiles every recorded request as before.
4. The replay measurement (Q6 b) and its report; the live gate (Q6 c) after the owner's decision.
5. An ADR (next free number) recording the rules; K39 and K43 updated with the result.

## Out of scope

Q8, and: a migration, a plugin change, a new setting beyond the policy value, any extractor change.

## Steps

1. This document, approved; AGENTS §1/§2 and STATUS name Phase 31.
2. `packet-v12` with deterministic cases and the ADR, behind the policy.
3. The zero-call replay (Q6 b) and its report.
4. The owner's decision on the default; then the live gate (Q6 c).

## Stop conditions

Stop and ask the owner when: a replayed set gets worse by more than one case; a history-cue case loses its answer; a
secret or private line reaches a packet it did not reach before; `packet-v11`'s compiled output changes for any
recorded request; a migration or runtime dependency would be needed.

**Known risk.** Dropping an excerpt because it reuses an old value can drop a legitimate one when the old value is a
common word ("여관"); the reuse threshold and the turn condition (b) bound it, and the replay reports every dropped
excerpt. A question about the past without a cue word ("어디서 지냈었지?") loses the old value; Q4's list is the trade-off.

**High risk (AGENTS §14):** recall semantics that change memory selection (what the packet carries), knowledge marks on
printed history (ADR 0038 amendment 1), replay of recorded requests.
