# Phase 68 — Cleaning up conversations missing from the host

Status: **approved**, 2026-11-26 (owner: Q1–Q4 all answered as recommended `(a)`, build now on a feature branch for the upcoming `0.7.0` release; pulls in C10 of `docs/proposals/IDEA-SURVEY-2026-09-29.md` / AGE-4 from "After 1.0", host evidence H22 already recorded). **Built on `feat/phase68-orphan-delete` (2026-11-26, zero-call checks + scoped high-risk self-review done; real-host check on PocketRisu / 6113 open).**

**High risk** (`AGENTS.md §14`) once built:
- **irreversible bulk deletion of raw evidence** (Invariant 1, D23, ADR 0009): every selected conversation and all of its rows (`source_revision`, extractions, assertions, repairs, carry links, model calls) are permanently deleted;
- **false-positive deletion risk** (H22): a character moved to PocketRisu's Trash or deactivated leaves `db.characters` identically to a deleted chat, and a refused/empty host DB read or a second PocketRisu install sharing the same sidecar would mark live chats as missing if unguarded;
- **carried-memory side effect** (ADR 0085): deleting a conversation that another active chat carries via `conversation_carry` (`source_conversation_id`) deletes that active carry link with it.

Invariants it touches (`AGENTS.md §3`):
- **Raw evidence is never destroyed by NMOS itself** (amended by ADR 0009): only on the owner's explicit, reviewed, two-step confirmation; never automatic, never on startup, never on the request path.
- **The plugin never mutates host chat data**: reads `getDatabase(['characters'])` read-only, strictly on demand when the owner presses Scan.
- **No schema migration, no extractor/embedding/canon generation change, no packet policy change**: zero model calls, zero re-extraction, zero recall or prompt behavior change.

---

## Why

PocketRisu fires no plugin hook when a chat is deleted (H10), and NMOS never scans or deletes chats on its own (D22, ADR 0009). Over time, deleted chats accumulate in NMOS's database, Inspector list, chat switcher, and archives. Today the owner must open each missing conversation one by one in Settings → This chat → Delete conversation, with no way to see which conversations no longer exist in PocketRisu.

Host evidence **H22** (`docs/HOST-FACTS.md`, measured 2026-10-01 on PocketRisu v1.13.0):
- The V3 API has no dedicated chat-list call. `getDatabase(['characters'])` returns every active character with every chat's `id`, under the same `"db"` permission NMOS already requests for personas (H17) — no new permission prompt.
- Cost depends on how many chats the owner opened in the current page session (unopened chats are placeholders, ≈0.5 ms total; 10,000–15,000 opened messages ≈94–154 ms). It therefore must run **only when the owner explicitly triggers a scan**, never on `beforeRequest` or on a background timer.
- **Critical host limit (H22 item 4):** a permanently deleted chat and a chat belonging to a character in PocketRisu's Trash or Deactivated (`nodeOnlyArchivedCharacters`, unreadable by plugins) are **indistinguishable** — both simply disappear from `getDatabase(['characters'])`.
- **Multi-install limit (H22):** NMOS records `host = 'pocketrisu'` and `host_chat_ref`, not which PocketRisu instance a chat came from. If one sidecar serves two PocketRisu instances, each sees the other's chats as missing.
- **Cross-conversation links:**
  - `conversation_carry` (Phase 60, ADR 0085): deleting a source conversation cascades/deletes any active carry link (`removed_at IS NULL`) pointing to it, removing carried memory from the target chat.
  - `branch_inherit` (Phase 67, migration `0042`): inherited copies are independent rows with no foreign key to the origin; deleting the origin only clears `branched_from_conversation_id` (ADR 0009 §5) and leaves the branch's inherited memory intact.

---

## What it does

### S1. Host active-chat scan (plugin, on demand only)

Add a read-only `hostChatIds(): Promise<HostChatScan>` helper in `adapters/pocketrisu-plugin/src/host.ts`:
- Calls `risuai.getDatabase(['characters'])` **only** when the owner clicks the Scan button in the panel.
- Returns a discriminated result — **never silently collapses errors or permission denials into an empty list**:
  - `{ ok: true, chatIds: string[], characterCount: number }` — only when `db` is non-null and `Array.isArray(db.characters)`. Collects every non-empty string `chat.id` across every character's `chats` array (deduplicated).
  - `{ ok: false, reason: 'unsupported' | 'denied' | 'invalid' }` — when `getDatabase` is absent, returns `null` (permission denied, H17), or `characters` is not an array.
- **Empty-host guard:** if `ok === true` and `characterCount === 0` (or `chatIds.length === 0`), the UI refuses to auto-select and displays an explicit warning ("호스트에서 활성 채팅을 하나도 찾지 못했습니다 / No active chats returned by host") before allowing any preview/deletion, preventing catastrophic wipe if a host update changes the DB shape.

### S2. Sidecar preview endpoint (`POST /v1/conversations/orphans/preview`)

Behind the same auth guard as `POST /v1/conversations/{id}/delete` (`Depends(auth)`):
- **Request body:**
  ```json
  {
    "host": "pocketrisu",
    "active_chat_refs": ["<host chat id>", "..."]
  }
  ```
  - Validates `host` (non-empty string, defaults to `"pocketrisu"`) and `active_chat_refs` (list of strings; bounded e.g. max 50,000 entries, NUL/surrogate rejected with 422 per D40).
- **Query:** reads **all** `conversation` rows for `host` (not capped at `readmodel.list_conversations`'s 200-row limit) whose `host_chat_ref` is not in `active_chat_refs`. (Includes both normal conversations and any stub conversations with `head_commit_id IS NULL` — see Q2.)
- **Per-candidate metadata returned** (newest `last_retrieval` / `created_at` first):
  - `id` (UUID), `host_chat_ref`, `character` (`host_character_name`), `chat` (`host_chat_name`),
  - `messages` (count on head, 0 if no head), `commits`, `created_at`, `last_retrieval`,
  - `carried_by`: list of active carry targets (`WHERE source_conversation_id = c.id AND removed_at IS NULL`), each with `{ id, character, chat, mode, target_missing: bool }` so the UI can distinguish *"carried by an active chat"* from *"carried only by another orphan"*,
  - `branch_children`: count of conversations with `branched_from_conversation_id = c.id` (informational only: branch copies survive origin deletion per migration `0042`).
- **Response also includes:**
  - `total_host_conversations`: total NMOS conversations stored for `host`,
  - `matched_active`: how many NMOS conversations matched `active_chat_refs`,
  - `orphans`: candidate array.
- Pure read-only query; modifies nothing.

### S3. Sidecar bulk delete endpoint (`POST /v1/conversations/delete-batch`)

Behind `Depends(auth)` (same guard as single delete and restore, PHASE-38 Q6):
- **Request body:**
  ```json
  {
    "ids": ["<conversation uuid>", "..."]
  }
  ```
  - Deduplicates UUIDs preserving order; rejects empty list (`422`) and caps batch size per request (e.g. max 500; `422` above cap).
- **Execution:** deletes each requested conversation **individually using the existing `ledger.delete_conversation(conn, conv_id)`** (one transaction per conversation):
  - Preserves migration `0012`'s `nmos.delete_conversation` single-conversation database trigger guard untouched (no trigger weakening, no new SQL delete path to drift from future migrations!).
  - Takes the per-conversation `FOR UPDATE` lock as single delete does (ADR 0009 §4).
  - If a conversation was already deleted concurrently (`None`), records it under `not_found` instead of failing the batch.
  - Logs one audit line per deleted conversation (same format as single delete) plus a batch summary line (`deleted_batch requested=N deleted=M not_found=K`).
- **Response:**
  ```json
  {
    "deleted": [
      { "id": "<uuid>", "counts": { "messages": 42, "revisions": 45, "carry_links": 0, ... } }
    ],
    "not_found": ["<uuid>"],
    "totals": { "conversations": 3, "messages": 120, "revisions": 135, "carry_links": 0 }
  }
  ```

### S4. Panel UI (Settings → Backup & Data, `#nmos-backup` group)

Add a **"목록에 없는 대화 정리 / Clean up missing chats"** card inside Settings → Backup (`data-group="backup"`, beside Export and Restore):
1. **Explanatory notice (always visible before scan):**
   - Clearly states that PocketRisu's Trash and deactivated characters also disappear from the active list (H22), and that if multiple PocketRisu instances share one sidecar, other instances' chats will appear missing too.
   - Recommends exporting a backup before bulk deletion.
2. **Step 1 — Scan button (`누락된 대화 찾기 / Scan missing chats`):**
   - Calls `hostChatIds()`, then `POST /v1/conversations/orphans/preview`.
   - On `denied`/`unsupported`/`invalid`, shows a clear error (including the PocketRisu permission reset hint if `"db"` was denied) and displays no delete controls.
   - If 0 orphans are found, shows *"모든 NMOS 대화가 현재 PocketRisu 목록에 있습니다 ({matched}/{total}) / All NMOS conversations exist in PocketRisu"*.
3. **Step 2 — Preview & Checkbox Selection:**
   - **Select-all checkbox (`전체 선택 / Select all`)** at the top of the list (supports `checked` / `indeterminate` / unchecked states, with live selected count badge e.g. `N / M 선택됨`).
     - *Initial state after scan:* see Q1 (default: safe orphans without active `carried_by` links checked, or all unchecked — owner decides; carry-linked items start **unchecked** either way!).
     - *When toggling Select All:* see Q1 (toggles all listed candidates, including warned ones, OR toggles safe ones first; when any carry-linked item is selected, an inline warning banner explicitly lists the affected target chats).
   - **Per-row display:** checkbox, `캐릭터 · 채팅명` (fallback `host_chat_ref`), message count, last used local timestamp, and:
     - **Carry warning badge (owner decision: warn only, selectable):** if `carried_by` has any active target chat, display a yellow/amber warning badge (`⚠ <대상 채팅>이(가) 이 기억을 이어받는 중 — 삭제 시 이어받은 기억도 함께 제거됨`) while leaving the checkbox **enabled** so the owner can still choose to delete it.
     - Note: if the currently open chat in the panel (`activeChatId`) happens to be deleted, clear `activeChatId` / packet cache and refresh the chat switcher list after deletion (ADR 0009 §8).
4. **Step 3 — Two-click confirmation & execution:**
   - Button: **`선택한 N개 대화 삭제 / Delete N selected`** (disabled when 0 selected).
   - First click arms the button in red (`danger`) with a clear summary: *"N개 대화(메시지 약 M건)를 영구 삭제합니다. 복구할 수 없습니다."* — and if any selected conversation is a carry source, adds an extra red/amber line: *"⚠ K개 활성 채팅의 이어받은 기억 링크도 함께 삭제됩니다."*
   - Second click sends `POST /v1/conversations/delete-batch`, forgets cached packets (ADR 0009 §8), refreshes `knownChats` / Home meta, and shows the deleted totals. Changing any checkbox disarms the confirmation button immediately.
   - The standalone browser Inspector stays read-only (ADR 0009 §7).

### S5. What it does not change

- Database schema (0 migrations), `migrations/0012` delete guard trigger, `ledger.delete_conversation` internals.
- Extraction, embedding, canon, summary, or packet policies/generations.
- Request path (`beforeRequest`, `output` listener) — zero added latency or calls.
- Single-conversation delete (`POST /v1/conversations/{id}/delete`) and archive export/restore.

---

## Out of scope

- Automatic or scheduled deletion of missing chats (violates Invariant 1 / ADR 0009 and H22 Trash ambiguity).
- Reading PocketRisu's `nodeOnlyArchivedCharacters` (not exposed by PocketRisu V3 API, H22).
- Recording PocketRisu install/instance identity on conversations (would need a migration and host/plugin identity design).
- Detaching/freezing `conversation_carry` snapshots to survive source deletion (separate ADR 0085 amendment if ever wanted).
- Deleting individual messages or non-orphan chats from this screen (existing single-chat Delete handles live chats).

---

## Open owner decisions

| # | Question | Proposed default | Alternative |
|---|---|---|---|
| Q1 | **Initial checkbox state & "Select all" behavior** | **(a)** After scan, **all unchecked** by default (safest against Trash/multi-install accidents). Clicking **Select all** toggles **all** candidates in the list (including carry-warned ones); if any carry-warned row is checked, a prominent banner above the Delete button lists which active chats will lose carried memory. | **(b)** After scan, safe orphans (no active `carried_by`) start checked and carry-warned ones start unchecked; Select all toggles safe rows unless carry-warned rows are explicitly checked. |
| Q2 | **Include conversations with `head_commit_id IS NULL` (aborted/empty sync stubs)?** | **(a) Yes**, include them in the orphan preview (labeled `메시지 0`), so dead stubs can be cleaned up too. | **(b) No**, match `list_conversations` (`head_commit_id IS NOT NULL`) only. |
| Q3 | **Empty host result (`characters` has 0 chats total)** | **(a) Block scan** with an explicit warning and no checkboxes, so a host DB change or fresh/unloaded state can never mass-delete everything. | **(b)** Allow deleting with an extra warning. |
| Q4 | **Scope / timing relative to 1.0 quiet weeks** | **(a) Build on a feature branch / PR now** (no DB migration, no generation/packet change; high risk for bulk deletion, zero-call tests + isolated host check). Deploy timing stays owner's choice. | **(b)** Hold implementation until after the 2026-12-09 quiet-weeks window. |

---

## Acceptance criteria

1. **Zero-call sidecar tests (`apps/sidecar/tests/test_orphan_delete.py`):**
   - `POST /v1/conversations/orphans/preview` finds orphans beyond the 200-row `list_conversations` cap, excludes conversations matching `active_chat_refs`, scopes strictly to the requested `host`, reports accurate `messages`, `carried_by` (active `removed_at IS NULL` links only, ignoring removed links), and `branch_children`.
   - `POST /v1/conversations/delete-batch` deletes every requested conversation via `delete_conversation` (all tables cleaned, `source_revision` trigger still refuses raw `DELETE` outside the transaction), leaves unselected conversations untouched, handles concurrent `not_found` gracefully, rejects empty/oversized/malformed lists with 422, and enforces `Depends(auth)`.
   - Deleting an origin conversation with `branch_inherit` leaves the branch's inherited rows intact; deleting a `conversation_carry` source deletes the carry link and counts it in `totals.carry_links`.
2. **Plugin unit & DOM tests (`adapters/pocketrisu-plugin/test/`):**
   - `hostChatIds()` handles normal characters/chats, empty/placeholder chats, duplicate IDs, `null` (denied), missing API (`unsupported`), and malformed shapes (`invalid`) without ever returning an empty `ok: true` on denial/error.
   - Panel UI tests verify: scan flow, 0-orphan state, empty-host block (Q3), checkbox selection, **Select all** checked / unchecked / indeterminate sync, carry-warning badge rendered while checkbox stays selectable, checkbox edit disarms armed delete button, two-click confirmation text (with carry warning count when applicable), packet cache invalidation (`onAction`), and chat list refresh.
   - `npm test`, `npm run typecheck`, `npm run build` pass.
3. **Host check (isolated PocketRisu or owner's test install 6113):**
   - Scan lists a genuinely deleted chat, warns on a carry-source chat, leaves live chats untouched, and bulk-deletes selected rows cleanly; a trashed character's chat is visibly shown in preview and NOT deleted when left unchecked.
4. **Scoped high-risk self-review (`AGENTS.md §14`):** explicitly verifies deletion guard, permission-denied fail-closed path, carry-link warning accuracy, and zero request-path impact.

---

## Implementation steps (after owner approval)

1. Owner answers Q1–Q4 and approves Phase 68.
2. Sidecar: read-only preview helper + `POST /v1/conversations/orphans/preview` + `POST /v1/conversations/delete-batch` + pytest suite.
3. Plugin: `hostChatIds()` in `host.ts` + Settings → Backup orphan cleanup card in `ui.ts` + `i18n.ts` strings (ko/en) + vitest/DOM tests + dist build.
4. Scoped high-risk self-review, full test suites, docs/STATUS update, PR.
