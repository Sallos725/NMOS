# NMOS Status

## Current phase

**Phase 0 — complete (2026-09-22).** Phase 0A exit criteria and all Phase 0B acceptance criteria are met.

**Current: Phase 1–3 toward a public beta (owner authorization 2026-09-22).** Specs:
`docs/phases/PHASE-1.md` (deterministic state, inspector), `PHASE-2.md` (LLM extraction, facts),
`PHASE-3.md` (hybrid retrieval). Phase 4 (principal modes) and 5+ (threads, MCP) are outside the beta.

## What exists

| Part | Where | State |
|---|---|---|
| Host evidence | `docs/HOST-FACTS.md`, `fixtures/host/a14c911-2026-09-22/` | S1–S14 (S13 N/A), Q1–Q8, 0B runtime findings |
| Architecture | `ARCHITECTURE.md` | H1–H14, D1–D15, O2/O3/O4 resolved |
| Sidecar | `apps/sidecar` (Python 3.12, FastAPI, psycopg 3) | reconcile / bodies / retrieve / output / trace / health |
| Schema | `migrations/0001_source_layer.sql` | source layer + observations + traces; immutability triggers |
| Plugin | `adapters/pocketrisu-plugin` → `dist/nmos-pocketrisu.js` | gating (D13), manifest, sync, recall injection, fail-open |
| Deployment | `docker-compose.yml`, `docker/sidecar.Dockerfile`, `.env.example` | postgres 16 + sidecar |
| Tests | `apps/sidecar/tests` (35), `adapters/pocketrisu-plugin/test` (22) | all passing |
| Performance | `docs/perf/phase0.md` | all Phase 0 targets met |
| Decisions | `docs/adr/0001`–`0004` | gating, branches, token, recall scoring |
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
- Phase 1 scope/spec approval.
