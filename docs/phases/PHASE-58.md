# Phase 58 — How a feeling feels: its strength, its sign, and a feeling under it

Status: **approved**, 2026-11-18 (owner, in the design conversation of 2026-11-18: Q1–Q4 answered below; "완성되면 6003
및 6113에 올릴 준비"). An owner request, not a roadmap stage. Ships in `1.0.0` with Phase 57 (Q4: production gets it
and the 1.0 quiet weeks restart on its build). Steps 2 and 3 done 2026-11-18 on branch
`Sallos725/track-affinity-scores-host` (step 3: `docs/perf/phase58-switch.md`, the switch queues nothing on a copy of
production). Q5 answered as proposed and step 4 done (owner, 2026-11-18): on 6113 and production since 15:36 KST, the
switch queued nothing on either; the quiet weeks restarted (earliest end 2026-12-02). Linear: AGE-93.

**High risk** (`AGENTS.md §14`):
- **a new extractor generation** (`extract-v18`): a prompt change, so a new generation key (D20) and a release's one
  generation for the milestone (`AGENTS.md §13`);
- **a migration** (`0035`: `assertion.feeling`);
- **what a generation change queues**: a switch between `extract-v16` and `extract-v18` queues no re-extraction (Q3),
  an exception to PHASE-57 Q5's policy for a release's version change.

Invariants it touches (`AGENTS.md §3`): **every automatic claim has provenance** (the strength and the feeling under
it are read from the turn by the extraction that quotes it, never computed afterwards); **unknown is a valid result**
(a feeling the turn does not weigh has no strength, and is shown as today); **derived rows carry their generation**
(the detail is a column of the assertion its extraction wrote).

## Why

The owner wants to follow how strongly a character feels toward another, and negative feelings with the positive,
even when the card never shows a number (design conversation, 2026-11-18). A score from -100 to 100 estimated by the
model was declined earlier (`docs/proposals/IDEA-SURVEY-2026-09-29.md` §5: a number the story never states cannot be
traced, and hides "unknown"); the owner does not need a number either ("굳이 numeric으로 보여줄 필요는 없고").

NMOS already keeps feelings (`feels_toward`, ADR 0038): one per direction of a pair, `stated` or strongly `implied`,
with the quote, the stated cause (`because`, ADR 0040) and the versions it replaced. What it lacks:
1. **How strong.** "좋아함" said once in passing and "좋아함" that drives a scene are the same row.
2. **A sign.** Nothing tells warmth from resentment except the words, so the panel cannot show the balance of a pair.
3. **Two feelings at once.** A direction holds one feeling (`single`), so "loves him and resents him" collapses into
   one value or the later one replaces the earlier.

## What it does

S1. **`extract-v18`** is `extract-v16` (the default, what production runs) with one rule and one answer field:
`feeling`, on `feels_toward` only.
- `intensity`: `faint` (a hint, mild), `clear` (plainly shown), `strong` (overwhelming, it drives the scene) — three
  steps, read from how the TARGET turn shows it.
- `valence`: `positive` (warmth, trust, attraction, gratitude, admiration, relief), `negative` (anger, fear,
  resentment, contempt, jealousy, distrust, disgust, guilt toward them), or `null` when it is neither (curiosity,
  surprise).
- `under`: a second feeling the TARGET turn shows running beneath the first (`value`, `intensity`, `valence`), or
  `null`. Only when the turn shows both; never a guess.
- The model gives `feels_toward` again when only the strength changes or a feeling under it appears or fades, with the
  whole feeling: the slot stays `single`, and the newer statement replaces the older whole (ADR 0013), so a feeling
  that fades needs no ending of its own (Q1 of the design: one slot, a feeling under it).
- Not built on `extract-v17` (Phases 45 and 51, selectable, its live gate deferred): `extract-v18` changes what
  production runs by this field only.

S2. **Stored with the assertion.** Migration `0035`: `assertion.feeling jsonb`, null for every other predicate, every
older generation and a feeling the turn does not weigh. `extraction.normalize` keeps a valid `feeling` on a
`feels_toward` row of a compiler in `FEELINGS`: an unknown `intensity` drops the detail (the value stays, as today), an
unknown `valence` becomes `null`, an `under` without a value or an intensity is dropped. Canon reads never write it.
It is copied wherever an assertion is (`ASSERTION_COLUMNS`: the canon copy of Phase 57, reveal checks, archives).

S3. **The switch queues nothing** (Q3: from now on, history by hand). A generation change between `extract-v16` and
`extract-v18` whose spec differs only in the compiler and its prompt is classified `adds` (`generations.classify`)
and queues what a carry-on queues: only turns no generation serves. Older turns keep their `extract-v16` facts (ADR
0014), with no strength. "Extract all history" (per chat, an explicit action) re-extracts a chat with `extract-v18`,
as for any generation. Any other version change keeps PHASE-57 Q5.

S4. **Shown, with colour by sign** (Q2: positive, negative, mixed). Wherever a feeling is listed today (the panel's
memory document and a person's sheet, the browser Inspector's pair rows): the value, its strength in words
(옅음 / 뚜렷함 / 강함; faint / clear / strong), and "밑에: …" / "under: …" for the second feeling. A dot before it in
the sign's colour: positive, negative, or **mixed** when the two feelings have opposite signs. A feeling without detail
is shown exactly as today. Colours are tokens of the sidecar's stylesheet with a dark-mode variant
(`design-philosophy-doc`); the text says the sign too, so colour is never the only cue.

S5. **What it does not change.** The packet (`packet-v19`), the author's note, the memory map, recall and its ranking
are byte-identical: the detail is for the owner to read (recommended in the design conversation, the owner did not
ask for it in the packet; the packet is a later, separate decision).

## Out of scope

- A number, or a score summed over turns.
- More than one slot per direction (`multi` feelings), or a feeling between groups.
- The detail in the packet, the author's note or the memory map; recall by strength.
- Re-extracting history on the switch, or a backfill job of its own (Q3: "extract all history" is the manual fill).
- `extract-v17`'s speakers and horizons in `extract-v18`.
- The plugin: the panel's content is the sidecar's (PHASE-52 approach A), so the plugin build does not change.

## Questions (answered, owner 2026-11-18)

- **Q1 — where the strength is read.** (a) A separate check beside extraction, as reveal checks are. **(b) In the
  extraction prompt, a new generation.** Answered (b). The extraction sees the turn and writes the feeling already; a
  second call would read the same turn again.
- **Q2 — the colours.** **(a) Positive, negative, mixed.** (b) Positive, negative, neutral. (c) Positive, negative.
  Answered (a); a feeling with no sign is shown without a dot.
- **Q3 — the 1,864 feelings production holds.** **(a) From now on, history by hand.** (b) All at once on the switch.
  (c) From now on only. Answered (a): S3, and "extract all history" per chat.
- **Q4 — `1.0.0`.** (a) In `1.0.0`, production gets it and the quiet weeks restart. (b) After `1.0.0`. Answered (a)
  ("6003에 올리고 리셋하자").
- **Q5 — the gate.** `AGENTS.md §7` item 6 asks a full live gate of an extraction change. The owner stopped paid runs
  (2026-10-25), and S3 queues nothing on the switch, so the checks below are zero-call and the owner's use on the test
  install, then production, is the live check (as `extract-v17`'s default was deferred). **Answered (owner,
  2026-11-18): as proposed.**

## Steps

1. This spec and ADR 0081 (docs).
2. **Build.** `extract-v18` (prompt, `FEELINGS`, `normalize`), migration `0035`, `ASSERTION_COLUMNS` and the fact read,
   `generations.classify`'s `adds`, the history entries' detail, the panel and Inspector rendering, `NMOS_EXTRACT_COMPILER`
   accepting `extract-v18`. Tests: the prompt carries the rule and the field only for `extract-v18`; `normalize`
   keeps, cleans and drops as S2 says and never on another predicate or compiler; a feeling with detail round-trips the
   database and an archive; a stronger restatement replaces the weaker as the current version and both stay in the
   history; `adds` queues nothing on a covered chat and the uncovered turns on a partial one, both ways; any other
   version change keeps Q5; the panel shows strength, the feeling under it and the sign's class, and a feeling without
   detail renders byte-identical; the packet of a chat with detail is byte-identical to the same chat without it.
3. **The check** (no paid call): the migration and the switch on a throwaway copy of production's database (test PG
   :5436, never production's): the jobs the switch queues before any worker runs (expected 0), every row count and id
   hash unchanged; the prompt's size against `extract-v16`'s. Then the owner's use on the test install (6131/6113).
4. **Deployment** (owner's go): 6113, then production, `NMOS_EXTRACT_COMPILER=extract-v18`, after a fresh dump and an
   `.env` backup; the quiet weeks restart (Q4).

## Acceptance criteria

1. With `extract-v18` active, a turn that shows a feeling yields a `feels_toward` row whose `feeling` holds a valid
   strength, and a second feeling only with a quote that shows it (unit tests with a stub model; the owner's use).
2. Switching production's copy from `extract-v16` to `extract-v18` queues **no** extraction job and changes no row.
3. A chat's packet is byte-identical with and without the detail.
4. A feeling with no detail renders exactly as before in the panel and the Inspector.
5. Switching back to `extract-v16` queues nothing and serves the same facts, the detail no longer shown for turns
   `extract-v16` covers.

## Stop conditions

- The switch would queue extraction on the copy: stop; nothing is deployed until it queues none.
- The detail changes a packet, a recall result or the author's note in any test: stop and remove it from that path.
- The prompt grows by more than 15 % of `extract-v16`'s system prompt: report it before the deployment (each
  extraction pays it).

## Risk and release

High risk (see the top). Off path: `extract-v16` stays the code default, so an install that does not select
`extract-v18` sees no change but the migration's null column. In `1.0.0` (Q4); whether `extract-v18` becomes the code
default at the tag is the owner's decision at the tag, after the quiet weeks on production.
