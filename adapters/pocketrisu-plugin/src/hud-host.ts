// Draws the progress display (D28) on the PocketRisu page through the host's main-DOM proxy (H16) and
// polls the sidecar's coverage while background work is pending. Best effort throughout: an error turns
// the display off for the session and never reaches the request path.

import { EMPTY, nextChange, parseCoverage, pending, reduce, view, type ActivityEvent, type HudState, type HudView } from './hud';
import type { Lang } from './i18n';

/** The part of PocketRisu's `SafeElement` proxy the display uses. Every call crosses the frame bridge. */
export interface HudElement {
  remove(): Promise<void>;
  appendChild(child: HudElement): Promise<void>;
  addClass(name: string): Promise<void>;
  setStyleAttribute(value: string): Promise<void>;
  setStyle(property: string, value: string): Promise<void>;
  setTextContent(value: string): Promise<void>;
  getBoundingClientRect(): Promise<{ left: number; top: number; right: number; bottom: number }>;
  /** Registered on the whole document by the host, whatever the element (H16). */
  addEventListener(type: 'click', listener: (event: { clientX: number; clientY: number }) => void): Promise<string>;
  removeEventListener(type: 'click', id: string): Promise<void>;
}

export interface HudDocument {
  querySelector(selector: string): Promise<HudElement | null>;
  createElement(tag: string): Promise<HudElement>;
}

export interface HudDeps {
  enabled(): Promise<boolean>;
  lang(): Promise<Lang>;
  /** The host page, or null without the `mainDom` permission. */
  rootDocument(): Promise<HudDocument | null>;
  /** Where the user is; changes when they open another character or chat. Must be cheap. */
  position(): Promise<string>;
  coverage(conversationId: string): Promise<unknown>;
  openPanel(): void;
  now(): number;
  debug(...args: unknown[]): void;
  setTimer(fn: () => void, ms: number): unknown;
  clearTimer(handle: unknown): void;
}

export const POLL_MS = 3000;
export const MAX_POLL_ERRORS = 5;
/** Bursts of events (host retries of one request, H2) share one coverage call. */
export const MIN_POLL_GAP_MS = 1000;

const CLASS = 'nmos-hud';
// Under the panel frame (z-index 1000) so the open panel covers it.
const ROOT_STYLE = 'position:fixed;top:calc(8px + env(safe-area-inset-top));right:calc(8px + env(safe-area-inset-right));'
  + 'z-index:900;min-width:140px;max-width:min(320px,calc(100vw - 72px));background:#1d1e24;border:1px solid #30323b;border-radius:12px;'
  + 'padding:6px 12px;font:13px/1.4 system-ui,-apple-system,"Noto Sans KR",sans-serif;'
  + 'box-shadow:0 2px 10px rgba(0,0,0,.35);cursor:pointer;user-select:none';
const TEXT_STYLE = 'display:block;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;color:#e8e8ec';
const TRACK_STYLE = 'display:none;height:3px;margin-top:4px;background:#30323b;border-radius:2px;overflow:hidden';
const FILL_STYLE = 'height:3px;width:0;background:#4c6ef5;border-radius:2px;transition:width .3s';
const COLORS: Record<HudView['kind'], string> = { busy: '#e8e8ec', ok: '#8ce99a', muted: '#9a9ca8', warn: '#ffd43b' };

interface Drawn { root: HudElement; text: HudElement; track: HudElement; fill: HudElement; listener: string; last: string }

export function createHud(deps: HudDeps) {
  let state: HudState = EMPTY;
  let problem: string | null = null;
  let drawn: Drawn | null = null;
  let conversation: string | null = null;
  let where: string | null = null;
  let pollTimer: unknown = null;
  let expiryTimer: unknown = null;
  let pollErrors = 0;
  let lastPoll = -Infinity;
  let queue: Promise<void> = Promise.resolve();

  /** All work runs in order on one chain; nothing here ever rejects to the caller. */
  function run(task: () => Promise<void>): void {
    queue = queue.then(task).catch(fail);
  }

  async function fail(error: unknown): Promise<void> {
    problem = error instanceof Error ? error.message : String(error);
    deps.debug('[NMOS] progress display stopped for this session:', problem);
    stopPolling();
    await erase().catch(() => {});
  }

  async function active(): Promise<boolean> {
    if (!problem && (await deps.enabled())) return true;
    stopPolling();
    await erase();
    return false;
  }

  async function erase(): Promise<void> {
    if (expiryTimer !== null) deps.clearTimer(expiryTimer);
    expiryTimer = null;
    const d = drawn;
    drawn = null;
    if (!d) return;
    await d.root.removeEventListener('click', d.listener);
    await d.root.remove();
  }

  async function draw(): Promise<Drawn> {
    const doc = await deps.rootDocument();
    if (!doc) throw new Error('no access to the PocketRisu page (mainDom permission)');
    // A pill left by an earlier load of the plugin (re-import without reload, H16).
    await (await doc.querySelector(`.${CLASS}`))?.remove();
    const body = await doc.querySelector('body');
    if (!body) throw new Error('the PocketRisu page has no body');
    const root = await doc.createElement('div');
    await root.addClass(CLASS);
    await root.setStyleAttribute(ROOT_STYLE);
    const text = await doc.createElement('span');
    await text.setStyleAttribute(TEXT_STYLE);
    const track = await doc.createElement('div');
    await track.setStyleAttribute(TRACK_STYLE);
    const fill = await doc.createElement('div');
    await fill.setStyleAttribute(FILL_STYLE);
    await track.appendChild(fill);
    await root.appendChild(text);
    await root.appendChild(track);
    await body.appendChild(root);
    const listener = await root.addEventListener('click', (event) => { void hit(event); });
    return { root, text, track, fill, listener, last: '' };
  }

  // The host listens on the whole document: act only on clicks inside the pill.
  async function hit(event: { clientX: number; clientY: number }): Promise<void> {
    try {
      const d = drawn;
      if (!d) return;
      const r = await d.root.getBoundingClientRect();
      if (event.clientX >= r.left && event.clientX <= r.right && event.clientY >= r.top && event.clientY <= r.bottom) {
        deps.openPanel();
      }
    } catch (error) {
      deps.debug('[NMOS] progress display click failed:', error instanceof Error ? error.message : error);
    }
  }

  async function render(): Promise<void> {
    if (expiryTimer !== null) deps.clearTimer(expiryTimer);
    expiryTimer = null;
    const now = deps.now();
    const v = view(state, now, await deps.lang());
    if (!v) return erase();
    drawn ??= await draw();
    const d = drawn;
    const key = JSON.stringify(v);
    if (d.last !== key) {
      d.last = key;
      await d.text.setTextContent(v.text);
      await d.text.setStyle('color', COLORS[v.kind]);
      await d.track.setStyle('display', v.fraction === null ? 'none' : 'block');
      if (v.fraction !== null) await d.fill.setStyle('width', `${Math.round(v.fraction * 100)}%`);
    }
    const next = nextChange(state, now);
    if (next !== null) expiryTimer = deps.setTimer(() => { expiryTimer = null; run(render); }, next - now);
  }

  /** Remember which chat the work belongs to; another chat drops the progress shown for the last one. */
  async function follow(conversationId: string | null): Promise<void> {
    if (!conversationId) return;
    where = await deps.position();
    if (conversationId === conversation) return;
    conversation = conversationId;
    state = { ...state, progress: null };
    stopPolling();
  }

  function startPolling(): void {
    if (pollTimer !== null || !conversation) return;
    pollErrors = 0;
    pollTimer = deps.setTimer(() => run(poll), Math.max(0, lastPoll + MIN_POLL_GAP_MS - deps.now()));
  }

  function stopPolling(): void {
    if (pollTimer !== null) deps.clearTimer(pollTimer);
    pollTimer = null;
  }

  async function poll(): Promise<void> {
    pollTimer = null;
    if (!(await active()) || !conversation) return;
    if (where !== null && (await deps.position()) !== where) {
      conversation = null;
      state = { ...state, progress: null };
      return render();
    }
    let again = false;
    lastPoll = deps.now();
    try {
      const coverage = parseCoverage(await deps.coverage(conversation));
      pollErrors = 0;
      state = reduce(state, { type: 'coverage', coverage }, deps.now());
      again = pending(coverage) > 0;
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      deps.debug('[NMOS] coverage poll failed:', message);
      // 404: the sidecar has not seen this chat yet; nothing to follow.
      again = !/HTTP 404/.test(message) && ++pollErrors < MAX_POLL_ERRORS;
    }
    await render();
    if (again) pollTimer = deps.setTimer(() => run(poll), POLL_MS);
  }

  return {
    /** Request-path activity from core.ts. */
    event(event: ActivityEvent): void {
      run(async () => {
        if (!(await active())) return;
        if (event.type === 'request-end' || event.type === 'background') await follow(event.conversationId);
        state = reduce(state, event, deps.now());
        await render();
        if (event.type === 'request-end' || event.type === 'background') startPolling();
      });
    },
    /** A panel action queued background work: follow that conversation, or the last one seen. */
    background(conversationId?: string): void {
      run(async () => {
        if (!(await active())) return;
        if (conversationId) await follow(conversationId);
        startPolling();
      });
    },
    /** The toggle changed: off erases at once; on clears an earlier failure. */
    refresh(): void {
      run(async () => {
        if (await deps.enabled()) {
          problem = null;
          return;
        }
        stopPolling();
        state = EMPTY;
        await erase();
      });
    },
    /** Why the display stopped for this session, if it did. */
    problem: (): string | null => problem,
    /** Resolves when queued work has run (tests). */
    settled: (): Promise<void> => queue,
  };
}
