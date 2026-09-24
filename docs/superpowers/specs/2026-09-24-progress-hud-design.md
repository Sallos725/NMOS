# Progress HUD — design

Date: 2026-09-24. Owner decisions in this session: show both request outcome and background progress
(option A); off by default, turned on from the panel (option A); proceed with this design.

## Problem

NMOS works out of sight. To know whether memory is on, whether it reached the model, or whether
background extraction is still running, the user has to open the 🧠 panel. The beta.7 preset bug
(no memory on any request, ADR 0001 amendment 2) went unnoticed for this reason.

## Scope

Not a Phase 5 feature: an adapter-only UI addition, recorded as an owner decision (D-number and
`docs/STATUS.md`). No sidecar or schema change. The plugin stays thin: no new request-path work,
fail-open unchanged.

## What the user sees

A small pill in the top-right corner of the PocketRisu page (over the chat, safe-area aware, clear
of the chat input on a 390 px viewport). Only the chat that is open now is tracked.

| Moment | Pill |
|---|---|
| `beforeRequest` starts (main generation only, D13) | `🧠 기억 불러오는 중…` |
| `beforeRequest` ends | `✓ 기억 주입 (N자)` / `– 관련 기억 없음` / `⚠ 건너뜀: <short reason>`; hidden after 4 s |
| Background work pending for this chat | `추출 132/480 · 임베딩 480/480` with a bar; `· ⚠ 실패 3` when failed > 0 |
| Background work finished | `✓ 처리 완료`; hidden after 3 s |

A request outcome shows over the progress bar for its 4 s, then the progress view returns if work is
still pending. Tapping the pill opens the NMOS panel on the Status tab. English strings follow the
`language` arg.

## Toggle

- New plugin arg `hud` (`int`, 1 = on; PocketRisu initialises it to 0 = off).
- Settings tab: a checkbox "Floating progress display". Status tab: when off, a one-line hint with a
  "Turn on" button.
- Turning it on requests the `mainDom` plugin permission (`requestPluginPermission('mainDom')`) from
  the click. If it is denied, or the build has no `getRootDocument`, the arg is set back to 0 and the
  panel says why in one line.
- Off: no permission request, no coverage polling, and any pill already drawn is removed.

## Components

- **`src/hud.ts` — pure state.** `reduce(state, event) → state` and `view(state, now) → View | null`
  (text, kind, progress fraction, expiry). Events: `request-start`, `request-end {outcome, chars,
  error}`, `coverage {extract, embed}`, `chat-changed`, `tick`. No DOM, no timers: fully unit tested.
- **`src/hud-host.ts` — main-DOM renderer.** Gets the root document once (after permission), creates
  one `div.nmos-hud` under `body` with inline styles, and updates it with `setInnerHTML` of escaped
  text only. Registers one click listener (open panel). Removes the element on off. Every call is
  wrapped: a failure logs once at debug level and disables the HUD for the session.
- **`src/core.ts`** — `createAdapter` takes an optional `onEvent(event)` sink. `beforeRequest` emits
  `request-start` / `request-end` synchronously and never awaits the sink. It keeps the reconcile
  response's `conversation_id` per host chat id, so the poller knows which coverage to ask for.
- **Poller (in `hud-host.ts`).** Runs only while the HUD is on and the current chat has a known
  conversation id. Starts after `onOutput`, after the panel's extract-history / rebuild / settings
  save, and after a `request-end`. Calls `GET /v1/conversations/{id}/coverage` every 3 s while
  `extraction.pending + embeddings.pending > 0`; stops at zero, on a chat change, or after 5
  consecutive errors. `compiled/eligible` and `embedded/eligible` drive the bar.

## Error handling

- The HUD can never delay or fail a generation: events are fire-and-forget, and the renderer's
  errors are swallowed after one debug log.
- A missing permission API, a denied prompt, or a proxy call that throws switches the HUD off for
  the session and, on the next panel open, shows the reason.
- Coverage 404 (chat not synced yet) shows nothing.

## Host evidence first

Before building the renderer, verify on an isolated PocketRisu v1.12.0 (`ghcr.io/pocketrisu/pocketrisu:latest`,
headless Playwright, see the PocketRisu test harness) and record in `docs/HOST-FACTS.md`:

1. `requestPluginPermission('mainDom')` and `getRootDocument()` exist in the V3 API; what the prompt
   looks like; whether a denial is remembered (as with the replace-content prompt).
2. The proxy element API: `createElement`, `setInnerHTML`, `appendChild`, `querySelector`,
   `addEventListener`, `remove`; whether `setInnerHTML` sanitises and whether inline `style` survives.
3. The element survives chat switches and new messages; after a plugin reload the old element is
   left behind (so the renderer must reuse or remove an existing `div.nmos-hud` on start).
4. Position on a 390 px viewport does not cover the chat input or the ☰ menu.

If (1) or (2) fails, stop and report; do not ship a HUD built on guesses.

## Testing

- vitest: `hud.ts` reducer/view (each outcome, progress math, expiry, outcome over progress,
  chat change, failed count); `core.ts` emits start/end for main requests only and never blocks
  when the sink throws; poller start/stop rules with a fake clock and fake API.
- Real host: send → outcome pill; extract-history → bar counts up to done; off → pill gone and no
  `/coverage` in `save/request-logs.db`; denied permission → arg back to 0.

## Docs

ARCHITECTURE (D-number, host fact H16 if new), `docs/HOST-FACTS.md`, `docs/STATUS.md`, README and
`docs/guide.ko.md` (how to turn it on, what it shows), CHANGELOG.
