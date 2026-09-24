# Phase 8 — Event Participants

> **Status: implemented (2026-09-24); every acceptance criterion met but one, which awaits the
> owner's decision (below); not released.** Approved by the owner on 2026-09-24, with the recommended
> answer to every question (Q1–Q5). Evidence: `docs/perf/phase8-extraction.md`, ADR 0021. This is the next
> slice of Track B stage B3 (`docs/proposals/TRACK-B-PHASE-5-PLUS.md` §6, "Event, relationship, and
> open-thread projections": "first-class events with participants"), narrowed to what current evidence
> supports; this document is its B0. Phase 7 (`v0.1.0-beta.14`) took promise threads and event
> salience from the same stage.

## Owner decisions (2026-09-24)

The owner chose the recommended answer to each question. The spec below is written for those answers.
In the owner's words: participants only (Q1); typed `with: [{name, type}]` from the extractor, stored as
JSON, no read-time text inference (Q2); only `event`, `goal`, `knows`, `destroyed` (Q3); a participant
counts like the subject for facts and character claims, the persona never counts, and participation
never infers or changes a knowledge mark (Q4); no read-time fallback before `extract-v8` (Q5). KNOWN
ENTITIES must not change because of participants; the ADR 0012 amendment and the acceptance criteria
apply as written.

| # | Question | Decided | Alternatives not taken |
|---|---|---|---|
| Q1 | **Phase boundary.** What remains of B3: event participants, place, observers, narrative time, relationship history, other thread kinds, causal links. Which part is Phase 8? | **Participants only**: the other characters an event (or another fact told in its value) involves. It is the one measured gap (below). Relationships are measured in this phase's real-model tier, as report-only evidence for a later decision. | (b) Participants and relationship history in the packet ("used to be rivals until turn 40"). No relationship was ever extracted in the recorded runs, so this would be built without evidence. (c) First-class event records (participants, place, observers, narrative time). |
| Q2 | **How are participants recorded?** | By the extractor: a new field `with`, a list of `{name, type}` objects for the other characters or groups the value involves, as named in the turn. It is stored in `assertion.participants` as JSON (migration 0017) under a new generation `extract-v8`. A stored type is required because ADR 0012 keys identity by `(type, name)`; an untyped name must not silently prefer a character over a same-named group. | (b) Store names only and resolve `character`, then `group`. This guesses when both types have the same name. (c) At read time, find known entity names in the value text. No new generation, but a name can be an ordinary word: "하나" is also "one", and the Phase 6 scene text has "성냥은 하나도 없었다" ("not a single match left"). (d) Allow one `object` on `event` (one participant only; still a new generation). |
| Q3 | **Which assertions carry participants?** | Only the predicates where the recorded runs show the gap: `event`, `goal`, `knows`, and `destroyed` (78 usable assertions in 18 scenes; below). `event` carries most of it (51 in 15 scenes); `destroyed` (12 in 2), `knows` (10 in 3) and `goal` (5 in 2) rest on few scenes, and the real-model tier adds one scene for each. `fulfilled` is excluded even though two values name another character: ADR 0019 consumes every resolution in the thread fold, so it has no fact-recall or character-page consumer in this phase. | (b) `event` only (51 of the 78 usable assertions, 15 of the 18 scenes). (c) Every value-bearing predicate except aliases and thread resolutions; this would include predicates for which no participant behavior has been measured. |
| Q4 | **How does a participant count for recall?** | Like the subject: a participant named in the user's message scores as a mention (2.0), in the previous reply 1.0, for facts and for character claims alike (claims are selected by the same function; 14 of the 78 usable assertions are claims). The persona's names never count, as for threads (ADR 0019). The event cap and salience (ADR 0020) and knowledge marks (D19) are unchanged. | (b) Weaker than the subject (e.g. 1.5), so facts about the addressed character come first. (c) Only in the Inspector. |
| Q5 | **Turns extracted before `extract-v8`** have no participants. | Nothing at read time: they recall as today until **Extract all history**. A second, text-based rule for older turns would give two answers to the same question depending on the generation. | (b) Q2 (c) as a fallback for older generations only. |

## Goal

A fact about two people is remembered from both sides. After Phase 8:

- when the user talks to or about a character, the events that happened *to* them (not only *by*
  them) can reach the packet: `카이토 event: 유이를 경비병들에게 넘겨주었다` (카이토 handed 유이 over to the
  guards) comes back when 유이 is addressed;
- a character's page in the Inspector lists the events and facts they take part in;
- nothing about who took part is guessed from text matching; the extractor names participants and the
  resolver links them, as it does for subjects and objects.

## Evidence behind the scope

**A quarter of events name another person that recall never sees.** The scope audit
[`fixtures/model/phase8/scope-audit.json`](../../fixtures/model/phase8/scope-audit.json) lists every
valid `event`, `destroyed`, `goal`, `knows` and `fulfilled` assertion of the 280 recorded real-model
runs (`fixtures/model/phase5/`, `phase6/`, `phase7/`; Korean synthetic scenes, `deepseek-v4.1-flash`):
308 assertions. For each, the other people its value involves were identified by reading the value
(a manual review by the implementing agent, not the owner; the rules are in the file). A participant is
a character or group other than the subject and object that the value acts on, gives to, accompanies
or addresses, or whose possession it is about (`kind: possessor`, e.g. `카이토 knows: 하나의 비밀`).
`python3 tools/check_phase8_scope_audit.py` checks every entry against its run file, fails on a
missing, duplicate or stale entry, and prints the counts below;
`apps/sidecar/tests/test_participant_scope.py` runs it in CI.

| Predicate | Valid | Name another person | Usable | Usable scenes | Not usable |
|---|---:|---:|---:|---:|---|
| `event` | 223 | 62 | 51 (47 facts, 4 claims) | 15 | 11 persona only |
| `destroyed` | 25 | 12 | 12 (facts) | 2 | — |
| `goal` | 35 | 9 | 5 (2 facts, 3 claims) | 2 | 4 hypothetical (never in the packet) |
| `knows` | 19 | 11 | 10 (3 facts, 7 claims) | 3 | 1 persona only |
| `fulfilled` | 6 | 2 | 0 | 0 | 2 thread resolutions (ADR 0019) |

Usable means a Phase 8 predicate, a fact or claim that can reach the packet, and at least one
participant other than the persona: 78 assertions in 18 distinct scenes. The counts come from repeated
runs (three per scene, and the Phase 5 scenes twice, in two fixture directories), so the scene count is
the stronger measure. Examples: `유이 event: 카이토에게 은빛 열쇠를 건넸다`, `산적들 event: 다리 위에서
카이토를 덮쳐 왔다`, `카이토 event: 유이를 경비병들에게 넘겨주었다` (two participants, one a group),
`늙은 선장 event: 폭풍 속에서 하나의 품에서 숨을 거두었다`.

The first draft counted with a fixed name list (85 cases). The review found it wrong both ways. It
counted 12 assertions whose only other person is the persona (a confession, a walk and a meal with
`{{user}}`), which recall never treats as a mention, and one self-alias (`미나토 하루카 goal: 하루라고
불리기`). It missed groups (산적들, 경비병들, 선배 기사들) and people outside the list (왕, 부단장, 보건실
선생님). The fixed-list numbers are withdrawn.

**Mention-based recall ignores them.** `relevant_facts` counts a mention only for the subject and
object entities (`names`). `apps/sidecar/tests/test_participant_scope.py` takes three recorded events
(`유이 → 카이토`, `산적들 → 카이토`, `카이토 → 유이`), each labeled major and then unlabeled, against three
queries addressing only the second person ("…야, 오랜만이야.", "…, 괜찮아?", "…는 어디 있어?"): 0 of 18
select the event, while addressing the subject does. The lexical bar does not help: the name is a small
part of the fact's trigrams. The test states the rule for facts without participant data, so it keeps
holding after Phase 8 for turns of older generations (Q5).

**Taking part is not knowing.** An owner-reported Inspector row (2026-09-24, a real chat, owner's
extraction model `gemma4:31b-cloud`; the chat text is not committed) shows why participants must stay
apart from knowledge marks. In the TARGET turn, A tells B in secret that A once left C's class early
by telling C "my stomach hurts", when the real cause was anxiety. C was present, heard the excuse and
nodded; B, C's child, decides not to write it down "because C might see". The stored fact is
`A event: left C's class early, lying about a stomach ache`, `knowledge=limited`, `known_by={A, B}`,
no `hidden_from`. C is involved in the event (a participant) but is the one person the fact is kept
from. Putting C in `known_by` because C was there would tell the model C knows it was a lie. The turn
also has the shape of the absent-householder control ("C's class") with the opposite answer: here C
was present. The deterministic and real-model tiers below include this case.

**Relationships are not in the evidence.** No `relationship` assertion appears in the 280 runs (no
scene was about one), and `feels_toward` appears 3 times. Whether the extractor records relationship
changes, and whether the packet needs their history, is unknown. Phase 8 measures it (Real-model tier)
and builds nothing for it.

**Goals as threads stay out** for the reason Phase 7 gave (most extracted goals are next-scene plans).

## In scope

1. **Participants field (Q2, Q3).** Extraction item field `with`: a list of objects
   `{name: string, type: "character" | "group"}` for other characters or groups the value involves,
   as the TARGET turn names them, at most 6. Validation keeps entries with a name of at most 60
   characters and one of those two types; drops the subject, object and duplicates by normalized
   `(type, name)`; and keeps the field only on `event`, `goal`, `knows` and `destroyed`. Migration
   0017: `assertion.participants jsonb`, NULL for every existing row. The column contains a JSON array,
   never another shape.
2. **Extraction `extract-v8`.** Registry unchanged; the prompt gains one rule: `with` lists the other
   characters or groups the value is about (who received, who was attacked, who is kept from
   something), with each one's type. It is emitted only for the four predicates in item 1, lists only
   entities named in the TARGET turn, never repeats the subject or object, and never lists a place or
   item. New generation: recent window only, older turns served by `extract-v7` (ADR 0014).
3. **Resolution.** A participant is a typed mention and resolves exactly like a subject or object of
   that type (ADR 0012); it is shown as an entity or as unresolved/ambiguous text. Participants join
   the resolver's mention set under a new `RESOLVER_VERSION`, so a character first seen only as an
   event's participant can have an Inspector page. Different types never merge, and an ambiguous
   alias links nobody. A resolved participant and all of its aliases join the fact's `names`. A
   participant is not part of any version key: it never makes two facts different or the same.
   Participants never change extraction input. They are not KNOWN ENTITIES hint candidates (ADR 0012,
   item 5): `entity_hints` keeps ordering candidates from subject and object mentions only. And they
   rank below every name source of `resolve-v1` (subjects, objects and evidenced alias names) when the
   resolver picks an entity's representative spelling and name order, whatever their transcript
   position: the resolver reads participant mentions in a second pass, after all `resolve-v1`
   sources. A participant-only entity takes its participant spelling (for its Inspector page). An
   entity that `resolve-v1` also knows keeps exactly the name, alias order and grouping it had, so the
   serialized KNOWN ENTITIES block is byte-for-byte the one without participants. This is an amendment
   to ADR 0012, recorded in the Phase 8 ADR.
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
- Deriving participants from text at read time for any generation (Q2 c, Q5 b).
- Participants on predicates outside the measured set. This includes assertions without a value
  (`possesses`, `located_in`, `member_of`), object relations (`relationship`, `feels_toward`,
  `promised`), aliases (`also_called`), thread resolutions (`fulfilled`), and the currently unmeasured
  value predicates (`has_status`, `identity`, `world_fact`, `has_trait`).
- Participants as KNOWN ENTITIES hint candidates. Adding them would change the extraction input: 40
  hints cost ≈350 prompt tokens (`docs/perf/phase5-extraction.md`), and the larger risk is that they push
  existing hints out of a full list. That needs its own token, crowd-out and false-merge evaluation.
- Knowledge inference from participation ("카이토 took part, so 카이토 knows"). That is Track B, B5.
- Canon sources (B4), principal-aware knowledge and hard POV (B5), MCP and forensic recall (B6), owner
  repair (B7).
- Any change to the plugin's request path, gating or deadline.

## Upgrade and cost

- Migration 0017 adds one nullable column; no backfill.
- With an LLM configured, `extract-v8` becomes active at startup. Each chat re-extracts its latest
  `NMOS_EXTRACT_BACKFILL` turns (default 100) once. That is the second such re-extraction in two
  releases, after beta.14's `extract-v7`. Older turns keep their `extract-v7` facts, without
  participants, until "extract all history".
- The resolver becomes `resolve-v2` because typed participants join its mention set. Entity ids and
  Inspector entity URLs are recomputed on the next read, as ADR 0012 specifies for a resolver change;
  no stored source or assertion row is rewritten. Existing aliases and subject/object identity rules
  are otherwise unchanged. KNOWN ENTITIES hints are byte-for-byte unchanged (item 3). Because the
  second pass leaves every `resolve-v1` root in place, only the version string changes existing
  entity ids; the bump still changes every Inspector entity URL once, which is the cost of following
  ADR 0012's rule that a resolver change is a new version.
- The prompt grows by one field in the answer schema and one rule: an estimated +2–4 % prompt tokens,
  and a few completion tokens per assertion with participants. Both measured and stated in the release
  notes.
- With extraction off, no participant data is produced and recall behavior is unchanged. The
  `resolve-v2` id recomputation above still occurs because resolver identity is a code version, not an
  extraction setting.

## Evaluation

### Deterministic tier (CI)

New cases in `apps/sidecar/tests/memeval.py` and unit tests. Every existing case keeps passing.

| Case | Must hold |
|---|---|
| addressed participant | "Hana confesses to Kaito." (major event with `with: [{name: Kaito, type: character}]`), 12 turns later "Kaito, long time no see.": the event is in the packet |
| subject still counts | the same event comes back when Hana is addressed, as before |
| alias | the participant is named by an alias ("하나(Hana)" established earlier): still a mention |
| persona participant | an event with `with: [{name: {{user}}, type: character}]` does not come back for a query naming only the persona |
| minor event | a minor event with a participant still needs the query to be about it (ADR 0020) |
| cap | participant mentions do not exceed the event cap |
| not a version key | otherwise identical events with different participant arrays share one version key; events with different values remain distinct |
| participant is not a knower | a limited event with `known_by: [Kaito, Hana]`, `hidden_from: [Yui]` and `with: [{name: Yui, type: character}]`: addressing Yui brings it back with exactly the stored marks. The same event without `hidden_from` comes back with `known_by="Kaito, Hana"` only, and no mark names Yui. |
| typed identity | a character and group with the same normalized name stay distinct; an ambiguous alias links neither |
| participant-only entity | a typed participant never used as a subject or object still has an entity and character page |
| predicate boundary | `with` is kept on `event`, `goal`, `knows` and `destroyed`; it is dropped on `fulfilled`, `possesses` and every other predicate |
| validation | the subject or object repeated in `with` is dropped; malformed entries, unknown types and normalized duplicates are dropped |
| hints unchanged | a character named only as a participant is not in KNOWN ENTITIES, and the serialized KNOWN ENTITIES block is byte-for-byte the one without participants, including the hard case: a participant spelling of an entity occurs before its first subject/object mention and before the `also_called` that joins its aliases |
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
- a goal, a knowledge fact and a destroyed-item fact about another character;
- controls: solo events (a walk, cooking), an event at someone's house without them ("하나는 카이토의 집
  앞을 지나갔다"), and a scene with "하나도" as a word and no character 하나;
- **secret about a shared event** (modeled on the owner report under Evidence; the text is new and
  synthetic): A tells B in secret that A once lied to C, who was present, to leave C's class early, and
  B promises not to write it down so that C won't see. C is named as "C의 수업", the same shape as the
  absent-householder control, but C was there;
- **relationship report (no extraction-rate bar):** a friendship turning into rivalry, a confession
  accepted (becoming lovers), and a reconciliation. Recorded: whether `relationship` or `feels_toward` is
  extracted, whether the new value supersedes the old one (read with the fact fold), and whether the
  history would answer "what were they before".

The Phase 5, 6 and 7 scenes are re-run with `extract-v8`.

The scope evidence is committed with this draft: `fixtures/model/phase8/scope-audit.json`, checked by
`python3 tools/check_phase8_scope_audit.py`, and the 0-of-18 recall check in
`apps/sidecar/tests/test_participant_scope.py` (both in CI). The Phase 8 summary adds the new scenes
to the same audit format.

### Performance

`tools/bench_facts.py --phase7` with participants on half of the events, at 1k / 5k / 10k, alternately
against beta.14. Fact read (with participant resolution and mention scoring) adds at most 15 ms p50 at
10k.

## Acceptance criteria

- [x] Every deterministic case above passes in CI, and every existing evaluation case still passes.
- [x] Two-person and group scenes: the other participant(s) are in `with` in at least two of three
      runs per scene.
- [x] Goal, knowledge and destroyed-item scenes: the other character is in `with` with the right type
      in at least two of three runs.
- [x] Controls: every solo, absent-householder and "하나도" run has an empty `with`. Separately, every
      participant emitted in a positive scene is named as a character or group in the TARGET turn.
- [x] Secret about a shared event: C is in `with` in at least two of three runs, and C is in
      `known_by` in no run. Whether C is in `hidden_from` is recorded, with no bar: this phase does
      not change knowledge extraction.
- [ ] The Phase 5, 6 and 7 bars still hold with `extract-v8`. *Not met as written (2026-09-24):* all
      hold except the Phase 7 minor-event scene "chores", 1/3 (two runs extracted no event). Ten more
      runs gave `extract-v7` 3/10 and `extract-v8` 4/10 on it, so this is not a regression; no minor
      scene was labeled major. Awaiting the owner's decision (`docs/perf/phase8-extraction.md`).
- [x] Relationship report recorded (numbers, no extraction-rate bar). A result is a later-phase input,
      not a Phase 8 failure unless it exposes an invariant violation or a regression caused by Phase 8.
- [x] The scope audit check and `test_participant_scope.py` still pass; the audit gains the Phase 8
      scenes.
- [x] Prompt and completion tokens per turn, v7 against v8, measured and in the release notes.
- [x] Fact read at 10k: at most +15 ms p50 against beta.14.
- [x] Upgrade from a `v0.1.0-beta.14` database: migration 0017 applies, only the recent window is
      queued, older turns are served by `extract-v7` and recall as before; `resolve-v2` recomputes
      entity ids without rewriting source or assertion rows.
- [x] A real-host smoke run (PocketRisu v1.12.0) injects a major event from outside the prompt window
      by addressing its participant, not its subject, with no lexical overlap beyond the participant's
      name. The plugin is unchanged.
- [x] `ARCHITECTURE.md` (a new decision for participants), an ADR for participants that amends ADR 0012
      (participant mentions, the second pass, hints unchanged), README, the Korean
      guide, `docs/KNOWN-ISSUES.md` and the changelog updated.

## Implementation order

Each step is one reviewable change with its tests.

1. **Schema and validation**: migration 0017, `with` normalization, stored participants; nothing reads
   them yet.
2. **Resolution and recall (Q4)**: typed participants in the resolver's mention set (`resolve-v2`),
   in `names`, mention scoring, persona exclusion, hints unchanged; works on rows written by stub
   extractors in tests.
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
- the relationship report exposes an architecture-invariant violation, or Phase 8 changes relationship
  behavior; an existing non-invariant relationship limitation is recorded for a later owner decision
  and does not by itself fail this phase;
- a second migration, a stored projection or a new runtime dependency seems necessary;
- a change would overwrite old assertions or extractions instead of adding a generation.
