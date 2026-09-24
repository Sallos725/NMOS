# Phase 7 — Promise Threads and Event Salience

> **Status: approved by the owner on 2026-09-24, with the recommended answer to every question
> (Q1–Q5).** Implementation follows "Implementation order" below. This is Track B
> stage B3 (`docs/proposals/TRACK-B-PHASE-5-PLUS.md` §6, "Event, relationship, and open-thread
> projections"), narrowed to what current evidence supports; this document is its B0.

## Owner decisions (2026-09-24)

The owner chose the recommended answer to each question. The spec below is written for those answers.

| # | Question | Decided | Alternatives not taken |
|---|---|---|---|
| Q1 | **Phase boundary.** B3 lists events (participants, place, observers, narrative time), versioned relationships, open threads of nine kinds, causal links and event salience. Which part is Phase 7? | **Promise threads and event salience.** These are the two measured gaps (below). First-class event records, relationship history in the packet, other thread kinds, causal links and narrative time wait for their own evidence. | (b) Add goals as threads (see "Evidence": most extracted goals are short plans that would stay open). (c) The whole B3 stage. |
| Q2 | A promise is almost always **said in dialogue**, so it is extracted as a character claim, and half the time as `hypothetical` (never in the packet). When does a promise open a thread? | A `promised` assertion opens a thread when the one who **makes** it says it (speaker = subject) or the narration states it, with modality `actual` or `hypothetical`. Saying a promise is what makes it (a performative), and its content is always in the future. A promise reported by someone else stays a claim. `extract-v7` also tells the model that a promise that was made is `actual`. | (b) Only narrated `actual` promises (today's fact rule; loses most promises). (c) Any `promised` assertion, whoever reports it. |
| Q3 | How does a thread **close**? | The extractor is shown the chat's **open promises** (like KNOWN ENTITIES, ADR 0012) and records a new predicate `fulfilled` (kept) or a negative `promised` (broken, withdrawn, released) with the listed text. The read-time fold matches it to the open thread of the same maker by text. A resolution that matches nothing, or more than one thread, closes nothing and shows in the Inspector. | (b) Store the thread's id in the resolving assertion (a new column; breaks when the opening turn is re-extracted under a later generation). (c) No closing in this phase: threads stay open until owner repair (B7). |
| Q4 | **Event salience.** How do important events get ahead of minor ones? | Both: (1) a **cap** of 3 events among the facts in a packet, applied at read time to all data at once; (2) the extractor labels each `event` `major` or `minor` (`extract-v7`, one nullable column, migration 0016). Within the cap, major events come first; a minor event needs a lexical match with the query, a name mention alone is not enough. Unlabeled events (older generations) keep today's rule inside the cap. | (b) The cap only: no label, no migration. (c) Neither. |
| Q5 | **Packet form** of an open promise. | A `<Threads>` section after `<State>` and before `<Facts>`, at most 3 open promises whose maker or recipient is mentioned now (the user's persona does not count as a mention). One sentence in the Note, added only when the section is present: a thread is a promise made and not yet kept or broken. A promise that is a thread is not repeated as a `<Fact>` or `<Claim>`. | (b) Keep promises as `<Fact>` / `<Claim>` lines with `status="open"`, in the facts budget. (c) Inspector only. |

## Goal

The memory keeps track of what the story has left open, and spends the packet on what matters. After
Phase 7:

- a promise made in dialogue is remembered as an open promise until the story keeps or breaks it
  (Q2, Q3), and it reaches the packet when its maker or recipient comes up again, however long ago it
  was made (Q5);
- a kept or broken promise leaves the packet and stays in the thread's history with the turn that
  closed it;
- the newest events of a character no longer fill every fact slot; important events rank ahead of
  minor ones (Q4).

## Evidence behind the scope

**Promises are extracted but never become facts.** In the Phase 5 real-model tier
(`fixtures/model/phase5/`, scene "plan to meet", Korean synthetic, `deepseek-v4.1-flash`), 하나 says
she will meet the user at the lighthouse when the rain stops. All 6 runs extracted
`하나 promised {{user}}: 비가 그치면 내일 아침 등대 앞에서 만나기`, every one as `source=character_claim`
(ADR 0013: a statement in dialogue is a claim). 3 of 6 labeled it `hypothetical`, which keeps it out
of the packet altogether (ADR 0013, item 3); the other 3 reach the packet only as a `<Claim>`, in the
claims budget (half the facts limit), where they compete by recency with every other claim about 하나.

**Older facts lose every fact slot to recent events.** `relevant_facts` scores a fact 2.0 when a name
it involves is in the user's message, adds the lexical overlap, and breaks ties by position (newest
first). A deterministic check (2026-09-24; synthetic facts, the function as released in beta.13): one
narrated promise of 하나 at turn 10 (a fact) and 185 minor events of 하나 at turns 15–199, `facts_limit` 8.

| Query | Facts returned |
|---|---|
| "하나야, 오랜만이야." | 8 events, turns 192–199; no promise |
| "하나랑 같이 걷는다." | 8 events, turns 192–199; no promise |
| "하나, 등대 기억나?" | the promise (shares "등대"), then 7 events |

So the promise, like any older non-event fact about a main character, is recalled only when the user
happens to repeat its words, which is the case where the reminder matters least.

**Events are the most frequent predicate.** Actual `event` assertions per extracted turn in the
real-model tiers (synthetic scenes of 1–3 turns): 51 in 62 runs and 43 in 62 (Phase 5), 39 in 43
(Phase 6). `event` is multi-valued, so every one stays current: a chat of thousands of turns holds
thousands of current events, and any mention of a main character ties them all.

**Goals are mostly short plans.** Of the 22 `goal` assertions in the same tiers, 12 are plans for the
next scene or the next day ("도서관에 가기", "비가 그치면 등대에 가 보기", 10 of them beside the promise
they restate) and 5 are aims the same turn carries out ("편지를 아무도 보지 못하게 하는 것", then the
letter is burned). Only 5 are a lasting resolve ("카이토에게 편지를 보여주지 않는 것"). As threads, the
plans would stay open after they are carried out, because the extractor records the visit as an
`event`, not as the goal's end. That is why Q1 leaves goals out.

**Not in the evidence yet**, and therefore out of scope until measured: wrong current relationships
(`relationship` and `feels_toward` are already versioned per pair, D6), a question about a
relationship's past, events needing participants or places as structure, and causal questions.

## In scope

1. **Event cap (Q4, part 1; read time).** Fact selection (`relevant_facts`) takes at most
   `NMOS_EVENTS_LIMIT` (default 3, runtime setting, 0–`facts_limit`) `event` facts per packet; the
   other slots go to the remaining relevant facts. No generation change: it applies to existing data
   at once.
2. **Thread fold (Q2, Q3; read time).** A deterministic fold over the head's `promised`, `fulfilled`
   and negative `promised` assertions, per maker entity (ADR 0012), in position order, then extraction
   order within a turn. A `promised` assertion opens a thread when its source is narration, or a claim
   whose `asserted_by` resolves to its subject, and its modality is `actual` or `hypothetical`.
   `dreamed` and `unknown` promises, and promises reported by a third party, stay claims or other
   assertions as today. Each thread has a status: `open`, `kept` (closed by `fulfilled`) or `broken`
   (closed by a negative `promised`), with the closing assertion as evidence. Nothing is stored: the
   result is a function of head membership, the served extractions (ADR 0014) and entity resolution.
   An edit or delete that removes the promise, or its resolution, changes the next read.
3. **Matching a resolution to a thread (Q3).** A resolution matches the open threads of the same maker
   entity (and the same recipient, when the resolution names one): first by equal normalized text,
   otherwise by the single thread whose trigram similarity to the resolution's text is at least
   `THREAD_MATCH_MIN` (set on the deterministic cases, stated in the ADR) and ahead of the next one by
   a margin. No match, or a tie, closes nothing; the Inspector lists it as an unmatched resolution.
4. **Extraction `extract-v7`.**
   - Registry: `fulfilled` (subject: `character` | `group`; value: the promise or aim that was carried
     out, as OPEN PROMISES lists it).
   - Prompt: a promise that was made is `actual` (its content is in the future by nature);
     `fulfilled` when the TARGET turn carries out a listed promise; `promised`, negative, when it
     breaks, withdraws or releases one; copy the listed text. For every `event`: `salience`, `major`
     when it changes the story (a confession, a betrayal, a death, a first meeting, a secret revealed,
     a decision that changes a relationship or a goal) and `minor` otherwise.
   - Input: an OPEN PROMISES block (at most 8, open threads before the target turn whose maker or
     recipient is mentioned in the target turn or its context, newest first), stored with the
     extraction's hints (ADR 0012) for provenance.
   - This is a new extractor generation: recent window only, older turns served by `extract-v6`
     (ADR 0014). Older turns never contain `fulfilled` or a salience label.
5. **Event salience (Q4, part 2).** Migration 0016: `assertion.salience text NULL CHECK (salience IN
   ('major', 'minor'))`, NULL for every existing row and for every non-event assertion. Validation
   drops the field from other predicates and stores a missing or invalid value as NULL. Within the
   event cap, a major event ranks ahead of any minor or unlabeled one at equal mention score, and a
   minor event is kept only when its lexical overlap with the query reaches the existing bar (0.35).
6. **Packet (Q5).** `<Threads>` after `<State>`, before `<Facts>`:
   `<Thread kind="promise" by="하나" to="{{user}}" turn="10">비가 그치면 등대 앞에서 만나기</Thread>`.
   At most 3 open threads (`NMOS_THREADS_LIMIT`, runtime setting, 0 turns the section off) whose
   maker or recipient is mentioned in the user's message or the previous reply, other than the user's
   persona; mention in the user's message first, then newest. A thread whose opening message is still
   in the prompt is left out (D3). Budget order: state, threads, facts, claims, excerpts. The Note
   sentence is added only when a thread line is kept. No plugin change.
7. **Inspector (read-only).** A threads list per conversation: open, kept and broken promises with
   maker, recipient, opening turn, closing turn and evidence; unmatched resolutions. Event facts show
   their salience (or "—" for unlabeled).
8. **Evaluation (below):** deterministic cases, a real-model tier, a latency bound.

## Out of scope

- First-class event records (participants, place, observers, privacy) and event links. Events stay
  `event` assertions. A structure needs a recorded question it would answer that the assertion cannot.
- Narrative (story) time, partial or relative. Threads and salience use transcript order.
- Thread kinds other than promises: goal, mystery, debt, threat, meeting, missing item, unanswered
  question, unfinished task (Q1). Goals stay facts and claims as today.
- Thread expiry, or closing a thread because it is old. Only the story (or, later, the owner) closes
  one.
- Relationship projections: history lines in the packet, inverses, symmetry, perspective.
- Causal links beyond a resolution's evidence (Track B §6 B3 "initial causal-link scope" is limited to
  fulfills/breaks here, and those are the resolution itself).
- Salience for anything but `event`, deleting or down-sampling minor events (the owner's 2026-09-23
  note: salience is a priority, never a reason to delete), and any change to excerpt ranking.
- Stored threads, a thread queue, owner resolution (B7).
- Canon sources (B4), principal-aware knowledge and hard POV (B5), MCP and forensic recall (B6).
- Any change to the plugin's request path, gating or deadline.

## Upgrade and cost

- Migration 0016 adds one nullable column; no backfill.
- With an LLM configured, `extract-v7` becomes active at startup. Each chat re-extracts its latest
  `NMOS_EXTRACT_BACKFILL` turns (default 100) once. Older turns keep their `extract-v6` facts until
  "extract all history": their promises open threads (Q2 applies at read time) but cannot close, and
  their events are unlabeled. The prompt grows by one registry line, three rules and the OPEN PROMISES
  block: an estimated +5–8 % prompt tokens per turn, to be measured and stated in the release notes.
- With extraction off: the event cap and the thread fold apply to existing assertions at once;
  nothing closes a thread and no event is labeled.

## Evaluation

### Deterministic tier (CI)

New cases in `apps/sidecar/tests/memeval.py` and unit tests for the fold and fact selection. Every
existing case keeps passing.

| Case | Must hold |
|---|---|
| promise recalled | 하나 promises (turn 10, claim by 하나); 90 turns of 하나's minor events later the user writes "하나야, 오랜만이야.": the packet has the promise in `<Threads>` |
| spoken, hypothetical | the same promise labeled `hypothetical` (older-generation behavior) still opens the thread |
| reported promise | 카이토 says 하나 promised something: no thread; a `<Claim>` as today |
| dreamed promise | a promise in a dream: no thread |
| kept | a later `fulfilled` with the listed text closes it: `kept`, not in the packet, history keeps both turns |
| kept, reworded | `fulfilled` text differs a little from the promise: matched by similarity |
| broken | a negative `promised` closes it as `broken` |
| two promises | 하나 has two open promises; a resolution close to both closes neither and is listed as unmatched |
| other maker | 카이토's `fulfilled` never closes 하나's promise |
| edit removes the resolution | the kept turn is edited away: the thread is open again on the next read, before any re-extraction |
| delete removes the promise | the promise turn is deleted: no thread |
| in context | a promise whose message is still in the prompt: not in `<Threads>` |
| persona only | a query naming only the user's persona does not bring in threads |
| event cap | the check above: at most 3 events among the facts, the rest of the slots go to other relevant facts |
| salience | with a major event at turn 20 and minor ones after it, a mention brings the major event first; a minor event without lexical overlap is not kept |
| unlabeled | older-generation events rank as today inside the cap |
| rebuild | discarding and re-extracting a chat reproduces the same threads and statuses (stub extractor) |
| determinism | the same head and extractions give the same threads regardless of row insertion order across turns |

### Real-model tier (evidence, not CI)

Korean synthetic scenes (labeled as such), three runs each, with the configured extraction model.
Prompts, raw outputs, model and endpoint go under `fixtures/model/phase7/`, and a summary goes to
`docs/perf/phase7-extraction.md`. At least two scenes each:

- a promise made in dialogue; a promise made in narration; a conditional promise;
- a promise kept a few turns later (with OPEN PROMISES shown); a promise broken; a promise released by
  its recipient;
- control: a turn unrelated to an open promise (OPEN PROMISES shown), and a promise only discussed
  ("remember what you promised?");
- control: a promise reported by a third party;
- events: major (a confession, a betrayal, a first meeting, a secret revealed) and minor (a walk, a
  meal, small talk with an action).

### Performance

`tools/bench_scale.py` facts tier at 1k / 5k / 10k with promise threads and events. Fact read with the
thread fold and the cap adds at most 30 ms p50 at 10k. The OPEN PROMISES query runs in the worker,
not on the request path; its cost per extraction is measured and reported.

## Acceptance criteria

- [ ] Every deterministic case above passes in CI, and every existing evaluation case still passes.
- [ ] Promise scenes (dialogue, narration, conditional): a thread opens in at least two of three runs.
- [ ] Kept, broken and released scenes: the thread closes with the right status in at least two of
      three runs.
- [ ] Control scenes: no `fulfilled` and no negative `promised` for a promise the turn does not keep
      or break, in any run.
- [ ] Reported-promise controls: no thread in any run.
- [ ] Major-event scenes labeled `major` and minor-event scenes labeled `minor` in at least two of
      three runs each.
- [ ] The Phase 5 and Phase 6 bars still hold on their scenes with `extract-v7` (at most 10 % of
      actual-event assertions labeled non-actual; `destroyed` bars of `docs/phases/PHASE-6.md`).
- [ ] Prompt tokens per turn, v6 against v7, measured and in the release notes.
- [ ] Fact read at 10k: at most +30 ms p50 in the facts tier.
- [ ] Upgrade from a `v0.1.0-beta.13` database: migration 0016 applies, only the recent window is
      queued, older turns are served by `extract-v6`, and their promises show as open threads at once.
- [ ] A real-host smoke run (PocketRisu v1.12.0) injects a packet with an open promise from outside
      the prompt window. The plugin is unchanged.
- [ ] `ARCHITECTURE.md` (a new decision for threads and salience; D6 registry note), ADRs for the
      thread fold and for event salience, README, the Korean guide, `docs/KNOWN-ISSUES.md` and the
      changelog updated.

## Implementation order

Each step is one reviewable change with its tests.

1. **Event cap (Q4, part 1)**: read-time only, no generation change. Useful on its own, and it
   applies to existing data at once.
2. **Thread fold and packet (Q2, Q3, Q5)**: open threads from existing `promised` assertions,
   closing by a negative `promised` (older generations already produce it), matching (item 3), the
   `<Threads>` section and the Note sentence. Read-time only (ADR 0019).
3. **`extract-v7` and migration 0016 (Q3, Q4 part 2)**: `fulfilled`, the prompt rules, OPEN PROMISES
   hints, `salience`; stub rules for the deterministic cases.
4. **Salience ranking**: major-first ranking and the lexical bar for minor events.
5. **Inspector**: threads, unmatched resolutions, event salience.
6. **Evaluation and release**: real-model tier, measurements, docs, release notes with cost.

## Stop conditions

Stop and ask the owner when:

- a thread would have to be closed by inference the story did not state (a promise "probably"
  forgotten, a meeting that "must have" happened);
- matching needs information the stored assertions do not carry (an id, a time inside a turn);
- the real-model tier shows false `fulfilled` or false breaks in control scenes, or misses opening or
  closing below the bar, and a prompt fix does not bring it within the bar;
- salience labels do not separate the major and minor scenes (the cap alone then stays, and part 2
  needs a new decision);
- open threads pile up in a long real chat faster than the story closes them (a sign that the opening
  rule is too wide);
- a second migration, a stored projection or a new runtime dependency seems necessary;
- a change would overwrite old assertions or extractions instead of adding a generation.
