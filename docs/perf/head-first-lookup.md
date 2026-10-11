# A short head looked up by its own revisions (ADR 0052 amendment 1)

Date: 2026-10-11. Base: PHASE-41 amendment 2 (`30acd4a`) on `main` `6b6cbb2`. All measurements ran read-only on a
private restored copy of the trial install's database, on the existing gate copies, or on throwaway databases in a
private PostgreSQL container. No provider calls; no writes to the trial install. Private chat text stays outside the
repository.

## The problem

The whole-message lexical route and every keyword lookup (`_MATCHES`) take trigram-index candidates from all chats'
revisions, recheck them, and keep the head's afterwards. On data with long messages that recheck dominates: the trial
install's copy holds 634 revisions, but one chat's old revisions reach 695,000 characters. A short chat's keyword then
ran past its 25 ms slice and was dropped as if too common, and its whole-message route took ~145 ms.

## Choosing when to look up by the head

Restricting the lookup to the head's revision ids gives the same rows (by construction: the head filters after the
lookup are unchanged; checked on all 521 recorded live keywords and 120 words on a 10,000-message chat, zero
mismatches). Left to the planner, the restricted statement sometimes still took the trigram index (statistics-dependent)
and rechecked a 10,000-message chat for a 41-message one, so the head's revisions are read first behind an `OFFSET 0`
fence. Its cost then follows the head's characters. Every recorded live keyword, both ways, best of two:

| Head characters | Lookups | Index-first over 25 ms | Head-first over 25 ms | Head-first max |
|---|---:|---:|---:|---:|
| under 50,000 | 185 | 44 | 0 | 12.7 ms |
| 50,000–100,000 | 60 | 28 | 0 | 22.3 ms |
| 100,000–200,000 | 68 | 21 | 49 | 42.0 ms |
| 200,000–400,000 | 104 | 27 | 104 | 79.2 ms |
| over 400,000 | 104 | 27 | 104 | 114.4 ms |

A head of at most 100,000 characters and 500 messages is looked up by its revisions; larger heads keep the
index-first lookup. On a 10,000-message chat the id list alone costs ~21 ms a statement, hence the message cap.
The particle supplement stays index-first: restricted, its boundary pattern rechecked every head revision, ran out the
word's slice, and on the gate lost the supplemented answer of both `m12-butcher` probes.

## Live requests (option on, three alternating rounds, vectors off)

| Route | Before (`main`) | After (amendments 2 and 3) |
|---|---:|---:|
| Keyword p50 / p95 | 89.5 / 155.1 ms | 59.4 / 145.8 ms |
| Whole-message lexical p50 / p95 | 141.3 / 227.2 ms | 27.5 / 191.0 ms |
| Keyword candidates found (99 replays) | 231 | 285 |

Majority packet text is identical for 31 of 33 requests;
the other two vary across rounds in both lanes (a keyword at the edge of its slice). Repeated eight times twice per
lane, those two degraded in 8 of 32 replays on `main` and 3 of 32 after the change.

## A 10,000-message chat and a short chat in one database

Synthetic `bench_scale` corpus plus a 41-message chat, in-process API, 10 queries per chat, three alternating rounds:

| Chat | Lane | API p50 / p95 | Whole-message timeouts | Keyword all cut |
|---|---|---:|---:|---:|
| 10,000 messages | before | 18.9 / 358.9 ms | 3/30 | 18/30 |
| 10,000 messages | after | 19.5 / 360.4 ms | 3/30 | 18/30 |
| 41 messages | before | 31.5 / 417.9 ms | 6/30 | 9/30 |
| 41 messages | after | 33.6 / 116.9 ms | 0/30 | 4/30 |

Packet text is identical for all 60 pairs. The 10,000-message chat keeps the index-first lookup (one id query added).

## Historical gate

Cached query vectors, 338 probes, three alternating rounds per lane, the recorded particle option on in both lanes,
zero embedding calls (the gate copies hold one chat each, so the change can only skip non-head revisions there):

- First candidate (particle supplement also restricted): 310, 308 and 310 of 338 against `main`'s 312 in every round.
  Both `m12-butcher` probes failed in all rounds: the restricted particle query ran out its slice and the answer's
  supplemented candidates (16 keyword candidates, 13 restricted) were lost. The supplement went back to index-first.
- Second candidate (restricted only by message count): 312/338 in every round, majority text identical for 338/338,
  but the live replay showed a chat of long messages losing a rare keyword to its slice; the character limit and the
  fence followed.
- Final, head-first alone against `main`: 312/338 in every round of both lanes; no probe changed its majority result
  or placed a forbidden phrase it did not before. Majority packet text is identical for 337/338; the other probe varied
  between two packets across `main`'s rounds and gave the first of them in every round after the change.
- PR source (amendments 2 and 3) against `main`: 312/338 in every round of both lanes, majority packet text identical
  for 338/338, no changed result or forbidden phrase; two probes varied across `main`'s rounds, none after the change.

## Limits

- Thresholds come from one host and one trial install's data; slower hosts move the 25 ms edge.
- A head over 100,000 characters still rechecks other chats' messages; that needs a per-chat index (a schema change),
  not proposed here.
- These are replays and in-process measurements, not host or network latency.
