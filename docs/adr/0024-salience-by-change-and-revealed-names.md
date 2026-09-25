# 0024 — Salience by what an event changes; names revealed later (`extract-v9`)

Status: accepted, 2026-09-25. Owner-reported after `v0.1.0-beta.16` (not a phase feature). The owner
chose, from a batch of options: name the categories of a major event without a "when unsure, major"
bias; link an unnamed character to its later name both automatically (this ADR) and by hand (ADR 0025).
Amends ADR 0020 (the label's definition), ADR 0012 (alias evidence) and ADR 0021 (KNOWN ENTITIES).

## Context

The owner found it hard to tell which facts NMOS treats as important. A read of their two chats on the
production database (`extract-v8`, `gemma4:31b-cloud`):

- In the longer chat (61 turns) 5 of 46 events were `major`. None of the major ones was routine, but
  every turning point told in words was `minor`: two changes of speech level, a new form of address, a
  relationship one character allowed, and an admission of responsibility. A `minor` event reaches the
  packet only when the query is about the event itself (ADR 0020), so a mention of the people involved
  never brought these back. The admission was stored nowhere else.
- In the second chat a measuring device that burst under the protagonist's power, with the rank test
  suspended because of it, was a `minor` event (the owner: it must not be).
- A character first shown without a name was written as a made-up description, only as a participant
  of an event. The next turn named her (a character already known), but ADR 0012 links two names only
  when both occur in one turn's text, and a description the model coined never occurs in the text. The
  two stayed separate entities. ADR 0021 also kept participant-only entities out of KNOWN ENTITIES, so
  the extractor of the next turn was never shown the description.

## Decision

1. **Salience by change (`extract-v9`).** An event is `major` when it changes the story from then on,
   in action or only in words. The prompt names the categories: a confession, an admission of guilt or
   responsibility, a secret or hidden identity revealed (the confession itself is an event of the turn,
   besides any fact about the past act it tells of); a betrayal, a death, a first meeting; a change in
   how two characters treat or address each other (speech level, a new form of address, a first kiss or
   embrace, a relationship accepted or allowed); a decision that changes a relationship, a goal or a
   plan; a power, ability or nature shown for the first time, or an incident others must now deal with
   (an accident, an explosion, an important object destroyed, a result that changes someone's status or
   plans), recorded as an event itself. Routine and scene business is `minor`: meals, chores, travel,
   small talk, repeated gestures, the next step of an activity already under way. There is no bias for
   unclear cases. Recall rules (ADR 0020) are unchanged.
2. **Unnamed characters.** A character the target turn shows without a name is named by a short
   description starting with `?` (e.g. `?검은 망토의 남자`). The prompt lists such characters, known from
   earlier turns, apart from KNOWN ENTITIES under **UNNAMED CHARACTERS**, each with at most two earlier
   facts about it (the latest that describes it — trait, identity or status — and the latest of any
   kind, with their turn and evidence quote): the turn that showed it may be beyond the context window
   or cut to 2,000 characters. A closing line after the target turn asks the model to check each one
   and, if the turn shows who it is, to add `also_called` with the name as subject and the description
   as listed as value. A character counts as unnamed while every name it goes by starts with `?`.
3. **Participants are hinted (amends ADR 0021).** KNOWN ENTITIES and UNNAMED CHARACTERS take typed
   participants as mentions too, after the subject and object of the same row: a character first shown
   without a name is often only a participant. Participants still never create alias edges, and they do
   not change the spelling, names or grouping of an entity that subjects and objects define.
4. **Alias evidence (amends ADR 0012 item 2).** An `also_called` is valid when both names occur in the
   target turn (as before), or when one does and the other is exactly a name of the same type that this
   extraction was shown in KNOWN ENTITIES or UNNAMED CHARACTERS (the recorded `hints`). Anything else
   stays `pending`. The resolver rules for narration and self-introductions are unchanged.
5. **Display name.** An entity is named after its first mentioned name that does not start with `?`,
   so a revealed character takes its name even when the description came first (`resolve-v4`, with
   ADR 0025).
6. **Generation.** The prompt, the registry description of `also_called` and the hint block change, so
   `extract-v9` is a new extractor generation (D20). As with every generation, only each chat's recent
   window is re-extracted (ADR 0014); older turns keep their `extract-v8` labels until "extract all
   history".

## Consequences

- Measured on the real turns of the owner's two chats (3 runs each, `gemma4:31b-cloud`, prompts built
  from the production facts; `docs/perf/extract-v9.md`, chat text not committed): the speech-level,
  form-of-address and relationship-allowed turns went from 0/3 major to 2/3–3/3, the device incident
  from 0/3 to 3/3, and routine turns stayed minor. The admission was major in 2/3: models tend to
  record the past act, not the admission. The reveal turn linked the description in 12/12 chained runs
  (0/3 with `extract-v8`). On synthetic scenes `deepseek-v4.1-flash` reached at least 2 of 3 runs on every new scene; `gemma4:31b`
  extracted no event at all in three short dialogue scenes. No Phase 6–8 bar got worse beyond one-run
  variance.
- More events are `major`. Within the event cap of 3, major events come first by mention (ADR 0020), so
  a character with many major events fills the cap with them; older major events of a long chat can
  crowd out newer ones. The cap and ranking are unchanged and measured only by the existing memory
  evaluation.
- A model can link a listed description to the wrong named character. The alias lives only while its
  turn is active, the Inspector shows its turn, and the owner can join names by hand (ADR 0025); an
  owner "split" of an automatic alias is not part of this change.
- The `?` names reach the packet as written (e.g. `?검은 망토의 남자`), which tells the response model the
  identity is not known. Names written by `extract-v8` and earlier have no `?`; they are not listed as
  unnamed, so their reveal is linked only by hand.
- Prompt cost: see `docs/perf/extract-v9.md` (the salience text and the unnamed rule add tokens to every
  call; the closing line only when an unnamed character is listed).
