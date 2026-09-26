# NMOS Status

## Current phase

**Phase 9 — Accountable Packets: complete (2026-09-26), released in `v0.1.0-beta.19`.** The owner asked for
the work on a new branch and approved the merge after review. Spec `docs/phases/PHASE-9.md` (Track B, B6
narrowed to recording and budgeting what the packet holds), ADR 0027, D39, migration 0020. Every request
records a ledger of what its packet offered and held, with provenance. `packet-v1` keeps room for the
best excerpt. A recorded request replays as of its time (story position and knowledge time), and
`tools/replay_packets.py` compares policies offline. Echo reports what the next reply reused. Evidence:
`docs/perf/phase9-packets.md`, including a real-host smoke and an answer probe with two response models.
Every acceptance criterion is met. No phase is current.

**Phase 8 — Event Participants: complete (2026-09-24), released in `v0.1.0-beta.15`.** Spec
`docs/phases/PHASE-8.md` (Track B, B3 narrowed to typed participants of `event`, `goal`, `knows`,
`destroyed`), approved with the recommended answer to every question (Q1–Q5). Typed participants
(ADR 0021, D33), `extract-v8`, migration 0017, `resolve-v2`, Inspector "With" and "Takes part in".
Evidence: `docs/perf/phase8-extraction.md`. Every acceptance criterion met; the Phase 7 minor-event
scene "chores" (1/3 with `extract-v8`, no event extracted; ten more runs: v7 3/10, v8 4/10) was accepted
by the owner as not a regression. No phase is current. Next: the rest of Track B, B3, not authorized.

**Phase 7 — Promise Threads and Event Salience: complete (2026-09-24), released in
`v0.1.0-beta.14`.** Spec `docs/phases/PHASE-7.md` (Track B, B3 narrowed to promise threads and event salience),
approved with the recommended answer to every question (Q1–Q5). Promise threads (ADR 0019), event cap
and salience (ADR 0020), `extract-v7` with `fulfilled` and OPEN PROMISES, migration 0016, D32, Inspector
promises. Evidence: `docs/perf/phase7-extraction.md` (real-model tier, fact-read latency, real-host
smoke, upgrade from a `v0.1.0-beta.13` database).

**Phase 6 — Item Transitions and Conflicts: complete (2026-09-24), released in `v0.1.0-beta.13`.**
Spec `docs/phases/PHASE-6.md` (Track B, B2), approved 2026-09-24 with the recommended answer to every
question (Q1–Q5). One whereabouts per item (ADR 0016), `destroyed` with `extract-v6` and
`disputed="true"` (ADR 0017), D30, Inspector item timelines and conflicts. Every acceptance criterion
met: `docs/perf/phase6-extraction.md` (real-model tier, fact-read latency, real-host smoke, upgrade from
a `v0.1.0-beta.12` database).

**Phase 5 — Entity Identity and Semantic Assertions: complete (2026-09-24), released in
`v0.1.0-beta.12`.** Spec `docs/phases/PHASE-5.md`, ADRs 0012–0014 (0012/0013 amended by the owner after
the real-model tier), D26/D27, D7/D20 amended. Every acceptance criterion met: deterministic cases in
CI, the real-model tier on the release candidate and a real-host smoke (`docs/perf/phase5-extraction.md`),
latency (`docs/perf/scale.md`), a real upgrade from a `v0.1.0-beta.10` database. Next: Track B, B2
(transition verifier), not authorized yet.
Outside the phase (owner decision 2026-09-24, D28): an optional progress display on the chat screen,
released in `v0.1.0-beta.12`.
Outside the phase (owner-reported bug 2026-09-24, ADR 0023, D34, released in `v0.1.0-beta.16`): the persona's name as
the host reports it is the persona, so `{{user}}` and a named persona (유우마) are one entity; the plugin
reads it with the host's "db" permission, asked at load (real-host check: `docs/HOST-FACTS.md`, "Persona
name"). Migration 0018, `resolve-v3`.
Outside the phase (owner report 2026-09-25, ADRs 0024 and 0025, D35 and D36, released in `v0.1.0-beta.17`): `extract-v9` labels an
event major by what it changes, in action or in words (admissions, speech-level and address changes, a relationship
allowed, an incident others must deal with), names a character shown without a name by a `?` description and links
it when a later turn reveals the name; the owner can join two names of a chat by hand in the panel (migration 0019,
`resolve-v4`). Evidence: `docs/perf/extract-v9.md`.
Outside the phase (owner request 2026-09-24, ADR 0022): Google Vertex AI service-account keys for the
extraction LLM, released in `v0.1.0-beta.15`. Mocked token exchange in CI; not yet run against real Vertex (needs an
owner-supplied service-account key).
Outside the phase (owner report 2026-09-26, ADR 0026, D37, released in `v0.1.0-beta.19`): characters forgot settled things (a 반말 agreement
went back to 존댓말). Reproduced read-only on the owner's database: in a crowded scene the fact ranking was decided by
`known_by` lists, so trivia took the four facts a 600-token packet holds. Now how the cast stand with each other
(`relationship`, `feels_toward`) and major events come first among equal mentions, standing facts take the budget before
threads, and the trace and Inspector show how many facts fit. Read side only.
Outside the phase (owner decision 2026-09-26 on `docs/proposals/SPEECH-AND-ADDRESS.md`, recommended answers; ADR 0028,
D38, released in `v0.1.0-beta.19`): `extract-v10` adds `addresses`, how one character speaks to and calls another, per direction, only when
the story settles it (a slip is not recorded); it ranks with relationships. Evidence: `docs/perf/extract-v10.md`
(owner's model on the owner's chat: 18/18 settled turns, 0/3 on the slip, 0/12 routine; synthetic 21/21 on two models;
isolated real host).
Outside the phase (owner request 2026-09-25, released in `v0.1.0-beta.18`): the Status tab shows the exact text the last request
injected ("Show the injected memory"), held in the plugin's memory only. Real-host check on
`ghcr.io/pocketrisu/pocketrisu:latest` at 1280 px and 390 px; the text matched what the stub model received.

**Phase 0 — complete (2026-09-22).** Phase 0A exit criteria and all Phase 0B acceptance criteria are met.

**Public beta `v0.1.0-beta.20` (2026-09-26), public repository and image.** Three fixes from the
2026-09-26 audit: a broken emoji no longer stops a chat's sync (A-01, ADR 0029), a reply quoting the
memory tag no longer turns memory off (A-02), and one bad job no longer stops the worker (A-04).
`v0.1.0-beta.19` (2026-09-26): Phase 9 (accountable
packets: packet ledger, `packet-v1`, echo, as-of replay), standing facts first (ADR 0026) and speech
level and forms of address (`extract-v10`, ADR 0028); migration 0020.
`v0.1.0-beta.18` (2026-09-25): The Status tab shows the
memory the last request injected (plugin only).
`v0.1.0-beta.17` (2026-09-25): `extract-v9` (salience by
what an event changes, unnamed characters and revealed names, ADR 0024) and owner entity links (ADR
0025); migration 0019.
`v0.1.0-beta.16` (2026-09-24): Bug fix: a named persona is
the persona (ADR 0023, above); migration 0018.
`v0.1.0-beta.15` (2026-09-24): Phase 8 (above), Google
Vertex AI keys for extraction (ADR 0022), an Inspector status-window example; migration 0017.
`v0.1.0-beta.14` (2026-09-24): Phase 7 (above); migration
0016. `v0.1.0-beta.13` (2026-09-24): Phase 6 (above) and O5
resolved: superseded vectors pruned (ADR 0015), full-manifest host observations compacted losslessly
(ADR 0018); migration 0015. `v0.1.0-beta.12` (2026-09-24): Phase 5 (above), `clean-v2`
normalizer (inline images no longer read as story), optional progress display (D28); migration 0014.
`v0.1.0-beta.11` (2026-09-24): Phase 5 step 1: a new LLM
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
| Architecture | `ARCHITECTURE.md` | H1–H17, D1–D41, O2/O3/O4/O5 resolved |
| Sidecar + worker | `apps/sidecar` (Python 3.12, FastAPI, psycopg 3, httpx) | sync, hybrid recall, state, facts, inspector; `nmos-worker` jobs |
| Schema | `migrations/0001`–`0020` | source layer, state, extraction/jobs, embeddings, config, knowledge, normalized text, projection generations, knowledge scope, conversation labels, turn extraction, conversation delete, append rows, assertion semantics, observation compaction, event salience, assertion participants, conversation persona, owner entity links |
| Plugin | `adapters/pocketrisu-plugin` → `dist/nmos-pocketrisu.js` | gating (D13), manifest, sync, recall injection, fail-open |
| Deployment | `docker-compose.yml`, `docker/sidecar.Dockerfile`, `.env.example` | postgres 16 + sidecar |
| Tests | `apps/sidecar/tests` (364), `adapters/pocketrisu-plugin/test` (91) | all passing; deterministic memory evaluation `docs/perf/eval-baseline.md` (with budget pressure since Phase 9) |
| Performance | `docs/perf/phase0.md`, `docs/perf/scale.md` | Phase 0 targets met. Since beta.10: sidecar append 715 → 156 ms and plugin manifest 175 → 17 ms at 10k (ADR 0010). Real host (PocketRisu v1.12.0): ≈1.5 s at 5k, ≈2.7 s at 10k, ≈4.1 s at 15k per warm generation (host stall after `getChatFromIndex`); default deadline 3 s covers up to ≈10k without extraction and embeddings (D24); with both on (15k facts, 15k vectors) 10k takes ≈3.2 s (A-09) |
| Known issues | `docs/KNOWN-ISSUES.md` | K1–K26 (K10 resolved) current as of `v0.1.0-beta.20`, each with workaround and tracking (host, Track B stage); resolved limitations listed |
| Next work | `docs/proposals/` | Track A (stabilization) A1–A5 done; Track B B1 = Phase 5, B2 = Phase 6 (complete); B3 narrowed = Phase 7 (complete); the rest of B3 and B4–B7 not authorized |
| Decisions | `docs/adr/0001`–`0030` | gating, branches, token (optional), recall scoring, hybrid tuning, projection generations, knowledge scope, turn extraction, conversation delete, append fast path, item holder; Phase 5: entity identity, assertion semantics, generation fallback; superseded projection retention; Phase 6: item whereabouts, item end; observation compaction; Phase 7: promise threads, event salience; Phase 8: typed participants; Vertex AI service-account keys; persona name; salience by change and revealed names; owner entity links; standing facts first; speech level and address; text PostgreSQL cannot store; host check without a token |
| Phase specs | `docs/phases/PHASE-0.md`–`PHASE-9.md` | 0–3 met; 4 soft subset met; 5–9 met |
| Retro | `docs/phases/PHASE-0-RETRO.md` | |
| Audits | `docs/audits/NMOS-AUDIT-2026-09-26.md` + `-REVIEW.md` | A-01 (ADR 0029, D40), A-02, A-04 fixed in `v0.1.0-beta.20`; A-03, A-07, A-08, A-16 fixed and A-09 measured (unreleased); the rest are owner decisions, listed in the review |

## Evidence status (Phase 0A)

| Scenario | Status | Fixture/evidence |
|---|---|---|
| S1–S12 | run | `fixtures/host/a14c911-2026-09-22/` (S4b, S8b variants) |
| S13 | not executable on `a14c911` (no group chat); N/A accepted by owner | HOST-FACTS S13 |
| S14 | run (100 / 1,000 messages) | `…/*S14*` |

## Open owner decisions

- O1 — relationship to MIRRA / VEIL.
- O5 — resolved 2026-09-24: superseded vectors and text pruned (ADR 0015, D29), full-manifest host
  observations compacted losslessly (ADR 0018, D31), everything else on abandoned worldlines kept.
- Phase 9 (accountable packets): complete, released in `v0.1.0-beta.19`.
- Phase 10+ (the rest of B3, Track B, B4–B7): not authorized.
- K26 (the token estimate over-counts Korean): whether to change the estimate or the default reserve.

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
