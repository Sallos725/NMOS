# Phase 5 — Entity Identity and Semantic Assertions

> **Status: current. Approved by the owner on 2026-09-23** (PR #34), with ADRs 0012–0014.
>
> Scope comes from the owner's decisions of 2026-09-23: Track B §4 "Owner decisions"
> (`docs/proposals/TRACK-B-PHASE-5-PLUS.md`) and three design questions answered the same day (name
> hints in extraction, negation ends the matching fact, the recent-window rule for every generation
> change). This is Track B stage B1; B0 is this document.

## Goal

Facts stop being keyed only by free text and stop treating everything extracted as something that
happened. After Phase 5:

- the same thing under two names is one entity when the story says so, or when the extractor reuses a
  known name; ambiguous names stay ambiguous;
- "did not", "lost", "no longer" are recorded as negation and end the matching current fact;
- plans, conditions, dreams and speculation are stored as such and never become current state;
- what a character says is a claim and never overwrites what the story narrates;
- changing the extraction model or prompt no longer re-pays the whole history automatically.

Known issues addressed: K8 (reduced), K9 (explicit loss and giving-up), K18 (bounded cost). See
`docs/KNOWN-ISSUES.md`.

## Evidence behind the scope

- K8, K9, K10 and ADR 0011: item names are free text; a lost item keeps its holder; holder and place
  are separate facts.
- `docs/perf/turn-extraction.md`: the per-turn prompt removed false facts from refused actions; one
  measured `possesses` error needed item-centric reading (ADR 0011).
- Phase 4 check (PHASE-4.md): a real model returned sensible knowledge scopes on Korean scenes but
  translated entity names into English in one scene. Names are not stable even within one model.
- Track B §2: `epistemic` is only `stated` / `implied`; claims, negation and hypotheticals cannot be
  represented.
- Re-extraction cost: ≈3.1k tokens per turn with the measured model, ≈15M tokens for a
  10,000-message chat (Track B §7).

## In scope

1. **Assertion semantics (ADR 0013).** `polarity` (positive / negative), `modality` (actual /
   hypothetical / dreamed / unknown), `source` (narration / character_claim) with `asserted_by`.
   Extraction compiler `extract-v5`: prompt, validation and normalization. "Skip speculation" becomes
   "label it".
2. **Fact reading (ADR 0013).** Fact versions come from actual narration only. A negative assertion
   ends the current version it denies (same object/value; for `possesses`, the same holder) and
   otherwise stands as a negative fact. Character claims attach to the fact they concern and never
   supersede narration. Hypothetical, dreamed and unknown assertions are stored and inspectable only.
   Legacy (`extract-v4` and older) assertions read as narration, as today.
3. **Packet.** `negated="true"` on negative facts; `<Claim by="…">` lines after facts, only when
   relevant to the query, within the existing budget; the packet Note explains both. Plugin
   unchanged.
4. **Entity identity (ADR 0012).** Read-time, deterministic resolution of subject and object mentions
   to entities per conversation: exact normalized name per type, the user's persona names, and
   `also_called` aliases whose two names both occur in the source turn. Aliases shared by several
   entities make a mention ambiguous. Fact version keys use entity IDs where resolved. Stable IDs;
   no LLM calls; invalidation follows head membership.
5. **Name hints (ADR 0012).** The extraction prompt lists up to `NMOS_EXTRACT_HINTS` (default 40)
   entities mentioned on the head before the target turn, with types. The list is stored on the
   extraction row. Hints do not affect extraction validity. `NMOS_EXTRACT_HINTS=0` turns them off.
6. **Generation change policy (ADR 0014).** Every extractor generation change queues only the recent
   window; older turns are served by the newest earlier generation that has them, one generation per
   turn, until "extract all history". Rebuild discards all generations of that chat. Coverage shows
   active / older generation / none.
7. **Inspector (read-only).** Per conversation: entities with names, type, where each alias was
   established, mention counts and ambiguous mentions; facts with entity, polarity, source and the
   generation that served them; claims; non-actual assertions; the hint list of an extraction.
8. **Schema.** One new migration: assertion `polarity`, `modality`, `source`, `asserted_by`;
   extraction `hints`. Defaults make existing rows legacy positive/actual; no rewrite.
9. **Evaluation (below)**: new deterministic cases and a real-model tier.

## Out of scope

- A transition verifier, conflict queue or transition rules beyond "a negation ends the fact it
  denies" (Track B, B2 — the next stage after Phase 5). Destroyed, eaten or used-up items without a
  loss statement keep their holder (K9 remainder), and holder/place disagreement (K10) stays.
- Events, relationships as projections, open threads, narrative time, event salience (B3).
- Character cards, lorebooks, persona or author notes as sources; an `authored_canon` source class
  (B4).
- Principal identity for knowledge marks in the packet, `character_pov`, hard isolation (B5).
- MCP, forensic recall, strategic selection (B6).
- Owner corrections: merge, split, lock, retract (B7).
- Finer modalities (observed, believed, suspected, promised, remembered, inferred, …) until a
  recorded fixture shows the coarse set producing a wrong current state and a real model labels them
  reliably.
- Persisted entity or alias tables, unless the latency bound below fails (ADR 0012 fallback).
- Entities across conversations or branches.
- Pruning superseded generations (the O5 decision of 2026-09-23). It is separate maintenance work;
  Phase 5 relies only on superseded LLM extractions being kept.
- Any change to the plugin's request path, gating or deadline.

## Upgrade and cost

- With an LLM configured, `extract-v5` becomes the active generation at startup. Each chat
  re-extracts its latest `NMOS_EXTRACT_BACKFILL` turns (default 100), recent first. Older turns keep
  their `extract-v4` facts (legacy) until the owner runs "extract all history" on that chat.
- Per call, the prompt grows by the new fields' instructions and the hint list (estimated +20–30 %
  prompt tokens; measured below and stated in the release notes with the measured number).
- With extraction switched off, no calls are made. Existing facts are legacy and read as today,
  except that entity resolution groups their exact names (and the persona names) per entity.

## Evaluation

### Deterministic tier (CI)

New synthetic cases in `apps/sidecar/tests/memeval.py` with stub-extractor rules for the new fields.
Every existing case keeps passing: no stale or other-branch text in any mode, `full` reaches every
gold, irrelevant questions stay empty.

| Case | Must hold |
|---|---|
| negated entry | "Alice did not enter the hall" is a negative fact, rendered `negated="true"`; not absent |
| lost item | "Hana lost the map" ends Hana's holding; the map has no current holder; history keeps Hana |
| negation of another place | "Hana is not at the station" while she is at home leaves "home" current |
| denial by a non-holder | "Kaito does not have the map" while Hana holds it changes nothing |
| hypothetical and dream | "If Hana goes to the harbor…" / "Hana dreamed she was at the harbor" never become location facts or packet lines |
| lie in dialogue | a newer character claim does not replace the narrated fact; it reaches the packet only as `<Claim>` and only when relevant |
| stated alias | "하나(Hana)" in one turn links the names; a fact under "Hana" and one under "하나" share one version key |
| unevidenced alias | `also_called` whose two names are not both in the turn stays `pending` |
| shared alias | a bare name that is an alias of two entities of one type is ambiguous and not linked |
| type separation | item "지도" and place "지도" are two entities |
| alias turn edited or deleted | the entity splits on the next read; no stale merged fact reaches the packet |
| hints | recorded on the extraction row; at most `NMOS_EXTRACT_HINTS`; only entities before the target turn; never from inactive sources |
| hint source deleted | an extraction that used a hint stays valid |
| generation change | only the recent window is queued; older turns are served by the previous generation; one generation per turn; coverage shows both; "extract all history" completes it |
| rebuild | discards every generation of the chat; no older facts reappear before re-extraction |
| legacy rows | `extract-v4` facts are served, inspectable, marked legacy, and never become claims |

### Real-model tier (evidence, not CI)

Korean scenes written for this evaluation (synthetic, labeled as such), run through the sidecar's own
prompt and validation with the configured extraction model, three runs each; prompts, raw outputs and
the model/endpoint are recorded under `fixtures/model/phase5/` and summarized in
`docs/perf/phase5-extraction.md`. At least two scenes per category: negation and loss, plan or
condition, dream, lie or boast in dialogue, stated alias, a second different item of the same kind
while the first is hinted (false-merge check), and control scenes of plain actual events.

### Performance

`tools/bench_scale.py` gains a facts tier (stub assertions, about one per turn) at 1k / 5k / 10k
messages and reports fact-read time with and without entity resolution.

## Acceptance criteria

- [ ] Every deterministic case above passes in CI, and every existing evaluation case still passes.
- [ ] Across all real-model runs, no hypothetical, dreamed or claimed content becomes a current fact.
- [ ] In the control scenes, at most 10 % of actual-event assertions are labeled non-actual
      (`hypothetical`, `dreamed`, `unknown`).
- [ ] Negation and loss scenes produce negative assertions that end the right fact in at least two of
      three runs per scene.
- [ ] False-merge check: the second item keeps its own name in at least two of three runs. Otherwise
      hints ship off by default (`NMOS_EXTRACT_HINTS=0`) and this is recorded.
- [ ] Prompt tokens per turn with and without hints are measured and stated in the release notes.
- [ ] Entity resolution adds at most 50 ms p50 to the fact read at 10,000 messages in the facts tier.
      Otherwise the ADR 0012 fallback (persisted per head, same rules) is implemented and measured
      before release.
- [ ] Changing the resolver version re-derives every entity link with zero LLM calls and zero queued
      jobs.
- [ ] Upgrading a database written by `v0.1.0-beta.10` queues only the recent window, serves older
      turns from `extract-v4`, and shows that in the Inspector.
- [ ] With extraction switched off, existing facts read as in `v0.1.0-beta.10` (legacy), except
      that versions are grouped by entity (e.g. `{{user}}` and `유저` are one persona).
- [ ] A real-host smoke run (PocketRisu v1.12.0) injects a packet with the new attributes in one chat;
      the plugin is unchanged.
- [ ] `ARCHITECTURE.md` D7 (hints) and D20 (fallback) amended, D26 (entity identity) and D27
      (assertion semantics) added; README, the Korean guide,
      `docs/KNOWN-ISSUES.md` (K8, K9, K18) and the changelog updated.

## Implementation order

Each step is one reviewable change with its tests.

1. **Generation fallback (ADR 0014).** Useful on its own: it also bounds the cost of a plain model
   change. Must land before step 2 activates `extract-v5`. *Done 2026-09-24* (tests in
   `test_generations.py`; fact-read timings in `docs/perf/scale.md`, which also records the fixed
   `allBefore` stall).
2. **Schema and `extract-v5`**: migration, prompt, validation, `also_called`, stored hints column
   (empty until step 5).
3. **Fact reading and packet (ADR 0013)**: actual narration only, negation, claims, legacy rows.
4. **Entity resolution (ADR 0012)**: read-time resolver, entity-keyed versions, Inspector entities,
   facts-tier benchmark.
5. **Name hints**: worker builds and records the list; generation key includes the count.
6. **Evaluation and release**: real-model tier, measurements, docs, release notes with cost.

## Stop conditions

Stop and ask the owner when:

- entity resolution would link names without evidence in the source turn;
- a hinted name visibly merges different entities in the real-model tier and switching hints off is
  not enough;
- the real-model tier shows the coarse modality set mislabeling actual events above the bar, and a
  prompt fix does not bring it under it;
- a change would overwrite old assertions or extractions instead of adding a generation;
- the latency bound fails and the persisted fallback also fails it;
- a new runtime dependency seems necessary.
