# Phase 21 — "At first": how it started, when the message asks

> **Status: approved (2026-10-01) with every proposed answer (Q1–Q6); current.** The owner asked that a model call
> classifying the message (Q1's alternative) be reviewed later, outside this phase. Not a roadmap stage: a correction found by measurement
> (a local benchmark of the owner's chats, 2026-09-30/10-01), tracked as AGE-26 under AGE-24. The other findings of
> AGE-24 are separate: AGE-25 (a re-extraction loses facts it had), AGE-27 (role relationships extracted as places),
> AGE-28 (a given name without the family name).

## Questions and proposed answers

| # | Question | Proposed answer | Alternatives |
|---|---|---|---|
| Q1 | What makes a message ask how it started? | **A first cue in the message:** 처음, 맨 처음, 최초, 예전, 옛날, 원래, 초반, "첫" followed by a space, 번 or 째 (첫 만남, 첫번째, 첫째; not 첫눈), and in English "at first", "first time", "originally", "in the beginning". Read from the message only, like the "why" cue (packet-v6, ADR 0040). | A model call that classifies the message (a call on the request path; the owner asked for it to be reviewed later, outside this phase). |
| Q2 | What changes when it is there? | **Two things, only for that request.** (a) **Events:** the event cap orders the events mentioned first (whether, not how strongly; clarified in step 2, ADR 0056) and then by turn, **oldest first, before salience and score** (today: mention, `major`, score, newest); so an old `minor` event of a mentioned character comes before a newer `major` one. A `minor` event no longer needs the lexical bar (ADR 0020) to stay a candidate. Among other facts, equal scores go to the older one (today: the newer). (b) **History in the window:** a standing fact (`relationship`, `feels_toward`, `addresses`) whose current version's source is in the chat window stays a candidate **only when one of its earlier versions starts before the window** (its position is lower than the window's first message): the packet prints those versions (ADR 0038) and the window does not hold them. When every version is in the window, the fact stays out as today. | Only (a); only (b) (the measurement below needs both). |
| Q3 | "마지막에 / 최근에" (how it is now)? | **No change.** Ties already go to the newest, and the current version is what the packet prints first. | A last cue that drops earlier versions. |
| Q4 | How do recorded requests replay? | **A recall option `first_cue` recorded in the trace, on for new requests; a trace without it replays with it off** (as `lexical_keywords`, Phase 18). The packet policy stays `packet-v10`. | A new packet policy `packet-v11`. |
| Q5 | Does the packet grow? | **No budget change.** The candidates differ; the fitter and the budget are as today. Measured: the median packet changes by less than 1 % on every set (−0.8 % to +0.0 %). | — |
| Q6 | How is it measured? | **Replays only, no model call:** the owner's M0 main chat (the cases that need memory); two restored copies of production (`extract-v13`, `extract-v14`) with probes generated from their own narrated facts and the window cut to the last 20 messages (a 32k user); the synthetic 240-turn chat's 25 cases at the last cut and 15 new first-cue cases; deterministic cases for Q1–Q4. | The M0 cases only (one chat). |

## Goal

"처음에 뭐라고 불렀지?", "처음에 둘이 같이 만든 게 뭐였지?": the answer is the oldest of several similar things, and
today's ranking hands the slots to the newest. After this phase a message that asks how it started gets the start.

## Evidence behind the scope

Measured with read-only replays of recorded requests (vectors off for every variant, so only fact selection differs;
counts only). Today's code against Q2:

| Set | Today | Q2 |
|---|---|---|
| Owner's M0 main chat, cases that need memory | 6/10 | **7/10** |
| Restored production copy (`extract-v14`), generated first-cue probes, 20-message window | 6/8 | **8/8** |
| Restored production copy (`extract-v13`), same | 5/5 | 5/5 |
| Synthetic 240-turn chat, 15 first-cue cases (packet only) | 4/15 | 5/15 |
| Synthetic chat, its 25 cases at the 240 cut; the same 25 after a first connection | 23/25, 24/25 | 23/25, 24/25 |

- The M0 case failed because two `minor` events of the first turns did not pass the lexical bar and later, `major`
  events of the same character took the event slots; the copies' cases failed because a pair's current form of address
  was in the window, so the fact and its first version were left out.
- Measured with Q2 (b) as written (an earlier version before the window); the looser rule (any history) gave the
  same counts on every set.
- Each half of Q2 alone fixes only its own cases (ablation): without (a) the M0 case fails again; without (b) the
  `extract-v14` copy stays at 6/8.
- Most of the synthetic set's remaining misses are a given name used without the family name (AGE-28), outside this phase.
- A who-is-this question ("X는 무슨 일을 해?") was also tested with a ranking bonus for `identity`: no change on any set,
  and the copies' generated who-probes already pass today (7/7, 4/4). Not in scope.

## In scope (Phase 21)

1. **The cue (Q1)** and the two changes (Q2) in fact selection, behind the recorded option (Q4).
2. **Deterministic cases:** the cue's words and non-words (첫눈 is not a cue); with the cue an old `minor` event of
   a mentioned character before a newer `major` one, and without it the reverse (today); a `minor` event below the
   lexical bar kept with the cue only; a standing fact whose current source is in the window kept when an earlier
   version starts before the window, and left out when every version is in the window; a trace without `first_cue`
   replaying unchanged.
3. **Evaluation (Q6)** and docs: an ADR, `ARCHITECTURE.md` (a decision), CHANGELOG, `docs/perf/first-cue.md`.

## Out of scope (Phase 21)

- AGE-25 (re-extraction), AGE-27 (extraction of role relationships), AGE-28 (given names, romanized lorebook names).
- A model call on the request path; packet budget or fill changes; a "last" cue (Q3).

## Acceptance criteria

- [ ] Every existing test and memory-evaluation case passes; recorded `packet-v10` requests without `first_cue`
      replay as they were.
- [ ] The deterministic cases of In scope 2.
- [ ] Q6's sets: M0 main cases that need memory at least +1; each restored copy's first-cue probes at least as many as
      today; the synthetic 25-case sets no worse than today; no new forbidden phrase placed on any set.
- [ ] Request-path latency unchanged within noise (the cue is a regular expression on the message).

## Steps (one pull request each)

1. This document, approved; AGENTS §2 and STATUS name Phase 21 current.
2. The cue, the selection changes, the recorded option, the deterministic cases (ADR 0056).
3. The evaluation and docs; Phase 21 complete.

Every merge reaches the owner's `:edge`; no tag (AGENTS.md §13).

## Stop conditions

Stop and ask the owner when:

- a recorded request without `first_cue` replays differently;
- any Q6 set gets worse, or a forbidden phrase appears that did not before;
- the cue needs more than the message (a model call, the chat's language detection).
