# NMOS Status

## Current phase

**Phase 0 — complete (2026-09-22).** Phase 0A exit criteria and all Phase 0B acceptance criteria are met.

**Phases 1–3 complete — public beta `v0.1.0-beta.1` (2026-09-22).** Specs with evidence:
`docs/phases/PHASE-1.md`, `PHASE-2.md`, `PHASE-3.md`. Outside the beta: Phase 4 (principal /
character-POV knowledge, D9) and 5+ (threads, causal links, verifier, MCP).

## What exists

| Part | Where | State |
|---|---|---|
| Host evidence | `docs/HOST-FACTS.md`, `fixtures/host/a14c911-2026-09-22/` | S1–S14 (S13 N/A), Q1–Q8, 0B runtime findings |
| Architecture | `ARCHITECTURE.md` | H1–H14, D1–D15, O2/O3/O4 resolved |
| Sidecar + worker | `apps/sidecar` (Python 3.12, FastAPI, psycopg 3, httpx) | sync, hybrid recall, state, facts, inspector; `nmos-worker` jobs |
| Schema | `migrations/0001`–`0004` | source layer, state, extraction/jobs, embeddings (pgvector) |
| Plugin | `adapters/pocketrisu-plugin` → `dist/nmos-pocketrisu.js` | gating (D13), manifest, sync, recall injection, fail-open |
| Deployment | `docker-compose.yml`, `docker/sidecar.Dockerfile`, `.env.example` | postgres 16 + sidecar |
| Tests | `apps/sidecar/tests` (52), `adapters/pocketrisu-plugin/test` (23) | all passing (CI) |
| Performance | `docs/perf/phase0.md` | all Phase 0 targets met |
| Decisions | `docs/adr/0001`–`0005` | gating, branches, token (optional), recall scoring, hybrid tuning |
| Retro | `docs/phases/PHASE-0-RETRO.md` | |

## Evidence status (Phase 0A)

| Scenario | Status | Fixture/evidence |
|---|---|---|
| S1–S12 | run | `fixtures/host/a14c911-2026-09-22/` (S4b, S8b variants) |
| S13 | not executable on `a14c911` (no group chat); N/A accepted by owner | HOST-FACTS S13 |
| S14 | run (100 / 1,000 messages) | `…/*S14*` |

## Open owner decisions

- O1 — relationship to MIRRA / VEIL.
- O5 — retention of abandoned worldlines (and `host_observation` growth).
- Phase 4+ scope.
