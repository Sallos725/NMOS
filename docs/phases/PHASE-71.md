# Phase 71 — Action Button vs. Metadata Tag Clarity & Raw Inspector Grouping (UI Polish)

Status: **approved**, 2026-11-26 (owner requested drafting and implementing all three visual-clarity items from `0.6.0` user feedback). Not a roadmap stage.

**Not high risk** (`AGENTS.md §14`): pure presentation & client-side DOM styling layer (`adapters/pocketrisu-plugin/src/ui.ts`, `adapters/pocketrisu-plugin/src/icons.ts`, and `apps/sidecar/src/nmos_sidecar/views.py` `STYLE` only).
- **No database migration, no storage/ledger/repair API change, no extractor/embedding/canon/packet/recall change, no sanitizer allowlist change, and zero HTML markup changes in `inspector.py` or default `views.memory`/`views.person`** (all Phase 60 and Tier 3 Wave 4 golden files stay byte-identical).

---

## Why

User feedback from `0.6.0` highlighted a core affordance failure on the facts screen:

> "`사실` 탭에 온갖 내용이 들어가있는데, UI가 직관성이 너무 떨어지는 것 같아… 박스 형태의 버튼들(철회, 정정 등)이랑 단순 텍스트(사소, 공개, 사건, 위치 등)랑 어떤 게 버튼인지 구분이 안감."

While Phase 69/70 structurally moved daily curation into the card-based Memory Explorer (`탐색 · 수정`), three visual-affordance gaps remain on `main`:

1. **Weak button vs. passive chip contrast**: Every repair button (`철회`, `정정`, `고정`, `숨기기`, `되돌리기`) renders with only `button.mini` (neutral gray `var(--c-raised)`), visually close to passive metadata pills (`.chip` / `.v-tag` for `사소`, `공개`, `사건`, `위치`). Even destructive actions (`철회`, `캐릭터 아님`, `무시`) carry no danger tint or icon.
2. **Low-affordance `수정` disclosure toggle on Explorer & Person Sheet cards**: `<details class="v-edit"><summary>수정</summary>` renders as muted borderless text (`list-style: none`, no chevron or button outline), making it hard to spot as an interactive control before hovering.
3. **Inline mixing of metadata chips and repair buttons in Raw Inspector tables (`진단 → 원본 인스펙터`)**: Inside `#s-facts` and other raw tables, `span.rp` action buttons sit inline right beside fact text and `.chip` labels in the same `<td>` without visual separation.

---

## What it does

### S1. Semantic Repair Buttons with Inline SVG Icons (`ui.ts`, `icons.ts`)

- Classify every repair button in `repairControls()` and `closeControls()` by intent (preserving the `mini` class and exact `textContent` for compatibility):
  - **Destructive / retract (`mini rp-btn rp-danger`)**: `fact_retract`, `told_retract`, `entity_exclude`, `state_dismiss`, `attention_dismiss` — red-tinted surface, border, and high-contrast rose text with subtle elevation shadow and `close` icon.
  - **Modify / action (`mini rp-btn rp-act`)**: `fact_correct`, `fact_lock`, `fact_restore`, `fact_hidden`, `entity_note`, `secret_found_out`, `secret_keep`, `alias_join`, `branch_inherit`, `thread_reopen`, `fact_add`, and `thread_close` buttons — accent/indigo-tinted interactive surface, border, crisp light text, subtle elevation shadow, and action icon (`edit`, `lock`, `eyeOff`, `undo`, `check`).
  - **Undo (`mini rp-btn rp-undo`)**: `undo`, `undo_batch` — warm amber-tinted surface, border, and `undo` icon.
- Inline `correctForm` and `hiddenForm` Save buttons use `mini primary` (matching `noteForm`) so primary commit vs. cancel is unmistakable.
- Add 4 lightweight stroke-only SVG icons (`edit`, `lock`, `undo`, `eyeOff`) to `icons.ts` built via `document.createElementNS` (`aria-hidden="true"`, zero `innerHTML`).

### S2. Unmistakably Passive Metadata Chips & Tags (`ui.ts`, `views.py` `STYLE`)

- Soften `.nmos .insp .chip` and `.nmos .v .chip` into recessed, flat, non-interactive pills (`border-radius: 999px`, muted translucent tint, low-contrast hairline border, `cursor: default`, `user-select: text`, no shadow or hover lift).
- Soften default `.nmos .v-tag` in `views.STYLE` to match the same clearly non-clickable passive pill style (`cursor: default`, `user-select: text`), creating sharp contrast against elevated, rounded-rectangle (`6px`), color-tinted `.rp-btn` action buttons.

### S3. Interactive `수정` Disclosure Button on Cards (`views.py` `STYLE`)

- Style `.nmos .v-edit > summary` as a compact disclosure button (`padding: 4px 10px`, `border-radius: 7px`, `background: var(--c-raised)`, `border: 1px solid var(--c-line-strong)`, subtle shadow) with a `▸` / `▾` chevron (`::before`) and clear accent hover / `[open]` highlight.

### S4. Dedicated Action Row Grouping in Raw Inspector Tables (`ui.ts` `placeMarks()`)

- In `placeMarks()`, after populating `span.rp[data-repair]` (and injecting `#s-facts` `fact_hidden`), group populated direct-child `span.rp` elements inside `<td>` cells into a dedicated `<div class="rp-bar">` row at the bottom of the cell (`rp-bar has-sep` with a subtle dashed top divider when the cell also contains text/chips/links).
- Leaves `span.rq[data-bulk]` checkboxes in place, leaves unparsed/dropped empty `span.rp` untouched, and requires **zero** HTML changes in `inspector.py` so every golden snapshot stays byte-identical.

---

## Out of scope

- Any DB migration, repair API change, packet/recall change, or sanitizer allowlist change.
- Modifying `inspector.py` HTML markup or browser-only Inspector rendering (golden-protected).
- Reworking Memory Explorer category structure or adding new repair kinds.

---

## Security & Verification Plan

- **XSS & DOM safety**: zero `innerHTML` / `outerHTML` / `eval` sinks; all new icons use `document.createElementNS` with static hardcoded SVG path descriptors; `placeMarks()` moves only existing sanitized `span.rp` nodes inside `<td>` without parsing raw strings.
- **CSS isolation**: every rule added to `views.STYLE` starts with `.nmos` with zero `@import` or `url(`.
- **Acceptance criteria**:
  1. **Plugin unit & DOM tests (`adapters/pocketrisu-plugin/test/phase71-ui.test.ts`)**:
     - `repairControls` assigns `rp-danger` (`fact_retract`, `told_retract`, `entity_exclude`, `attention_dismiss`), `rp-act` (`fact_correct`, `fact_lock`, `fact_hidden`, `entity_note`, `thread_close`), and `rp-undo` (`undo`, `undo_batch`), attaches decorative `svg.ic` (`aria-hidden="true"`), and preserves exact button `textContent`.
     - `placeMarks` groups populated `span.rp` inside Raw Inspector `<td>` cells into `.rp-bar.has-sep` when paired with text/chips (including injected `#s-facts` `fact_hidden`), omits `.has-sep` when the cell holds only actions, and leaves empty dropped `span.rp` and `span.rq` checkboxes untouched.
     - `npm test`, `npm run typecheck`, `npm run build` pass.
  2. **Sidecar tests (`NMOS_TEST_REQUIRE_DB=1`)**:
     - `test_phase69_views.py` (including `test_views_style_stays_strictly_scoped_under_nmos`), `test_views.py`, `test_phase60_views_unchanged.py` (golden byte-identity), `test_tier3_inspector_ontology.py` (golden byte-identity), `test_docs_consistency.py`, and `test_plugin_build.py` all pass.

---

## Implementation steps

1. ~~Write `PHASE-71.md` and update `AGENTS.md` / `docs/STATUS.md` pointers.~~ *(done 2026-11-26)*
2. ~~Add `edit`, `lock`, `undo`, `eyeOff` SVG shapes to `adapters/pocketrisu-plugin/src/icons.ts`.~~ *(done 2026-11-26)*
3. ~~Update `adapters/pocketrisu-plugin/src/ui.ts` (CSS for `.chip`, `.rp-btn.*`, `.rp-bar`, semantic `repairControls` / `closeControls` / inline forms, and `placeMarks` `<td>` `.rp-bar` grouping).~~ *(done 2026-11-26)*
4. ~~Update `apps/sidecar/src/nmos_sidecar/views.py` `STYLE` (passive `.v-tag` / `.v .chip` contrast and `.v-edit > summary` disclosure button with chevron).~~ *(done 2026-11-26)*
5. ~~Add `adapters/pocketrisu-plugin/test/phase71-ui.test.ts` and sidecar style assertions; run plugin + sidecar test suites, typecheck, and plugin build; record verification results.~~ *(done 2026-11-26)*

---

## Verification (2026-11-26, zero-call)

- **Plugin (`8b0220b23b4e`)**: `npm test` **42 files / 588 passed** (including 3 new tests in `adapters/pocketrisu-plugin/test/phase71-ui.test.ts`), `npm run typecheck`, `npm run build`.
- **Sidecar**: **87 passed / 0 failed** across `test_docs_consistency.py` (2), `test_plugin_build.py` (2), `test_phase69_views.py` (8, including `test_views_style_stays_strictly_scoped_under_nmos` and `test_phase71_views_style_passive_tags_and_edit_disclosure`), `test_views.py` (32), `test_phase60_views_unchanged.py` (3 golden byte-identical), `test_tier3_inspector_ontology.py` (16 golden byte-identical), and `test_inspector.py` (24).
- **Scoped self-review**: zero `innerHTML`/`outerHTML`/`eval` sinks; all new icons built via `createElementNS` (`aria-hidden="true"`); caught Python string escape (`\25B8` → `\\25B8`) in `views.STYLE` and added regression assertion; aligned `.v-edit-body` / `.v-card-acts` `span.rp` left margin to `0`.
- **Open**: live visual check in PocketRisu (desktop + mobile viewport) on Memory Explorer and Raw Inspector before merging.
