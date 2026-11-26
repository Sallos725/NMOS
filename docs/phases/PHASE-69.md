# Phase 69 — Memory Explorer, Focused Attention & Dashboard Home (UI/UX Overhaul)

Status: **approved**, 2026-11-26 (owner approved Q1–Q3 as recommended `(a)` on 2026-11-26: default `요약` with `탐색 · 수정` beside it, keep `원본 인스펙터` under `진단`, include Phase 68 + Phase 69 in `0.7.0`). Not a roadmap stage.

**Not high risk** (`AGENTS.md §14`): pure presentation layer (new read-only sidecar HTML view fragments + plugin shell layout, client-side filtering, and styling).
- **No database migration, no storage/ledger write path change, no extractor/embedding/canon generation change, no packet/recall change, no request-path change.**
- **Sanitizer boundary preserved**: every new fragment uses `safeFragment`'s strict tag allowlist (`div`, `p`, `h1`, `h2`, `span`, `b`, `br`, `a`, `details`, `summary`) with no inline scripts or styles; all mutations continue through existing repair, entity-link, and settings APIs.

---

## Why

A critical review of the post-Phase-59 / post-`#345` panel (`views.py`, `inspector.py`, `ui.ts`) revealed four structural UX problems matching the owner's day-to-day friction ("still hard to find what is where", "`자세히` holds the real essence yet is hard to read"):

1. **Split-brain dual UI (`views.py` vs `inspector.py`).** `스토리 문서` (`views.py`) is clean and legible but caps sections to 3 items and is mostly read-only; meanwhile 85 % of NMOS's actual value (all facts, inline repairs, adding facts, locking, secrets, beliefs/forgettings/disguises, items, canon, alias joining/splitting, source-turn inspection) lives inside `자세히` (`inspector.py`), hidden behind a tiny muted footer link (`v-foot`) or 3 clicks deep under `기억 → 원본 · 진단 → 원본 인스펙터`.
2. **`자세히` is a 23-section developer DB dump.** `inspector.detail()` stacks up to 23 `<details>` sections (16 open by default) with a flat 20-link `.toc` wall and 6–10 column HTML tables (`canon` 9 cols, `retrievals` 10 cols, `members` 7 cols) that force horizontal scrolling, crush Korean prose, and jam repair inputs/buttons (`span.rp`) inline inside table cells.
3. **Navigation duplication and 5-layer nesting.**
   - **Home** repeats 6–8 destination tiles (`기억`, `기억 지도`, `작가의 노트`, `설정`, `백업`, `다른 채팅`) that already sit permanently in the Phase 59 top bar and chat switcher.
   - Clicking **`기억 → 확인 필요`** loads the entire 23-section raw Inspector scrolled to `#s-attention` instead of a dedicated triage workspace.
   - **`기억 → 원본 · 진단`** hides a 3rd-level toggle (`처리 상태 | 모델 호출 | 원본 인스펙터`), creating up to 5 layers of hierarchy (`Top tab → Memory sub-tab → Diag toggle → 20-link TOC → <details>`).
4. **Mixed concerns and terminology drift.** Story memory, owner curation, and system debug logs sit interleaved on one page, and the UI switches voices between plain Korean (`열린 일`, `사람들`, `직접 고침`) and internal developer terms (`스레드`, `엔티티`, `수리`, `원전`, `단언`, `양태`, `헤드`, `커밋`).

---

## What it does

### S1. Memory Explorer (`GET /v1/views/c/{id}/explore` & `/views/c/{id}/explore`)

Promotes the core reading & editing power of `자세히` into a dedicated, card-based workspace designed for both desktop panels and narrow mobile screens (no multi-column horizontal-scroll tables):
- **Structured categories** (tagged with `data-cat` for instant client-side switching without re-fetching):
  - **사실 (`facts`)**: current narrated facts with subject/predicate/value, turn link (`/inspector/c/{id}/t/{turn}`), source badge (`설정`, `직접 수정`, `이어받음`, `고정됨`), `because`, `when_happened`, and conditional slot badges (`[공적인 자리]`/`[사적인 자리]`/`[상황]`). Setting-only (canon) facts are marked with `data-canon="1"` and toggleable via a clean filter chip so story facts stay front and center. Header offers a direct **`+ 사실 추가`** button (reusing Phase 67 `fact_add`).
  - **관계 · 호칭 (`pairs`)**: pair cards showing relationship, role, feeling dot/strength/underneath, and conditional forms of address.
  - **약속 · 목표 (`threads`)**: open and closed threads with kind tags, horizon pills (`이번 장면`/`이야기 줄기`/`오래 감`), and direct close/reopen actions.
  - **비밀 · 믿음 · 망각 (`epistemic`)**: open/revealed secrets (holders, kept_from, turn), character beliefs (`believes`), forgettings (`forgot`), disguises, and who-told-whom chains (`told`).
  - **아이템 (`items`)**: current holder/location/destroyed state with an expandable concise history line.
  - **인물 · 대상 (`entities`)**: compact entity directory with type badge, aliases, mention count, pin badge, excluded badge, and one-tap jump to the upgraded Person Sheet.
  - **카드 · 로어북 설정 (`canon`)**: card, lorebook, persona, and author's note entries rendered as stacked cards (source badge, title/key, char count, read status, short preview) instead of a 9-column table.
- **Instant client-side filter bar** in the plugin (reusing `doc-search-bar` & `filter-chips` patterns):
  - Category pills (`전체`, `사실`, `관계 · 호칭`, `약속 · 목표`, `비밀 · 믿음`, `아이템`, `인물 · 대상`, `카드 · 로어북`) with live item counts.
  - Text search input (filters cards instantly across visible categories).
  - Character filter dropdown (`전체 인물` + cast list, filtering cards via `data-who`).
  - Toggle chip: `설정(카드·로어북) 포함` (default off on `facts` when story facts exist, or clearly separated, so lorebooks never bury the story).
- **Clean inline editing (no cluttered table-cell inputs)**:
  - Each editable card carries the existing `data-rp` repair markers inside a tidy, expandable **`수정`** action drawer (`<details class="v-edit">`) or compact footer row, wired to the existing `ui.ts` repair handlers + preview + undo toast.

### S2. Dedicated Attention & Repairs View (`GET /v1/views/c/{id}/attention` & `/views/c/{id}/attention`)

Replaces the jarring `#s-attention` jump into the 23-section raw Inspector:
- Clicking **`기억 → 확인 필요`** renders a focused 3-section curation screen:
  1. **확인이 필요한 항목 (Needs attention)**: card rows with existing Phase 57 bulk-select checkboxes, category filter chips, and bulk apply/dismiss controls.
  2. **충돌 (Conflicts)**: story-vs-story, canon-vs-story, and lock-vs-story cards with clear old/new comparison and direct resolution buttons (`원전 고정`, `이야기 유지`, `정정`).
  3. **내가 직접 수정한 기록 (Direct edits / Repairs)**: active and taken-back repairs rendered as clean cards with one-click Undo (with preview where applicable).
- Shows a crisp empty state (`확인할 항목이 없습니다`) when the queue is clear, without dumping 20 unrelated debug tables underneath.

### S3. Upgraded Person Sheet (`/v1/views/c/{id}/person/{eid}`)

Makes the Person Sheet self-sufficient so users no longer need to fall through a tiny footer `자세히` link to `/inspector/c/{id}/e/{eid}` for routine character management:
- **Header & character controls** (wired by `ui.ts` from existing APIs):
  - Character name, aliases, and quick character switcher dropdown.
  - Inline **항상 기억에 고정 (`entity_pin`)** toggle.
  - Inline **이름 합치기 / 분리 (`entity-links` / `name_split`)** section with existing Phase 20 preview modal/panel.
  - Inline **캐릭터 아님 (`entity_exclude`)** action (with undo note when excluded).
- **Complete character sections** in card format:
  - Current status (`지금`), relationships/feelings/addresses, **editable facts about them** (with inline `수정` drawer and source-turn links), held items, promises/goals, knows & hidden-from secrets, beliefs/forgettings/disguises, who-told-whom, carried lines, and timeline.
- Quiet footer link to `/inspector/c/{id}/e/{eid}` stays available only as *"원본 인스펙터에서 보기"* (if Q2 a).

### S4. Flattened Navigation & Real Dashboard Home

1. **Flattened `기억` (Memory) sub-tabs** — 5 clear, single-purpose siblings:
   - **`요약`** (`story`: `/v1/views/c/{id}/memory`) — quick narrative overview (now, open threads, story so far, changed from setting, carried memory) with direct links to `탐색 · 수정` and Person Sheets.
   - **`탐색 · 수정`** (`explore`: `/v1/views/c/{id}/explore`) — promoted card-based Memory Explorer (S1).
   - **`확인 필요`** (`attention`: `/v1/views/c/{id}/attention`, badge) — dedicated triage & repairs workspace (S2).
   - **`관계도`** (`map`: `/v1/views/c/{id}/map`) — existing interactive graph + side drawer.
   - **`진단`** (`diag`: `처리 상태` `/working` | `모델 호출` `/calls` | `원본 인스펙터` `/inspector/c/{id}`) — explicitly scoped to troubleshooting, last packet ledger, coverage, model calls, and raw DB inspection.
2. **Real Dashboard Home (`/v1/views/hub?compact=1` inside the Phase 59 shell)**:
   - Removes the duplicate navigation tiles (`기억`, `기억 지도`, `작가의 노트`, `설정`, `백업`, `다른 채팅`) that already live permanently in the top bar / chat switcher.
   - Focuses Home on **live status & immediate context for the active chat**:
     - `homeQuickBar`: current chat ON/OFF strip, urgent advisories, live worker progress card (`#345`).
     - **처리 및 상태 카드**: working state, extraction/embedding progress bars, model call count.
     - **확인 필요 알림 배너** (only when `attention > 0` → opens dedicated `확인 필요` tab directly).
     - **방금 답장에 들어간 기억** (compact snapshot of the latest reply: placed lines, tokens, latency, expandable line preview → link to `진단` for full packet ledger).
     - **지금 장면 & 열린 일 미리보기** (compact current-scene chips + top open threads → direct button to `요약` or `탐색 · 수정`).
   - **Backward compatibility**: `/v1/views/hub` without `compact=1` (older plugins) and browser `/views/hub` preserve their existing layout.

### S5. Unified Plain-Korean Terminology

Standardize user-facing labels across `views.py`, `i18n.ts`, and `ui.ts` (Korean & English):
| Internal / Old Inspector term | Unified Korean UI label | Unified English UI label |
|---|---|---|
| 스레드 / 열린 일 | 약속 · 목표 (요약: 열린 일) | Promises & goals (Open threads) |
| 엔티티 / 사람들 | 인물 · 대상 | People & entities |
| 수리 / 직접 고침 | 직접 수정 | Direct edits |
| 원전 / 설정 | 카드 · 로어북 설정 | Card & lorebook setting |
| 원본 인스펙터 / 자세히 | 탐색 · 수정 *(일상)* / 원본 인스펙터 *(진단 전용)* | Explore & edit *(daily)* / Raw inspector *(diagnostics)* |

Internal technical terms (`커밋`, `헤드`, `양태`, `단언`, predicate keys) remain only inside `진단 → 원본 인스펙터` (and hover tooltips) where exact ledger terms are needed.

### S6. Backward Compatibility & Graceful Degradation

- All existing routes (`/v1/inspector*`, `/inspector*`, `/v1/views/hub`, `/v1/views/c/{id}/memory`, `/map`, `/working`, `/person/{eid}`) continue to work with zero breaking changes.
- Plugin gracefully falls back to `/v1/inspector/c/{id}` if connected to an older sidecar returning HTTP 404 on `/v1/views/c/{id}/explore` or `/attention`.
- `safeFragment` in `inspector.ts` adds only safe read-only data attributes (`data-cat`, `data-who`, `data-canon`) for client-side filtering — no new HTML tags, no inline styles, no scripts.

---

## Out of scope

- Any DB migration, extraction/embedding/canon generation change, packet/recall change, or new repair kind.
- Replacing or deleting `/inspector/*` (standalone browser Inspector remains intact and read-only).
- Rewriting Author's Note Studio (`notes`) or Settings 2-column architecture (already well-structured from Phase 59 / `#345`).
- Changing PocketRisu's host DOM outside the plugin iframe or HUD.

---

## Owner decisions (resolved 2026-11-26)

| # | Question | Decision |
|---|---|---|
| Q1 | **Default sub-tab when opening `기억` (Memory)** | **(a) `요약` (`story`)** first, with **`탐색 · 수정` (`explore`)** right beside it as the 2nd tab (and remembering the last sub-tab visited in the session). |
| Q2 | **Keep Raw Inspector in the panel under `진단`?** | **(a) Yes**, keep `진단 → 원본 인스펙터` (and browser `/inspector`) intact. |
| Q3 | **Include in `0.7.0` release?** | **(a) Yes**, ship Phase 68 + Phase 69 together in `0.7.0` after live desktop/mobile visual verification on 6113. |

---

## Acceptance criteria

1. **Sidecar tests (`apps/sidecar/tests/test_phase69_views.py`):**
   - `GET /v1/views/c/{id}/explore` (and `/views/c/{id}/explore`) returns valid HTML with all populated categories (`facts`, `pairs`, `threads`, `epistemic`, `items`, `entities`, `canon`), safe escaping (XSS payloads escaped), `data-cat`/`data-who`/`data-canon` attributes, existing repair markers (`data-rp`/`data-act`), and zero `<table>` elements.
   - `GET /v1/views/c/{id}/attention` (and `/views/c/{id}/attention`) renders only attention queue (with bulk markers), conflicts, and repairs — never unrelated debug tables — plus clean empty state.
   - `GET /v1/views/c/{id}/person/{eid}` renders editable character facts, items, epistemic sections, and pin/link/exclude hook containers cleanly.
   - `GET /v1/views/hub?compact=1` omits duplicate nav tiles (`기억`, `작가의 노트`, `설정`, `백업`, `다른 채팅`) and includes latest-reply memory summary + attention/progress; `/v1/views/hub` without `compact=1` remains backward-compatible.
2. **Plugin unit & DOM tests (`adapters/pocketrisu-plugin/test/phase69-ui.test.ts`):**
   - `safeFragment` preserves `data-cat`/`data-who`/`data-canon` while still stripping scripts, event handlers, inline styles, and unsafe URLs.
   - Memory sub-tab bar renders the 5 flattened tabs (`요약`, `탐색 · 수정`, `확인 필요`, `관계도`, `진단`), routes `확인 필요` to `/v1/views/c/{id}/attention`, and falls back to `/v1/inspector/c/{id}` on 404 from an older sidecar.
   - Explorer client-side filter bar filters cards accurately by category pill, search text, character dropdown, and setting-only toggle; inline repair drawer triggers repair API + undo toast.
   - Upgraded Person Sheet wires pin toggle, entity link join/split preview, and fact repairs directly.
   - `npm test`, `npm run typecheck`, `npm run build` pass.
3. **Live visual check (desktop + mobile viewport on 6113 / isolated PocketRisu):**
   - Zero horizontal table overflow on 390 px mobile width across Home, 요약, 탐색 · 수정, 확인 필요, and Person Sheet.
   - Owner reviews the revamped screens and approves before merging/releasing `0.7.0`.

---

## Verification (2026-11-26, zero-call)

- **Plugin (`23eb675c99b3`)**: `npm test` **40 files / 578 passed** (including 6 new tests in `adapters/pocketrisu-plugin/test/phase69-ui.test.ts`), `npm run typecheck`, `npm run build`.
- **Sidecar (`NMOS_TEST_REQUIRE_DB=1`)**: **110 passed / 0 failed** across `test_phase69_views.py` (7), `test_views.py` (32), `test_memorymap.py` (19), `test_phase60_views_unchanged.py` (3 byte-identical golden checks), `test_phase60_carry_views.py` (2), `test_phase60_carry_data.py` (4), `test_phase60_happened_views.py` (10), `test_phase60_told_views.py` (13), `test_tier3_inspector_ontology.py` (16), `test_docs_consistency.py` (2), and `test_plugin_build.py` (2).
- **Security & self-review**: zero `innerHTML`/`outerHTML`/`eval` sinks added in plugin source; every chat value HTML-escaped via `_v(...)` (tested with XSS payloads across Explorer, Attention, and Compact Home); `safeFragment` allowlist adds only strict read-only data attributes (`data-cat`, `data-who`, `data-canon`); every `views.STYLE` selector remains scoped under `.nmos` with no `@import`/`url(`. Scoped review fixed unused imports, double space in `with` metadata, clickable source-turn links in Attention cards, and hiding `factAddCard` when leaving Explorer.
- **Open**: live visual check on isolated PocketRisu / 6113 test install (desktop + 390 px mobile viewport) before merging and cutting `0.7.0`.

## Implementation steps

1. ~~Owner answers Q1–Q3 and approves Phase 69.~~ *(done 2026-11-26: Q1–Q3 `(a)`)*
2. ~~Sidecar: add `explore()`, `attention()`, upgraded `person(rich=True)`, `memory(rich=True)`, and `hub(compact=True)` in `views.py` + routes in `api.py` + sidecar tests.~~ *(done 2026-11-26)*
3. ~~Plugin: update `safeFragment` allowlist (`data-cat`/`data-who`/`data-canon`), add Explorer filter bar & inline edit drawer wiring, flatten Memory sub-tabs, wire upgraded Person Sheet controls (pin + links staying in views), switch Home hub to `compact=1`, unify `i18n.ts` labels, add DOM tests + build dist (`23eb675c99b3`).~~ *(done 2026-11-26)*
4. Scoped self-review and automated suites complete; live desktop/mobile visual verification on 6113 open before `0.7.0` release prep.
