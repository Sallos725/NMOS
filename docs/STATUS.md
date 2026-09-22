# NMOS Status

## Current phase

**Phase 0 — complete (2026-09-22).** Phase 0A exit criteria and all Phase 0B acceptance criteria are met.

**Public beta `v0.1.0-beta.3` (2026-09-22), private repository.** Phases 1–3 complete. Phase 4 soft
subset complete (knowledge scope `public` / `limited` / `unknown`, D19, `docs/phases/PHASE-4.md`).
Plugin settings panel configures providers, embeddings, tuning and parser rules. Validated with a
real RisuRealm sim bot and a fresh install from release assets. Still outside the beta: hard
character-POV isolation, threads/causal links, verifier, MCP (Phase 5+; not authorized).

**Stabilization (issues #6–#14) implemented on the `main` line after beta.3, not yet released.**
Projection generations and coverage (D20, ADR 0006), normalized text (D21), knowledge scope (ADR 0007),
CORS PUT, large-chat envelope (`docs/perf/scale.md`), release gate. The next beta is a stabilization
release; see `CHANGELOG.md` → Unreleased for known limitations.

## What exists

| Part | Where | State |
|---|---|---|
| Host evidence | `docs/HOST-FACTS.md`, `fixtures/host/a14c911-2026-09-22/` | S1–S14 (S13 N/A), Q1–Q8, 0B runtime findings |
| Architecture | `ARCHITECTURE.md` | H1–H14, D1–D21, O2/O3/O4 resolved |
| Sidecar + worker | `apps/sidecar` (Python 3.12, FastAPI, psycopg 3, httpx) | sync, hybrid recall, state, facts, inspector; `nmos-worker` jobs |
| Schema | `migrations/0001`–`0009` | source layer, state, extraction/jobs, embeddings, config, knowledge, normalized text, projection generations, knowledge scope |
| Plugin | `adapters/pocketrisu-plugin` → `dist/nmos-pocketrisu.js` | gating (D13), manifest, sync, recall injection, fail-open |
| Deployment | `docker-compose.yml`, `docker/sidecar.Dockerfile`, `.env.example` | postgres 16 + sidecar |
| Tests | `apps/sidecar/tests` (94), `adapters/pocketrisu-plugin/test` (29) | all passing |
| Performance | `docs/perf/phase0.md`, `docs/perf/scale.md` | Phase 0 targets met; default deadline met up to ≈5k messages, fail open beyond ≈8k |
| Decisions | `docs/adr/0001`–`0007` | gating, branches, token (optional), recall scoring, hybrid tuning, projection generations, knowledge scope |
| Phase specs | `docs/phases/PHASE-0.md`–`PHASE-4.md` | 0–3 met; 4 soft subset met |
| Retro | `docs/phases/PHASE-0-RETRO.md` | |

## Evidence status (Phase 0A)

| Scenario | Status | Fixture/evidence |
|---|---|---|
| S1–S12 | run | `fixtures/host/a14c911-2026-09-22/` (S4b, S8b variants) |
| S13 | not executable on `a14c911` (no group chat); N/A accepted by owner | HOST-FACTS S13 |
| S14 | run (100 / 1,000 messages) | `…/*S14*` |

## Open owner decisions

- O1 — relationship to MIRRA / VEIL.
- O5 — retention of abandoned worldlines, `host_observation` growth, and superseded projection generations (ADR 0006).
- Making the repository and GHCR package public — checklist below.
- Phase 5+ scope.

## Before making the repository public

| Item | State |
|---|---|
| Security notice (plain-text API keys in `app_config`, no internet exposure, token for LAN/Tailscale) | done — README "Security", guide.ko "보안 주의" |
| README/guide claims scoped to the tested PocketRisu build | done |
| Private IP in experiment notes generalized (`192.168.x.x`) | done |
| Outdated agent docs (`CODEX-PROMPT.md`, `STARTER-CONTENTS.md`) archived to `docs/reference/`; `AGENTS.md` current; `PHASE-4.md` added | done |
| Commit author email in git history | done — `main` and tags `v0.1.0-beta.1`–`3` rewritten to the GitHub noreply address |
| Repository description/topics | done |
| GHCR `nmos-sidecar` package visibility → Public | owner action (package settings); anonymous pull failed with 401/403 when last checked |
| Anonymous `docker pull` + fresh install from release assets after the item above | pending |
| README screenshot (settings panel or Inspector) | pending |
