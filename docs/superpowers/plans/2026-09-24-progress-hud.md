# Progress HUD Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A small floating pill on the PocketRisu page that shows each request's memory outcome and the
background extraction/embedding progress of the open chat, off by default and turned on from the panel.

**Architecture:** Pure state in `src/hud.ts` (events → view), a best-effort main-DOM renderer and
coverage poller in `src/hud-host.ts` over PocketRisu's `SafeElement` proxy, fire-and-forget activity
events from `core.ts`, and a toggle in the panel (`ui.ts`) that asks for the `mainDom` permission.
Spec: `docs/superpowers/specs/2026-09-24-progress-hud-design.md`.

**Tech Stack:** TypeScript, esbuild, vitest (plugin only; no sidecar change).

Plugin root below: `adapters/pocketrisu-plugin`. Test: `npm test`, types: `npm run typecheck`, bundle: `npm run build`.

---

## Host facts this plan relies on (verified 2026-09-24, Task 1 records them)

Source reading of PocketRisu v1.12.0 (`src/ts/plugins/apiV3/v3.svelte.ts`, from the image's source map)
and a live run of a probe plugin on an isolated `ghcr.io/pocketrisu/pocketrisu:latest` instance:

- `risuai.requestPluginPermission('mainDom')` shows the host confirm *"Plugin {} is requesting to access
  the main Document, which may expose sensitive information. Do you want to allow this?"*. A grant or a
  denial is persisted; later calls resolve without a prompt. After a denial the host shows a guide;
  undo is Settings → Plugin → row menu → "권한 응답 초기화" (reset permission responses).
- `risuai.getRootDocument()` returns a `SafeDocument` proxy (or `null` without permission). Every method
  is async over the iframe bridge. Used: `querySelector`, `createElement`, `appendChild`, `remove`,
  `addClass`, `setStyleAttribute`, `setStyle`, `setTextContent` (text is escaped),
  `getBoundingClientRect`, `addEventListener`/`removeEventListener`. `setAttribute` only allows `x-*`.
  `setInnerHTML` runs DOMPurify (inline `style` kept, handlers stripped); the HUD does not use it.
- `SafeElement.addEventListener(type, fn)` registers on **the whole document**, not the element, and
  hands the listener a trimmed event (`clientX`, `clientY`, …). A pill click must be detected by
  comparing the coordinates with the pill's rect. Listeners are removed when the plugin unloads.
- A pill appended to `body` stays through settings open/close, character creation and chat view; on
  a 390 px viewport it sits top-right above the message list, clear of the chat input and the left
  arrow. A plugin re-import without reload leaves the old pill in the DOM (the renderer removes an
  existing `.nmos-hud` before drawing). A page reload clears it; the grant survives the reload.
- The panel frame is `position:fixed; z-index:1000`; host dialogs use `z-50`. The permission prompt is
  therefore requested with the panel frame hidden, then the frame is shown again (checked in Task 7).

## File structure

| File | Responsibility |
|---|---|
| `src/hud.ts` (new) | Pure: activity/HUD events, `reduce`, `view`, `nextChange`, `parseCoverage`, `pending`. |
| `src/hud-host.ts` (new) | `createHud(deps)`: serialised render/poll loop over a `HudDocument` port; click hit test; stale cleanup; fail-off. |
| `src/core.ts` | `createAdapter(host, onActivity?)`: emits `request-start` / `request-abandon` / `request-end` / `background`; remembers `conversation_id` per chat. |
| `src/host.ts` | `createRisuHud(...)` wiring `createHud` to `risuai`; `HudControl` (`enable`/`disable`/`problem`/`background`); `registerHooks` returns the status-panel opener. |
| `src/entry.ts` | Build adapter + HUD, pass activity events through. |
| `src/ui.ts` | Settings card with the toggle, status-tab hint/"turn on", poke the HUD after history/rebuild/save. |
| `src/i18n.ts` | `hud.*` strings (ko/en). |
| `scripts/build.mjs` | `//@arg hud int …` header line. |
| `test/hud.test.ts`, `test/hud-host.test.ts` (new), `test/core.test.ts` | Unit tests. |

## Task 1: Record host evidence

**Files:** `docs/HOST-FACTS.md` (new section "Main-page HUD (2026-09-24)"), `ARCHITECTURE.md` (H16 row).

- [ ] Write the facts above as a HOST-FACTS section (setup: isolated container on `localhost:6101`,
      empty save dir, headless Chromium 1223, probe plugin `hud_spike`/`hud_deny`).
- [ ] Add ARCHITECTURE H16: *"With the `mainDom` permission a V3 plugin can draw on the host page
      through the async `SafeElement` proxy; listeners are document-wide; grants/denials persist."* →
      consequence: *"The progress HUD is opt-in, hit-tests clicks, and removes a stale pill on start."*
- [ ] Commit `Docs: host facts for a main-page HUD (H16)`.

## Task 2: `hud.ts` pure state (TDD)

**Files:** create `src/hud.ts`, `test/hud.test.ts`; modify `src/i18n.ts`.

Types:

```ts
export type Outcome = 'injected' | 'nothing-relevant' | 'failed';
export interface Counts { done: number; total: number; pending: number; failed: number }
export interface Coverage { extract: Counts | null; embed: Counts | null }
export type ActivityEvent =
  | { type: 'request-start' }
  | { type: 'request-abandon' }
  | { type: 'request-end'; outcome: Outcome; chars: number; error?: string; conversationId: string | null }
  | { type: 'background'; conversationId: string | null };
export type HudEvent = ActivityEvent | { type: 'coverage'; coverage: Coverage } | { type: 'reset' };
export interface HudState {
  request: null | { phase: 'running' } | { phase: 'done'; outcome: Outcome; chars: number; error?: string; until: number };
  progress: null | { coverage: Coverage } | { finishedUntil: number };
}
export interface HudView { kind: 'busy' | 'ok' | 'muted' | 'warn'; text: string; fraction: number | null }
export const OUTCOME_MS = 4000, DONE_MS = 3000;
export function reduce(state: HudState, event: HudEvent, now: number): HudState;
export function view(state: HudState, now: number, lang: Lang): HudView | null;
export function nextChange(state: HudState, now: number): number | null;
export function parseCoverage(json: unknown): Coverage;   // sidecar /coverage → counts; null when a generation is off
export function pending(c: Coverage): number;
```

Rules: running request > request outcome (until `until`) > pending progress > "done" (until
`finishedUntil`) > nothing. Coverage with nothing pending turns a shown progress into "done";
without a shown progress it stays hidden. Progress text lists only generations with `total > 0`;
bar fraction = Σdone / Σtotal; failed count appended when > 0. Skipped reason: `deadline…` →
"제한 시간 초과", else "사이드카 오류".

Tests (`test/hud.test.ts`), each a failing test first:
- [ ] running → `🧠 기억 불러오는 중…`, no bar.
- [ ] end injected/nothing/failed(deadline)/failed(other) → the four texts; hidden after `OUTCOME_MS`.
- [ ] coverage with pending → `추출 132/480 · 임베딩 480/480`, fraction (132+480)/960; failed → `· ⚠ 실패 3`.
- [ ] outcome shows over progress, progress returns after it expires.
- [ ] pending → 0 gives `✓ 처리 완료` for `DONE_MS`; 0 without prior progress shows nothing.
- [ ] `parseCoverage` maps `compiled`/`embedded`/`eligible`; a `generation: null` section is `null`.
- [ ] `nextChange` returns the earliest future expiry or `null`.
- [ ] English strings via `lang = 'en'`.
- [ ] Run `npm test -- hud.test` → PASS; commit `Plugin: progress HUD state (pure)`.

## Task 3: `hud-host.ts` renderer and poller (TDD)

**Files:** create `src/hud-host.ts`, `test/hud-host.test.ts`.

```ts
export interface HudElement { remove(); appendChild(c); addClass(n); setStyleAttribute(v); setStyle(p, v);
  setTextContent(v); getBoundingClientRect(); addEventListener('click', fn): Promise<string>; removeEventListener('click', id) }
export interface HudDocument { querySelector(s): Promise<HudElement | null>; createElement(tag): Promise<HudElement> }
export interface HudDeps { enabled(): Promise<boolean>; lang(): Promise<Lang>; rootDocument(): Promise<HudDocument | null>;
  position(): Promise<string>; coverage(conversationId: string): Promise<unknown>; openPanel(): void; now(): number;
  debug(...a: unknown[]): void; setTimer(fn: () => void, ms: number): unknown; clearTimer(h: unknown): void }
export const POLL_MS = 3000, MAX_POLL_ERRORS = 5;
export function createHud(deps: HudDeps): { event(e: ActivityEvent): void; background(conversationId?: string): void;
  refresh(): void; problem(): string | null; settled(): Promise<void> };
```

Behaviour: all work runs on one promise chain (`settled()` exposes it for tests). Disabled → erase
and do nothing else. First draw removes an existing `.nmos-hud`, builds `div.nmos-hud > span + div > div`
with inline styles (fixed top-right, safe-area aware, `max-width:min(320px,calc(100vw - 72px))`,
z-index 900 so the panel frame covers it), registers one click listener and opens the panel only when
the click falls inside the pill's rect. Only changed views touch the DOM. `request-end` and
`background` start polling their conversation (immediately, then every `POLL_MS`) while anything is
pending; polling stops at zero pending, on HTTP 404, after `MAX_POLL_ERRORS` consecutive errors, or
when `position()` differs from the one recorded with the conversation (the user moved to another
chat; progress is cleared). Any renderer error sets `problem`, stops polling, erases the pill; later
events are ignored until `refresh()` with the toggle on.

Tests with a fake document (records calls, returns fake elements with a settable rect) and a manual
timer queue:
- [ ] disabled: no `rootDocument` call, no DOM.
- [ ] request-start draws once; a stale `.nmos-hud` is removed first; same view twice → one `setTextContent`.
- [ ] click inside rect → `openPanel`; outside → not.
- [ ] request-end with conversation → coverage polled; pending 2 → bar; next tick pending 0 → "done"; expiry → erased, polling stopped.
- [ ] 404 stops polling at once; 5 errors stop polling.
- [ ] position change clears progress and stops polling.
- [ ] `rootDocument` null → `problem` set, nothing drawn, later events ignored; `refresh()` clears it.
- [ ] `refresh()` with toggle off erases the pill and removes the listener.
- [ ] Run `npm test -- hud-host` → PASS; commit `Plugin: progress HUD renderer and coverage poller`.

## Task 4: activity events from `core.ts` (TDD)

**Files:** modify `src/core.ts`, `test/core.test.ts`.

- `createAdapter(host, onActivity?: (e: ActivityEvent) => void)`; `emit` wraps the sink in try/catch.
- `ReconcileResult.conversation_id?: string`; a `Map<chatId, conversationId>` (bounded like the cache).
- `beforeRequest`: after the aux/packet/enabled checks emit `request-start`; no chat or no user turn →
  `request-abandon`; cache hit, success and failure → `request-end` with outcome, packet chars, error
  and the known conversation id.
- `onOutput` (enabled): emit `background` with the known conversation id.

Tests:
- [ ] main request emits start then end(injected, chars, conversationId from reconcile).
- [ ] aux request and disabled settings emit nothing.
- [ ] failing sidecar emits end(failed, error).
- [ ] a throwing sink does not change the returned prompt.
- [ ] cache hit emits start + end.
- [ ] onOutput emits background with the conversation id learned earlier.
- [ ] Run `npm test` → PASS; commit `Plugin: request activity events for the HUD`.

## Task 5: host wiring, toggle and panel

**Files:** modify `src/host.ts`, `src/entry.ts`, `src/ui.ts`, `src/i18n.ts`, `scripts/build.mjs`.

- `host.ts`: declare `requestPluginPermission?` / `getRootDocument?` / `onUnload?` on `risuai`.
  `createRisuHud({ coverage, openPanel })` builds `createHud` with `enabled = arg('hud') === '1'`,
  `position = "<charIndex>:<chatIndex>"`, `rootDocument = getRootDocument?.() ?? null`, real timers,
  and returns `HudControl`:
  - `enable()`: `'unsupported'` if either API is missing; otherwise hide the panel frame, request
    `mainDom`, show the frame again (finally), set `hud` to 1 or 0, `refresh()`, return `'on'`/`'denied'`.
  - `disable()`: set `hud` 0, `refresh()`.
  - `problem()`, `background(id?)` pass through. `onUnload` removes the pill (best effort).
- `registerHooks(..., hud)` puts `hud` in `PanelDeps` and returns `() => open('status')`.
- `entry.ts`: `createAdapter(risuHost, (e) => hud.event(e))`; `coverage` via `adapter.api('GET', …, 5000)`.
- `ui.ts`: Settings — first card "진행 표시" with a checkbox applied immediately (not part of the save
  form), sub text explaining the host prompt and that NMOS only draws the pill; result line for
  on/denied/unsupported/off. Status — when `hud` is off, a card with the hint and a "진행 표시 켜기"
  button; when `problem()` is set, show it. After extract-history (queued > 0) and rebuild,
  `hud.background(conversation)`; after a settings save with `queued_jobs`, `hud.background()`.
- `build.mjs`: `//@arg hud int 1 = floating progress display (turn on from the NMOS panel)`.
- [ ] `npm run typecheck && npm test && npm run build` → clean; commit `Plugin: progress HUD toggle and wiring`.

## Task 6: docs

**Files:** `ARCHITECTURE.md` (D28), `docs/STATUS.md`, `README.md`, `docs/guide.ko.md`, `CHANGELOG.md`.

- [ ] D28 — *Optional progress HUD (owner decision 2026-09-24).* Off by default; opt-in asks for
      `mainDom`; request events are fire-and-forget; coverage polled only while pending; not a Phase 5 feature.
- [ ] README/guide: how to turn it on, the host prompt wording, how to undo a denial, what each pill means.
- [ ] CHANGELOG "Unreleased": Added — progress HUD.
- [ ] Commit `Docs: progress HUD (D28)`.

## Task 7: real-host check

On the isolated PocketRisu (`localhost:6101`) with a sidecar and the stub LLM:
- [ ] install the built plugin, reload; turn on from Settings → host prompt visible above the panel
      (frame hidden while it is open) → Yes → `hud` = 1.
- [ ] send a message → `🧠 기억 불러오는 중…` then `✓ 기억 주입` / `– 관련 기억 없음`; screenshot desktop + 390 px.
- [ ] Inspector → extract all history → bar counts up to `✓ 처리 완료`, then hides.
- [ ] click the pill → panel opens on Status.
- [ ] turn off → pill gone; no `/coverage` calls after that in `save/request-logs.db`.
- [ ] new instance: deny → toggle back off with the reset hint.
- [ ] Record results in HOST-FACTS / the PR; commit.
