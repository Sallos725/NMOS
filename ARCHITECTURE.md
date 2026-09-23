# NMOS — Architecture

> Narrative Memory OS for PocketRisu (primary) and RisuAI (secondary).
> This file is the **stable contract**. It changes rarely and only by explicit decision.
> Phase-specific scope lives in `docs/phases/PHASE-N.md`. The long-form design rationale
> lives in `docs/reference/ultimate_narrative_memory_architecture.md` (reference only, not a spec).

---

## 1. Core idea

Preserve conversation, canon, edits, swipes and branches as **immutable source history**.
Treat every "memory" (facts, state, relationships, knowledge, summaries, threads, style)
as a **rebuildable projection** of that history.

```text
Host (PocketRisu)
   │  beforeRequest / output listener / snapshots
   ▼
Thin Host Adapter (plugin)          ← no memory logic here
   │  HTTP (token auth)
   ▼
Sidecar
   ├─ Reconciler ──► Source Ledger (immutable)
   │                    │
   │                    ▼
   │               Compiler (async, versioned)  ──► Projections (rebuildable)
   │                                                   │
   └─ Retrieval ◄──────────── Indexes (rebuildable) ◄──┘
        │
        ▼
   Selector ► Context Compiler ► MemoryPacket ► back to plugin ► injected
```

## 2. Invariants (non-negotiable)

1. **Raw evidence is never destroyed.** Summaries may replace text in the prompt, never in storage.
2. **Derived memory is rebuildable** from `source ledger + compiler version + config`.
3. **The response model never writes canonical memory.** MCP tools, if any, are read-only.
4. **Unknown is a valid result.** States include known / unknown / ambiguous / conflicting / pending / inferred.
5. **Current state and historical state are both answerable** (versioned facts, not overwrites).
6. **Character knowledge ≠ world knowledge.**
7. **Inactive sources cannot influence generation.** After edit/delete/reroll/swipe, dependent derived memory is invalidated before the next packet is built.
8. **Retrieval ≠ utilization.** Retrieved, visible, placed-in-context, and actively-used are separate decisions.
9. **Storage is replaceable.** Domain code depends on repository/index interfaces, not on pgvector/Postgres specifics.
10. **Every automatic claim has provenance** back to source revisions and compiler version.

Additional operational invariants:

- **Fail open.** Sidecar down or slow ⇒ the host generates normally without memory.
- **Never knowingly inject stale semantic state.** Stale ⇒ mask it and fall back to raw evidence or abstain.
- **The plugin never mutates host chat data** (no `setChatToIndex`).

## 3. Layers and responsibilities

| Layer | Owns | Must not contain |
|---|---|---|
| Host Adapter (plugin) | ID capture, manifest building, request gating, packet injection, output notification, settings | DB, extraction, ranking, long work, migrations |
| Source Layer | conversations, source objects/revisions, worldline commits, membership, host observations | interpretation of content |
| Compiler | normalization, entity/assertion/event extraction, validation, verification | direct writes to projections without provenance |
| Projection Layer | fact/knowledge/relationship versions, threads, scenes | anything not rebuildable from ledger + compiler |
| Retrieval Layer | routing, lexical/SQL/vector/graph search, fusion, selection, packet compilation | canonical writes |

## 4. Verified host facts (PocketRisu `a14c911`, source 2026-09-12, runtime 2026-09-22)

These were checked in source and **override** assumptions in the reference document.
H1–H7 were re-checked and extended by the Phase 0A runtime spike; H8–H14 are new runtime facts
(H13–H14 found while running Phase 0B against the real host).
Evidence for every runtime claim is in `docs/HOST-FACTS.md`.

| # | Fact | Consequence |
|---|---|---|
| H1 | `beforeRequest` replacer is called as `replacer(formated, model)`; 2nd arg is the **model mode** (`ModelModeExtended`), not a request purpose. Runtime: send/reroll/continue/retry → `model`; Auto Suggest → `submodel`. Trigger/Lua LLM calls also use `model` (source). | Main-generation gating needs a heuristic; auxiliary requests (summary, translation, etc.) pass through the same hook. |
| H2 | The replacer runs **inside the retry loop**; `formated` is only reset per fallback model. Runtime: 2 failures + 1 success = 3 calls with identical prompts, ~7 ms apart. | Injection must be idempotent (marker check) and reconcile/retrieve must be cached per request. |
| H3 | The replacer runs **after** host prompt assembly and context trimming, and **before** the Lua `request` trigger, whose returned array replaces the prompt wholesale. | Injected tokens can overflow max context; triggers may rewrite our packet. |
| H4 | New AI messages get `chatId = generationId`. Regeneration that replaces a message yields a **new** `chatId`, and the replaced reply moves into the new message's `swipes`; `continue` keeps the existing `chatId` but **replaces `generationId`** (so `generationId ≠ chatId` afterwards). With the default `useSayNothing`, "Continue Response" on a char tail appends a `*says nothing*` message and continues *that* message, which becomes `role: 'char'`. | Reroll is observed as delete + append, not as a new revision of the same ID. Lineage must be inferred from position/parent/swipes. `generationId` is not a stable message key. |
| H5 | Chat branching calls `reissueMessageIds()` and copies messages up to and including the branch point. The copied AI messages **keep their origin `generationId`**. A `{{specialcomment::branchedfrom::<origin chat.id>::<origin chat name>::<origin branch-point chatId>::}}` message is appended last (`role: 'char'`, `isComment`, `disabled: true`). | Cross-chat branches are new conversations unless we parse this marker; the prefix maps to the origin by position (and by `generationId` for AI messages). |
| H6 | `normalizeChat()` assigns UUID `chatId` to messages missing one at hydration and import. Message ids are unique only **within** a chat: importing a chat keeps every message `chatId` under a new `chat.id`. | Logical message identity is `(host chat id, Message.chatId)`, never `chatId` alone. |
| H7 | `output` listeners are awaited sequentially; snapshots are plain copies. The `output` snapshot precedes some host post-processing (reroll `swipes` are attached after it). | Listener must return immediately; background work is fire-and-forget. Output notifications are provisional hints; the next request snapshot is authoritative. |
| H8 | V3 plugins run only in a secure context (sandbox uses `crypto.randomUUID`). Over plain-HTTP LAN they do not load; on localhost/HTTPS `crypto.subtle` is available in the sandbox. | Plugin-side SHA-256 is always available where NMOS can run; deployment must be localhost or HTTPS (Remote Access). |
| H9 | The current chat index is positional: importing a chat prepends it without changing `chatPage`, so the same index then names a different chat. | Never use character/chat index as identity; key conversations by `chat.id`. |
| H10 | Edit, delete, disable, swipe switch, branch, import and reload fire no plugin hook. | Divergence is discovered only at the next main-generation snapshot. |
| H11 | Build `a14c911` has no group-chat type (`character.type` is only `"character"`; `isGroupChat` is hard-coded `false`). | Group-chat principal logic has no host surface on this build. |
| H12 | `saveSecretHeader` is an unimplemented stub; `nativeFetch` fetches directly from the browser (proxy fallback), passes headers through, and accepts a numeric `requestTimeoutMs`. | Sidecar token lives in a plugin arg (ADR 0003); sidecar must serve CORS; deadlines use `requestTimeoutMs` + a local timer. |
| H13 | V3 `addRisuReplacer` registers no unload callback (`loadPlugins` clears only `chatOutput`). After a V3 plugin is disabled, updated or re-imported, its old `beforeRequest` replacer stays registered against a dead iframe and **every generation hangs** until the page is reloaded. | Always reload PocketRisu after installing/updating/disabling the NMOS plugin (documented in README). The plugin cannot guard against this. |
| H14 | On reroll the host removes the tail AI message *before* `beforeRequest` runs (S2 beforeRequest saw 7 of 8 messages; confirmed in 0B live runs). The regenerated reply appears only in the next request's snapshot. | Live reroll reconciles as "head minus tail" → retract; lineage to the new reply is not observable in the same request. |
| H15 | The V3 plugin iframe is sandboxed with only `allow-scripts allow-modals allow-downloads` and `allow="screen-wake-lock"`. Runtime (v1.12.0): a `target="_blank"` link is blocked ("sandboxed frame whose 'allow-popups' permission is not set"), and `navigator.clipboard.writeText` is refused by permissions policy. The V3 API has no call that opens a URL. | The plugin cannot open a browser tab. The Inspector is shown inside the panel from `/v1/inspector*`, and links in it must be handled by the panel (following one would navigate the plugin frame). |

## 5. Key decisions

Short ADR-style entries. Full ADRs go in `docs/adr/`.

**D1 — Plugin-first, no fork.** Pure plugin mode is the only supported mode until profiling
proves a bridge API is needed (see reference §82 criteria). Any future fork is bridge-only.

**D2 — Token budget is reserved, not stolen.** Because of H3, the user lowers the host's
max context by `reservedMemoryTokens` (setting). The packet never exceeds that reserve.
Trimming host history from inside the plugin is a later, opt-in feature.

**D3 — Do not re-inject what the host already sent.** Evidence whose source revision is
already present in the outgoing `formated` messages is excluded from the packet.
Activated lorebook entries are treated the same way. Lorebook is canon for conflict checks,
not a retrieval payload by default.

**D4 — Worldline commits only on divergence.** Appends update membership; commits are created
for edit / delete / swipe / reroll / disable / branch / import / manual. Full DAG semantics
are kept in the schema but not exercised beyond what reconciliation needs.

**D5 — Lazy compilation.** Assistant output enters the ledger as `PROVISIONAL` immediately,
but semantic compilation runs only after it becomes `ACCEPTED` (user continued from it).
Swipe churn does not burn extraction calls.

**D6 — Closed predicate registry.** The compiler may only emit predicates defined in
`packages/domain/predicates` with declared subject/object types, cardinality
(single/multi-valued), and epistemic class. Unknown predicates become `pending` candidates
for review, not facts.

**D7 — Bounded extraction context, per turn (revised 2026-09-23, ADR 0008).** The unit of
extraction is the **turn**: a run of user messages plus the run of replies that answers it (comments,
disabled and pre-`allBefore` messages excluded; the greeting is turn 0). A turn is extracted once,
when its anchor (last reply) is accepted, with at most the previous `K` turns as context
(`NMOS_EXTRACT_TURNS`, default 3). An edit inside turn *t* re-extracts only turns `[t, t+K]`.
Extraction is keyed by `(anchor revision, turn_hash, extractor generation)` (D20).

**D8 — Synchronous invalidation, asynchronous recompilation.** At `beforeRequest`, stale
derived rows are masked synchronously (no LLM). Re-extraction is queued. Until it finishes,
retrieval uses raw evidence for the affected range.

**D9 — Principal modes.** `omniscient_narrator` (default for single-call bots): world truth
available, character knowledge boundaries attached as annotations.
`character_pov`: hard epistemic ACL; hidden values are never placed in context.
Hard isolation across simultaneously generated characters is out of scope (reference §30).

**D10 — Deterministic structure first.** Status windows, HTML/regex display blocks, and other
machine-shaped content in messages are parsed deterministically (per-bot parser configs)
before any LLM extraction. This is the preferred source for current-state facts.

**D11 — Lexical recall must work for CJK.** Postgres default FTS tokenization is inadequate
for Korean/Japanese. Use `pg_trgm` (or `pg_bigm` if available) for raw evidence recall.
Exact-quote recall always prefers lexical over vector search. The trigram index covers the normalized
text projection (D21), not raw content.

**D13 — Main-generation gating (O3, ADR 0001).** Inject only when `mode === 'model'` and the
host chat's latest user message is in a non-assistant prompt message (cleaned-text anchor match,
newest first; no preset layout assumed). The packet goes before that turn.

**D14 — Branches are new conversations (O4, ADR 0002).** Record origin chat ref, origin
conversation (if known) and branch-point message ref from the `branchedfrom` marker; no
cross-conversation revision linking.

**D15 — Raw recall scoring (ADR 0004).** Candidates must match the latest user message
(`word_similarity ≥ 0.4`); the previous AI turn only breaks ties; `disabled` and `allBefore`-cut
ranges are inactive and never recalled.

**D16 — Deterministic state via parser rules (Phase 1).** JSON rules → `state_observation`
projection; current state read through head membership (inherits D8 invalidation).

**D17 — Extraction validity is keyed by window (Phase 2, D7; ADR 0008).** `active_membership.turn_hash`
(anchor rows) makes an extraction valid only while the head shows the same turn and bounded context;
the per-message `window_hash` is kept for generations compiled before turns. Jobs run in `nmos-worker`
through a SKIP LOCKED queue; single-valued predicates form fact versions.

**D18 — Hybrid recall (Phase 3, ADR 0005).** Exact cosine over head-membership chunk embeddings (pgvector),
RRF with lexical, abstention by per-signal bars, query-side instruction for instruction-tuned embedders,
fail-open to lexical on embedding timeout.

**D19 — Soft character knowledge (Phase 4 subset; revised 2026-09-22, ADR 0007).** Each assertion
has `knowledge = public | limited | unknown`. `public` is openly known and needs no list; `limited`
names characters shown to know it (`known_by`) and/or characters it is kept from (`hidden_from`);
`unknown` means the evidence does not show who knows. Awareness of anyone not listed is unknown, never
"does not know"; the packet Note says exactly this. A name in both lists is contradictory evidence and
is dropped from both (noted on the assertion). Names are free text in this soft phase. A fact hidden
from a character addressed right now is ranked first. Hard POV isolation stays out of scope: a sim bot
writes every character in one generation (D9).

**D20 — Derived projections are bound to a generation (ADR 0006).** An extractor generation hashes
compiler version, prompt and predicate-registry fingerprints, normalizer version, endpoint identity,
model and output-affecting settings. An embedding projection hashes endpoint, model, normalizer,
chunker and document profile. Credentials are never part of a key. Jobs, extractions and embedding
rows carry their key. A worker only claims jobs for the generation its handler implements. Readers
use only the active generation. Older generations stay stored for audit and are never mixed in.
Activation queues the recent window first, then every older item an earlier generation covered, at
background priority. Coverage (compiled / pending / failed / not queued) is measured per conversation
and partial coverage is shown as partial.

**D21 — One normalized-text projection (ADR 0006).** `revision_text(revision, normalizer)` stores
`clean_text()` output. Lexical recall, embedding, extraction and excerpting read it, and query text is
normalized the same way. It is derived: written at ingest, backfilled at startup, rebuildable with
`nmos-rebuild --text`. Raw `source_revision.content` is unchanged. Bounded processing of long messages
(embedding 8 × 700 chars, extraction 6,000 target / 2,000 context chars) is recorded per revision and
visible in the Inspector.

**D22 — NMOS never ingests a chat by itself; history and rebuild are explicit (ADR 0008).** A chat
enters the ledger only when the user generates in it with the plugin on. First sight extracts the
latest `NMOS_EXTRACT_BACKFILL` turns; the rest of a chat is extracted on request
(`POST /v1/conversations/{id}/extract-history`). A rebuild (`POST /v1/conversations/{id}/rebuild`)
marks the chat's active-generation extractions discarded (kept for audit) and re-extracts every turn.

**D12 — MCP is optional deep recall**, never the correctness mechanism. Tools are read-only
and bound server-side to `(conversation, worldline, principal)` via a scope token.

## 6. Stack (confirmed by owner 2026-09-22; O2 resolved: PostgreSQL)

| Part | Choice |
|---|---|
| Sidecar | Python 3.12, FastAPI, Pydantic v2, psycopg 3 with explicit SQL, `uv` |
| DB | PostgreSQL 16 + `pg_trgm` (+ `pgvector` from Phase 3) |
| Migrations | plain SQL files in `migrations/`, applied by a small runner |
| Worker | same codebase, separate process, Postgres-backed job table (`SKIP LOCKED`) |
| Plugin | TypeScript → single bundled `.js` (esbuild) in PocketRisu V3 plugin format |
| Tests | pytest (sidecar), vitest (plugin pure functions) |
| Deploy | Docker Compose on homelab; token auth via `saveSecretHeader`; TLS if crossing hosts |

## 7. Repository layout

```text
nmos/
├── AGENTS.md / CLAUDE.md / ARCHITECTURE.md
├── docker-compose.yml         # postgres + sidecar (Phase 0B)
├── .env.example
├── docs/
│   ├── HOST-FACTS.md          # runtime host evidence (Phase 0A, extended in 0B)
│   ├── STATUS.md
│   ├── phases/PHASE-0.md … PHASE-4.md (+ PHASE-0-RETRO.md)
│   ├── perf/phase0.md, perf/scale.md
│   ├── adr/
│   └── reference/             # long-form design doc (non-normative)
├── adapters/
│   ├── pocketrisu-spike/      # Phase 0A observation plugin (throwaway)
│   └── pocketrisu-plugin/     # Phase 0B thin adapter (TypeScript → dist/nmos-pocketrisu.js)
├── apps/
│   └── sidecar/               # Python package nmos_sidecar:
│                              #   canonical, reconcile (pure), ledger, retrieval, packet, api, migrate, rebuild
├── migrations/                # numbered SQL, applied by nmos-migrate
├── fixtures/
│   ├── host/                  # recorded PocketRisu observations
│   └── unit/                  # cross-language hash vectors
├── tools/                     # Phase 0A spike tooling (collector, stub model, report, synthetic chat)
└── docker/
```

Later phases add `apps/worker/` (Phase 2) and split domain code into packages only when a second
consumer needs it; empty future directories are not created in advance.

## 8. Roadmap (summary)

| Phase | Deliverable | Uses LLM? |
|---|---|---|
| 0A | Host observation spike → `HOST-FACTS.md` | No |
| 0B | Adapter + sidecar + ledger + reconcile + raw lexical recall + budgeted injection | No |
| 1 | Deterministic state parsers (D10), inspector v0 (read-only), traces — **done (beta)** | No |
| 2 | Predicate registry (D6), bounded extraction (D7), assertions, fact versions — **done (beta)** | Yes, async |
| 3 | Hybrid retrieval (SQL + trigram + pgvector), RRF, selector, abstention — **done (beta)** | Embeddings only |
| 4 | Soft subset — knowledge marks (D19) — **done (beta)**; hard principal modes (D9 `character_pov`) not authorized | Yes |
| 5+ | Threads, causal links, hierarchy, verifier, forensic recall, MCP | Yes |

Each phase gets its own `PHASE-N.md` with acceptance criteria before work starts.

## 9. Open decisions

These must be resolved by the owner, not by an implementing agent.

- **O1 — Relationship to MIRRA and VEIL.** Is NMOS MIRRA v2 (superseding its SQLite/MCP-first
  choices)? Does NMOS absorb VEIL's knowledge-boundary role, or consume VEIL as a separate
  plugin for disclosure pacing?
- ~~O2 — Postgres vs SQLite~~ — **resolved 2026-09-22: PostgreSQL** (§6).
- ~~O3 — Main-generation gating heuristic~~ — **resolved 2026-09-22: D13 / ADR 0001.**
- ~~O4 — Cross-chat branch policy~~ — **resolved 2026-09-22: D14 / ADR 0002.**
- **O5 — Retention of abandoned worldlines.**
