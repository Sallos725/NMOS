# AGENTS.md — NMOS Codex Operating Contract

NMOS (Narrative Memory OS) is an external long-term memory layer for PocketRisu role-play.
PocketRisu is the host. NMOS is the memory substrate. The host adapter stays thin.

This file is the operating contract for Codex and other implementation agents.

---

## 0. What to do when the owner says only "build it", "make it", or equivalent

Continue the **current phase** as far as possible without violating any stop condition.

The current phase, the latest release and what is complete are in `docs/STATUS.md` ("Current phase");
read them there, not here. Unless STATUS names a current phase, none is: hard POV isolation (D9
`character_pov`), the rest of Track B B3 and B4–B7 are not authorized. Bug fixes, correctness, docs and
CI work stay allowed. The planned order of future work is `docs/ROADMAP-1.0.md` (a draft; each stage still
needs its phase document and owner approval).

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
4. `docs/phases/PHASE-N.md` — the phase spec for the code you touch (`PHASE-18.md` is the latest, approved and next;
   `PHASE-17.md` is current; `PHASE-0.md`…`PHASE-16.md` still define the behavior they introduced).
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
| 6 — item transitions and conflicts (Track B, B2) | complete (2026-09-24, beta.13) | `PHASE-6.md`, ADRs 0016–0017 |
| 7 — promise threads and event salience (Track B, B3) | complete (2026-09-24, beta.14) | `PHASE-7.md`, ADRs 0019–0020 |
| 8 — event participants (Track B, B3) | complete (2026-09-24, beta.15) | `PHASE-8.md`, ADR 0021 |
| 9 — accountable packets (Track B, B6 narrowed) | complete (2026-09-26, beta.19) | `PHASE-9.md`, ADR 0027 |
| 10 — knowledge and secrets (Stage 4; Track B, B5 narrowed) | complete (2026-09-27), not released | `PHASE-10.md`, ADRs 0033–0037 |
| 11 — narrative engine, part 1 (Stage 5) | complete (2026-09-28), not released; one criterion partly met (owner accepted) | `PHASE-11.md`, ADRs 0038–0040 |
| 12 — narrative engine, part 2 (Stage 5: summaries, character state) | complete (2026-09-28), not released; the latency criterion missed by 3 ms at 10,000 messages (owner accepted) | `PHASE-12.md`, ADRs 0042–0043 |
| 13 — verification and repair, part 1 (Stage 6: owner repair, needs-attention queue) | complete (2026-09-28), not released; the latency criterion missed by 2 ms (owner accepted) | `PHASE-13.md`, ADR 0044 |
| 14 — verification and repair, part 2 (Stage 6: canon sources) | complete (2026-09-29), not released; the latency criterion missed with a 200-entry lorebook read whole (owner accepted) | `PHASE-14.md`, ADRs 0045–0047 |
| 15 — a packet that fills its budget (P1 of `docs/proposals/PUBLIC-RELEASE-AND-BENCHMARK.md`) | complete (2026-09-29), not released | `PHASE-15.md`, ADR 0049 |
| 16 — export and restore (Stage 6, part 3) | complete (2026-09-29) but for the owner's phone check of the panel's Export (K38, open); not released | `PHASE-16.md`, ADR 0050 |
| 17 — model-call cost and fallback outcomes (C4, C5 of `docs/proposals/IDEA-SURVEY-2026-09-29.md`) | **current** (approved 2026-09-29) | `PHASE-17.md` |
| 18 — recall by the words that matter (keyword lexical recall, `packet-v10` excerpts) | **next** (approved 2026-09-30; starts when Phase 17 is complete) | `PHASE-18.md` |
| 19+ (Stages 7–8 of `docs/ROADMAP-1.0.md`) | **not authorized** | `docs/ROADMAP-1.0.md`, `docs/proposals/TRACK-B-PHASE-5-PLUS.md` |

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
- Storage is PostgreSQL; replacing it is not a goal (invariant 9, amended 2026-09-26).
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
   For a material change, run the scoped review workflow (§14); cross-model review is required only when §14 classifies the change as high risk.
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

Upgrade fixtures (audit A-16; a database written by an earlier release, restored and upgraded by
`tests/test_upgrade.py`). Needs the compose Postgres; runs that release's code from a temporary worktree:

```bash
cd apps/sidecar && uv run python ../../tools/make_upgrade_fixture.py v0.1.0-beta.16   # → fixtures/upgrade/
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

# the canon probe (Phase 14; shapes only, never alters the prompt; setup in fixtures/host/canon-v1.13.0-2026-09-28/)
cat adapters/pocketrisu-spike/nmos-canon-probe.js
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

---

## 13. Release cadence

Owner decisions, 2026-09-26 and 2026-09-27. The road to 1.0 is `docs/ROADMAP-1.0.md`. `main` takes merges
as before; tags follow these rules.

| Kind | Examples | Release |
|---|---|---|
| Urgent | memory lost for every request, a security fix, data loss or corruption | a patch release (`0.N.x`) right away |
| Milestone | a roadmap stage meets its done criteria | the next minor version (`0.2.0` … `0.6.0`, then `1.0.0`) |
| Everything else | features of the stage in progress, UI, performance, docs, tests, defaults | no tag; ships with the next milestone |

- **Every `main` merge publishes `ghcr.io/sallos725/nmos-sidecar:edge`** (and `:edge-<commit sha>`) after
  CI passes, with no tag and no GitHub release. The owner runs it to try work in progress; the plugin
  for the same commit is `adapters/pocketrisu-plugin/dist/nmos-pocketrisu.js`. A migration on `main`
  reaches an `:edge` database before any release, so back up before switching production to `:edge`.
- **A patch release must not ship half a stage.** If `main` holds user-visible work of an unfinished
  stage, branch `release/0.N` from the last tag, cherry-pick the fix, and tag there.
- **At most one extractor generation per milestone.** An extractor prompt or registry change goes on the
  "Queued for the next extractor generation" list in `docs/STATUS.md` and ships with the stage.
- **A bug fix that needs a migration, a new predicate, a new extractor generation, a new UI feature or a
  new ADR is feature work**: it joins the current stage's plan, or ask the owner. Keep other fixes small.
- Every release before `1.0.0` is a GitHub pre-release (`release.yml`).

---

## 14. Scoped review and cross-model escalation

Every non-trivial change gets a review before the lead reports it done. The default is a **diff-scoped
self-review by the lead**. An independent review by the other model is an escalation for high-risk changes,
not a repository-wide second pass.

### Scope

- Start from the branch diff against the task base (normally `origin/main`):
  `git diff --name-only origin/main...HEAD` and `git diff origin/main...HEAD`.
- Review all changed code. Expand only as needed into direct callers/callees, shared interfaces/types,
  directly relevant tests, and schema/migrations when the changed path depends on them.
- Do not inspect `fixtures/model/**`, generated output such as `dist/**`, large JSON/JSONL artifacts,
  historical changelogs, or unrelated documentation unless a changed code path specifically requires it.
- Do not perform a repository-wide audit unless the owner explicitly asks for one.

### Risk and escalation

A change is **high risk** when it can materially affect one or more of these guarantees:

- stored data, schema, migrations, upgrades, backfills, deletion, or data-loss recovery;
- reconciliation, immutable source history, membership, canon, identity, or provenance;
- authentication, secrets, authorization, security boundaries, or sensitive logging;
- retrieval/injection semantics that change memory selection, isolation, provenance, or fail-open behavior;
- deployment compatibility where a mistake can corrupt persisted state or weaken a security boundary.

For a high-risk change, the lead gets **one** independent, read-only review through
`.ai/scripts/peer-review` before reporting the change done (how-to: `.ai/README.md`; Claude's workflow:
`.claude/skills/peer-review`). Use `architecture` for a design/invariant question and `security` for a
sensitive flow.

For other non-trivial changes, the lead's scoped self-review is sufficient. Trivial edits (for example
wording, typo fixes, or test-only renames with no behavior change) may skip review; say so in the report.

### External reviewer rules

- The lead names the reviewer: Claude leading calls `codex`; Codex leading calls `claude`.
- Keep the external review scoped to the diff and the minimum dependency cone. On an inline run, attach
  only the authority/spec files and touched files needed to validate the high-risk property; never attach
  the whole tree.
- Findings are hypotheses. The lead verifies every cited line or reproduction, fixes what is confirmed,
  reruns the relevant tests, and reports what it rejected and why. An `ARCHITECTURE.md §9` decision goes
  to the owner.
- The reviewer never edits, commits, delegates, or calls the script again. One external review per change;
  never loop Codex → Claude → Codex.
- If the reviewer CLI is unavailable or authentication fails, report that fact and continue without
  silently substituting a repository-wide self-audit.

This overlay grants no exceptions: this file, `ARCHITECTURE.md`, and the current phase spec take
precedence, and a reviewer's suggestion does not authorize scope.
