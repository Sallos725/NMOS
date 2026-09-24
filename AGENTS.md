# AGENTS.md — NMOS Codex Operating Contract

NMOS (Narrative Memory OS) is an external long-term memory layer for PocketRisu role-play.
PocketRisu is the host. NMOS is the memory substrate. The host adapter stays thin.

This file is the operating contract for Codex and other implementation agents.

---

## 0. What to do when the owner says only "build it", "make it", or equivalent

Continue the **current phase** as far as possible without violating any stop condition.

The current phase is always the one named in `docs/STATUS.md`. As of 2026-09-23:

> **Phase 5 — Entity Identity and Semantic Assertions (`docs/phases/PHASE-5.md`, ADRs 0012–0014) is
> complete (2026-09-24, `v0.1.0-beta.12`).** Phases 0–3 and the Phase 4 soft subset are complete.
> Public beta. No phase is current: hard POV isolation (D9 `character_pov`) and everything past Phase 5
> (Track B, B2–B7) are not authorized. Bug fixes, correctness, docs and CI work stay allowed.

Do not start a phase without its phase document and without the evidence it requires. Work that is
not a phase feature (bug fixes, correctness, docs, CI) is allowed at any time. It must still keep the
invariants and must not pre-build the next phase.

A short or vague owner prompt does not authorize scope expansion.

---

## 1. Authority order — read every session

Read these files in this order before changing code:

1. `AGENTS.md` — workflow and implementation-agent rules.
2. `ARCHITECTURE.md` — stable architecture contract, invariants, verified facts, decisions.
3. `docs/STATUS.md` — current phase and open owner decisions.
4. `docs/phases/PHASE-N.md` — the phase spec for the code you touch (`PHASE-4.md` is the latest;
   `PHASE-0.md`…`PHASE-3.md` still define the behavior they introduced).
5. `docs/HOST-FACTS.md` — facts established by the live PocketRisu spike.
6. Relevant ADRs in `docs/adr/`.

Reference only:

- `docs/reference/ultimate_narrative_memory_architecture.md`
- `docs/reference/initial_narrative_memory_plan.md`
- `docs/reference/CLAUDE-original.md`
- `docs/reference/CODEX-PROMPT.md`, `docs/reference/STARTER-CONTENTS.md` (historical Phase 0A handoff)

Reference documents explain intent. They are **not** permission to implement future-phase features.

If two normative documents appear to conflict:

- architecture invariants win over implementation convenience;
- the current phase defines allowed scope;
- do not silently reinterpret either document;
- stop and report the conflict if it affects implementation.

---

## 2. Current phase gate

| Phase | State | Spec |
|---|---|---|
| 0A / 0B | complete (host evidence S1–S14, O3/O4 resolved) | `PHASE-0.md`, `PHASE-0-RETRO.md` |
| 1 — deterministic state | complete (beta) | `PHASE-1.md` |
| 2 — bounded extraction | complete (beta) | `PHASE-2.md` |
| 3 — hybrid recall | complete (beta) | `PHASE-3.md` |
| 4 — character knowledge, soft subset | complete (beta) | `PHASE-4.md` |
| 4 — hard POV isolation (`character_pov`) | **not authorized** | — |
| 5 — entity identity and semantic assertions (Track B, B1) | complete (2026-09-24, beta.12) | `PHASE-5.md`, ADRs 0012–0014 |
| 6 — item transitions and conflicts (Track B, B2) | **draft, not authorized** | `PHASE-6.md` (draft) |
| 7+ (Track B, B3–B7) | **not authorized** | `docs/proposals/TRACK-B-PHASE-5-PLUS.md` |

Before any further Phase 4/5 feature work, the stabilization issues #6–#14 had to land (D19–D21,
ADR 0006/0007, `docs/perf/scale.md`).

Real-world evidence gates are not boxes an agent may check optimistically. Host behavior comes from
`ARCHITECTURE.md §4` and `docs/HOST-FACTS.md`; performance claims come from measurements in
`docs/perf/`.

**Never fabricate fixtures, measurements, host facts, timings, or scenario results.**

If code is ready but a live host or model check has not been run, stop at the evidence boundary and
tell the owner exactly what to run. Re-running host evidence (e.g. for a new PocketRisu version)
follows the Phase 0A rules: real scenarios against the target build, recorded fixtures, corrections to
`ARCHITECTURE.md §4` where evidence contradicts it.

---

## 3. Non-negotiable architecture invariants

Treat `ARCHITECTURE.md §2` as binding. In particular:

- Raw evidence is never destroyed (only the owner may delete a whole conversation; ADR 0009).
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
- Do not add a PocketRisu fork or bridge patch. `ARCHITECTURE D1` is binding unless the owner decides
  otherwise.

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
- Schema changes go through new numbered SQL files in `migrations/`.
- Never edit an already-applied migration.
- Derived rows (extractions, embeddings, normalized text) carry the generation/normalizer that
  produced them (D20, D21). A change to a prompt, registry, normalizer, chunker, model or endpoint
  must produce a new generation, never overwrite or silently reuse old rows.

### Plugin

- Keep the plugin thin.
- No memory DB, ranking, semantic extraction, embedding, or long-running work in the plugin.
- No retry-with-backoff loops inside `beforeRequest`.
- Any request-path call must have a hard deadline.
- Fail open: return the host's messages unchanged on plugin failure.
- Never call `setChatToIndex`, `setCharacterToIndex`, or otherwise mutate host data.
- Treat injected memory as untrusted data, not as instructions.
- All injection logic must be idempotent because `beforeRequest` can run more than once.

### Models

- Generative LLM calls run only in the worker, never on the request path (PHASE-2).
- The request path may embed the query only, with its own short timeout and lexical fallback (PHASE-3).
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

## 6. Phase 0A spike (historical)

The Phase 0A observation spike (`adapters/pocketrisu-spike/`, `tools/spike_*`) is kept only for
re-running host observations. If it is re-run, it must still never inject memory, alter prompts,
mutate chats, or call a model. Its results go to `docs/HOST-FACTS.md` and `fixtures/host/`.

---

## 7. Starting a new phase

1. The owner authorizes the phase explicitly.
2. A `docs/phases/PHASE-N.md` exists with goal, scope, out-of-scope and acceptance criteria.
3. `docs/STATUS.md` and §0/§2 of this file name it as current.
4. Only then implement it; record evidence against each acceptance criterion.

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

### Python

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
- Host calls isolated behind `host.ts`.
- Never use array index as durable message identity.
- PocketRisu `Message.chatId` is the host logical ID only within the verified semantics.
- Normalize Unicode NFC and CRLF→LF where the phase spec requires canonical hashing.

---

## 11. Commands

### Current code

```bash
cp .env.example .env && docker compose up -d --build           # postgres 16 + sidecar on 127.0.0.1:8790
cd apps/sidecar && uv sync && uv run pytest                     # needs compose postgres (127.0.0.1:5436)
cd adapters/pocketrisu-plugin && npm install && npm test && npm run typecheck && npm run build
docker compose exec sidecar nmos-migrate                        # apply migrations
docker compose exec sidecar nmos-rebuild                        # rebuild active_membership from commits
docker compose exec sidecar nmos-rebuild --text                 # rewrite the normalized-text projection
```

Scale benchmarks (#12, results in `docs/perf/scale.md`):

```bash
cd apps/sidecar && uv run python ../../tools/bench_scale.py 1000,5000,10000,25000
cd adapters/pocketrisu-plugin && node scripts/bench-manifest.mjs 1000,5000,10000,25000
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

Keep this section accurate when commands change.

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

"Code complete" and "phase complete" are different states: a phase is complete only when its
evidence-bearing acceptance criteria were actually met.
