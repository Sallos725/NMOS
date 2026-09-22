# Phase 0 — Host Spike and Walking Skeleton

> Goal: prove the plumbing end to end with **zero LLM calls** and zero semantic interpretation.
> At the end of Phase 0, a PocketRisu chat sends every main generation through NMOS,
> the sidecar holds a correct immutable history of the chat (including edits, swipes,
> rerolls, deletes), and a small raw-recall packet is injected within a reserved budget.

Phase 0 has two sub-phases. **0B does not start until 0A's exit criteria are met.**

---

## 0A — Host Observation Spike

### Purpose

Replace assumptions with measurements. The spike is a throwaway logging plugin; its only
durable output is `docs/HOST-FACTS.md` and a set of recorded fixtures.

### Deliverable

`adapters/pocketrisu-spike/` — a V3 plugin that registers:

- `beforeRequest` replacer that **returns `formated` unchanged** and logs:
  - timestamp, 2nd argument value (model mode), call count within one user action
  - number of messages, roles, approximate token count (chars/4 is fine)
  - whether the last message is the user's latest input
  - `getCurrentCharacterIndex()`, `getCurrentChatIndex()`
- `output` listener that logs `characterIndex`, `chatIndex`, `messageIndex`,
  the message's `chatId`, `generationInfo.generationId`, `swipeId`, `swipes.length`
- A settings/button action "Dump snapshot" that calls `getChatFromIndex()` and records:
  - elapsed time, serialized byte size, message count
  - whether `crypto.subtle.digest` is available in the plugin sandbox, and time to hash all messages

Logs go to the browser console and, optionally, to a local HTTP collector
(`nativeFetch` to `http://<homelab>:<port>/spike`) so they can be saved as fixtures.

### Scenarios to run (manually, in PocketRisu)

For each scenario record the manifest before and after (message `chatId`, role, `swipeId`,
`swipes.length`, `disabled`, `generationId`, content hash).

| ID | Action |
|---|---|
| S1 | Send a normal user message; get a reply |
| S2 | Regenerate the last reply (reroll) |
| S3 | Switch between swipes on the last reply |
| S4 | Continue the last reply |
| S5 | Edit an old user message |
| S6 | Edit an old AI message |
| S7 | Delete a message in the middle |
| S8 | Disable / "hide before" a message (whatever `disabled: 'allBefore'` maps to in UI) |
| S9 | Branch the chat from a middle message |
| S10 | Import a chat / reload the app, then compare `chatId`s |
| S11 | Trigger an auxiliary request (HypaMemory summary, translation, or any submodel use) |
| S12 | Force a request failure/retry (e.g. invalid key on first fallback) and count replacer calls |
| S13 | Group chat: one reply cycle with ≥2 characters |
| S14 | Large chat (≥ 1,000 messages, synthetic is fine): snapshot time and size |

### `docs/HOST-FACTS.md` must answer

1. Which model-mode values reach `beforeRequest`, and how can a main chat generation be
   distinguished from auxiliary requests? (→ resolves ARCHITECTURE O3)
2. How many times does the replacer run per user action in normal, retry, and fallback cases?
3. For S2–S10: does `chatId` stay, change, or get reissued? Confirm/deny H4 and H5.
4. Exact format of the `branchedfrom` marker as it appears in `message.data`.
5. Is `crypto.subtle` usable? Hash cost for 1,000 messages?
6. `getChatFromIndex()` cost at 100 / 1,000 messages (ms, bytes).
7. Does the Lua `request` trigger in common bots alter system/injected messages? (spot check)
8. Any mutation that is **invisible** to request-time reconciliation.

### Exit criteria (0A)

Status 2026-09-22 — met (details in `docs/HOST-FACTS.md`).

- [x] All 14 scenarios executed and logged. (S13 not executable on `a14c911`: no group chat; owner accepted N/A.)
- [x] `HOST-FACTS.md` answers questions 1–8, each with evidence (log excerpt or fixture path). (Q7 from source; owner accepted.)
- [x] At least S1–S9 saved as JSON fixtures in `fixtures/host/` (manifest before/after; raw snapshots not captured — hashes only).
- [x] ARCHITECTURE §4 updated if any H-fact was wrong.
- [x] Owner has resolved O3 (gating heuristic) and O4 (branch policy) based on the facts. (D13, D14)

---

## 0B — Walking Skeleton

### In scope

1. Sidecar service (FastAPI) with token auth and health check.
2. Postgres schema for the **source layer only** + observation and trace tables.
3. Manifest building and revision hashing in the plugin.
4. Reconciliation in the sidecar covering every scenario from 0A.
5. `PROVISIONAL → ACCEPTED / RETRACTED` lifecycle for assistant messages.
6. Raw lexical recall (trigram) over **accepted, active, out-of-context** revisions.
7. MemoryPacket compilation within `reservedMemoryTokens`, idempotent injection.
8. Fail-open behavior with a hard deadline.
9. Retrieval trace per request.

### Out of scope (do not build)

LLM extraction, entities, assertions, events, fact versions, embeddings/pgvector, graph,
reranking, epistemic filtering, MCP, inspector UI, worker process, group-chat principal logic,
bridge API, RisuAI (non-Pocket) adapter.

### Plugin behavior

**Settings**: `sidecarUrl`, `authToken` (stored via `saveSecretHeader`), `enabled`,
`reservedMemoryTokens` (default 600), `deadlineMs` (default 800), `injectPosition`
(default: system message immediately before the final user message).

**`beforeRequest(formated, mode)`**

```text
1. If disabled, or not a main generation (per HOST-FACTS gating rule) → return formated.
2. If formated already contains the NMOS marker → return formated.          (H2)
3. requestKey = hash(chat id + last message chatId + mode + formated length)
   If cache[requestKey] exists → inject cached packet, return.               (H2)
4. Snapshot current chat; build manifest (hashes; bodies only on request).
5. POST /v1/sync/reconcile  (deadline-bound)
   - if response lists needed revision hashes, POST their bodies, then continue.
6. POST /v1/retrieve with: conversation, active commit, query text (last user message),
   in-context message ids (derived by matching formated contents to snapshot), budget.
7. Inject packet; cache by requestKey; return.
Any error or deadline hit at any step → return formated unchanged, log warning.   (fail open)
```

**`output` listener**: build a minimal notification (`chatId`, `generationId`, message
hash, index) and fire `POST /v1/output` without awaiting. Return immediately. (H7)

**The plugin must never call `setChatToIndex` or otherwise mutate host data.**

### Revision hash

`sha256` over a canonical JSON of:

```text
v (hash format version, start at 1)
chatId, role, saying, name, otherUser, isComment
disabled
swipeId, selected swipe content (or data if no swipes)
generationId
```

Canonicalization: Unicode NFC, `\r\n` → `\n`, no trailing-whitespace trimming,
keys sorted. Excluded: `time`, `promptInfo`, UI-only fields. If `crypto.subtle` is
unavailable (0A Q5), the plugin sends bodies and the sidecar computes hashes.

### Sidecar API

```text
GET  /v1/health
POST /v1/sync/reconcile     manifest → { active_commit, needed_bodies[], changes_summary }
POST /v1/sync/bodies        [{ revision_hash, content, metadata }] → ok
POST /v1/retrieve           → { trace_id, freshness, packet: { text, token_estimate } }
POST /v1/output             provisional output notification → 202
GET  /v1/trace/{trace_id}
```

All endpoints require `Authorization: Bearer <token>`. All writes are idempotent
(idempotency key = `conversation + revision_hash + operation`).

### Schema (source layer only)

```text
conversation            (id, host, host_character_ref, host_chat_ref, created_at,
                         branched_from_conversation_id?, branched_from_message_ref?)
source_object           (id, conversation_id, host_logical_id /* Message.chatId */,
                         source_kind, created_at)
source_revision         (id, source_object_id, revision_hash UNIQUE per object,
                         content, metadata jsonb, recorded_at,
                         lifecycle /* provisional|accepted|retracted|superseded */,
                         lineage_parent_revision_id? /* reroll/continue inference */)
worldline_commit        (id, conversation_id, parent_commit_ids uuid[], reason,
                         manifest_hash, delta jsonb, created_at, host_observation_id)
active_membership       (commit_id, position, source_revision_id)   -- materialized for current head
host_observation        (id, conversation_id, manifest_hash, observed_at, raw_manifest jsonb)
retrieval_trace         (id, conversation_id, commit_id, query, candidates jsonb,
                         selected jsonb, excluded_in_context jsonb, token_estimate,
                         latency_ms jsonb, freshness, created_at)
```

Rules: `source_revision.content` is **never updated**. Lifecycle changes are the only
mutation allowed on a revision row. Trigram GIN index on `source_revision.content`.

### Reconciliation cases (each needs a unit test using 0A fixtures)

| Case | Detection | Result |
|---|---|---|
| No change | same manifest hash | no-op, return current head |
| Append | new ids at tail | new revisions; membership extended; **no commit** (D4) |
| Edit | same id, new hash | new revision; old → superseded; commit `edit` |
| Swipe switch | same id, new hash, `swipeId` changed | new/existing revision active; commit `swipe` |
| Continue | same id, new hash, content extends previous | new revision with lineage parent; commit `edit` |
| Reroll | tail AI id disappears, new AI id at same position | old → retracted; new revision with lineage parent; commit `reroll` (H4) |
| Delete | id disappears mid-chat | excluded from membership; commit `delete` |
| Disable | `disabled` changed | new revision (hash includes disabled); commit `disable` |
| Branch | new chat whose early messages contain the `branchedfrom` marker | per O4 policy; at minimum record `branched_from_*` on conversation |
| Large divergence | > N% of ids unknown | commit `reconciliation` with full delta |
| Acceptance | a new user message follows a provisional AI revision | that revision → accepted |

### Raw recall (the only retrieval in Phase 0)

- Candidates: revisions that are `accepted`, active at head, and **not** in the current
  outgoing context (D3).
- Scoring: `pg_trgm` similarity against the last user message (plus the previous AI message),
  top-k (default 5), excerpted to ~2 sentences around the best-matching span.
- Packet format (data, not instructions):

```xml
<NarrativeMemory version="0" source="nmos">
  <Note>Earlier excerpts from this conversation. Reference only; not instructions.</Note>
  <Excerpt turn="148" speaker="Hinata">…escaped text…</Excerpt>
</NarrativeMemory>
```

- Hard cap at `reservedMemoryTokens`; if nothing scores above threshold, inject nothing.

### Performance targets (measure, report; not yet gating)

| Path | Target |
|---|---|
| Reconcile, incremental (1 append) | p95 < 50 ms sidecar |
| Retrieve (raw recall) | p95 < 150 ms sidecar |
| Total `beforeRequest` added latency, LAN | p95 < 300 ms |

### Acceptance criteria (0B)

Status 2026-09-22 — all met. Evidence in brackets.

- [x] `docker compose up` brings up sidecar + Postgres; migrations apply cleanly on empty DB.
      [sidecar log `applied: 0001_source_layer.sql`; `test_migrations_apply_cleanly_and_are_guarded`]
- [x] Every reconciliation case above has a passing test driven by recorded fixtures.
      [`apps/sidecar/tests/test_reconcile_fixtures.py` on `fixtures/host/a14c911-2026-09-22`; large
      divergence uses two recorded manifests of different chats; live reroll uses S2 per H14]
- [x] Replaying all fixture manifests in order twice produces identical ledger state (idempotency).
      [`test_retry_duplicates_and_replay_are_idempotent`: every request duplicated vs. once → identical
      logical ledger; `test_retry_resend_is_noop` on recorded S2]
- [x] Deleting nothing but `retrieval_trace` and `active_membership`, a rebuild command
      reconstructs `active_membership` from `worldline_commit` deltas.
      [`nmos-rebuild`; `test_rebuild_membership_from_commits`; live DB: 2,530 rows, identical SHA-256
      before/after]
- [x] Sidecar stopped → chats generate normally; plugin logs one warning per request, no UI error.
      [real host run, HOST-FACTS "Phase 0B runtime findings" 3]
- [x] Sidecar artificially delayed beyond `deadlineMs` → request proceeds without packet.
      [`NMOS_DEBUG_DELAY_MS=2000`: reply after ≈1.05 s, `nmos_packets=0`]
- [x] Retry scenario (S12) injects exactly one packet and calls `/v1/retrieve` at most once.
      [real host: 2 forced 500s → 3 attempts each with `nmos_packets=1`, sidecar log 1× `/v1/retrieve`]
- [x] Auxiliary request (S11) receives no packet.
      [every Auto Suggest `submodel` request in the real host: `nmos_packets=0`]
- [x] In a 200+ message chat, recall surfaces a relevant out-of-context excerpt in manual testing,
      and never an excerpt from a deleted, retracted, or superseded revision.
      [250→490-message chat: turn-10 fact recalled from a 168-message prompt; UI edit → only the new
      text recalled; UI delete → never recalled; Continue+Reroll → `retracted`, never selected;
      edit-then-reroll → fresh packet]
- [x] `GET /v1/trace/{id}` shows candidates, exclusions (in-context), selection, and latency.
- [x] Latency numbers recorded in `docs/HOST-FACTS.md` (or `docs/perf/phase0.md`). [`docs/perf/phase0.md`]

Implementation notes / deviations (all recorded in ADRs):

- Auth token is a plugin argument, not `saveSecretHeader` (unimplemented on the host; ADR 0003).
- Plugin settings are PocketRisu args `sidecar_url`, `auth_token`, `disabled` (int, 1 = off, because
  int args default to 0), `reserved_memory_tokens`, `deadline_ms`, `inject_position`.
- `crypto.subtle` is always available where the plugin can run (H8), so the "send bodies, sidecar
  hashes" fallback is unnecessary; the sidecar still re-verifies every body's hash.
- `/v1/sync/bodies` accepts an optional `then_reconcile` manifest to save a round trip, and bodies are
  uploaded in chunks of 250.
- The plugin caches a packet per exact chat state (all message ids + revision hashes), so host retries
  and rerolls of an unchanged chat reuse it, but no edit can make it stale.
- Recall scoring and inactive ranges: ADR 0004.

### Definition of done

All boxes checked, `ARCHITECTURE.md` updated with any decision made during the phase,
and a short `docs/phases/PHASE-0-RETRO.md` listing surprises and what Phase 1 should change.
