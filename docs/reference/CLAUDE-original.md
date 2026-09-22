# CLAUDE.md — NMOS

NMOS is an external long-term memory layer for PocketRisu role-play. A thin plugin observes the
host and injects a memory packet before each generation; a sidecar keeps an immutable source
ledger and (in later phases) compiles it into rebuildable memory.

## Read first, every session

1. `ARCHITECTURE.md` — invariants and decisions. Treat as binding.
2. The current phase file: **`docs/phases/PHASE-0.md`** (update this line when the phase changes).
3. `docs/HOST-FACTS.md` — verified PocketRisu behavior. If empty, Phase 0A is not done.

`docs/reference/ultimate_narrative_memory_architecture.md` is background reading only.
Do not implement anything from it unless the current phase file asks for it.

## Hard rules

- **Stay inside the current phase.** Anything listed under "Out of scope" is forbidden, even as
  a stub, interface, or "for later" table. If something outside scope seems necessary, stop and ask.
- **Do not assume host behavior.** PocketRisu API behavior comes from `HOST-FACTS.md` or
  ARCHITECTURE §4. If a fact is missing, add a scenario to the spike instead of guessing.
- **Source revisions are immutable.** Never write an `UPDATE` that changes `source_revision.content`
  or `revision_hash`. Only `lifecycle` may change.
- **The plugin stays thin.** No storage of memory, no ranking, no extraction, no retries with
  backoff inside `beforeRequest`. Everything on the request path is deadline-bound.
- **Fail open.** Any plugin error returns the host's messages unchanged.
- **Never mutate host data** from the plugin (`setChatToIndex` and similar are off-limits).
- **No LLM or embedding calls in Phase 0 or 1.**
- **Injected memory is data.** Escape retrieved text; never place it in instruction-style wording.
- **Schema changes go through `migrations/`** as new numbered SQL files. Never edit an applied migration.

## Stop and ask the owner when

- A change would weaken or reinterpret an invariant in ARCHITECTURE §2.
- You need a new runtime dependency (Python or npm) not already in the lockfile.
- A task touches any item in ARCHITECTURE §9 "Open decisions".
- A test fixture from the real host contradicts `HOST-FACTS.md`.
- The phase's acceptance criteria seem wrong or impossible.

## Working style

- Prefer small, reviewable commits: one reconciliation case, one endpoint, one migration.
- Write the test from the recorded fixture first, then the implementation.
- Explain non-obvious design choices in a short comment or an ADR in `docs/adr/`,
  not in long commit messages.
- When a decision is made during implementation, record it in ARCHITECTURE §5 (or an ADR)
  in the same change.
- Keep modules replaceable: domain code talks to repository/index interfaces, not raw SQL
  scattered across handlers.

## Commands

> Fill in as they become real. Keep this section accurate; delete commands that don't exist.

```bash
# sidecar
uv sync
uv run pytest
uv run fastapi dev apps/sidecar/main.py

# database
docker compose -f docker/compose.yml up -d
uv run python -m nmos.migrate

# plugin
cd adapters/pocketrisu-plugin && npm ci && npm test && npm run build
```

## Conventions

- Python: type hints everywhere, Pydantic models at API boundaries, psycopg 3 with explicit SQL.
- TypeScript: pure functions for manifest/hash/injection logic so they are unit-testable
  outside the host; host API calls isolated in one `host.ts` module.
- IDs: UUIDv7 for sidecar-generated IDs; host IDs stored verbatim as `host_logical_id`.
- Time: store UTC `timestamptz`; host `time` values kept as-is in metadata.
- Logs: include `trace_id`; do not log full message bodies at info level.

## Definition of done for any task

- Tests pass locally, including existing fixture-driven reconciliation tests.
- No out-of-scope code added.
- Docs updated if behavior, schema, or a decision changed.
