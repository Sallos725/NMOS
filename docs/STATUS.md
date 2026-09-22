# NMOS Status

## Current phase

**Phase 0 — complete (2026-09-22).** Phase 0A exit criteria and all Phase 0B acceptance criteria are met.

**Public beta `v0.1.0-beta.3` (2026-09-22), private repository.** Phases 1–3 complete; Phase 4 in
its soft form (knowledge marks `known_by` / `hidden_from`, D19). Plugin settings panel configures
providers, embeddings, tuning and parser rules. Validated with a real RisuRealm sim bot and a fresh
install from release assets. Still outside the beta: hard character-POV isolation, threads/causal
links, verifier, MCP (Phase 5+).

## What exists

| Part | Where | State |
|---|---|---|
| Host evidence | `docs/HOST-FACTS.md`, `fixtures/host/a14c911-2026-09-22/` | S1–S14 (S13 N/A), Q1–Q8, 0B runtime findings |
| Architecture | `ARCHITECTURE.md` | H1–H14, D1–D15, O2/O3/O4 resolved |
| Sidecar + worker | `apps/sidecar` (Python 3.12, FastAPI, psycopg 3, httpx) | sync, hybrid recall, state, facts, inspector; `nmos-worker` jobs |
| Schema | `migrations/0001`–`0006` | source layer, state, extraction/jobs, embeddings, config, knowledge |
| Plugin | `adapters/pocketrisu-plugin` → `dist/nmos-pocketrisu.js` | gating (D13), manifest, sync, recall injection, fail-open |
| Deployment | `docker-compose.yml`, `docker/sidecar.Dockerfile`, `.env.example` | postgres 16 + sidecar |
| Tests | `apps/sidecar/tests` (62), `adapters/pocketrisu-plugin/test` (28) | all passing (CI) |
| Performance | `docs/perf/phase0.md` | all Phase 0 targets met |
| Decisions | `docs/adr/0001`–`0005` | gating, branches, token (optional), recall scoring, hybrid tuning |
| Phase specs | `docs/phases/PHASE-0.md`–`PHASE-4.md` | 0–3 met; 4 soft form met |
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
- Making the repository and GHCR package public — checklist below.
- Phase 5+ scope.

## Before making the repository public

| Item | State |
|---|---|
| Security notice (plain-text API keys in `app_config`, no internet exposure, token for LAN/Tailscale) | done — README "Security", guide.ko "보안 주의" |
| README/guide claims scoped to the tested PocketRisu build | done |
| Private IP in experiment notes generalized (`192.168.x.x`) | done |
| Outdated agent docs (`CODEX-PROMPT.md`, `STARTER-CONTENTS.md`) archived to `docs/reference/`; `AGENTS.md` current; `PHASE-4.md` added | done |
| Commit author email in git history | owner decision (keep, or rewrite history to a noreply address before publishing) |
| GHCR `nmos-sidecar` package visibility → Public | owner action (package settings); anonymous pull currently fails with 401/403 |
| Anonymous `docker pull` + fresh install from release assets after the two items above | pending |
| Repository description/topics, README screenshot | pending |
