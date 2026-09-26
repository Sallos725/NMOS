# NMOS Roadmap to 1.0

> Owner decision, 2026-09-27: NMOS is not called stable until stages 4–8 of the original roadmap
> (`docs/reference/ultimate_narrative_memory_architecture.md` §84) are done. Each stage is one release;
> 1.0.0 follows the last one. **This document is a draft**: the order and each stage's done criteria
> wait for the owner decisions marked **R1…**, and stage 4 is under discussion. A stage still needs its
> own `docs/phases/PHASE-N.md`, approved by the owner, before implementation (`AGENTS.md` §2).

## Where NMOS stands

| Original stage | Content (§84) | State after `v0.1.0-beta.21` |
|---|---|---|
| 0 — Host adapter spike | plugin, injection, no fork | done |
| 1 — Source ledger | immutable revisions, reconcile, worldlines | done |
| 2 — Minimal compiler | entities, events, assertions, provenance, fact versions | done |
| 3 — Retrieval core | SQL, lexical, vector, RRF, packet, traces | done |
| 4 — Epistemic engine | observer model, knowledge projection, principal ACL, false beliefs, private thoughts | partial: knowledge marks as hints (Phase 4 soft subset), leak report (Phase 9) |
| 5 — Narrative engine | causal links, open threads, scenes, episodes, arcs, dynamic character state | partial: promise threads, event salience, participants (Phases 7–8) |
| 6 — Verification and repair | transition verifier, conflict queue, inspector, entity merge/split, canon locking | partial: item transitions and conflicts (Phase 6), Inspector, owner merge (ADR 0025) |
| 7 — Forensic recall | raw-history search, evidence traversal, exact quotes | partial: packet ledger and as-of replay (Phase 9) |
| 8 — PocketRisu bridge | partial chat reads, mutation events | not started |

Stages 0–3 are the foundation and are done. Stages 4–8 are what remains before 1.0.

## Versions

| Version | When |
|---|---|
| `0.1.x` | the current feature set; after `v0.1.0-beta.21` only urgent fixes |
| `0.2.0` … `0.6.0` | one per stage, in the order of R1, when that stage meets its done criteria |
| `1.0.0` | the 1.0 gate below |

Every version before 1.0.0 is a GitHub pre-release. Between versions the owner runs `:edge` (a build of
every `main` merge; `AGENTS.md` §13). Each stage ships at most one new extractor generation.

**R1 — order.** Recommended: **5 → 6 → 4 → 7 → 8**.
- 5 first: knowledge (stage 4) is acquired through events someone observed or was told, which stage 5 adds.
- 6 before 4: per-character filtering is only as good as the state it filters; repair tools let the
  owner fix that state by hand.
- 4 before 7: the original design exposes deeper recall only once visibility is enforced server-side
  (Track B, B6).
- 8 is independent of the others (a host patch) and can move earlier if host latency (K1, K3) matters
  more than features.

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

## Stage 6 — Verification and repair

*Original §20, §66–67; Track B, B2 remainder, B4, B7.* Has: item whereabouts, `destroyed`, conflicts,
Inspector, owner entity links.

Scope (draft):
- transition rules for status and identity and for relationships, with pending, conflicting and
  rejected outcomes;
- a conflict queue in the Inspector;
- owner repair, stored as audited source entries so it survives every rebuild: correct or retract a
  fact, split a wrong alias (K8), close or reopen a promise (K23), edit aliases;
- canon as sources: character card, lorebook, persona, author's note, with authority, canon lock, and
  card-against-story conflicts shown (each source type needs host evidence first);
- export and restore of the ledger, repairs and settings (§89).

Done when:
- K8 and K23 are closed;
- every repair survives a rebuild and a new extractor generation;
- export, restore into a fresh install and replay give the same packets;
- each canon source has recorded host evidence and a conflict fixture.

## Stage 4 — Epistemic engine (under discussion)

*Original §27–30; Track B, B5.* Has: `public` / `limited` / unknown marks with free-text `known_by`
and `hidden_from` (ADR 0007), the packet telling the model how to use them, the Phase 9 leak report.

The fixed limit (§30, K11): one generation writes every character, so a secret the packet holds can
reach any of them. Track B's hard stop names four answers: separate model calls per character,
intersection-only context, omniscient narrator, or documented soft isolation. The owner and the agent
are discussing what "done" means for this stage; its scope and criteria are written here once decided.

## Stage 7 — Forensic recall

*Original §44–55, §78; Track B, B6.* Has: packet ledger, as-of replay, echo, abstention.

Scope (draft):
- fast, normal and forensic recall paths;
- an exact-quote path that prefers raw text;
- labels for candidates (required, supportive, risky, hidden) and a penalty for overused memory;
- evidence traversal in the Inspector;
- read-only MCP only if host evidence shows PocketRisu lets the response model call tools. **R5**: if
  it does not, MCP leaves the 1.0 scope (recorded, not built).

Done when:
- an exact-quote case set ("what did Hana say the first night?") is answered with the source turn;
- overuse is measured by echo before and after;
- the MCP question is answered by recorded host evidence.

## Stage 8 — PocketRisu bridge

*Original §80–82.* Nothing exists yet.

Scope (draft):
- a PocketRisu patch: partial chat reads (`getChatManifest`), mutation events, canon mutation events;
- NMOS detects the bridge and uses it, and behaves as today without it.

Done when:
- on the isolated test instance, K1 (5k/10k/15k), K3 and K16 are measured with and without the bridge;
- without the bridge nothing changes;
- the patch is offered upstream (acceptance is not required).

**R6**: whether the owner's production PocketRisu runs the patched build.

## The 1.0 gate

- stages 4–8 meet their done criteria;
- no evaluation category is worse than in `0.1.x`;
- an upgrade from a `v0.1.0-beta.21` database and from each `0.x.0` works (`tests/test_upgrade.py`);
- two weeks on the owner's production with no heavy change;
- every open known issue is a host limit or an accepted trade-off.

## After 1.0

The owner's longer aim is long-term memory for LLMs in general, not only role-play. The parts of NMOS
that already carry over are the immutable ledger with rebuildable memory, provenance, hybrid recall
with abstention, the budgeted and recorded packet, and fail-open. What does not is the PocketRisu adapter
and the narrative predicate registry. A generic direction (a host-independent entry such as an
OpenAI-compatible proxy, a generic fact schema, the R2 benchmark as its measure) is decided after 1.0.
