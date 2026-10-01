# NMOS Roadmap to 1.0

> Owner decision, 2026-09-27: NMOS is not called stable until stages 4–8 of the original roadmap
> (`docs/reference/ultimate_narrative_memory_architecture.md` §84) are done. Narrowed on 2026-10-01 (**R7**, below):
> 1.0 needs stages 4–7; Stage 8 and Stage 6's transition rules and conflict queue move after 1.0. Each stage is one release;
> 1.0.0 follows the last one. **This document is a draft**: the order and each stage's done criteria
> wait for the owner decisions marked **R1…**; stage 4 has a draft design (`docs/proposals/STAGE-4-KNOWLEDGE.md`). A stage still needs its
> own `docs/phases/PHASE-N.md`, approved by the owner, before implementation (`AGENTS.md` §2).

## Where NMOS stands

| Original stage | Content (§84) | State after `v0.2.0` (2026-09-28) plus `main` (2026-09-29) |
|---|---|---|
| 0 — Host adapter spike | plugin, injection, no fork | done |
| 1 — Source ledger | immutable revisions, reconcile, worldlines | done |
| 2 — Minimal compiler | entities, events, assertions, provenance, fact versions | done |
| 3 — Retrieval core | SQL, lexical, vector, RRF, packet, traces | done |
| 4 — Epistemic engine | observer model, knowledge projection, principal ACL, false beliefs, private thoughts | done, released in `v0.2.0` (Phase 10; K11 rewritten to what remains) |
| 5 — Narrative engine | causal links, open threads, scenes, episodes, arcs, dynamic character state | done, released in `v0.2.0` (Phases 11–12) |
| 6 — Verification and repair | transition verifier, conflict queue, inspector, entity merge/split, canon locking | in progress: owner repair (Phase 13), canon sources (Phase 14) and export and restore (Phase 16) on `main`, Phase 20 the last phase; transition rules and conflict queue after 1.0 (R7) |
| 7 — Forensic recall | raw-history search, evidence traversal, exact quotes | partial: packet ledger and as-of replay (Phase 9); not authorized |
| 8 — PocketRisu bridge | partial chat reads, mutation events | not started; after 1.0 (R7) |

Stages 0–3 are the foundation and are done. Stages 4 and 5 are done. Stage 6 closes with Phase 20; Stage 7 is what
remains before 1.0 (R7).
Phase 15 (a packet that fills its budget, `docs/phases/PHASE-15.md`) is not a stage of this roadmap: it is P1 of
`docs/proposals/PUBLIC-RELEASE-AND-BENCHMARK.md`, approved 2026-09-29, and was done after Phase 14 and before Phase 16
(complete 2026-09-29). Phase 17 (the cost of NMOS's own model calls and fallbacks told apart in the HUD,
`docs/phases/PHASE-17.md`, approved 2026-09-29, complete 2026-09-30) is not a stage either: C4 and C5 of
`docs/proposals/IDEA-SURVEY-2026-09-29.md`. Phase 18 (keyword lexical recall and excerpts that fill their length,
`docs/phases/PHASE-18.md`, approved and complete 2026-09-30) is not a stage either: it follows Phase 17, before Stage 7. Phase 19 (one extractor
generation with a shorter context, synthetic prompt examples and evidence in the turn, `docs/phases/PHASE-19.md`,
approved 2026-09-30, complete 2026-10-01) is not a stage either: it ships the changes queued for the next extractor generation, before Stage 7.

## Versions

| Version | When |
|---|---|
| `0.1.x` | the feature set of the betas; `v0.1.0-beta.21` was the last, and only urgent fixes followed |
| `0.2.0` … `0.4.0` | one per stage, in the order of R1, when that stage meets its done criteria (`0.3.0` Stage 6, `0.4.0` Stage 7). `v0.2.0` (2026-09-28) was cut early at the owner's request: it carries Stages 4 and 5 together, plus the Stage 6 work then on `main` |
| `1.0.0` | the 1.0 gate below |

Every version before 1.0.0 is a GitHub pre-release. Between versions the owner runs `:edge` (a build of
every `main` merge; `AGENTS.md` §13). Each stage ships at most one new extractor generation.

**R1 — order.** Decided 2026-09-27: **Stage 4 first** (Phase 10); the order after it is decided when it is done. The owner then chose Stage 5 (2026-09-28) and Stage 6 (2026-09-28); on 2026-10-01 **Stage 7 before Stage 8** (forensic recall first). The earlier recommendation was 5 → 6 → 4 → 7 → 8:
- 5 first: knowledge (stage 4) is acquired through events someone observed or was told, which stage 5 adds.
- 6 before 4: per-character filtering is only as good as the state it filters; repair tools let the
  owner fix that state by hand.
- 4 before 7: the original design exposes deeper recall only once visibility is enforced server-side
  (Track B, B6).
- 8 is independent of the others (a host patch) and can move earlier if host latency (K1, K3) matters
  more than features.

**R7 — scope of 1.0.** Decided 2026-10-01 (owner). The roadmap had no visible end: its finish line was the whole
original design, and most recent phases (15, 17, 18, 19) were outside it. So:
- **Stage 8 leaves the 1.0 scope.** It needs a deep PocketRisu patch that production would have to run; it is recorded
  under "After 1.0", not built. R6 is moot until then.
- **Stage 6 ends with Phase 20.** Transition rules and the conflict queue move after 1.0; the owner's repair in the
  panel (Phase 13) and the "Needs attention" list stand in for them (an accepted trade-off).
- **Until 1.0, a new phase is a Stage 7 item.** Urgent fixes (`AGENTS.md` §13) are the exception. Other ideas,
  including C10 of `docs/proposals/IDEA-SURVEY-2026-09-29.md` (memory of chats deleted in the host; host evidence
  H22 recorded), wait under "After 1.0" unless the owner pulls one in by name.
- **Pulled in by name (2026-10-01): NMOS without Docker** (AGE-29, Phase 23). PocketRisu's portable and Termux users
  cannot run the Docker install, so a 1.0 they cannot attach misses part of the host's users.

The road left is Stage 7 (`0.4.0`) and two quiet weeks on production.

## Measuring progress (M0, before the first stage)

A stage is "done" by measurement, not by features merged. Before the first stage:

- **An RP evaluation on real chats**: questions with known answers taken from the owner's chats (current
  and past state, promises, relationships, speech level, secrets), scored on the packet NMOS builds.
  It uses the offline replay that exists (`tools/replay_packets.py`, recorded packet ledgers) and is read-only
  against production data.
- **The deterministic baseline** (`docs/perf/eval-baseline.md`) extended per stage with that stage's
  categories.
- **R2 — a public long-term memory benchmark** (LongMemEval, `ultimate…` §99). Recommended: run it
  as a report, without a target, so that NMOS's core can be compared with other memory systems and the
  generic direction after 1.0 starts from a number.

Each stage records its numbers in `docs/perf/`. No category may get worse than the previous release.

## Stage 5 — Narrative engine

*Original §24–26, §31–37; Track B, B3 remainder.* Has: promise threads, event salience and cap, typed
participants, `relationship` / `feels_toward` / `addresses` versioned per direction.

Scope (draft):
- open threads beyond promises: goal, unanswered question or mystery, threat, debt, missing item,
  unfinished task (**R3**: all of them or a first subset);
- evidence-backed links between events: fulfills, resolves, breaks, reveals, contradicts, explicit
  cause. No inferred causality;
- one relationship history per pair, with direction and symmetry rules and a link between
  `relationship` and `feels_toward` (closes K24);
- scenes, episodes and arcs as rebuildable summaries (§36–37), so the packet can speak for the whole
  chat, not only for the facts retrieval found;
- per-character current state: goals, condition, mood (§32);
- **R4**: partial and relative story time ("three days later", §22) in this stage or after 1.0.

Done when:
- the evaluation has cases for each thread type (opened, resolved, deleted), causal questions ("why is
  Hana angry at Kaito?") answered from linked events, relationships now and before, and old events
  kept out when irrelevant;
- the real-model tier passes on at least two extraction models;
- on the owner's longest chat, replayed offline, an early event is placed when it becomes relevant
  and summaries cover the chat within the budget;
- K24 is closed.

**Done (2026-09-28, Phases 11–12; released in `v0.2.0`).** Thread kinds opened, ended, deleted and edited back in the memory
evaluation (53 of 53), stated causes linked, relationships per pair with what they replaced (K24's direction case
closed; a feeling recorded apart from a relationship stays by the owner's decision, PHASE-11 Q5); the real-model tier
on `gemma4` and `deepseek` for `extract-v13` and for summaries; on the owner's longest chat, replayed offline, answers
outside the prompt window 2 → 5 of 12 with the story covering every scene within the default budget
(`docs/perf/extract-v13.md`, `docs/perf/summaries.md`). Open: goals the story never closes in words (K23, Stage 6).

## Stage 6 — Verification and repair

*Original §20, §66–67; Track B, B2 remainder, B4, B7.* Has: item whereabouts, `destroyed`, conflicts,
Inspector, owner entity links. Part 1 on `main` (Phase 13, ADR 0044): owner repair (close or reopen a thread, retract or
correct a fact, a secret found out or kept, split two names) in the panel, audited and surviving rebuilds, and a
"Needs attention" list per chat; K8 and K23 rewritten to what remains (`docs/perf/repair.md`). Part 2, Phase 14
(approved 2026-09-28, complete 2026-09-29): canon as sources. Then Phase 15, the packet that fills its
budget (approved and complete 2026-09-29, `docs/phases/PHASE-15.md`; not a Stage 6 item), and Phase 16: export and
restore (approved and complete 2026-09-29, `docs/phases/PHASE-16.md`, ADR 0050, `docs/perf/archive.md`).
Phase 20 (approved and complete 2026-10-01, `docs/phases/PHASE-20.md`, `docs/perf/join-preview.md`): a name join, split or undo shown before it is made, and an
undo that re-extracts the turns a join covered (C7 of the idea survey). Open beyond them: transition rules, not yet
assigned to a phase.

Scope (draft):
- ~~transition rules for status and identity and for relationships, with pending, conflicting and
  rejected outcomes~~ — after 1.0 (R7);
- ~~a conflict queue in the Inspector~~ — after 1.0 (R7);
- owner repair, stored as audited source entries so it survives every rebuild: correct or retract a
  fact, split a wrong alias (K8), close or reopen a promise (K23), edit aliases;
- canon as sources: character card, lorebook, persona, author's note, with authority, canon lock, and
  card-against-story conflicts shown (each source type needs host evidence first);
- export and restore of the ledger, repairs and settings (§89).

Done when:
- K8 and K23 are closed; closed 2026-10-01 by owner decision: the owner's repair in the panel is the fix,
  and NMOS finding a split name or an ended thread by itself is not planned (reading the context for it costs
  too much per turn);
- every repair survives a rebuild and a new extractor generation;
- export, restore into a fresh install and replay give the same packets;
- each canon source has recorded host evidence and a conflict fixture.

## Stage 4 — Epistemic engine

*Original §27–30; Track B, B5.* Has: `public` / `limited` / unknown marks with free-text `known_by`
and `hidden_from` (ADR 0007), the packet telling the model how to use them, the Phase 9 leak report.

The fixed limit (§30, K11): one generation writes every character, so a secret the packet holds can reach any
of them. A pilot on the owner's chat with two response models (`docs/perf/stage4-leak-pilot.md`) found the
limit matters less than the data: once a fact says whom it is kept from, the packet keeps it unsaid and the
holder still remembers it; withholding content stops leaks only by making the holder forget. Draft design:
`docs/proposals/STAGE-4-KNOWLEDGE.md` (owner answers 2026-09-27); spec `docs/phases/PHASE-10.md`.

Scope (draft):
- the extraction separates *present* from *kept from*, and a secret ends when the story shows the hidden
  character learning it (next extractor generation);
- the packet marks private facts with their holders and whom they are kept from (the pilot's A), by default;
- a strict mode per chat (intersection: only what everyone present knows), off by default;
- first-person chats keep only what the narrator knows (a per-chat setting).

Done when (draft):
- on a case set from real chats, replayed offline with the owner's response models, no leak where a fact marks
  whom it is kept from, and the holder remembers the secret whenever the scene calls for it;
- a secret the story reveals is no longer marked hidden in later packets;
- strict mode and first person have cases of their own;
- K11 is rewritten to what remains (host-sent text, one generation for every character).

Tentative owner decision (2026-09-27): a holder's own slip, such as a child blurting a secret, is direction,
not a failure.

**Done (2026-09-27, Phase 10; released in `v0.2.0`).** Every done criterion is met: `docs/perf/secrets-eval.md` (48 replies of
the owner's response models on real scenes without a leak; holders remember), `docs/perf/extract-v12.md` (a
revealed secret ends), the strict and narrator cases in the memory evaluation, and K11 rewritten.

## Stage 7 — Forensic recall

*Original §44–55, §78; Track B, B6.* Has: packet ledger, as-of replay, echo, abstention.

Scope (draft):
- fast, normal and forensic recall paths;
- an exact-quote path that prefers raw text;
- labels for candidates (required, supportive, risky, hidden) and a penalty for overused memory;
- evidence traversal in the Inspector;
- no read-only MCP. **R5**, decided 2026-10-01 (owner): MCP leaves the 1.0 scope (recorded, not built). The
  packet already carries memory into the prompt and forensic recall is reached through the panel, so a tool the
  response model calls adds nothing the stage needs.

Done when:
- an exact-quote case set ("what did Hana say the first night?") is answered with the source turn;
- overuse is measured by echo before and after.

## Stage 8 — PocketRisu bridge (after 1.0)

*Original §80–82.* Nothing exists yet. **Out of the 1.0 scope (R7, 2026-10-01).** The draft below is kept for after 1.0.

Scope (draft):
- a PocketRisu patch: partial chat reads (`getChatManifest`), mutation events, canon mutation events;
- NMOS detects the bridge and uses it, and behaves as today without it.

Done when:
- on the isolated test instance, K1 (5k/10k/15k), K3 and K16 are measured with and without the bridge;
- without the bridge nothing changes;
- the patch is offered upstream (acceptance is not required).

**R6**: whether the owner's production PocketRisu runs the patched build.

## The 1.0 gate

- stages 4–7 meet their done criteria (Stage 6 as narrowed by R7);
- no evaluation category is worse than in `0.1.x`;
- an upgrade from a `v0.1.0-beta.21` database and from each `0.x.0` works (`tests/test_upgrade.py`);
- two weeks on the owner's production with no heavy change;
- every open known issue is a host limit or an accepted trade-off.

## After 1.0

Moved here by R7 (2026-10-01), in no order: Stage 8 (PocketRisu bridge); Stage 6's transition rules and conflict
queue; C10 of the idea survey (memory of chats deleted in the host).

The owner's longer aim is long-term memory for LLMs in general, not only role-play. The parts of NMOS
that already carry over are the immutable ledger with rebuildable memory, provenance, hybrid recall
with abstention, the budgeted and recorded packet, and fail-open. What does not is the PocketRisu adapter
and the narrative predicate registry. A generic direction (a host-independent entry such as an
OpenAI-compatible proxy, a generic fact schema, the R2 benchmark as its measure) is decided after 1.0.
