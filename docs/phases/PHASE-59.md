# Phase 59 — Panel UI/UX overhaul: persistent shell, unified memory workspace, author's note studio, structured settings

Status: **approved**, 2026-11-21 (owner approved the 7-screen redesign mockup in conversation and directed full UI implementation). An owner request, not a roadmap stage. Builds on Phase 52 (the hub and memory screens) and Phase 55 (the memory map).

**Not high risk** (`AGENTS.md §14`):
- No schema or migration change.
- No extraction, recall, packet, or normalizer change.
- **Sanitizer boundary unchanged**: `safeFragment` and `keepAttribute` in `adapters/pocketrisu-plugin/src/inspector.ts` keep the exact same allowlist of tags and attributes; all interactive chrome and inline SVG icons are rendered by the plugin shell itself via DOM APIs, never from sidecar HTML.
- Backwards compatible with older sidecars that do not report `features.views` (legacy 3-tab UI remains intact) and with older sidecars that omit additive `meta` on `/v1/views/hub`.

## Why

Phase 52 replaced raw tables with a hub and document views, but real daily use exposed clear UX friction (owner feedback, 2026-11-21):
1. **Lost orientation & hidden navigation.** The top bar disappeared once `viewsOn` turned on, forcing users to hunt for `← 뒤로` or click the small title text to get home, with no way to switch chats from anywhere.
2. **Scattered related views.** Memory document, memory map, needs-attention queue, working status, and raw inspector lived behind separate hub tiles and footer links.
3. **Hidden actions and unclear cost/risk.** Thread repair controls were hidden behind invisible tap targets on lines; the author's note form appeared awkwardly inline above the hub without showing which sections invoke the LLM; per-chat ON/OFF and per-chat settings were split across Connection and This Chat.
4. **Flat visual hierarchy.** Uniform dark cards without icons, status badges, progress indicators, or semantic color tints made screens monotonous and harder to scan quickly.

## What it does

D1. **Persistent app shell (desktop top bar + mobile 4-tab bottom bar) & global chat switcher.**
- Desktop (`> 720px`): persistent top bar with Brand mark (Home), **Chat Switcher dropdown** (shows current chat · character · turn and lists all known chats with search to switch from anywhere), **4 primary tabs** (`홈`, `기억` with live attention count badge, `작가의 노트`, `설정`), live health status pill, language selector, and close.
- Mobile (`<= 720px`): compact top bar (brand, chat switcher, status dot, language, close) + fixed 4-tab bottom navigation bar with safe-area padding.
- `GET /v1/views/hub` adds an additive `meta` object (`conv`, `working`, `attention`, `chats`, `usage`) so the shell hydrates in zero extra requests.

D2. **Actionable Home Hub.**
- Elevated hero status card (last reply memory summary, inline status dot, direct jump to working/injected memory) + plugin-rendered **This Chat ON/OFF quick bar** for the currently open PocketRisu chat, plus urgent advisories (insecure context, deadline, budget, vector fallback).
- Prominent amber Needs-Attention banner when items need review.
- Memory snapshot card with Scene Now chips and Open Threads preview, dedicated Author's Note & Memory Map cards, and processing progress bars (using existing `data-l`/`data-w` marks placed by `placeMarks`).

D3. **Unified Memory Workspace with explicit actions.**
- Persistent sub-tab bar under `기억`: `스토리 문서` | `인물 · 관계도` (when `features.map`) | `확인 필요 (N)` | `원본 · 진단` (toggles between plain-language Working status and raw Inspector ledger), each with a 1-line purpose description.
- Desktop sticky left table of contents (`>= 860px`) / mobile horizontal jump pills on the Memory document.
- Semantic kind badges (`약속`, `목표`, `위협`, `질문`, `빚`), setting-change diff chips, Phase 58 feeling dots/detail, and **explicitly visible repair buttons** on `.v-line` items rather than invisible tap-only controls.

D4. **Dedicated Author's Note Studio.**
- Top-level `작가의 노트` tab (also opened by the hub's `data-act="notes"` block).
- 2-column split layout on desktop (stacked on mobile): section toggle cards with clear cost/verification badges (`모델 1회 호출`, `무료 · 즉시`, `미검증 · 모델 1회`), live estimated LLM call summary on the Generate button, Phase 56 custom prompt box, and right-hand preview pane with provenance summary and 1-click Copy.

D5. **Structured 2-Column Settings (This Chat vs Global).**
- Left sticky sidebar on desktop (categorized selector on mobile) explicitly separated into:
  - **이 채팅 전용 (`chat`)**: This Chat NMOS ON/OFF switch, Memory Mode (`strict`/`narrator`), Replies Only (`replies_only`), Status Window auto-detection, and Per-Chat Maintenance (`과거 전체 추출`, `이 채팅 내보내기`, `기억 다시 만들기`, `이 채팅 삭제`) with cost/risk badges.
  - **전체 시스템 설정**: `연결`, `AI 모델`, `기억 예산·검색`, `상태창 고급 규칙`, `화면/HUD`, `전체 백업·복원`.

D6. **Refined dark design tokens & lightweight inline SVG icons.**
- Updates `fixtures/unit/design-tokens-v1.json`, `apps/sidecar/src/nmos_sidecar/tokens.py`, and `adapters/pocketrisu-plugin/src/palette.ts` in lockstep with deeper slate-indigo dark surfaces and semantic `violet` / `cyan` accent tokens while preserving WCAG AA contrast (`>= 4.5:1`) and existing `--c-*` keys.
- Adds `adapters/pocketrisu-plugin/src/icons.ts` (~18 minimal SVG stroke icons constructed via `createElementNS`, zero external assets or dependencies).

## Verification

- Sidecar: `uv run pytest tests/test_views.py tests/test_memorymap.py tests/test_docs_consistency.py` and full test suite.
- Plugin: `npm test`, `npm run typecheck`, `npm run build` (verify bundle size growth stays modest).
- Visual check: headless Chromium screenshots of rendered desktop (`1100px`) and mobile (`375px`) screens.
- Live PocketRisu desktop and iPhone check: left for the owner on their install.
