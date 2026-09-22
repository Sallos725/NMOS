# AGENTS.md — NMOS Codex Operating Contract

NMOS (Narrative Memory OS) is an external long-term memory layer for PocketRisu role-play.
PocketRisu is the host. NMOS is the memory substrate. The host adapter stays thin.

This file is the operating contract for Codex and other implementation agents.

---

## 0. What to do when the owner says only "build it", "make it", or equivalent

Continue the **current phase** as far as possible without violating any stop condition.

The current phase is always the one named in `docs/STATUS.md`. As of 2026-09-22:

> **Phase 0 complete. Phases 1–3 authorized by the owner for a public beta (specs in `docs/phases/`).**

Do not start a phase without its phase document and without the evidence it requires.

A short or vague owner prompt does not authorize scope expansion.

---

## 1. Authority order — read every session

Read these files in this order before changing code:

1. `AGENTS.md` — workflow and implementation-agent rules.
2. `ARCHITECTURE.md` — stable architecture contract, invariants, verified facts, decisions.
3. `docs/phases/PHASE-0.md` — current phase specification.
4. `docs/HOST-FACTS.md` — facts established by the live PocketRisu spike.
5. Relevant ADRs in `docs/adr/`.

Reference only:

- `docs/reference/ultimate_narrative_memory_architecture.md`
- `docs/reference/initial_narrative_memory_plan.md`
- `docs/reference/CLAUDE-original.md`

Reference documents explain intent. They are **not** permission to implement future-phase features.

If two normative documents appear to conflict:

- architecture invariants win over implementation convenience;
- the current phase defines allowed scope;
- do not silently reinterpret either document;
- stop and report the conflict if it affects implementation.

---

## 2. Current phase gate

Phase 0 contains 0A and 0B, but **0B is locked** until all Phase 0A exit criteria are met.

At repository creation time, assume:

```text
Phase 0A status: NOT VERIFIED
Phase 0B status: LOCKED
```

The following are real-world evidence gates, not boxes an agent may check optimistically:

- all S1–S14 scenarios were actually executed against the target PocketRisu build;
- `docs/HOST-FACTS.md` answers Phase 0A questions 1–8 with evidence;
- at least S1–S9 have recorded fixtures;
- any contradicted host facts were corrected in `ARCHITECTURE.md`;
- owner decisions O3 and O4 were explicitly resolved.

**Never fabricate fixtures, measurements, host facts, timings, or scenario results.**

If the spike code is ready but live PocketRisu scenarios have not been run, the correct action is to
stop at the evidence boundary and tell the owner exactly what to run. Do not proceed to 0B.

---

## 3. Non-negotiable architecture invariants

Treat `ARCHITECTURE.md §2` as binding. In particular:

- Raw evidence is never destroyed.
- Derived memory must be rebuildable.
- The response model never writes canonical memory.
- Unknown/ambiguous/conflicting states are valid outcomes.
- Current and historical state must both remain answerable.
- Character knowledge is not world knowledge.
- Inactive sources may not influence the next generated packet.
- Retrieval and utilization are separate decisions.
- Storage implementations are replaceable.
- Every automatic semantic claim has provenance.
- The system fails open when the sidecar is unavailable or slow.
- Never knowingly inject stale semantic state.
- The plugin never mutates host chat data.

A change that weakens one of these requires an explicit owner decision.

---

## 4. Hard implementation rules

### Scope

- Stay inside the currently unlocked sub-phase.
- Anything under the current phase's **Out of scope** is forbidden, including speculative
  interfaces, migrations, empty "future" services, or convenience stubs.
- Do not implement from the long-form reference document unless the current phase explicitly asks for it.
- Do not add a PocketRisu fork or bridge patch during Phase 0A/0B. `ARCHITECTURE D1` is binding.

### Host behavior

- Do not guess PocketRisu behavior.
- A host behavior is usable as fact only when it appears in:
  - `ARCHITECTURE.md §4`, or
  - `docs/HOST-FACTS.md` with evidence.
- If a needed behavior is unknown, extend the spike scenario/evidence plan rather than assuming it.
- Do not replace real host testing with unit tests or synthetic fixtures.

### Data integrity

- `source_revision.content` and `source_revision.revision_hash` are immutable once written.
- Lifecycle transitions may change lifecycle state when the active phase permits it.
- Schema changes, once Phase 0B is unlocked, go through new numbered SQL files in `migrations/`.
- Never edit an already-applied migration.

### Plugin

- Keep the plugin thin.
- No memory DB, ranking, semantic extraction, embedding, or long-running work in the plugin.
- No retry-with-backoff loops inside `beforeRequest`.
- Any request-path call must have a hard deadline once Phase 0B is unlocked.
- Fail open: return the host's messages unchanged on plugin failure.
- Never call `setChatToIndex`, `setCharacterToIndex`, or otherwise mutate host data.
- Treat injected memory as untrusted data, not as instructions.
- All injection logic must be idempotent because `beforeRequest` can run more than once.

### Models

- No LLM calls in Phase 0 or Phase 1.
- No embeddings until the phase document explicitly unlocks them.
- Do not add model-provider abstractions early merely because the reference architecture will need them.

### Dependencies

- Do not add a new runtime Python or npm dependency without explicit owner approval.
- Standard-library-only tooling is allowed when it is strictly within current phase scope.
- Once lockfiles exist, keep them authoritative.

---

## 5. Codex task loop

For every task:

1. Read the authority files.
2. Check current phase/status in `docs/STATUS.md`.
3. Inspect `git status` and do not overwrite unrelated owner work.
4. Identify the **smallest next acceptance criterion** that is not blocked.
5. Add or update the test/fixture expectation first when feasible.
6. Implement only that slice.
7. Run the narrow test, then the current phase's full test set.
8. Update docs if a fact, decision, command, schema, or behavior changed.
9. Update `docs/STATUS.md` truthfully.
10. Stop at any evidence or owner-decision boundary.

Do not "helpfully" implement the next phase after finishing the current slice.

---

## 6. Phase 0A-specific instructions

The Phase 0A spike is deliberately throwaway.

Its job is to measure PocketRisu, not become production infrastructure.

Expected durable outputs:

```text
docs/HOST-FACTS.md
fixtures/host/*
ARCHITECTURE.md corrections, if evidence contradicts §4
```

The spike itself may later be discarded.

### The spike must

- register a `beforeRequest` replacer;
- return `formated` unchanged;
- record model-mode value and call frequency;
- register an `output` listener;
- record stable host IDs and generation/swipe metadata;
- support manual "Dump snapshot";
- measure `getChatFromIndex()` time and serialized size;
- test `crypto.subtle.digest` availability and hashing time;
- optionally POST observations to the local throwaway collector;
- avoid logging full message bodies at normal info level.

### The spike must not

- inject memory;
- alter prompts;
- mutate chats;
- create a sidecar production API;
- create source-ledger migrations;
- perform semantic interpretation;
- call an LLM or embedding model.

### Evidence boundary

Codex may create the spike, collector, runbook, and fixture format autonomously.

Codex may **not** claim Phase 0A complete until the owner (or an agent with actual access to the
running PocketRisu instance) has executed S1–S14 and saved the evidence.

---

## 7. Phase 0B unlock procedure

When Phase 0A evidence exists:

1. Read every S1–S14 fixture.
2. Complete `docs/HOST-FACTS.md`.
3. Reconcile findings with `ARCHITECTURE.md §4`.
4. Present O3 and O4 to the owner with evidence-backed options if still unresolved.
5. Obtain the owner's explicit O3/O4 decisions.
6. Change `docs/STATUS.md` from `0A` to `0B`.
7. Only then create Phase 0B production skeleton/code.

Do not infer owner decisions from preference or convenience.

---

## 8. Stop and ask the owner when

Stop implementation and ask when:

- a change would weaken/reinterpret an invariant;
- a new runtime dependency is required;
- an open decision in `ARCHITECTURE.md §9` must be chosen;
- live host evidence contradicts `ARCHITECTURE.md` or existing `HOST-FACTS.md`;
- a phase acceptance criterion appears impossible or incorrect;
- strong group-chat epistemic isolation would require host orchestration changes;
- a PocketRisu bridge/fork appears necessary according to measured performance/behavior.

When asking, state:

```text
Observed evidence
Current architectural rule
Why implementation is blocked
Smallest decision needed from owner
Options and trade-offs
```

Do not ask questions merely to avoid making an implementation choice already covered by the docs.

---

## 9. Working style

- Prefer small, reviewable changes.
- One reconciliation case / endpoint / migration per commit once those concepts are unlocked.
- Write fixture-driven tests before implementation when real fixtures exist.
- Keep pure logic separate from host/API code.
- Put non-obvious architectural decisions in an ADR, not a long source comment.
- Keep host-specific code inside the adapter.
- Keep domain/storage code out of HTTP handlers.
- Avoid speculative abstractions.
- Favor explicit, auditable code over cleverness.

---

## 10. Coding conventions

### Python — once Phase 0B is unlocked

- Python 3.12.
- Type hints everywhere.
- Pydantic models at HTTP/API boundaries.
- psycopg 3 with explicit SQL per architecture decision.
- UTC `timestamptz`.
- UUIDv7 for NMOS-generated IDs.
- Host IDs are stored verbatim as `host_logical_id`.
- Structured logs include `trace_id`.
- Do not log full message bodies at info level.

### TypeScript / JavaScript

- Pure functions for:
  - canonicalization,
  - hashing,
  - manifest construction,
  - injection,
  - marker detection.
- Host calls isolated behind `host.ts` once the production adapter exists.
- Never use array index as durable message identity.
- PocketRisu `Message.chatId` is the host logical ID only within the verified semantics.
- Normalize Unicode NFC and CRLF→LF where the phase spec requires canonical hashing.

---

## 11. Commands

### Phase 0B (current code)

```bash
cp .env.example .env && docker compose up -d --build           # postgres 16 + sidecar on 127.0.0.1:8790
cd apps/sidecar && uv sync && uv run pytest                     # needs compose postgres (127.0.0.1:5436)
cd adapters/pocketrisu-plugin && npm install && npm test && npm run typecheck && npm run build
docker compose exec sidecar nmos-migrate                        # apply migrations
docker compose exec sidecar nmos-rebuild                        # rebuild active_membership from commits
```

After installing or updating the plugin in PocketRisu, reload the page (ARCHITECTURE H13).

### Phase 0A spike tooling (kept for re-running host observations)

```bash
# optional local observation collector (stdlib only)
python tools/spike_collector.py --host 0.0.0.0 --port 8765

# optional stub OpenAI-compatible model with forced failures (stdlib only)
python tools/spike_stub_llm.py --port 8766

# synthetic S14 import file
python tools/make_synthetic_chat.py --messages 1000

# summarize collected observations / before-after manifest diffs
python tools/spike_report.py fixtures/host/incoming

# inspect the spike script
cat adapters/pocketrisu-spike/nmos-host-spike.js
```

The PocketRisu spike itself is loaded through PocketRisu's plugin UI.

### Future commands

Add commands for later phases only when the phase is unlocked and the files exist. Keep this section accurate.

---

## 12. Definition of done for any change

A change is done only when:

- it is inside current scope;
- relevant tests/checks pass;
- no fake host evidence was introduced;
- docs reflect any changed behavior or decision;
- `docs/STATUS.md` is accurate;
- no out-of-scope architecture was pre-built;
- the next blocked action is explicit.

For Phase 0A specifically, "code complete" and "phase complete" are different states.
