# Phase 6 — Item Transitions and Conflicts

> **Status: complete (2026-09-24), released in `v0.1.0-beta.13`.** Approved by the owner on 2026-09-24,
> with the recommended answer to every question (Q1–Q5). This is Track B
> stage B2 (`docs/proposals/TRACK-B-PHASE-5-PLUS.md` §6), narrowed to what current evidence supports;
> this document is its B0.
>
> The roadmap amendment of 2026-09-23 (Track B §4, owner decision 2) put B2 directly after B1 because
> K9 and K10 are measured current-state errors.

## Owner decisions (2026-09-24)

The owner chose the recommended answer to each question. The spec below is written for those answers.

| # | Question | Decided | Alternatives not taken |
|---|---|---|---|
| Q1 | How does the packet show a **conflict** (two incompatible current states for one key)? | Show the latest value marked `disputed="true"`, with the other value in the same line. The model sees both and is told neither is certain. | (b) Leave the key out of the packet (Inspector only). (c) Latest wins, conflict only in the Inspector (today's behavior, plus visibility). |
| Q2 | An item's **holder** (`possesses`) and **place** (`located_in`) can disagree (K10). How is that resolved? | One item **whereabouts**: the newer of "held by X" and "at place P" is current and closes the other. Both from the same turn stay together ("held by Hana, at the library"). | (b) Keep them as two facts and flag a disagreement as a conflict (Q1). (c) Leave as is (K10 stays). |
| Q3 | How does an item **stop existing** (burned, eaten, used up) without a loss statement (K9)? | A new predicate `destroyed` (subject: item; value: how). It ends the item's whereabouts. It needs a new extractor generation (`extract-v6`), so each chat re-extracts its recent window once (ADR 0014). | (b) Let `has_status` take items ("burned"). This is also a new generation, and a status does not say that the item is gone. (c) No extraction change. K9 stays. |
| Q4 | The story later has someone holding or placing an item it **destroyed** earlier. | A **conflict** (Q1): the later statement is shown as disputed, not silently accepted or dropped. | (b) The later statement wins: the item exists again. (c) The later statement is rejected (Inspector only). |
| Q5 | **O5, the rest:** retention of abandoned worldlines and host observations. This does **not** block Phase 6, which stores nothing new. | **Lossless compaction** of full-manifest host observations. An edit, reroll, swipe or delete stores only the rows that changed against the previous observation, as appends already do (beta.10). Keep everything else. Separate maintenance work, like ADR 0015. | (b) Keep everything as is. (c) Keep only the latest N full observations per chat and hash the rest (lossy: loses evidence). |

Why Q5 matters: in a synthetic 10,000-message chat, every non-append sync (edit, reroll, swipe,
delete) stores the full manifest as its host observation. That is ≈1.1 MB on disk (1.7 MB as text) per
action, while the commit itself is under 1 KB. (Measured 2026-09-24: a `tools/bench_scale.py` chat of
10,000 messages, synced, then one reroll and one edit; `pg_column_size` / text length of
`host_observation.raw_manifest` and `worldline_commit.delta`.) A hundred rerolls in such a chat add ≈110 MB. Vectors
and extractions of off-head revisions are small by comparison: a rerolled reply that the user never
continued from is never accepted, so it is never embedded or extracted.

## Goal

Current state follows the story's transitions for items, and incompatible evidence is shown rather
than settled by row order. After Phase 6:

- a destroyed, eaten or used-up item has no current holder or place (K9 remainder);
- an item has one current whereabouts: held by someone, or at a place (K10);
- evidence that breaks a transition rule is a visible conflict, in the Inspector and (Q1) in the
  packet;
- every current fact can show the transitions that led to it.

Known issues addressed: K9, K10. See `docs/KNOWN-ISSUES.md`.

## Evidence behind the scope

- K9 (ADR 0011 item 4, ADR 0013): a new holder ends the previous one, and so does a loss statement
  (3/3 in the Phase 5 real-model tier, `docs/perf/phase5-extraction.md`). An item that is destroyed or
  used up with neither keeps its last holder.
- K10 (ADR 0011, Consequences): `possesses` and `located_in` are separate version keys. The per-turn
  extraction comparison recorded `은빛 열쇠 located_in 서랍` in the same chat where the item's holder
  was also tracked (`docs/perf/turn-extraction.md`, row 3).
- Current fact reading (`facts.py`) is a fold over narrated, actual assertions in position order, then
  extraction order within a turn. A negation ends only the version it denies (ADR 0013). No rule links
  two version keys, so nothing can end an item's holder except another `possesses` assertion.
- Track B §6 B2 acceptance examples: transfer closes the previous holder, contradictions do not
  resolve silently, a deep edit masks dependent state at once, and rebuilds reproduce results.
  Masking and rebuilds already hold, because facts are computed at read time from head membership
  (D8, ADR 0012). Phase 6 must keep that.

Not in the evidence yet, and therefore measured before it can widen the scope: same-turn
contradictions (two different current values for one key in one turn), and conflicts between
narrated statements across turns. In a linear chat, a newer narrated state is normally a change and
not a contradiction.

## In scope

1. **Transition fold (read time).** Replace `facts._versions` for item keys with a deterministic fold
   per item entity over its `possesses`, `located_in` and `destroyed` assertions (narrated, actual),
   in position order, then extraction order within a turn. Each assertion gets an outcome:
   `current`, `superseded`, `ended` (closed by a negation or by `destroyed`) or `conflicting`. Other
   predicates keep today's fold, and their assertions report `current` / `superseded` / `ended` in the
   same vocabulary. Nothing is stored. The result is a function of head membership, the served
   extractions (ADR 0014) and entity resolution (ADR 0012).
2. **Item whereabouts (Q2).** One version key per item entity for `possesses` and `located_in`. The
   newer assertion is current and closes the older one. Assertions from the same turn combine into one
   whereabouts ("held by Hana, at the library"). A negation ends only what it denies (ADR 0013,
   unchanged). `located_in` of characters and groups is unchanged.
3. **Item end (Q3).** Registry predicate `destroyed` (subject type `item`; value: how, in the chat's
   language). Prompt rule: only when the item no longer exists or can no longer be held or used
   (burned, eaten, drunk, used up, shattered beyond use). Not when it is merely damaged, hidden or
   lost (a loss is a `possesses` negation). It ends the item's whereabouts. It is itself a current fact
   (`destroyed: burned`) until the item appears again.
4. **Conflicts (Q4).** A positive `possesses` or `located_in` for an item after its `destroyed` is
   `conflicting`, and so is the `destroyed` it contradicts. Conflicts are derived at read time like
   everything else. Nothing is queued or stored. Owner resolution (merge, retract, lock) stays Track B,
   B7.
5. **Packet (Q1).** A conflicting item key is rendered once, as its latest assertion with
   `disputed="true"` and the other value in the line. The packet Note gets one sentence: disputed means
   the story is inconsistent here and neither value is certain. A destroyed item renders as
   `<Fact kind="destroyed">…</Fact>` only when relevant, like any other fact. Budget and ordering are
   unchanged. No plugin change.
6. **Inspector (read-only).** Per item: the transition timeline (holder, place, end, with turn and
   outcome of each assertion); a conflicts list for the conversation; each fact's outcome history.
7. **Extraction `extract-v6`.** The registry gains `destroyed`, and the prompt gains its rule. This is
   a new extractor generation: recent window only, older turns served by `extract-v5` (ADR 0014).
   Older generations never produce `destroyed`, so older turns cannot end an item this way until
   "extract all history".
8. **Evaluation (below):** deterministic cases, a real-model tier, a latency bound.

No migration is expected: `destroyed` is a registry entry, and outcomes and conflicts are computed at
read time. If implementation finds a schema change necessary, stop and ask (stop conditions).

## Out of scope

- A semantic verifier model (Track B §6 B2 keeps it out of the first slice).
- Stored conflict records, a conflict queue, owner resolution (B7).
- Transition rules for characters: death or other terminal status, `has_status` and `identity`
  transitions, `relationship` inverses and symmetry. None has a recorded error yet. Adding one needs a
  fixture showing a wrong current state first.
- Same-turn or cross-turn contradiction rules for any other predicate (see "Not in the evidence yet").
  Phase 6 only measures them in the real-model tier.
- Deriving a held item's place from its holder's location (that would invent a fact).
- Transfer "from" fields, events, relationships as projections, threads, narrative time (B3).
- Canon sources (B4), principal-aware knowledge and hard POV (B5), MCP and forensic recall (B6).
- O5 remainder (Q5): its own maintenance change after the owner's answer, not part of this phase.
- Any change to the plugin's request path, gating or deadline.

## Upgrade and cost

- With an LLM configured, `extract-v6` becomes active at startup. Each chat re-extracts its latest
  `NMOS_EXTRACT_BACKFILL` turns (default 100) once. Older turns keep their `extract-v5` facts until
  "extract all history". The prompt grows by one registry line and one rule: an estimated +3–5 %
  prompt tokens per turn, to be measured and stated in the release notes.
- With extraction off: whereabouts (Q2) and the new fold apply to existing facts at once (read time).
  `destroyed` never appears.

## Evaluation

### Deterministic tier (CI)

New cases in `apps/sidecar/tests/memeval.py` and unit tests for the fold. Every existing case keeps
passing.

| Case | Must hold |
|---|---|
| transfer | A holds → B holds: B current; history keeps A (ADR 0011, unchanged) |
| put down | Hana holds the map → the map is on the table (later turn): whereabouts "on the table"; Hana no longer holds it |
| picked up | the map is on the table → Kaito picks it up: whereabouts "held by Kaito"; the place is closed |
| same turn | "Hana holds the map in the library" (one turn): held by Hana and at the library, both current in one whereabouts |
| destroyed | Hana holds the letter → she burns it: no holder, no place; `destroyed: burned` is current |
| eaten | the apple is eaten: no holder; the fact says eaten |
| damaged, not destroyed | "the sword cracked" does not end its holder (stub rule mirrors the prompt rule) |
| use after end (Q4) | letter burned (turn 5) → Hana reads the letter (turn 9, `possesses`): conflicting; packet shows it disputed with both values |
| edit removes the end | the burning turn is edited away: the holder is current again on the next read, before any re-extraction |
| older generation | older turns served by `extract-v5` never contain `destroyed`; an item they left with a holder keeps it until a v6 turn ends it |
| character location | `located_in` of a character is unchanged by any item rule |
| rebuild | discarding and re-extracting a chat reproduces the same outcomes and conflicts (stub extractor) |
| determinism | the same head and extractions give the same outcomes regardless of row insertion order across turns |

### Real-model tier (evidence, not CI)

Korean synthetic scenes (labeled as such), three runs each, with the configured extraction model.
Prompts, raw outputs, model and endpoint go under `fixtures/model/phase6/`, and a summary goes to
`docs/perf/phase6-extraction.md`. At least two scenes each: burned or torn letter, eaten or drunk
item, consumable used up, item damaged but intact (control), item put down and picked up, item lost
(control for the existing negation), and plain actual events (control). Also recorded: every turn
with two different values for one single-valued key. That number decides whether a same-turn
conflict rule is worth a later phase.

### Performance

`tools/bench_scale.py` facts tier at 1k / 5k / 10k with item assertions (holder, place, end). The new
fold adds at most 30 ms p50 to the fact read at 10k.

## Acceptance criteria

Status 2026-09-24. Evidence: `docs/perf/phase6-extraction.md` (`deepseek-v4.1-flash:cloud`, 13 scenes
× 3 runs; fact-read latency; real-host smoke; upgrade).

- [x] Every deterministic case above passes in CI, and every existing evaluation case still passes
      (memory evaluation 25/25 in `full`, `docs/perf/eval-baseline.md`; fold cases in
      `tests/test_transitions.py`).
- [x] Destroyed, eaten or used-up items get a `destroyed` assertion that ends the whereabouts in at
      least two of three runs per scene: 3/3 in all four scenes.
- [x] Damaged-but-intact controls: no `destroyed` in any run (0 of 6).
- [x] Control scenes: `destroyed` never appears for an item that still exists (0 of 12 runs), and the
      Phase 5 bar still holds (0 of 35 actual-event assertions labeled non-actual).
- [x] Put-down and pick-up scenes end with the whereabouts the scene states in at least two of three
      runs: 3/3 and 3/3.
- [x] Same-turn multi-value turns counted and reported: 2 of 39 runs, both compatible `has_status`
      values in one scene, no item key.
- [x] Prompt tokens per turn, v5 against v6, measured: 1,328 → 1,424 (+7.2 %; the spec estimated
      +3–5 %). To be stated in the release notes.
- [x] Fact read at 10k: at most +30 ms p50 in the facts tier. Measured +23 ms median over five
      alternating runs (`tools/bench_facts.py`).
- [x] Upgrade from a `v0.1.0-beta.12` database queues only the recent window. Older turns are served
      by `extract-v5`, and whereabouts apply to them at once.
- [x] A real-host smoke run (PocketRisu v1.12.0) injects a packet with a destroyed item and one
      disputed fact. The plugin is unchanged.
- [x] `ARCHITECTURE.md` (D30 for transitions; D6 registry note), ADRs 0016 and 0017, README, the Korean
      guide, `docs/KNOWN-ISSUES.md` (K9, K10) and the changelog updated.

Finding for the owner (not a bar): in 1 of 3 runs of the loss scene (a map blown into the sea), the
model recorded `destroyed` instead of a lost holding. Hana's holding ends either way; the fact reads
"destroyed" where "lost" was meant. No prompt change was made.

## Implementation order

Each step is one reviewable change with its tests.

1. **Fold and whereabouts (Q2)**: read-time only, with no generation change. Useful on its own for
   K10, and it applies to existing data at once. *Done 2026-09-24* (ADR 0016, D30;
   `tests/test_transitions.py`, memory evaluation 20/20 in `full`). Outcome labels for every
   assertion come with the Inspector (step 4).
2. **`destroyed` and `extract-v6` (Q3)**: registry, prompt, stub rules, cases "destroyed", "eaten",
   "damaged". *Done 2026-09-24* (ADR 0017, D30 amended; memory evaluation 24/24 in `full`, with
   "edit removes the end" too).
3. **Conflicts and packet (Q1, Q4)**: outcome `conflicting`, `disputed="true"`, the packet Note.
   *Done 2026-09-24* (ADR 0017 items 4–5, D30; case "use after end", memory evaluation 25/25 in
   `full`).
4. **Inspector**: item timelines, the conflicts list, outcome history. *Done 2026-09-24*: every
   history entry carries `outcome` (`current` / `superseded` / `ended` / `conflicting`, also in
   `/v1/conversations/{id}/facts?history=true`); the Inspector shows a conflicts table, one timeline per
   item and a `disputed` chip on facts (`tests/test_transitions.py`).
5. **Evaluation and release**: real-model tier, measurements, docs, release notes with cost.
   *Done 2026-09-24* (`docs/perf/phase6-extraction.md`; released in `v0.1.0-beta.13`).

## Stop conditions

Stop and ask the owner when:

- a rule would create a fact the story did not state (a derived place, an inferred owner);
- a transition would need information the stored assertions do not carry (a transfer's "from", time
  inside a turn beyond extraction order);
- the real-model tier shows `destroyed` on intact items, or misses it on destroyed ones below the bar,
  and a prompt fix does not bring it within the bar;
- conflicts turn out frequent in control scenes (a sign the rule is wrong, not the story);
- a schema change, a stored projection or a new runtime dependency seems necessary;
- a change would overwrite old assertions or extractions instead of adding a generation.
