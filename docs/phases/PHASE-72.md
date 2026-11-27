# Phase 72 — Inspector Section Tabs, Floating Back-to-Top Button & Sticky Explorer Toolbar (UI Polish)

Status: **approved**, 2026-11-28 (owner selected Option 3 + both plugin panel and standalone browser Inspector/Views, with Phase 72 golden baseline update for browser `page()` chrome; PR to `main`, no tag yet). Not a roadmap stage.

**Not high risk** (`AGENTS.md §14`): pure presentation & client-side DOM navigation layer (`apps/sidecar/src/nmos_sidecar/tokens.py`, `inspector.py` `STYLE`/`page()`, `views.py` `full_page()`/`PLACE`, and `adapters/pocketrisu-plugin/src/ui.ts`, `icons.ts`, `i18n.ts`).
- **No database migration, no storage/ledger/repair API change, no extractor/embedding/canon/packet/recall change, no sanitizer allowlist change, and zero HTML changes in embedded fragments** (`embed=True` Inspector bodies, `views.memory`, `views.person`, `views.explore` remain byte-identical).
- Only standalone browser `inspector.page()` chrome (`<style>`, floating `.nm-top` button, and static `<script data-nmos-nav="1">` progressive enhancement) changes in the browser-page golden snapshots (`api-inspector-chat.{ko,en}.html`, `tier3-w4/{stub-chat,v20-chat}.txt`); `<main>...</main>` stays 100% byte-identical.

---

## Why

Immediate user feedback right after `v0.7.0`:

> "인스펙터에서 top 버튼같은 거 하나 띄워줄 수 있을까? 아니면 탭단위로 보여준다던가. 턴 길어지면 아래에서 한참 올라가야해서 불편해"

On long chats, two navigation friction points compound each other:

1. **No quick return to top**: Neither the plugin panel (`.nmos` scroll container) nor standalone browser pages (`/inspector/*`, `/views/*`) provide a floating Back-to-Top button.
2. **All Raw Inspector sections stacked vertically at once**: `inspector.detail()` opens most `<details id="s-...">` sections by default (`state`, `coverage`, `conflicts`, `threads`, `pairs`, `facts`, `items`, `entities`, `claims`, `packet`, etc.). Switching sections on a long conversation forces long vertical scrolling; likewise, in Memory Explorer (`/explore`), scrolling down moves the category/search toolbar off-screen.

---

## What it does

### S1. Floating Back-to-Top Button (Panel + Browser `/inspector/*` + Browser `/views/*`)

- **Plugin (`ui.ts`, `icons.ts`, `i18n.ts`)**:
  - Adds stroke-only `arrowUp` SVG icon (`document.createElementNS`, `aria-hidden="true"`).
  - Mounts a fixed bottom-right floating `.nmos-top-btn` button inside `#nmos-panel` (`Top`, localized `aria-label`/`title` via `nav.top`).
  - Appears smoothly once `root.scrollTop > 280` (`.show`), hides when scrolled back near top or after tab/page resets, and scrolls smoothly to `top: 0` on click.
  - On mobile (`<= 720px`), sits above `.nmos-bottomnav` (`bottom: calc(70px + env(safe-area-inset-bottom))`) so it never overlaps bottom navigation.
- **Standalone Browser (`tokens.py`, `inspector.py`, `views.py`)**:
  - Shared `tokens.browser_top_button(lang)` and `.nm-top` CSS in `tokens.BROWSER_BAR_STYLE` for both `inspector.page()` and `views.full_page()`, toggled on `window.scrollY > 280`.

### S2. Raw Inspector Section Tabs with Show-All Toggle (Panel + Browser `/inspector/*`)

- Whenever a Raw Inspector page renders `p.toc` alongside `>= 2` `<details id="s-...">` sections:
  - Progressive client-side enhancement turns `p.toc` into a `.toc.insp-tabs` tab bar (`role="tablist"`, sticky below top chrome on desktop `> 720px`, static on mobile `<= 720px`) with a trailing **Show all / Tab view** toggle button (`.toc-all`, localized via `insp.tab_all` / `insp.tab_one`).
  - **Tab view (default)**: displays only the active section (`display: ''`, `open = true`) and hides the others (`display: 'none'`). Default active tab follows explicit hash/section target (`#s-...` or `#a-...` inside a section), then saved refresh state (`Place.tab` in panel), then the first initially-open section.
  - **Show all mode**: reveals every section (restoring default open flags plus the active section) so Ctrl+F full-page scanning remains one click away.
  - Clicking lazy sections (`#s-people`, `#s-status`) in the panel triggers timeline/status loading immediately; in-page hash jumps (such as Timeline `"아래 표에서 보기"` `#a-...` links in the browser) automatically switch to the containing section tab.
  - Preserves the active tab / Show-all mode across panel refreshes (e.g. after inline repairs) via `Place.tab`.

### S3. Sticky Memory Explorer Toolbar on Desktop & Browser Explorer Tabs (`ui.ts`, `views.py`)

- **Plugin (`/explore`)**: makes `.nmos.shell-on .exp-toolbar` sticky below `.nmos-topbar` on desktop (`> 720px`) and static on mobile (`<= 720px`, paired with the floating `Top` button so mobile viewport height stays open). Clicking a category chip while scrolled down (`root.scrollTop > 220`) smoothly scrolls back to top so the chosen category begins cleanly in view.
- **Standalone Browser (`/views/c/{id}/explore`)**: enhances `.v-exp-toolbar-slot` in `views.full_page()` (`PLACE`) with sticky desktop positioning, interactive category tabs (`전체`/`All` + per-category chips), and a live text search input—all built strictly with DOM APIs (`createElement`/`textContent`/`replaceChildren`, zero `innerHTML`).

---

## Out of scope

- Any DB migration, repair API change, packet/recall/generation change, or sanitizer allowlist change.
- Changing embedded HTML fragments (`embed=True`, `views.memory`, `views.person`, `views.explore`).
- Cutting a `v0.7.1` tag (this phase ships as a PR to `main` first).

---

## Security & Verification Plan

- **XSS & DOM safety**:
  - Zero `innerHTML`, `outerHTML`, `insertAdjacentHTML`, `document.write`, or `eval` sinks in both TypeScript (`ui.ts`) and standalone browser scripts (`inspector.PAGE_SCRIPT`, `views.PLACE`).
  - `icons.ts` `arrowUp` uses `document.createElementNS` with static path descriptors; `tokens.ARROW_UP_SVG` is a static literal; all dynamic labels use `escape()` server-side or `textContent` client-side.
  - Browser scripts (`<script data-nmos-nav="1">` and `views.PLACE`) are pure static JS literals with zero user/DB data interpolated into script text; localized labels are read from escaped `data-*` attributes.
  - Embedded fragments (`/v1/inspector/*`, `/v1/views/*`) continue to emit zero `<script>` tags.
- **CSS isolation**: every rule in `views.STYLE` remains strictly scoped under `.nmos` with zero `@import` or `url(`.
- **Golden integrity**: verify via diff that updated browser golden snapshots (`api-inspector-chat.{ko,en}.html`, `tier3-w4/{stub-chat,v20-chat}.txt`) change **only** browser `page()` chrome (`<style>`, `.nm-top`, `<script data-nmos-nav="1">`) with zero bytes altered inside `<main>...</main>` or any embedded fragment.
- **Acceptance criteria**:
  1. **Plugin tests (`adapters/pocketrisu-plugin/test/phase72-ui.test.ts`)**:
     - Floating `Top` button visibility toggle on `scrollTop > 280`, smooth scroll-to-top click, and mobile CSS positioning above `.nmos-bottomnav`.
     - Raw Inspector section tabs: default single-section tabbing, tab click switching, active tab preservation on refresh, `#s-...` focus activation, Show-all ↔ Tab-view toggle, and lazy timeline loading on tab switch.
     - Memory Explorer desktop sticky toolbar CSS, mobile static override, and scroll-to-top on category switch when scrolled down.
     - `npm test`, `npm run typecheck`, `npm run build` pass.
  2. **Sidecar tests (`NMOS_TEST_REQUIRE_DB=1`)**:
     - Browser `inspector.page()` and `views.full_page()` include `.nm-top` and navigation scripts, while `embed=True` and `/v1/views/*` JSON fragments remain script-free and unchanged.
     - `test_views.py`, `test_phase69_views.py`, `test_phase70_entity_notes.py`, `test_inspector.py`, `test_inspector_timeline.py`, `test_phase60_views_unchanged.py`, `test_tier3_inspector_ontology.py`, `test_docs_consistency.py`, and `test_plugin_build.py` all pass.

---

## Verification (2026-11-28, zero-call)

- **Plugin (`4c4e6fe3c78a`)**: `npm test` **43 files / 591 passed** (including 3 new tests in `adapters/pocketrisu-plugin/test/phase72-ui.test.ts`), `npm run typecheck`, `npm run build`.
- **Sidecar (`NMOS_TEST_REQUIRE_DB=1`)**: **127 passed / 0 failed** across `test_docs_consistency.py`, `test_plugin_build.py`, `test_views.py` (including `test_phase72_browser_top_button_inspector_tabs_and_explorer_toolbar`), `test_phase69_views.py`, `test_phase70_entity_notes.py`, `test_inspector.py`, `test_inspector_timeline.py`, `test_phase60_views_unchanged.py`, and `test_tier3_inspector_ontology.py`.
- **Golden integrity check**: programmatic diff check confirmed 0 bytes changed inside `<main>...</main>` across all browser HTML pages, 0 bytes changed in `memory.{ko,en}.html` / `person.{ko,en}.html` / `api-memory.{ko,en}.html` / `api-person.{ko,en}.html`, and 0 bytes changed across all 96 non-browser sections in `tier3-w4/{stub-chat,v20-chat}.txt`.
- **Scoped self-review (`AGENTS.md §14`)**: caught and fixed sticky tab-bar scroll-offset drift (using `secEl.getBoundingClientRect().top` relative to `toc.getBoundingClientRect().bottom` instead of `toc`'s stuck position in both `inspector.PAGE_SCRIPT` and `ui.ts`); verified zero `innerHTML`/`outerHTML`/`eval` sinks and strict `.nmos` scoping in `views.STYLE`.
- **Open**: live visual check in PocketRisu (desktop + mobile viewport) and standalone browser `/inspector` & `/views/c/{id}/explore`; no `v0.7.1` tag yet.
