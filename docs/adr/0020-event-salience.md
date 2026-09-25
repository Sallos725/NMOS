# 0020 — Event cap and event salience

Status: accepted, 2026-09-24. Phase 7 steps 1, 3 and 4 (`docs/phases/PHASE-7.md`, owner answer Q4).
The cap is read-side only. The label is part of `extract-v7` and migration 0016.

## Context

`event` is the most frequent predicate: 39 to 51 actual events per 43 to 62 extracted turns in the
real-model tiers. It is multi-valued, so every event stays current. `relevant_facts` scores a mention
of a name the same for every fact about that entity and breaks ties by position. With 185 newer minor
events of 하나, "하나야, 오랜만이야." returned 8 events and none of her older facts (PHASE-7,
"Evidence"). The owner's note of 2026-09-23 asked for important events to go first, as a priority and
never as a reason to delete the rest.

## Decision

1. **Cap (step 1).** At most `events_limit` of a packet's facts are events (default 3; env
   `NMOS_EVENTS_LIMIT`, runtime-editable 0–30). The other slots go to the next relevant facts. This
   applies to all data at once.
2. **Label (step 3).** `extract-v7` asks for `salience` on every `event`: `major` when it changes the
   story (a confession, a betrayal, a death, a first meeting, a secret revealed, a decision that
   changes a relationship or a goal), otherwise `minor`. It is stored in `assertion.salience` (migration
   0016). Validation keeps it on events only and stores a missing or invalid value as NULL. Rows of
   older generations are NULL (unlabeled).
3. **Ranking (step 4).** Among the event candidates, the cap keeps the highest by mention score, then
   major before minor or unlabeled, then score and position. The kept events keep their place in the
   overall fact order. A `minor` event is a candidate only when the query is about the event itself: the
   trigram overlap between its value (not its subject's name) and the query reaches the lexical bar
   (0.35). A name mention alone is not enough. Unlabeled events keep the rule they had before: a
   mention, or the lexical bar on the whole fact.
4. **Nothing is deleted or down-sampled.** Minor events stay stored, current and visible in the
   Inspector. Excerpt ranking is unchanged.

## Amendment (2026-09-25, ADR 0024)

`extract-v9` defines `major` by what an event changes, in action or only in words, and names the
categories (admissions and confessions, changes in how characters treat or address each other, a
relationship allowed, a power first shown, an incident others must deal with). Routine scene business is
`minor`. Items 1, 3 and 4 are unchanged.

## Consequences

- A main character's routine does not crowd out older facts, promises (ADR 0019) or major events
  (`tests/test_extraction.py`; memory evaluation "events leave room", "major event first").
- A minor event reaches the packet when the user asks about it, not whenever its subject is named.
  If the label is wrong, a real turning point labeled `minor` behaves like that. The real-model tier
  (step 6) measures how the labels separate major and minor scenes. If they do not, the cap stays and
  the label needs a new decision (PHASE-7 stop condition).
- Chats with extraction off, and turns of older generations, get the cap only.
