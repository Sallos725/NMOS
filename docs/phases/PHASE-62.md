# Phase 62 — A long reply read to its end

Status: **draft**, 2026-11-24. Not approved: Q0–Q5 below are open, and nothing is built. A correction found by
measurement (K13), not a roadmap stage. The idea of reading a long reply further came up in the owner's survey of
another memory plugin (2026-11-24); nothing of its code or prompt text is used, and what is proposed here is NMOS's
own cap, already in the code, made a setting.

**High risk** (`AGENTS.md §14`) once built:
- **a new extractor generation when the setting is changed**: the cap is part of the extractor's and the reveal
  check's keys (`target_chars`), so another value is another generation (D20);
- **what a generation change queues**: a change of the cap alone must queue no re-extraction (S2), a new class beside
  PHASE-57 Q5 and PHASE-58 S3;
- **what the model is charged for**: every long turn costs more input from then on (the estimate below).

Invariants it touches (`AGENTS.md §3`): **every automatic claim has provenance** (an assertion's evidence is looked
for in the text its extraction was shown, so the check must read the same cap); **derived rows carry their
generation**; **unknown is a valid result** (a turn still cut stays flagged as cut).

## Why

Extraction shows the model the first 6,000 normalized characters of each message of the TARGET turn
(`extraction.TARGET_CHARS`, #13). K13 records it as an accepted limit and says the owner's long chats stay within it
once normalized. That was measured on the first M0 chat (longest message 15,621 raw characters, 5,481 normalized) and
no longer holds. Read-only aggregates on the owner's production database, 2026-11-24 (counts and lengths only):

| What | Measured |
|---|---|
| Accepted character replies | 685; mean 14,552 raw and 11,104 normalized characters (the normalizer keeps 76 %) |
| Replies over 6,000 normalized characters | 432 of 685 (63 %), mean 15,105 |
| Reply length, normalized | median 8,051; 75th 17,122; 90th 22,956; 95th 25,002; 99th 27,400; longest 33,417 |
| User messages | 763; 99th percentile 1,164, longest 4,919, none over 6,000 |
| Turns extracted by `extract-v18`, 2026-11-18 to 11-23 | 643 in 41 chats; 410 cut (64 %), 350 of them by more than 1,000 characters |
| TARGET characters the model was not shown | 51.2 % (3.78 of 7.38 million) |
| By chat | 12 chats nothing cut, 9 at 1–29 %, 12 at 30–59 %, 8 at 60 % or more |
| `extract-v19`, 2026-11-23 to 11-24 | 19 turns, 16 cut |

What lies past the cut is story: the share of Hangul is the same before and after it (66 % and 64 %), and seven cut
tails opened on a test copy were all narration and dialogue (categories only were noted). So the normalizer cannot fix it; more text has to be read. The end of a reply is also where a scene leaves
its people: where they are, what was decided, what was promised.

How much stays unread at each cap (the 685 replies):

| Cap (normalized characters) | 6,000 | 12,000 | 16,000 | 20,000 | 24,000 | 28,000 | 36,000 |
|---|---|---|---|---|---|---|---|
| Characters not read | 51.7 % | 25.8 % | 14.0 % | 5.8 % | 1.3 % | 0.2 % | 0 % |
| Replies cut | 63.1 % | 38.5 % | 27.9 % | 18.4 % | 6.3 % | 0.7 % | 0 % |

The same cap stops two other readers, which this phase leaves alone (Q4, Q5): scene summaries
(`summaries.MESSAGE_CHARS = 6000`; 57 summaries since 2026-11-10 left 49.9 % of their windows' characters unread) and vectors
(8 chunks of 700; 52.8 % of the accepted chat messages' characters lie past 5,600). Word and keyword recall search a
message whole, so an excerpt from the unread part can still be found; no fact, thread, secret or summary can come
from it.

## What it does

S1. **The cap is a setting.** `NMOS_EXTRACT_TARGET_CHARS` (default 6,000: every key and prompt as today; 6,000 to
36,000). The extractor's and the reveal check's specs already hold `target_chars`, so at the default nothing changes
and another value is another generation. Every reader of the cap reads the generation's value, not the constant:
- the prompt's TARGET lines (`build_prompt`), the listed quotes (`quotes_in`), the confirmation prompts
  (`confirm_prompt`, `alias_prompt`), the reveal check's TARGET;
- the evidence check's text (`shown_target`): an assertion quoted from past character 6,000 is kept, not parked;
- `coverage_of`, which also records the cap it used (`target_cap`; a row without it was read at 6,000), so the
  Inspector's "partly processed" mark (`readmodel`) and the coverage row's "target truncated" count say what each
  extraction read.
One model call per turn, as today (Q1). CONTEXT stays 1,000 characters per message.

S2. **Changing the cap queues nothing.** `generations.classify` names a change whose specs differ only in
`target_chars` (with or without a compiler of `ADDS`) `reads`, and activation queues for it what a carry-on queues
(ADR 0078): turns no generation serves. Turns already extracted keep their facts (ADR 0014). Reveal checks follow the
same rule: none is asked again. With the model changed in the same save, the owner's choice for a model change applies
as today.

S3. **"Read the cut turns again"** (Q3). A per-chat action beside "extract all history": it queues, for the active
generation, only the turns whose serving extraction was cut at a cap lower than the active one and lower than the
turn's length. The panel first shows the count and the estimated input tokens (`POST /v1/config/preview`'s pattern: a
rolled-back transaction). A re-read turn is extracted whole again (one call); the reveal check and the dropped-fact
restore of Phase 22 apply as for any re-extraction.

S4. **Said as it is.** K13 is corrected with this measurement (in this spec's pull request). The Status tab's
extraction line names the cap when it is not the default.

S5. **What it does not change.** The default (6,000), `extract-v16` as the code default, every prompt's wording, the
packet and recall, canon reading (`canonfacts.PART_CHARS`, its own parts), summaries, vectors, the plugin.

## Out of scope

- A cap above 36,000, or a reply read in several calls (Q1 (c)).
- Summaries and vectors past their caps (Q4, Q5): recorded in K13, their own decisions.
- The CONTEXT cut. It shows the first 1,000 characters of each earlier message, so a long earlier reply is seen from
  its beginning, not from where it ended. Noted for a later generation; changing it changes every turn's prompt.
- A paid measurement (Q2), a new default, a release tag.

## Questions (open)

- **Q0 — when.** R7 keeps new phases to Stage 7 until `1.0.0`, and a new extractor generation is feature work
  (`AGENTS.md §13`). **(a) Build it now behind the setting, default unchanged; production's switch is a separate
  go-ahead that restarts the quiet weeks, as for Phases 58 and 60.** (b) After `1.0.0`. Proposed (a): the build
  changes nothing until the setting is changed, and half of a long reply never reaching memory is the kind of gap
  `0.3.0` waited for (AGE-24).
- **Q1 — how a long reply is read.** **(a) One call, the cap as high as the setting says; the value proposed for
  production is 24,000** (1.3 % of characters unread, 6.3 % of replies still cut and flagged). (b) One call at 36,000
  (everything seen so far). (c) Parts of at most 12,000 with what the earlier parts recorded, as canon is read: every
  part repeats the prompt's fixed part (about 5,800 input tokens measured), and a turn's extraction becomes several
  answers to merge. Proposed (a): the smallest change, and whether one call loses detail at 25,000–30,000 characters
  is not known for the owner's models; (b) is the same build with another number, so the owner can try it.
- **Q2 — the gate.** `AGENTS.md §7` item 6 asks a full live gate of an extraction change; the owner stopped paid runs
  (2026-10-25). **(a) Zero-call checks (below) and the owner's use on the test install, then production, as for
  Phases 58 and 60.** (b) A small paid comparison first: 30 cut turns of a copy extracted at 6,000 and at 24,000,
  the facts whose evidence lies past 6,000 counted (about 30 × 22,600 = 0.7 million input tokens for the second
  reading; the first exists). Proposed (a); (b) is the only way to count what is gained before production pays.
- **Q3 — the turns already cut.** **(a) From now on, and S3's action per chat.** (b) From now on only ("extract all
  history" stays the manual fill). (c) Every cut turn of the recent window at the switch. Proposed (a).
- **Q4 — summaries.** **(a) Unchanged in this phase.** (b) `MESSAGE_CHARS` follows the setting: a scene summary reads
  8 turns, so its input roughly doubles (about 30,000 input tokens per summary measured now). Proposed (a): a summary
  is made from text the facts will now cover, and its cost is paid per window whatever its use.
- **Q5 — vectors.** **(a) Unchanged; `NMOS_EMBED_MAX_CHUNKS` already raises it, at the price of a new projection that
  embeds every chat again (K13).** (b) A cap change that keeps the vectors it has and embeds only the chunks past
  them. Proposed (a) here; (b) is worth its own spec if recall from long replies proves short.

## What it costs (estimate; production's recorded usage, `extract-v18`, 643 turns)

A turn now takes 11,869 input and 1,780 output tokens on average (1.03 calls). Input fits `5,763 + 1.089 × TARGET
characters read` (r² 0.23: the hints vary). At 24,000:

| | Now (6,000) | At 24,000 | Change |
|---|---|---|---|
| TARGET characters read per turn | 5,607 | about 11,300 | +5,700 |
| Input tokens per turn | 11,869 | about 18,100 | +6,200 (+52 %) |
| Output tokens per turn | 1,780 | 1,780 to 3,600 | +0 to +1,800: cut turns answer today no longer than uncut ones (1,790 and 1,762), so the lower end is as likely |
| The 643 turns of those six days | 7.63 M input | about 11.6 M | +4.0 M input |

Re-reading a cut turn (S3) is a whole call: about 22,600 input tokens for the mean cut turn (15,487 characters), so
the 410 cut turns of that week would take about 9.3 million input tokens. At an example rate of $1.50 per million
input and $7.50 per million output tokens (a third-party listing for one model in the usage log, not checked against
the provider's own page; the owner's rate replaces it): about +$0.009 to +$0.023 per live turn, and about $19 to $25
for those 410 turns. Cached input is not counted.

## Steps

1. This spec, K13's correction (docs). ADR with step 2.
2. **Build** (after approval): S1, S2, S4. Tests with a stub model: the prompt holds a reply's tail at 24,000 and
   not at 6,000; an assertion whose evidence lies past 6,000 is kept at 24,000 and parked at 6,000; quotes,
   confirmations and the reveal check read the same text; at the default every generation key (`extract-v15`–`v19`,
   reveal, summarize, canon, embed) and prompt is byte-identical to `main`; a change of the cap alone classifies
   `reads` and queues nothing on a covered chat, both ways, and only uncovered turns on a partial one; any other
   version change keeps PHASE-57 Q5; `coverage` and the Inspector's marks follow each row's own cap.
3. **Build** S3 (if Q3 (a)): the action, its preview, tests that it queues exactly the cut turns and none twice.
4. **The check** (no paid call): on a throwaway copy of production (test PG, never production's database), the
   jobs a change to 24,000 queues before any worker runs (expected 0), row counts and id hashes unchanged; the prompt
   sizes of the copy's cut turns at 24,000 against this estimate; S3's preview count against a direct count.
5. **The owner's use** on the test install, then production on the owner's go (a fresh dump and an `.env` backup
   first; the quiet weeks restart).

## Acceptance criteria

1. At the default cap, every generation key and every prompt is byte-identical to `main`.
2. At 24,000, a turn whose messages are each at most 24,000 normalized characters is shown whole, and its coverage
   says so (`target_used = target_chars`).
3. An assertion whose evidence lies past character 6,000 is kept at 24,000.
4. Changing the cap on production's copy queues **no** extraction and no reveal check, and changes no row; changing
   it back too.
5. "Read the cut turns again" queues exactly the turns cut below the active cap, shows their count and estimated
   tokens first, and queues nothing on a second press.
6. A chat's packet is byte-identical before and after the change of the cap, until a turn is extracted at the new cap.
7. The measured prompt sizes of step 4 are within 20 % of the estimate, or the estimate is corrected before step 5.

## Stop conditions

- A change of the cap would queue extraction or reveal checks on the copy: stop; nothing is deployed until it queues
  none.
- Any key or prompt differs at the default: stop.
- On the test install, long turns fail or time out (`NMOS_LLM_TIMEOUT_S`), or their answers arrive cut (not JSON)
  more often than short turns': report before production, with the model-call log's counts (Phase 61).
- The owner's use shows facts getting worse on long turns (missed where they were found, or invented): set the cap
  back; the earlier extractions still serve.

## Risk and release

High risk (see the top). Off path: at the default nothing changes. Ships when built, behind the setting; whether the
default rises is the owner's decision, with the others, at the `1.0.0` tag or after it.
