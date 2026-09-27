# NMOS Status

## Current phase

**Phase 11 — Narrative Engine, part 1 (Stage 5): approved 2026-09-28, in progress.** Spec
`docs/phases/PHASE-11.md`: the M0 evaluation on real chats (a restored backup, read-only), relationship history
per pair (K24), goal, question, threat and debt threads with a lifecycle, and explicit links, in one extractor
generation (`extract-v13`). The owner answered every question with the recommended answer; no release is decided.
Part 2 (summaries, character state) is Phase 12, not authorized yet.

**Phase 10 — Knowledge and Secrets (Stage 4): complete (2026-09-27), not released (owner).** Spec
`docs/phases/PHASE-10.md` (every acceptance criterion met), ADRs 0033–0037, D43–D47, migration 0021. A secret is
what the story keeps from someone and ends when they find it out (`extract-v12`); what someone in the scene does
not know goes in a `<Private>` section with a rule; a chat can choose strict or a first-person narrator; the
Inspector shows a chat's secrets. Along the way, by the owner's requests: the default reserve 800, a Status-tab
notice with the budget that holds what was left out and `packet-v4` (ADR 0036), and the plugin build check (ADR
0037, K19). Evidence: `docs/perf/secrets-eval.md` — on the owner's real scenes, 48 replies of Opus 5.5 and Gemini
3.1 Pro with no leak, the holder remembering the secret as often as the pilot's best condition once a thread
ranking fault was fixed (ADR 0019 amendment 1). Next: the owner's call on the `0.2.0` milestone (Stage 4 done).

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
extraction LLM, released in `v0.1.0-beta.15`. Mocked token exchange in CI; verified against real Vertex on
2026-09-26 with the owner's key (`google/gemini-3.8-flash`: connection test, extraction, recall; ADR 0022).
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

Outside the phase (owner decision 2026-09-27, unreleased): `extract-v11`, made before its milestone at the owner's
request. It carries the two queued audit items: the prompt says notes outside the story are not evidence (A-12;
an OOC note in a reply 0/3 → 3/3 ignored, the control kept 3/3) and the registry drops `Predicate.epistemic`
(A-14). Evidence: `docs/perf/extract-v11.md`. Memory-shaped markup still became a fact, because the normalizer
stripped the tag and kept the text; the owner then chose a normalizer generation (2026-09-27, unreleased):
`clean-v3` drops NMOS's own memory markup with its content (K27; `docs/perf/memory-poisoning.md`).

Outside the phase (owner decision on K26, 2026-09-26, ADR 0032, D42, unreleased): the default packet policy
is `packet-v2`, which estimates Korean at 1.2 tokens a character instead of 1.5, so more of the reserve is
used. Evidence: `docs/perf/token-estimate.md` (three tokenizers, a replay of the owner's recorded requests,
an answer probe with two response models).

**Phase 0 — complete (2026-09-22).** Phase 0A exit criteria and all Phase 0B acceptance criteria are met.

**Public beta `v0.1.0-beta.21` (2026-09-26), public repository and image.** The rest of the 2026-09-26
audit: deadline warnings in the plugin, a host check without a token (ADR 0030), the per-message extraction
window retired (ADR 0031), startup backfills committed step by step, one environment for sidecar and worker,
upgrade tests from beta.7/beta.16 databases, Vertex AI verified; no schema or generation change.
`v0.1.0-beta.20` (2026-09-26): Three fixes from the
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
| Architecture | `ARCHITECTURE.md` | H1–H18, D1–D47, O2/O3/O4/O5 resolved |
| Sidecar + worker | `apps/sidecar` (Python 3.12, FastAPI, psycopg 3, httpx) | sync, hybrid recall, state, facts, inspector; `nmos-worker` jobs |
| Schema | `migrations/0001`–`0021` | source layer, state, extraction/jobs, embeddings, config, knowledge, normalized text, projection generations, knowledge scope, conversation labels, turn extraction, conversation delete, append rows, assertion semantics, observation compaction, event salience, assertion participants, conversation persona, owner entity links, packet ledger, conversation memory mode |
| Plugin | `adapters/pocketrisu-plugin` → `dist/nmos-pocketrisu.js` | gating (D13), manifest, sync, recall injection, fail-open |
| Deployment | `docker-compose.yml`, `docker/sidecar.Dockerfile`, `.env.example` | postgres 16 + sidecar |
| Tests | `apps/sidecar/tests` (437), `adapters/pocketrisu-plugin/test` (112; DOM code under `happy-dom`) | all passing except one strict xfail that pins K24 until Phase 11 step 3; the M0 real-chat baseline is `docs/perf/m0-baseline.md` (5 of 12); deterministic memory evaluation `docs/perf/eval-baseline.md` (with budget pressure since Phase 9) |
| Performance | `docs/perf/phase0.md`, `docs/perf/scale.md` | Phase 0 targets met. Since beta.10: sidecar append 715 → 156 ms and plugin manifest 175 → 17 ms at 10k (ADR 0010). Real host (PocketRisu v1.12.0): ≈1.5 s at 5k, ≈2.7 s at 10k, ≈4.1 s at 15k per warm generation (host stall after `getChatFromIndex`); default deadline 3 s covers up to ≈10k without extraction and embeddings (D24); with both on (15k facts, 15k vectors) 10k takes ≈3.2 s (A-09); K3 on the real host (2026-09-27): rerolls and last-reply swipes stay on the fast path, an edit of an older message at 10k takes 3.6–3.8 s |
| Known issues | `docs/KNOWN-ISSUES.md` | K1–K29 (K10 resolved; K29 found on `main`) current as of `v0.1.0-beta.21`, each with workaround and tracking (host, Track B stage); resolved limitations listed |
| Next work | `docs/ROADMAP-1.0.md`, `docs/proposals/` | Road to 1.0: stages 4–8 of the original roadmap, one release each (draft, R1–R6 open). Track A (stabilization) A1–A5 done; Track B B1 = Phase 5, B2 = Phase 6 (complete); B3 narrowed = Phase 7 (complete); the rest of B3 and B4–B7 not authorized |
| Decisions | `docs/adr/0001`–`0037` | gating, branches, token (optional), recall scoring, hybrid tuning, projection generations, knowledge scope, turn extraction, conversation delete, append fast path, item holder; Phase 5: entity identity, assertion semantics, generation fallback; superseded projection retention; Phase 6: item whereabouts, item end; observation compaction; Phase 7: promise threads, event salience; Phase 8: typed participants; Vertex AI service-account keys; persona name; salience by change and revealed names; owner entity links; standing facts first; speech level and address; text PostgreSQL cannot store; host check without a token; per-message window retired; Korean token estimate; Phase 10: secrets, private section, memory mode, budget pressure; plugin build check |
| Phase specs | `docs/phases/PHASE-0.md`–`PHASE-11.md` | 0–3 met; 4 soft subset met; 5–10 met; 11 in progress |
| Retro | `docs/phases/PHASE-0-RETRO.md` | |
| Audits | `docs/audits/NMOS-AUDIT-2026-09-26.md` + `-REVIEW.md` | A-01 (ADR 0029, D40), A-02, A-04 fixed in `v0.1.0-beta.20`; A-03, A-05 (ADR 0030), A-06, A-07, A-08, A-10 (verified), A-15 (ADR 0031), A-16 fixed, A-09 measured with deadline warnings, A-12 measured (K27), in `v0.1.0-beta.21`; after it, A-11 fixed (access log), A-13 documented (K28), A-18 documented (K21), A-19 fixed (plugin tests); A-17 is a caution (K15), not a defect; A-12's prompt line and A-14 in `extract-v11`, and A-12's markup half in `clean-v3` (both unreleased) |

## Evidence status (Phase 0A)

| Scenario | Status | Fixture/evidence |
|---|---|---|
| S1–S12 | run | `fixtures/host/a14c911-2026-09-22/` (S4b, S8b variants) |
| S13 | not executable on `a14c911` (no group chat); N/A accepted by owner | HOST-FACTS S13 |
| S14 | run (100 / 1,000 messages) | `…/*S14*` |

## Audit follow-up (2026-09-27)

A read-only audit of `69800f0` is recorded in [Original vision → stable](proposals/ORIGINAL-VISION-TO-STABLE-2026-09-27.md) (Korean, at the owner's request; proposal only). Its isolated API/worker probes reproduced a reveal being applied to a different secret after an old source edit (G1), the K29 history-extraction workaround queuing no work for already compiled turns (G2), and malformed assertion output being recorded as complete (G3). The 421 sidecar and 104 plugin tests that existed then passed and did not cover these cases.

- **Fixed on `main` (unreleased):**
  - G1: a reveal links to its listed turn only while that turn reads as it did (ADR 0033 amendment 2).
  - G2: "Extract all history" also extracts again the turns extracted before an earlier turn's secret, so K29's workaround works (amendment 2).
  - G3: an answer without an `assertions` list fails the job (retried, then counted failed) instead of counting as compiled.
  - Each is covered in `test_secrets.py` / `test_extraction.py`; they were strict xfails before the fix.
- Exposure before the fix: G1 and G2 came with Phase 10, which production runs from `:edge`; no tag has them. G3 dates from `e21e9cd` (Phase 2) and is in every release up to `v0.1.0-beta.21`.
- No extractor generation change: the prompt, registry and normalizer are unchanged; the listed turn's hash is stored with the hints only. Reveals extracted before the fix carry no hash and keep the old linking.

The audit's other findings (G4–G17) stay proposals. No phase authorization or release decision was made.

A second analysis the same day (an external document the owner shared, not in the repository) was reviewed against
the code. Its confirmed defects are fixed on `main` as bug fixes (CHANGELOG, Unreleased): a saved API key is sent
only to the host it was saved for, the plugin's host reads count against the request deadline and its budget and
deadline arguments are capped, the worker waits for the sidecar's migrations, a recall reads the chat as its
request had it, and the plugin's DOM code has tests (`happy-dom`, owner-approved dev dependency). Not adopted: its
advice to tag `0.2.0` now (it missed G1–G3), a Dockerfile `HEALTHCHECK` (the worker runs the same image),
removing the assertion's `epistemic` field (it is live: `certainty="implied"`; A-14 removed only
`Predicate.epistemic`), and a plugin update channel (on hold by the owner; the host offers an update only for a
higher `//@version`). Its Stage 5–8 items remain phase work; next, once G1–G3 were fixed: M0 and Stage 5 (owner,
2026-09-28).

## Open owner decisions

- O1 — relationship to MIRRA / VEIL.
- O5 — resolved 2026-09-24: superseded vectors and text pruned (ADR 0015, D29), full-manifest host
  observations compacted losslessly (ADR 0018, D31), everything else on abandoned worldlines kept.
- Phase 9 (accountable packets): complete, released in `v0.1.0-beta.19`.
- Phase 11 (Stage 5, part 1): approved 2026-09-28 with the recommended answers (Q0–Q8); release on hold.
- Phase 12+ (the rest of Stage 5, Stages 6–8): not authorized.
- K26 — decided 2026-09-26: change the estimate (1.5 → 1.2 tokens per non-ASCII character, `packet-v2`,
  ADR 0032, D42); the default reserve stays 600. Raised to 800 on 2026-09-27 (owner; ADR 0035).
- Release cadence — decided 2026-09-26, revised 2026-09-27: one release per roadmap stage, urgent patches
  only in between, `:edge` built from every `main` merge (`AGENTS.md` §13).
- Roadmap to 1.0 — decided 2026-09-27: not stable until stages 4–8 of the original roadmap are done
  (`docs/ROADMAP-1.0.md`). Open: R1 order, R2 public benchmark, R3–R6 stage scope.
- Stage 4 — decided 2026-09-27: first milestone (R1); recommended answers to Q1–Q5; no release yet. Spec
  `docs/phases/PHASE-10.md`, approved 2026-09-27. Tentative: a holder's own slip is direction, not a leak.

## Queued for the next extractor generation

A change to the extraction prompt or registry makes a new generation and re-extracts each chat's recent
window at the provider's cost (ADR 0006, 0014). Owner-approved changes wait for the next one, so the cost is
paid once (owner decision 2026-09-26). None is queued: A-12 and A-14 shipped in `extract-v11` (owner decision
2026-09-27, `docs/perf/extract-v11.md`).

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
