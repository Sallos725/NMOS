# NMOS Status

## Current phase

**Phase 5 — Entity Identity and Semantic Assertions: current (authorized 2026-09-23).** Spec
`docs/phases/PHASE-5.md`, ADRs 0012–0014. Step 1 of 6 (generation fallback, ADR 0014) done and released in `v0.1.0-beta.11`, with the fix for
a stall in fact and state reads after edits in long chats (`docs/perf/scale.md`). Steps 2–3
(`extract-v5`, migration 0014, fact reading and packet per ADR 0013, D27), step 4 (read-time
entities, ADR 0012, D26) and step 5 (name hints in extraction, D7 amended) done, unreleased. Next: step 6
(real-model evaluation tier, measurements, release).
Outside the phase (owner decision 2026-09-24, D28): an optional progress display on the chat screen,
unreleased.

**Phase 0 — complete (2026-09-22).** Phase 0A exit criteria and all Phase 0B acceptance criteria are met.

**Public beta `v0.1.0-beta.11` (2026-09-24), public repository and image.** Phase 5 step 1: a new LLM
model re-extracts only each chat's recent window and older turns keep the previous model's facts (ADR
0014, D20 amended); fact and state reads no longer stall for seconds after an edit, reroll or swipe in a
long chat. No schema change. `v0.1.0-beta.10` (2026-09-23): Track A stabilization:
verified append fast path and incremental plugin manifest (ADR 0010, migration 0013), default request
deadline 3 s after a real-host check at 5k/10k/15k messages (D24), one current holder per item (ADR
0011, D25), broad lexical queries stopped at 200 matches, and a deterministic memory evaluation
(`docs/perf/eval-baseline.md`). Evidence: `docs/perf/scale.md`. `v0.1.0-beta.9` (2026-09-23): the owner can delete a
conversation from the panel's Inspector, raw messages included (ADR 0009, D23, invariant 1 amended;
migration 0012). Evidence: `docs/perf/scale.md` (delete timings, sync A/B), real-UI host check in
ADR 0009. `v0.1.0-beta.8` (2026-09-23): facts are extracted per turn
(user message + reply) with turn-counted backfill, and each chat has "extract all history" and
"rebuild memory" in the Inspector (ADR 0008, D7/D17 revised, D22; migration 0011). Evidence:
`docs/perf/turn-extraction.md` (model comparison, real-UI host check), `docs/perf/scale.md` re-check.
`v0.1.0-beta.7` (2026-09-23): main-generation gating no
longer assumes a preset layout (ADR 0001 amendment 2): presets that add instructions after the user's
turn got no memory in beta.6 and earlier. `v0.1.0-beta.6` (2026-09-23): the Inspector opens inside
the NMOS panel (Status | Inspector | Settings tabs): PocketRisu sandboxes plugins without
`allow-popups`, so the beta.5 link could not open a tab (ARCHITECTURE H15). One PocketRisu settings
entry. `v0.1.0-beta.5` (2026-09-23) was a packaging release: multi-arch image (`linux/amd64`,
`linux/arm64`), `:latest` tag on every release, Inspector "—" for never-enabled features, README
screenshots. `v0.1.0-beta.4` (2026-09-23) was the
stabilization release (issues #6–#19) and UI review on top of `v0.1.0-beta.3` (2026-09-22). Phases 1–3 complete. Phase 4 soft
subset complete (knowledge scope `public` / `limited` / `unknown`, D19, `docs/phases/PHASE-4.md`).
Plugin settings panel configures providers, embeddings, tuning and parser rules. Validated with a
real RisuRealm sim bot and a fresh install from release assets. Still outside the beta: hard
character-POV isolation, threads/causal links, verifier, MCP (Phase 5+; not authorized).

**beta.4 contents.** Projection generations and coverage (D20, ADR 0006), normalized text (D21),
knowledge scope (ADR 0007), CORS PUT, large-chat envelope (`docs/perf/scale.md`), release gate, no
search of unverifiable beta.3 vectors (#17), immediate provider disable (#18), strict config types
(#19), one NMOS panel (status/settings tabs, chat-menu entry, Korean/English), Inspector labels.
Known issues (current list): `docs/KNOWN-ISSUES.md`.

## What exists

| Part | Where | State |
|---|---|---|
| Host evidence | `docs/HOST-FACTS.md`, `fixtures/host/a14c911-2026-09-22/` | S1–S14 (S13 N/A), Q1–Q8, 0B runtime findings |
| Architecture | `ARCHITECTURE.md` | H1–H16, D1–D28, O2/O3/O4 resolved |
| Sidecar + worker | `apps/sidecar` (Python 3.12, FastAPI, psycopg 3, httpx) | sync, hybrid recall, state, facts, inspector; `nmos-worker` jobs |
| Schema | `migrations/0001`–`0014` | source layer, state, extraction/jobs, embeddings, config, knowledge, normalized text, projection generations, knowledge scope, conversation labels, turn extraction, conversation delete, append rows, assertion semantics |
| Plugin | `adapters/pocketrisu-plugin` → `dist/nmos-pocketrisu.js` | gating (D13), manifest, sync, recall injection, fail-open |
| Deployment | `docker-compose.yml`, `docker/sidecar.Dockerfile`, `.env.example` | postgres 16 + sidecar |
| Tests | `apps/sidecar/tests` (157), `adapters/pocketrisu-plugin/test` (46) | all passing; deterministic memory evaluation `docs/perf/eval-baseline.md` |
| Performance | `docs/perf/phase0.md`, `docs/perf/scale.md` | Phase 0 targets met. Since beta.10: sidecar append 715 → 156 ms and plugin manifest 175 → 17 ms at 10k (ADR 0010). Real host (PocketRisu v1.12.0): ≈1.5 s at 5k, ≈2.7 s at 10k, ≈4.1 s at 15k per warm generation (host stall after `getChatFromIndex`); default deadline 3 s covers up to ≈10k (D24) |
| Known issues | `docs/KNOWN-ISSUES.md` | K1–K21 current as of `v0.1.0-beta.10`, each with workaround and tracking (host, owner decision O5, Track B stage); resolved limitations listed |
| Next work | `docs/proposals/` | Track A (stabilization) A1–A5 done; Track B B1 is Phase 5 (current); B2–B7 not authorized |
| Decisions | `docs/adr/0001`–`0014` | gating, branches, token (optional), recall scoring, hybrid tuning, projection generations, knowledge scope, turn extraction, conversation delete, append fast path, item holder; Phase 5: entity identity, assertion semantics, generation fallback |
| Phase specs | `docs/phases/PHASE-0.md`–`PHASE-5.md` | 0–3 met; 4 soft subset met; 5 current |
| Retro | `docs/phases/PHASE-0-RETRO.md` | |

## Evidence status (Phase 0A)

| Scenario | Status | Fixture/evidence |
|---|---|---|
| S1–S12 | run | `fixtures/host/a14c911-2026-09-22/` (S4b, S8b variants) |
| S13 | not executable on `a14c911` (no group chat); N/A accepted by owner | HOST-FACTS S13 |
| S14 | run (100 / 1,000 messages) | `…/*S14*` |

## Open owner decisions

- O1 — relationship to MIRRA / VEIL.
- O5 — retention of abandoned worldlines and `host_observation` growth (needed before Track B, B2).
  Superseded generations: decided 2026-09-23 (keep LLM extractions, prune embeddings and
  deterministic projections after full coverage; Track B §4); not implemented yet.
- Phase 6+ (Track B, B2–B7): not authorized. B2 (transition verifier) is the intended next stage.

## Public release checklist (done 2026-09-23)

| Item | State |
|---|---|
| Security notice (plain-text API keys in `app_config`, no internet exposure, token for LAN/Tailscale) | done — README "Security", guide.ko "보안 주의" |
| README/guide claims scoped to the tested PocketRisu build | done |
| Private IP in experiment notes generalized (`192.168.x.x`) | done |
| Outdated agent docs (`CODEX-PROMPT.md`, `STARTER-CONTENTS.md`) archived to `docs/reference/`; `AGENTS.md` current; `PHASE-4.md` added | done |
| Commit author email in git history | done — `main` and tags `v0.1.0-beta.1`–`3` rewritten to the GitHub noreply address; later commits use it |
| Repository description/topics | done |
| Repository visibility → Public | done 2026-09-23 (after `v0.1.0-beta.4`) |
| GHCR `nmos-sidecar` package visibility → Public | done 2026-09-23 (owner) |
| Anonymous `docker pull` + fresh install from release assets | done 2026-09-23 — `0.1.0-beta.4` and `beta` pulled without login (same image); release compose file up with migrations 0001–0010; release plugin file installed in PocketRisu `a14c911`, synced a 37-message chat, Inspector showed it as *bot · chat* in Korean |
| README screenshot (settings panel or Inspector) | done 2026-09-23 — `docs/images/` (panel Status tab, Inspector), taken on the `v0.1.0-beta.4` release stack |
