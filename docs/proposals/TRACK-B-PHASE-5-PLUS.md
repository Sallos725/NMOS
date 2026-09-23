# Track B Proposal — Phase 5+ Semantic and Narrative Roadmap

> Proposal only. This document is not a normative phase specification and does not authorize
> implementation. `AGENTS.md`, `ARCHITECTURE.md`, and `docs/STATUS.md` continue to prohibit Phase 5+
> work until the owner explicitly approves a phase and its acceptance criteria.

## 1. Executive summary

The current beta has a reliable source ledger, synchronous invalidation, deterministic state,
per-turn assertions, fact history, hybrid retrieval, and soft knowledge annotations. Its next major
limitation is not retrieval breadth; it is semantic representation.

Subjects and objects are still free text. Events and relationships are predicates rather than
first-class versioned projections. Fact versions follow transcript order rather than narrative valid
time. Claims, observations, hypotheses, lies, negation, retcons, and conflicting evidence cannot yet
be represented with the fidelity described in the reference architecture.

The proposed Phase 5+ direction is therefore:

```text
Entity identity and semantic assertion model
    → transition verification and conflict handling
    → event / relationship / thread projections
    → canon unification
    → principal-aware epistemic access
    → strategic selection and forensic read interfaces
```

This ordering deliberately postpones MCP, graph infrastructure, and hard POV isolation until the
underlying identity, authority, and visibility models can support them safely.

## 2. Observed evidence

- Per-turn extraction fixed false facts caused by treating an attempted user action as a completed
  event, but ownership transfer can still leave multiple current holders (addressed partially in
  Track A, A4; a full fix needs entity identity and transitions).
- The current registry validates types and cardinality, yet entities are names, not stable IDs.
- `epistemic` is limited to `stated`/`implied`; knowledge scope is soft annotation.
- Current fact versions select the latest matching assertion by transcript position.
- The tested PocketRisu build has no group-chat host surface.
- A single sim-bot generation can write several characters, so hidden values cannot be hard-isolated
  inside one model call.
- Threads, causal links, verifier, MCP, and hard POV are explicitly outside the current beta.

## 3. Current architectural rule

- Phase 5+ is not authorized.
- A new phase requires an owner-approved phase document with goal, scope, out-of-scope, and
  evidence-bearing acceptance criteria.
- Unknown and conflicting states must remain valid outcomes.
- Character knowledge must remain separate from world knowledge.
- The response model may not write canonical memory.
- Every semantic claim needs source and compiler provenance.
- Raw evidence remains immutable except for explicit whole-conversation owner deletion.
- No PocketRisu fork is introduced without measured need.

## 4. Smallest owner decisions required

Before Phase 5 (B0/B1) implementation, decide:

1. **Phase boundary:** approve only semantic foundations first, or approve the full narrative-engine
   slice described below.
2. **Roadmap amendment:** the reference roadmap puts narrative engine before verifier/repair. This
   proposal recommends a small deterministic transition verifier earlier because a measured current
   fact error already requires transition semantics.
3. **Canon sources:** whether character cards and lorebooks enter the same authority model in the
   first new phase or a later one. (B1's authority classes depend on the answer.)
4. **O5 — retention of superseded projection generations only:** B1 adds a new extractor generation
   and a resolver generation; decide whether older generations are kept indefinitely (ADR 0006
   default) or pruned after a new one reaches full coverage.

Needed later, not before B0/B1:

- **O1 — MIRRA / VEIL relationship** (before B5): whether NMOS owns the knowledge-boundary role or
  interoperates with another component.
- **O5 — retention of abandoned worldlines, host observations, and conflict/audit history** (before
  B2's conflict queue grows it).
- **Hard POV ambition** (before B5): soft annotation only, or eventual separate-call/host-orchestrated
  isolation.

The measured ownership-transfer error is handled in Track A (A4, item-centric `held_by`) so that it
does not wait for B1 and B2.

### Owner decisions (2026-09-23)

Taken after `docs/KNOWN-ISSUES.md` mapped the remaining issues to stages (K8 → B1; K9, K10 → B2;
K11 → B5). They set the boundary for B0; Phase 5 itself starts only when `docs/phases/PHASE-5.md` is
approved (`AGENTS.md` §7).

1. **Phase boundary: B1 only.** Phase 5 is entity identity and semantic assertions (Option 1).
2. **Roadmap amendment: accepted.** The next stage after B1 is B2 (transition verifier), before B3
   (narrative engine). K9 and K10 are therefore fixed in the phase after Phase 5.
3. **Canon sources: later, in B4.** B1's authority classes are narration and character claim only.
   No authored-canon class until card/lorebook host evidence exists; adding it then is a new
   generation.
4. **O5, superseded generations only:** keep what is costly to recreate, prune what is cheap. Once a
   new generation reaches full coverage of a chat, superseded **LLM extraction** rows (and their
   assertions) are kept for audit and rollback; superseded **embeddings** and **deterministic
   projections** (e.g. B1's mention → entity resolver generations) may be pruned. Abandoned
   worldlines and `host_observation` growth stay open (before B2). Owner suggestion recorded for B3:
   keep important events first by priority, not by deleting the rest (see B3).
5. **Re-extraction (§7): recent window automatic, older history on request.** B1's new extractor
   generation re-extracts only the backfill window (`NMOS_EXTRACT_BACKFILL`, default 100 turns)
   automatically. Older turns are re-extracted by the Inspector's "extract all history", as D22 does
   for first-sight history; until then they are read through B1's compatibility path from the
   previous generation, shown as partial coverage.

## 5. Options and trade-offs

### Option 1 — Narrow Phase 5A only (recommended)

Implement stable entity identity and a richer assertion model, with read-only inspector support. Do
not yet add threads, causal links, MCP, or hard POV.

Pros:

- smallest schema and migration risk;
- provides the foundation every later subsystem needs;
- existing facts can be dual-read during migration;
- quality can be evaluated before adding more projections.

Cons:

- few immediately visible narrative features;
- ownership and relationship improvements arrive incrementally.

### Option 2 — Semantic foundation plus narrative engine

Approve entities, assertions, events, relationships, and open threads together.

Pros:

- produces visible long-range continuity features sooner;
- enables promises, debts, mysteries, and causal callbacks.

Cons:

- substantially larger correctness and evaluation surface;
- entity-resolution errors can contaminate several projections at once;
- harder to isolate extractor, resolver, and projection failures.

### Option 3 — Epistemic engine first

Move directly toward hard character-scoped recall.

Pros:

- targets the most RP-specific product distinction.

Cons:

- unsafe without stable entity/principal identity;
- cannot provide true privacy for multi-character single-call generation;
- likely forces an owner decision about host orchestration before the data model is ready.

Recommendation: Option 1, followed by gated narrative slices.

## 6. Proposed staged roadmap

### Stage B0 — Normative phase and evaluation design

Deliverables before production code:

- owner-approved `docs/phases/PHASE-5.md`;
- ADR for entity identity, mention resolution as its own projection, and reversible merge/split
  policy;
- ADR for assertion modality, authority, and polarity semantics (narrative time is deferred to B3);
- ADR deciding whether deterministic transition verification enters Phase 5;
- migration and rollback/backfill strategy, including a re-extraction cost estimate (see §7);
- benchmark fixtures for every accepted semantic behavior;
- explicit out-of-scope list.

No schema or empty service stubs should be created during B0.

### Stage B1 — Entity and semantic assertion foundation

#### Goal

Replace free-text identity as the sole semantic key while preserving current facts and provenance.

#### Proposed scope

- `entity` with stable NMOS ID and conversation/world scope;
- versioned `entity_alias` with source and confidence;
- unresolved/ambiguous entity mentions as first-class outcomes;
- assertions keep mentions as extracted text; a separate mention → entity projection, keyed by its own
  resolver generation, maps them to entity IDs. Changing the resolver rebuilds that projection
  without re-running LLM extraction;
- polarity: positive / negative;
- a coarse modality set: actual, claimed, hypothetical/intended, dreamed, unknown. Finer values
  (observed, believed, suspected, promised, remembered, inferred, …) are added only when a recorded
  fixture shows the coarse set producing a wrong current state, and after a real-model run shows the
  extractor can label them reliably;
- authority/source class, starting with two or three classes (e.g. narration, character claim,
  and authored canon if decision 3 admits it);
- transaction time and transcript position (already present);
- compiler generation and evidence links retained on every row;
- compatibility read path for the current assertion/fact data until rebuilt.

#### Out of scope

- automatic entity merge without reviewable evidence;
- narrative (story) time — it has no consumer before B3 and would be pre-built;
- full causal graph;
- hard epistemic ACL;
- model-facing MCP;
- graph database.

#### Acceptance examples

- Korean/English/Japanese aliases resolve to one entity **when the source text establishes the alias**
  (e.g. "하나(Hana)"), without discarding their source spellings; transliteration alone never merges;
- two characters with the same display name remain ambiguous rather than silently merged;
- “Alice did not enter” is not represented as absence of `entered`;
- a character claim does not overwrite stronger narrated world state;
- hypothetical, dreamed, and intended actions never become actual state by default;
- a resolver-generation change rebuilds entity links with zero LLM calls;
- current beta facts remain inspectable throughout migration and rebuild.

### Stage B2 — Deterministic transition verifier and conflict queue

#### Goal

Treat memory projection updates as explicit state transitions rather than “latest row wins” alone.

#### Proposed scope

- predicate contracts declaring cardinality, inverse/ownership semantics, and allowed subject/object
  types;
- deterministic checks for provenance, lifecycle, interval validity, cardinality, and source activity;
- transition rules for a deliberately small set of high-value predicates, beginning with location,
  possession, identity/status, and relationship;
- outcomes: accepted, pending, conflicting, rejected;
- conflict records preserving all evidence;
- synchronous masking of projections whose sole evidence becomes inactive;
- read-only Inspector views for conflicts and transition history.

An optional semantic-verifier model should remain outside the first slice unless deterministic checks
prove insufficient on recorded fixtures.

#### Acceptance examples

- item transfer A → B closes A's current possession and preserves historical possession;
- returning an item is distinguishable from merely mentioning it;
- contradictory sources produce a conflict rather than arbitrary last-write wins;
- a deep edit invalidates dependent current state before recompilation finishes;
- rebuilding from the ledger reproduces the same transition and conflict results.

### Stage B3 — Event, relationship, and open-thread projections

#### Goal

Represent long-range narrative continuity that cannot be recovered reliably from isolated facts.

#### Proposed scope

- first-class events with participants, location, observers, privacy, source assertions, and partial
  narrative time (introduced here, where the first consumer exists);
- explicit versus inferred event links kept separate;
- versioned typed relationships with perspective where needed;
- open threads for promise, goal, mystery, debt, threat, meeting, missing item, unanswered question,
  and unfinished task;
- thread resolution linked to evidence, never destructive deletion;
- retrieval routes for current relationships, unresolved threads, and relevant events;
- packet sections with independent budgets and provenance;
- event salience: important ("central") events rank and budget ahead of minor ones in retrieval and
  the packet. Owner suggestion (2026-09-23); it is a priority, never a reason to delete lower-ranked
  memory or evidence.

#### Initial causal-link scope

Allow only evidence-backed links such as fulfills, resolves, breaks-promise, reveals, contradicts,
and explicit causes. Broad inferred causality should remain pending until a later verifier phase.

#### Acceptance examples

- a promise at turn 10 is recalled when the participants meet much later;
- fulfillment closes the current thread while keeping its history;
- a deleted promise removes the thread from the active projection;
- relationship history answers both current and past questions;
- irrelevant old events do not appear merely because they share an entity.

### Stage B4 — Canon source unification

#### Goal

Bring authored canon and conversation-derived memory into one authority-aware source universe.

#### Proposed scope

- character card, scenario, example messages, active lorebook, persona, and author note as typed source
  revisions where the host surface is verified;
- source-specific authority policy;
- authored canon versus later story evolution;
- conflicts shown rather than silently overwritten;
- no duplication of lore already present in the outgoing prompt.

This stage needs new host-evidence scenarios for mutation and identity of every source type. Source
reading alone is not enough where runtime lifecycle affects correctness.

### Stage B5 — Principal-aware epistemic projection

#### Goal

Move from free-text soft annotations toward stable character knowledge state.

#### Proposed scope

- stable principal/entity references instead of name lists;
- acquisition/invalidation evidence and time;
- knows, believes, suspects, doubts, denies, misremembers, forgotten, unknown;
- observation/communication-based propagation only where evidence supports it;
- `omniscient_narrator` remains the default;
- `character_pov` filters hidden values before context construction only when the host request has one
  resolvable principal.

#### Hard stop

Do not claim hard isolation when one request generates multiple characters. Choose one explicitly:

- separate model calls per principal;
- intersection-only context;
- omniscient narrator;
- documented soft isolation.

If separate calls require PocketRisu orchestration changes, stop for an owner bridge/fork decision
with measured evidence.

### Stage B6 — Strategic selection, forensic recall, and MCP

#### Goal

Expose richer memory only after visibility and authority are enforceable server-side.

#### Proposed scope

- candidate labels: required, supportive, irrelevant, risky, hidden;
- redundancy and memory-overuse penalties;
- fast, normal, and forensic recall paths;
- exact-quote path preferring lexical/raw evidence;
- read-only MCP tools bound server-side to conversation, worldline, principal, and permissions;
- evidence explanation and trace traversal;
- no canonical write tool for the response model.

MCP remains optional deep recall. Automatic pre-request retrieval remains the correctness baseline.

#### Host-evidence precondition

`docs/HOST-FACTS.md` does not show whether PocketRisu (`a14c911` / v1.12.0) lets the response model
call tools, or how a plugin could expose them. Model-facing MCP needs new host scenarios for that
surface before any implementation, as B4 does for canon sources. Without a verified surface, B6 is
limited to the non-MCP parts (selection labels, recall paths, Inspector trace traversal).

### Stage B7 — Inspector repair and portable archive

#### Proposed scope

- review conflicts and pending candidates;
- correct/retract assertion through audited manual source entries;
- lock/unlock canon;
- merge/split entities reversibly;
- edit aliases and story time with audit history;
- rebuild selected projections;
- export source ledger, manual overrides, artifacts, and optional projections;
- restore/export compatibility tests.

This is an administrative surface. The response model must not receive these write capabilities.

## 7. Data migration principles

- Add only new numbered migrations; never edit migrations 0001–0012.
- Preserve current free-text assertions for audit.
- New projections must be rebuildable from source revisions and generation configuration.
- Backfill under an explicit generation; never silently reinterpret old rows in place.
- During transition, readers must not mix incompatible generations.
- Prefer dual-read with visible partial coverage over an all-at-once destructive migration.
- Every manual correction is source/audit data, not an untracked projection edit.
- Keep LLM extraction and deterministic resolution in separate generations, so resolver or registry
  work that does not change the extraction prompt does not force re-extraction.

### Re-extraction cost

A new extractor generation re-queues the history an earlier generation covered (D20). With the model
measured in `docs/perf/turn-extraction.md` (58,748 tokens for 19 turns, ≈3.1k tokens per turn), a
10,000-message chat (≈5,000 turns) costs on the order of 15M tokens to re-extract. B0 records this
estimate, decides whether older history is re-extracted automatically or only on request (as D22 does
for first-sight history), and states it in the release notes.

## 8. Retrieval and packet implications

The current packet priority is state → facts → excerpts. Later stages may extend it to:

```text
mandatory visible state and canon
    → knowledge boundaries
    → current relationships and critical threads
    → directly relevant events
    → supportive history
    → excerpts / evidence
```

This is not permission to force every section into every packet. Empty or irrelevant sections should
be omitted, and retrieval must be separated from utilization.

## 9. Evaluation plan

Each stage adds fixtures before implementation. The eventual comparison matrix should include:

- recent context only;
- simple vector RAG;
- current NMOS;
- the candidate stage with each new route separately enabled;
- the full candidate stage.

Required semantic categories:

- current and historical state;
- partial/relative narrative time;
- negative, hypothetical, intended, dreamed, claimed, and inferred assertions;
- alias ambiguity and incorrect-merge prevention;
- ownership and location transitions;
- lies and false beliefs;
- knowledge acquisition and secrecy;
- retcon/edit/delete/reroll/branch recovery;
- relationship evolution;
- promise/open-thread creation and resolution;
- causal explanation;
- exact quote;
- irrelevant-memory suppression;
- prompt-injection and memory-poisoning attempts.

Metrics include accuracy, leakage, false-memory rate, conflict/abstention correctness, branch
contamination, retrieval precision/recall, token cost, latency, compiler failure rate, and rebuild
time.

## 10. Phase-wide invariants and stop conditions

Stop implementation when:

- entity resolution would silently merge ambiguous actors;
- a verifier would need to invent narrative facts;
- a hidden value would be included in a claimed hard-POV packet;
- a source type's host identity or mutation lifecycle is unverified;
- a new runtime dependency is required without approval;
- an old projection would be overwritten instead of versioned;
- a graph database or host fork is proposed without measured need;
- response-model MCP would gain canonical write authority;
- an acceptance criterion cannot be supported by real or explicitly synthetic evidence.

## 11. Recommended first authorization

Authorize only Stage B0 and B1 initially.

Suggested Phase 5 title:

> **Phase 5 — Entity Identity and Semantic Assertions**

Suggested Phase 5 exit condition:

> NMOS can rebuild stable entities and modality/authority-aware assertions from the existing ledger,
> preserve ambiguity and conflict, maintain compatibility with current beta facts, and demonstrate on
> recorded fixtures that claims, negation, hypotheticals, and ambiguous aliases do not become
> incorrect canonical state. Entity resolution is rebuildable without LLM calls.

After this evidence exists, the owner can authorize B2 transition verification or revise the roadmap
before narrative features multiply the semantic surface.

## 12. Expected deliverables by stage

| Stage | Main deliverable | User-visible result |
|---|---|---|
| B0 | Normative Phase 5 spec and ADRs | Clear authorized boundary |
| B1 | Stable entities and richer assertions | Fewer identity/truth-category errors |
| B2 | Transition verifier and conflicts | Correct current state across transfers/contradictions |
| B3 | Events, relationships, threads | Long-range narrative callbacks and histories |
| B4 | Canon-source integration | Card/lore/story conflicts handled visibly |
| B5 | Principal knowledge projection | Real per-character filtering where host semantics allow |
| B6 | Strategic/forensic recall and MCP | Deeper evidence retrieval without weakening correctness |
| B7 | Audited repair and export | Owner control, portability, and disaster recovery |

## 13. Recommendation

Finish Track A first, then authorize a narrow B0/B1 Phase 5. Do not bundle the entire ultimate
architecture into one implementation phase. Each semantic layer should earn the next one through
fixtures, rebuildability, traceability, and measured RP quality improvement.
