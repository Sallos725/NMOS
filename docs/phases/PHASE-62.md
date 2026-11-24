# Phase 62 — A long reply read to its end

Status: **approved**, 2026-11-24 (owner, in the session that measured it: "나머지는 제안대로, 그대로 실행해줘", after asking
about Q4 and Q5 and seeing both proposals changed). Read as: Q0 (a), Q1 (a), Q2 (a), Q3 (a) as first proposed; Q4 (b)
and Q5 (a) as changed that day. Steps 2–4 are built with no paid call; step 5 (the test install, then production) waits
for the owner's go, as Q0 (a) says. A correction found by measurement (K13), not a roadmap stage. The idea of reading
a long reply further came up in the owner's survey of another memory plugin (2026-11-24); nothing of its code or prompt
text is used, and what is built here is NMOS's own cap, already in the code, made a setting. Linear: AGE-96.

**High risk** (`AGENTS.md §14`) once built:
- **new generations when the setting is changed**: the cap is part of the extractor's and the reveal check's keys
  (`target_chars`) and of the summarizer's (`message_chars`), so another value is another generation of each (D20);
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

The same cap stops two other readers: scene summaries
(`summaries.MESSAGE_CHARS = 6000`; 57 summaries since 2026-11-10 left 49.9 % of their windows' characters unread) and vectors
(8 chunks of 700; 52.8 % of the accepted chat messages' characters lie past 5,600). Word and keyword recall search a
message whole, so an excerpt from the unread part can still be found; no fact, thread, secret or summary can come
from it. A scene summary reads the messages themselves, not the facts, so reading further in extraction alone would
leave every summary where it is; and the opt-in trimming of Phase 60 counts a turn as covered once an extraction
serves it and a scene summary holds it, so old dialogue can leave the prompt while its second half is in neither.
Summaries follow the cap in this phase (Q4); vectors need no build, their setting exists (Q5).

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

S1b. **Scene summaries read with the same cap** (Q4). `summaries.MESSAGE_CHARS` becomes the setting's value: the
summarizer's spec already holds `message_chars`, so at the default its key is unchanged. A window is still one call;
at 24,000 the largest windows seen (about 198,000 characters over 8 turns) are about 140,000 input tokens in that one
call. The story so far is made from scene summaries and is not touched.

S2. **Changing the cap queues nothing.** `generations.classify` names a change whose specs differ only in
`target_chars` (with or without a compiler of `ADDS`) `reads`, and activation queues for it what a carry-on queues
(ADR 0078): turns no generation serves. Turns already extracted keep their facts (ADR 0014). Reveal checks follow the
same rule: none is asked again. So do summaries: a window an earlier summarizer wrote keeps its summary (ADR 0078
item 1), and only windows that come due afterwards are read at the new cap. With the model changed in the same save, the owner's choice for a model change applies
as today.

S3. **"Read the cut turns again"** (Q3). A per-chat action beside "extract all history": it queues, for the active
generation, only the turns whose serving extraction was cut at a cap lower than the active one and lower than the
turn's length. The panel first shows the count and the estimated input tokens (`POST /v1/config/preview`'s pattern: a
rolled-back transaction). A re-read turn is extracted whole again (one call); the reveal check and the dropped-fact
restore of Phase 22 apply as for any re-extraction. The preview counts separately the scene summaries of the windows
those turns are in, and the owner chooses whether they are written again with them.

S4. **Said as it is.** K13 is corrected with this measurement (in this spec's pull request). The Inspector's coverage
row names the cap when it is not the default (*amended at the build: the Inspector's rows are the sidecar's; the
Status tab's line is the plugin's and stays as it is*).

S5. **What it does not change.** The default (6,000), `extract-v16` as the code default, every prompt's wording, the
packet and recall, canon reading (`canonfacts.PART_CHARS`, its own parts), the summaries' prompts and their size
limits, vectors. *Amended at the build:* the first draft listed the plugin here too, but the per-chat action buttons
are the plugin's (`ui.ts`), so S3 adds one button to it: the plugin build changes and the owner imports it again. The
button shows only when the sidecar reports cut turns to read, so an older sidecar or the default cap shows nothing.

## Out of scope

- A cap above 36,000, or a reply read in several calls (Q1 (c)).
- Anything built for vectors (Q5: `NMOS_EMBED_MAX_CHUNKS` exists). A bound on a whole summary window.
- The CONTEXT cut. It shows the first 1,000 characters of each earlier message, so a long earlier reply is seen from
  its beginning, not from where it ended. Noted for a later generation; changing it changes every turn's prompt.
- A paid measurement (Q2), a new default, a release tag.

## Questions (answered, owner 2026-11-24: Q0 (a), Q1 (a), Q2 (a), Q3 (a), Q4 (b), Q5 (a))

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
  the facts whose evidence lies past 6,000 counted (about 0.6 to 0.7 million input tokens for the second reading;
  the first exists). Proposed (a); (b) is the only way to count what is gained before production pays.
- **Q3 — the turns already cut.** **(a) From now on, and S3's action per chat.** (b) From now on only ("extract all
  history" stays the manual fill). (c) Every cut turn of the recent window at the switch. Proposed (a).
- **Q4 — summaries.** (a) Unchanged in this phase. **(b) Scene summaries follow the setting.** Proposed (b) (changed
  2026-11-24 on the owner's question; the first draft proposed (a) for its cost alone, and its reason, that facts
  would cover the text, was wrong: a summary reads the messages, not the facts). A summary is the reader that most
  needs a scene whole, and trimming relies on it. The price: a scene summary's input about doubles (below), and the
  largest windows become one call of about 140,000 input tokens, which the extraction model must be able to take.
- **Q5 — vectors.** **(a) Nothing to build: `NMOS_EMBED_MAX_CHUNKS` already raises the cap (ADR 0062); the value
  proposed for production, set together with the extraction cap, is 35 (24,500 characters).** (b) A cap change that
  keeps the vectors it has and embeds only the chunks past them. Proposed (a) (changed 2026-11-24 on the owner's
  question; the first draft left vectors for later because a new projection embeds every chat again, and the record
  shows that to be small). Production's projection recorded 0.75 tokens per character, so embedding its 7.7 million
  characters again at 35 chunks is about 5.8 million tokens: about $0.70 at the embedder's listed $0.12 per million,
  or nothing while the provider's free allowance lasts. (b) would save about half of that and is not worth a
  mechanism. What is not known: whether chunks past 5,600 change what recall finds (M0's chats have no reply that
  long, and word and keyword recall already reach that text), how long the vector step takes with about twice the
  chunks (5,900 → 11,900 on production), and recall while the new projection is still filling. Step 4 times the
  vector step without an embedding call.

## What it costs (estimate; production's recorded usage, `extract-v18`, 643 turns)

A turn now takes 11,869 input and 1,780 output tokens on average (1.03 calls). What a character of TARGET costs is
not settled by the record, so the estimate is a range:
- **0.69 tokens per character** — the slope of a scene summary's input on the characters it read (57 summaries,
  r² 0.80): text alone. Nothing else in the extraction prompt grows with the cap, so this is the likelier figure.
- **1.26 tokens per character** — the slope of extraction's own input on TARGET characters over the 225 turns that
  were not cut (r² 0.55; 1.03 over all single-call turns, r² 0.42). Longer turns also come with longer hint lists,
  which this slope counts.

At 24,000 (5,700 more TARGET characters read per turn, 5,607 → about 11,300):

| | Now (6,000) | At 24,000 | Change |
|---|---|---|---|
| Input tokens per turn | 11,869 | about 15,800 to 19,100 | +3,900 to +7,200 (+33 % to +61 %) |
| Output tokens per turn | 1,780 | 1,780 to 3,600 | +0 to +1,800: cut turns answer today no longer than uncut ones (1,790 and 1,762), so the lower end is as likely |
| The 643 turns of those six days | 7.63 M input | about 10.2 M to 12.3 M | +2.5 M to +4.6 M input |

A scene summary (one per 8 turns) now takes 29,941 input tokens for 46,371 of its window's 92,566 characters. Read at
24,000 it takes about 61,000 (+31,000, at the summaries' own 0.69 tokens per character): about +3,900 input tokens
per turn on top of the table, so the phase as a whole adds about 7,800 to 11,100 input tokens per turn (+50 % to
+70 % of what a turn's extraction and its share of a summary take today, 15,600).

Re-reading a cut turn (S3) is a whole call: about 18,900 to 24,100 input tokens for the mean cut turn (15,487
characters, 9,211 of them unread today), so the 410 cut turns of that week would take about 7.7 to 9.9 million input
tokens. At an example rate of $1.50 per million input and $7.50 per million output tokens (a third-party listing for
one model in the usage log, not checked against the provider's own page; the owner's rate replaces it): about +$0.012
to +$0.030 per live turn with the summaries, and about $17 to $26 for those 410 turns (their summaries not counted). Cached input is not counted. Step 4 measures the
prompt sizes on a copy before anything is paid. Two more things cost what they did before, on longer prompts: a turn
whose call fails is tried up to five times at its full input, and "extract all history" after a change of the cap
reads every older turn again at the new cap, not only the cut ones (the new button reads only those).

## Steps

1. This spec, K13's correction (docs). ADR with step 2.
2. **Build** (after approval): S1, S2, S4. Tests with a stub model: the prompt holds a reply's tail at 24,000 and
   not at 6,000; an assertion whose evidence lies past 6,000 is kept at 24,000 and parked at 6,000; quotes,
   confirmations and the reveal check read the same text; at the default every generation key (`extract-v15`–`v19`,
   reveal, summarize, canon, embed) and prompt is byte-identical to `main`; a change of the cap alone classifies
   `reads` and queues nothing on a covered chat, both ways, and only uncovered turns on a partial one; any other
   version change keeps PHASE-57 Q5; `coverage` and the Inspector's marks follow each row's own cap; a scene summary's
   prompt holds a reply's tail at 24,000, its key is unchanged at the default, and a change of the cap queues no
   summary of a window already written.
3. **Build** S3 (if Q3 (a)): the action, its preview, tests that it queues exactly the cut turns and none twice.
4. **The check** (no paid call): on a throwaway copy of production (test PG, never production's database), the
   jobs a change to 24,000 queues before any worker runs (expected 0), row counts and id hashes unchanged; the prompt
   sizes of the copy's cut turns at 24,000 against this estimate; S3's preview count against a direct count; the
   vector step's time with stand-in chunks (existing vectors copied to the chunk numbers a cap of 35 would add: no
   embedding call), against today's.
5. **The owner's use** on the test install, then production on the owner's go (a fresh dump and an `.env` backup
   first; the quiet weeks restart): the cap and, if Q5 (a), `NMOS_EMBED_MAX_CHUNKS` in the same change, so the weeks
   restart once.

## Acceptance criteria

1. At the default cap, every generation key and every prompt is byte-identical to `main`.
2. At 24,000, a turn whose messages are each at most 24,000 normalized characters is shown whole, and its coverage
   says so (`target_used = target_chars`).
3. An assertion whose evidence lies past character 6,000 is kept at 24,000.
4. Changing the cap on production's copy queues **no** extraction, no reveal check and no summary, and changes no
   row; changing it back too.
5. "Read the cut turns again" queues exactly the turns cut below the active cap, shows their count and estimated
   tokens first, and queues nothing on a second press.
6. A chat's packet is byte-identical before and after the change of the cap, until a turn is extracted at the new cap.
7. The prompt sizes measured in step 4 lie inside the estimate's range, or the estimate is corrected and shown to the
   owner before step 5.

## Stop conditions

- A change of the cap would queue extraction, reveal checks or summaries on the copy: stop; nothing is deployed until it queues
  none.
- Any key or prompt differs at the default: stop.
- The extraction model cannot take the largest summary window in one call (its context, or a timeout): stop and
  bring Q4 back to the owner with the sizes; a bound that cuts the window again is not chosen silently.
- **Going back to an image without this phase.** An older image knows no `reads`: on a database whose active
  generations were made at another cap it calls the change a version change and extracts the recent turns again, at
  the owner's cost. Order: set the cap back to 6,000 on this image first (that queues nothing), then change the
  image. Step 4 shows both on the copy.
- On the test install, long turns fail or time out (`NMOS_LLM_TIMEOUT_S`), or their answers arrive cut (not JSON)
  more often than short turns': report before production, with the model-call log's counts (Phase 61).
- The owner's use shows facts getting worse on long turns (missed where they were found, or invented): set the cap
  back; the earlier extractions still serve.

## Risk and release

High risk (see the top). Off path: at the default nothing changes. Ships when built, behind the setting; whether the
default rises is the owner's decision, with the others, at the `1.0.0` tag or after it.
