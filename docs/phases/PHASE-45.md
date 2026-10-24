# Phase 45 — Who said it: speakers recorded at extraction, read by the quote route

Status: **draft**, 2026-10-12. A correction found by measurement under AGE-86 (the recall weaknesses left after
**R8 (owner, 2026-10-23, AGE-89/AGE-90): un-held and approved for implementation in `0.5.0`,** in one extractor generation `extract-v17` with Phase 51 (`docs/ROADMAP-1.0.md` R8).
`packet-v18`), not a roadmap stage. It addresses K47 inside Stage 7's forensic recall (the quote route of Phase 33,
ADR 0067). Not approved for implementation. **Q1 answered (owner, 2026-10-13): (a), speakers only.**
**Held (owner, 2026-10-13)** after step 3: one quotes case gained does not justify a generation of its own, so the
speakers go into `main` with the next extractor-generation change, and the re-extraction and its risk happen once.
Merged as the record of the measurement, like PHASE-44.

**Step 2 built, 2026-10-24** (branch `claude/extract-v17`, with Phase 51 in the same generation): `extract-v17` is
selectable and not the default. It lists the TARGET turn's quoted lines (`[Q1] …`, up to 30, 80 characters each, the
quote route's own `quotes_in`) and asks for `speakers` by number; "?" and unknown numbers are dropped, so a line whose
speaker the turn does not show is not stored. Migration `0030` adds `extraction.speakers`; archives carry it (round-trip
test). The quote route reads a stored speaker only where the line's own sentence names nobody, only from extractions of
the generation in use (live at the request's time, so a replay reads what was known), and not when two extractions
disagree; `{{user}}` is the persona. A question naming a speaker gets that speaker's other lines of the message after
their line, within `QUOTE_CHARS`, the line as placed today kept whole (S4). With `extract-v16` in use nothing is stored
and the route is unchanged (`tests/test_quote_speakers.py`); `extract-v15`'s and `extract-v16`'s prompts and generation
keys are byte-identical to `main`'s before this step (checked against `origin/main`'s code). Steps 3–5 are paid and
wait for the owner, with Q2 and Q3.

**Q2 and Q3 answered, paid steps approved (owner, 2026-10-24):** Q2 Gemini 3.8 Flash for the live gate (comparable to
step 3); Q3 `extract-v17` becomes the default when the live gate passes; step 3 here and PHASE-51's step 3 approved
together, capped at $70, after acceptance 1's zero-call replay.

**Acceptance 1 met, 2026-10-24 (zero calls).** Every gate probe (bench 314, quotes 24) replayed under `packet-v19`
with `extract-v16` in use. The replays ran on throwaway copies of the gate databases migrated to `0030`, so `main`'s
code (`82081b9`) and this branch's read the same rows: three rounds each, with the eval embedder. By the majority:
bench 300/314 on both, quotes 19/24 on both, none lost, none gained; mean tokens 2,041 and 2,040. Per round, both
sides vary as the lexical route does (`main` 319/319/319, the branch 319/317/319: one irrelevant-question case of S2,
in both its sets, failed in one round).

**Step 3 started and stopped, 2026-10-24: $0 spent.** Every call was refused (403): the Vertex project's billing is
disabled. The run waits for the owner.

**Step 3 run before approval, 2026-10-13: its pass rule is met, narrowly.** The owner approved the paid copy
measurement (plan A, about $50; spent $49.64). It ran on the local experiment branch: `extract-v16` against
`extract-v16` plus speakers. Each arm was extracted three times on Gemini 3.8 Flash, then each run was replayed under
`packet-v18` for three rounds.

| set | `extract-v16` runs | speakers runs |
|---|---|---|
| quotes, 24 cases | 19 / 19 / 19 | 19 / 20 / 20 |
| daily play (S1), 100 cases | 97 / 96 / 96 | 97 / 95 / 95 |

- **By the majority over runs:** 0 cases lost, 1 gained. The gain is a quotes case that passes in 3 of 3 speakers
  runs and 0 of 3 `extract-v16` runs.
- **Single-run flips:** four cases flipped in one run only. One quotes case and two daily-play cases failed in one
  speakers run each. One daily-play case passed in one run of each arm.
- **Smaller gain than the measured pair:** speakers plus the "how known" field gained 2 quotes cases, speakers alone
  gained 1.
- **Cost:** the extraction cost per call rose by about 8 % on the quotes database.

**High risk:**
- a new extractor generation;
- a migration on stored derived data;
- a change to what the quote route places.

## Why

1. **The quote route guesses who said a line from the text around it** (K47). Phase 33's route (`quotes._speaker`)
   reads a speech cue ("영감이 말했다") or the message's role. In untagged alternating dialogue it has no cue. Then a
   question naming a speaker ("도윤이 이안한테 뭐라고 했어?") picks a line by the words alone, often someone else's.
   Three of the 23 replay misses under AGE-86 are of this kind.
2. **The extractor already reads the whole turn and knows who speaks.** Plugin D keeps "key dialogue" lines with
   their speaker at extraction time. NMOS can ask its own extractor the same question for the turn's quoted lines,
   inside the call it already makes.
3. **An experiment measured it on private copies** (local branch, not merged; Gemini 3.8 Flash; replay of
   `packet-v18` with three replay rounds, majority deciding):
   - **Quotes, 24 cases, the extraction repeated three times per arm.** Control 19/19/19. With speakers 21/19/21.
   - **Gains:** two cases. One passed in all three speaker runs and in no control run. The other passed in two of
     three speaker runs and in no control run.
   - **Losses:** none by majority. One case failed in one of the three speaker runs.
   - **Daily-play set, 100 cases, one extraction each:** 97 and 97.
   - **Speaker-labelled quote lines placed in the packets:** 12 → 137 over three rounds.
   - **Caveat on the arms:** the experiment's control was `extract-v16` with a per-holder "how known" field
     (AGE-85), and the candidate added speakers on top of that. Q1 decides what `main` gets.
4. **A persona label the route never read.** The rule asks the extractor to write the persona's lines as
   `{{user}}`, as every NMOS prompt names the persona. Between 10 % and 16 % of the extracted speaker lines carry
   that label. The route has to read it as the persona's name, or a question naming the persona never matches those
   lines. The measurement above includes that reading.
5. **One extraction run per arm is not enough to judge.** The same experiment re-extracted a 40-case set three times
   per arm. Each run moved by about one case on its own. So this spec's copy measurement repeats every extraction
   three times and decides by the majority over runs (step 3).

## Proposal

S1. **`extract-v17`: `extract-v16` plus the turn's quoted lines.**
- The user prompt lists the TARGET turn's quoted lines as `[Q1] …`, up to 30 (`quotes.quotes_in`, the route's own
  quote finder).
- The output gains `speakers`: for each listed line, the character the turn shows saying it, written as the story
  names them, or `{{user}}` for the persona.
- A line whose speaker the turn does not show is left out. The extractor never guesses.
- No other rule of `extract-v16` changes. It is a new generation key, so turns are re-extracted as for any
  generation.

S2. **Stored with the extraction.** Migration `0030` adds `extraction.speakers jsonb NULL`, holding the lines' words
and the speaker. Older generations leave it NULL and read as today. Export and restore carry it like the other
extraction columns.

S3. **The quote route reads it.**
- When the text shows no speaker for a line, the route takes the one a live (not discarded) extraction of that turn
  named.
- If two live extractions name different speakers for the same words, the line names nobody.
- `{{user}}` resolves to the persona's display name.
- The route's ranking, budget and filters are unchanged.

S4. **A speaker's line keeps what it showed.** When the route places a line for a question naming its speaker, it
keeps the line's own excerpt as today. It then appends that speaker's other quoted lines from the same message,
bounded by the existing quote budget. Nothing the excerpt showed is cut away.

S5. **Not the default until the gate passes** (Q3). The packet policy does not change. With `extract-v16` active,
the route behaves exactly as today.

## Out of scope

- The address-history extractor variant measured beside it (AGE-86 "next 2"). It was equal on average and adds
  2.6× the address facts; it is held.
- A per-holder "how known" field (AGE-85) and its packet marks, unless Q1 (b) is chosen.
- Content-fingerprint reuse for copied chats (AGE-84).
- Any change to `packet-v18` or a new packet policy.

## Questions for the owner

- **Q1 — what `extract-v17` is built on.**
  - (a) `extract-v16` plus speakers only. **Recommended:** one change per generation, and the "how known" field
    keeps its own decision. It needs its own copy measurement (step 3), because the measured pair was built on (b).
  - (b) `extract-v16` plus the "how known" field plus speakers, exactly what was measured. This brings AGE-85's column
    and its packet marks into this phase.
- **Q2 — the gate model.** `AGENTS.md §7.6` asks an extraction change for the full live gate. Which model runs it:
  - the owner's production model;
  - Gemini 3.8 Flash, as in the copy measurement.
- **Q3 — the default.** `extract-v17` becomes the default when step 4 passes. Every existing chat then re-extracts
  once. On the trial install the speaker generation cost about $3.2 for 135 turns on Gemini 3.8 Flash.

## Steps

1. This spec, and the owner's answers.
2. **Implementation behind the compiler name, not the default.** S1–S4, migration `0030`, tests:
   - the prompt lists the lines;
   - the speakers are stored and exported;
   - the route reads a stored speaker, refuses one two extractions disagree on, and reads `{{user}}`;
   - the appended lines keep the excerpt;
   - with `extract-v16` active, nothing changes.
3. **Copy measurement** (paid; asked before it runs).
   - Private copies of the quotes and daily-play gate databases.
   - Each arm extracted three times: `extract-v16` and `extract-v17`.
   - Replay `packet-v18`, three rounds per run.
   - Pass:
     - no case lost by the majority over runs;
     - quotes at least +1 over `extract-v16`;
     - the daily-play set equal or better.
4. **The full live gate** (`AGENTS.md §7.6`, paid; asked before it runs) on the model Q2 names.
5. **Default** (Q3), `docs/STATUS.md`, an ADR (next free number) and `docs/KNOWN-ISSUES.md` K47.

## Acceptance criteria

1. With `extract-v16` active, a replay of every gate probe under `packet-v18` is identical to `main` before this
   phase (three rounds).
2. Step 3 meets its pass rule.
3. Step 4 meets the live gate's bars.
4. Export → restore round-trips `extraction.speakers`. A restore into a build without migration `0030` is refused as
   for any newer schema.
5. Extraction cost per turn rises by at most 25 %. On the copies the quotes database rose by about 4 % and the
   daily-play database by about 20 %.

## Stop conditions

- A case lost by the majority over runs in step 3. Stop, diagnose and report before any live call.
- The extractor names speakers the turn does not show (checked by hand on 20 lines from step 3). Stop and report.
