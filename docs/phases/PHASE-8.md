# Phase 8 — Event Participants

> **Status: DRAFT for owner approval (2026-09-24). Not authorized.** Nothing in this document may be
> implemented until the owner approves it and answers the open questions below. This is the next
> slice of Track B stage B3 (`docs/proposals/TRACK-B-PHASE-5-PLUS.md` §6, "Event, relationship, and
> open-thread projections": "first-class events with participants"), narrowed to what current evidence
> supports; this document is its B0. Phase 7 (`v0.1.0-beta.14`) took promise threads and event
> salience from the same stage.

## Open questions for the owner

Each question has a recommended answer. The spec below is written for the recommended answers. A
different answer changes only the parts it names.

| # | Question | Recommended | Alternatives |
|---|---|---|---|
| Q1 | **Phase boundary.** What remains of B3: event participants, place, observers, narrative time, relationship history, other thread kinds, causal links. Which part is Phase 8? | **Participants only**: the other characters an event (or another fact told in its value) involves. It is the one measured gap (below). Relationships are measured in this phase's real-model tier, as report-only evidence for a later decision. | (b) Participants and relationship history in the packet ("used to be rivals until turn 40"). No relationship was ever extracted in the recorded runs, so this would be built without evidence. (c) First-class event records (participants, place, observers, narrative time). |
| Q2 | **How are participants recorded?** | By the extractor: a new field `with` (the other characters or groups the value involves, as named in the turn), stored in `assertion.participants` (migration 0017) under a new generation `extract-v8`. Names are resolved to entities at read time like subjects and objects (ADR 0012). | (b) At read time, by finding known entity names in the value text. No new generation, but a name can be an ordinary word: "하나" is also "one", and the Phase 6 scene text has "성냥은 하나도 없었다" ("not a single match left"). (c) Allow one `object` on `event` (one participant only; still a new generation). |
| Q3 | **Which assertions carry participants?** | Every assertion with a value text (`event`, `goal`, `knows`, `destroyed`, `fulfilled`, `has_status`, `identity`, `world_fact`, `has_trait`). The gap shows in five of them (below); one rule is simpler for the model than a list. | (b) `event` only (51 of the 85 measured cases). |
| Q4 | **How does a participant count for recall?** | Like the subject: a participant named in the user's message scores as a mention (2.0), in the previous reply 1.0. The persona's names never count, as for threads (ADR 0019). The event cap and salience (ADR 0020) and knowledge marks (D19) are unchanged. | (b) Weaker than the subject (e.g. 1.5), so facts about the addressed character come first. (c) Only in the Inspector. |
| Q5 | **Turns extracted before `extract-v8`** have no participants. | Nothing at read time: they recall as today until **Extract all history**. A second, text-based rule for older turns would give two answers to the same question depending on the generation. | (b) Q2 (b) as a fallback for older generations only. |

## Goal

A fact about two people is remembered from both sides. After Phase 8:

- when the user talks to or about a character, the events that happened *to* them (not only *by*
  them) can reach the packet: 하나's confession to 카이토 comes back when 카이토 is addressed;
- a character's page in the Inspector lists the events and facts they take part in;
- nothing about who took part is guessed from text matching; the extractor names participants and the
  resolver links them, as it does for subjects and objects.

## Evidence behind the scope

**A quarter of events name a second character that recall never sees.** In the 280 recorded
real-model runs (`fixtures/model/phase5/`, `phase6/`, `phase7/`; Korean synthetic scenes,
`deepseek-v4.1-flash`), 51 of 223 valid `event` assertions name another character only inside `value`:

- `유이 event: 카이토에게 은빛 열쇠를 건넸다` (gave 카이토 the silver key);
- `산적들 event: 다리 위에서 카이토를 덮쳐 왔다` (bandits attacked 카이토 on the bridge);
- `늙은 선장 event: 폭풍 속에서 하나의 품에서 숨을 거두었다` (the captain died in 하나's arms).

The same happens in other value-carrying predicates:

| Predicate | Assertions naming another character only in `value` |
|---|---:|
| `event` | 51 of 223 |
| `destroyed` | 12 of 25 |
| `goal` | 10 of 35 |
| `knows` | 10 of 19 |
| `fulfilled` | 2 of 6 |

**Mention-based recall ignores them.** `relevant_facts` counts a mention only for the subject and
object entities (`names`). A deterministic check (2026-09-24; the function as released in beta.14):
three events whose second participant is 카이토, each labeled major and then unlabeled, against three
queries addressing 카이토 ("카이토야, 오랜만이야.", "카이토, 괜찮아?", "카이토는 어디 있어?"). 0 of 18
selected the event. The lexical bar does not help: the name is a small part of the fact's trigrams.
One of the three was 하나's confession to 카이토. Addressing 카이토 is when that fact matters most.

**Relationships are not in the evidence.** No `relationship` assertion appears in the 280 runs (no
scene was about one), and `feels_toward` appears 3 times. Whether the extractor records relationship
changes, and whether the packet needs their history, is unknown. Phase 8 measures it (Real-model tier)
and builds nothing for it.

**Goals as threads stay out** for the reason Phase 7 gave (most extracted goals are next-scene plans).

## In scope

1. **Participants field (Q2, Q3).** Extraction item field `with`: a list of names of other characters or
   groups the value involves, as the TARGET turn names them, at most 6. Validation keeps names only
   (strings, ≤ 60 characters, not the subject or object, no duplicates) and only on assertions that
   have a value. Migration 0017: `assertion.participants text[]`, NULL for every existing row.
2. **Extraction `extract-v8`.** Registry unchanged; the prompt gains one rule: `with` lists the other
   characters or groups the value is about (who received, who was attacked, who is kept from
   something). It lists only names in the TARGET turn, never the subject or object again, and never a
   place or item. New generation: recent window only, older turns served by `extract-v7` (ADR 0014).
3. **Resolution.** Participant names resolve like subjects and objects (type `character`, then `group`;
   ADR 0012), and are shown as entities or as unresolved text. They join the fact's `names`, so aliases
   work. They are not part of any version key: a participant never makes two facts different or the
   same.
4. **Recall (Q4).** A participant is a mention like the subject: 2.0 in the user's message, 1.0 in the
   previous reply. Persona names excluded. Event cap, salience and minor-event lexical bar unchanged.
5. **Packet.** The fact line is unchanged (the value already names the participant). No new attribute,
   no Note sentence, no plugin change.
6. **Inspector (read-only).** The facts table shows participants. A character's page gains "Takes part
   in": the facts where they are a participant but not the subject or object.
7. **Evaluation (below):** deterministic cases, a real-model tier with a relationship report, a
   latency bound.

## Out of scope

- Relationship projections of any kind: history lines in the packet, inverses, symmetry, perspective.
  This phase only measures relationship extraction.
- Event place, observers and privacy as fields. `located_in` and knowledge marks (D19) stay as they
  are, and observers are not knowledge.
- Narrative time, event links and causal links.
- Thread kinds other than promises (Phase 7 Q1).
- Deriving participants from text at read time for any generation (Q2 b, Q5 b).
- Participants on assertions without a value (`possesses`, `located_in`, `member_of`,
  `relationship`, `feels_toward`, `promised`: their object already names the other party).
- Knowledge inference from participation ("카이토 took part, so 카이토 knows"). That is Track B, B5.
- Canon sources (B4), principal-aware knowledge and hard POV (B5), MCP and forensic recall (B6), owner
  repair (B7).
- Any change to the plugin's request path, gating or deadline.

## Upgrade and cost

- Migration 0017 adds one nullable column; no backfill.
- With an LLM configured, `extract-v8` becomes active at startup. Each chat re-extracts its latest
  `NMOS_EXTRACT_BACKFILL` turns (default 100) once. That is the second such re-extraction in two
  releases, after beta.14's `extract-v7`. Older turns keep their `extract-v7` facts, without participants, until "extract all
  history".
- The prompt grows by one field in the answer schema and one rule: an estimated +2–4 % prompt tokens,
  and a few completion tokens per assertion with participants. Both measured and stated in the release
  notes.
- With extraction off: nothing changes.

## Evaluation

### Deterministic tier (CI)

New cases in `apps/sidecar/tests/memeval.py` and unit tests. Every existing case keeps passing.

| Case | Must hold |
|---|---|
| addressed participant | "Hana confesses to Kaito." (event with `with: [Kaito]`), 12 turns later "Kaito, long time no see.": the event is in the packet |
| subject still counts | the same event comes back when Hana is addressed, as before |
| alias | the participant is named by an alias ("하나(Hana)" established earlier): still a mention |
| persona participant | an event with `with: [{{user}}]` does not come back for a query naming only the persona |
| minor event | a minor event with a participant still needs the query to be about it (ADR 0020) |
| cap | participant mentions do not exceed the event cap |
| not a version key | two events differing only in participants stay two facts only if their values differ; a participant never merges or splits facts |
| validation | `with` on `possesses` is dropped; the subject or object repeated in `with` is dropped; non-string entries are dropped |
| older generation | a v7 row has no participants and recalls as before |
| Inspector | the character page lists "Takes part in" facts; the facts table shows participants |
| edit | editing the turn away removes the fact and its participants on the next read |

### Real-model tier (evidence, not CI)

Korean synthetic scenes (labeled as such), three runs each, with the configured extraction model.
Prompts, raw outputs, model and endpoint go under `fixtures/model/phase8/`, and a summary goes to
`docs/perf/phase8-extraction.md`. Scenes:

- two-person events: giving, attacking, confessing, rescuing (at least two each for giving and
  confessing);
- a group event (bandits attack two travelers);
- a goal and a knowledge fact about another character;
- controls: solo events (a walk, cooking), an event at someone's house without them ("하나는 카이토의 집
  앞을 지나갔다"), and a scene with "하나도" as a word and no character 하나;
- **relationship report (no bar):** a friendship turning into rivalry, a confession accepted
  (becoming lovers), and a reconciliation. Recorded: whether `relationship` or `feels_toward` is
  extracted, whether the new value supersedes the old one (read with the fact fold), and whether the
  history would answer "what were they before".

The Phase 5, 6 and 7 scenes are re-run with `extract-v8`.

### Performance

`tools/bench_facts.py --phase7` with participants on half of the events, at 1k / 5k / 10k, alternately
against beta.14. Fact read (with participant resolution and mention scoring) adds at most 15 ms p50 at
10k.

## Acceptance criteria

- [ ] Every deterministic case above passes in CI, and every existing evaluation case still passes.
- [ ] Two-person and group scenes: the other participant(s) are in `with` in at least two of three
      runs per scene.
- [ ] Goal and knowledge scenes: the other character is in `with` in at least two of three runs.
- [ ] Controls: no participant in any run that the TARGET turn does not name as a person, and none in
      the "하나도" scene.
- [ ] The Phase 5, 6 and 7 bars still hold with `extract-v8`.
- [ ] Relationship report recorded (numbers, no bar).
- [ ] Prompt and completion tokens per turn, v7 against v8, measured and in the release notes.
- [ ] Fact read at 10k: at most +15 ms p50 against beta.14.
- [ ] Upgrade from a `v0.1.0-beta.14` database: migration 0017 applies, only the recent window is
      queued, older turns are served by `extract-v7` and recall as before.
- [ ] A real-host smoke run (PocketRisu v1.12.0) injects an event by addressing its participant, not
      its subject. The plugin is unchanged.
- [ ] `ARCHITECTURE.md` (a new decision for participants), an ADR for participants, README, the Korean
      guide, `docs/KNOWN-ISSUES.md` and the changelog updated.

## Implementation order

Each step is one reviewable change with its tests.

1. **Schema and validation**: migration 0017, `with` normalization, stored participants; nothing reads
   them yet.
2. **Resolution and recall (Q4)**: participants in `names`, mention scoring, persona exclusion; works on
   rows written by stub extractors in tests.
3. **`extract-v8`**: the prompt rule and answer field; stub rules for the deterministic cases.
4. **Inspector**: participants column, "Takes part in".
5. **Evaluation and release**: real-model tier with the relationship report, measurements, docs,
   release notes with cost.

## Stop conditions

Stop and ask the owner when:

- the model lists people the turn does not name, or places or items, in the control scenes, and a
  prompt fix does not stop it;
- participant recall pulls in facts about a character that the turn only mentions in passing often
  enough to crowd the packet (the event cap should prevent this; if it does not, the rule is wrong);
- a participant would need to change a version key, a knowledge mark or a thread;
- the relationship report shows a current-state error that users would hit (a later phase needs the
  owner's decision; this phase does not fix it);
- a second migration, a stored projection or a new runtime dependency seems necessary;
- a change would overwrite old assertions or extractions instead of adding a generation.
