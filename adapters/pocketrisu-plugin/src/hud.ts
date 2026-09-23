// Floating progress display (HUD, D28): what to show, as pure state. No DOM and no timers: hud-host.ts
// draws the view on the PocketRisu page and polls the sidecar's coverage.

import { t, type Lang } from './i18n';

/** How long a request outcome and a "done" pill stay up. */
export const OUTCOME_MS = 4000;
export const DONE_MS = 3000;

export type Outcome = 'injected' | 'nothing-relevant' | 'failed';

export interface Counts { done: number; total: number; pending: number; failed: number }
/** Coverage of the active extraction and embedding generations; `null` when one is off or has no rows. */
export interface Coverage { extract: Counts | null; embed: Counts | null }

/** Request-path activity, emitted by core.ts and never awaited there. */
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

export const EMPTY: HudState = { request: null, progress: null };

export interface HudView { kind: 'busy' | 'ok' | 'muted' | 'warn'; text: string; fraction: number | null }

export function pending(c: Coverage): number {
  return (c.extract?.pending ?? 0) + (c.embed?.pending ?? 0);
}

export function reduce(state: HudState, event: HudEvent, now: number): HudState {
  switch (event.type) {
    case 'request-start':
      return { ...state, request: { phase: 'running' } };
    case 'request-abandon':
      return state.request?.phase === 'running' ? { ...state, request: null } : state;
    case 'request-end':
      return { ...state, request: { phase: 'done', outcome: event.outcome, chars: event.chars, error: event.error,
        until: now + OUTCOME_MS } };
    case 'coverage':
      if (pending(event.coverage) > 0) return { ...state, progress: { coverage: event.coverage } };
      // Work that was on screen has finished: say so briefly. Nothing was pending: stay hidden.
      return state.progress && 'coverage' in state.progress ? { ...state, progress: { finishedUntil: now + DONE_MS } } : state;
    case 'reset':
      return EMPTY;
    case 'background':
      return state;
  }
}

/** Running request > its outcome > pending work > "done" > nothing. */
export function view(state: HudState, now: number, lang: Lang): HudView | null {
  const r = state.request;
  if (r?.phase === 'running') return { kind: 'busy', text: t(lang, 'hud.recalling'), fraction: null };
  if (r?.phase === 'done' && now < r.until) {
    if (r.outcome === 'injected') return { kind: 'ok', text: t(lang, 'hud.injected', { n: r.chars }), fraction: null };
    if (r.outcome === 'nothing-relevant') return { kind: 'muted', text: t(lang, 'hud.nothing'), fraction: null };
    const reason = t(lang, r.error?.startsWith('deadline') ? 'hud.reason.deadline' : 'hud.reason.error');
    return { kind: 'warn', text: t(lang, 'hud.skipped', { r: reason }), fraction: null };
  }
  const p = state.progress;
  if (p && 'coverage' in p) return progressView(p.coverage, lang);
  if (p && now < p.finishedUntil) return { kind: 'ok', text: t(lang, 'hud.done'), fraction: 1 };
  return null;
}

function progressView(c: Coverage, lang: Lang): HudView {
  const parts: string[] = [];
  let done = 0;
  let total = 0;
  let failed = 0;
  for (const [key, counts] of [['hud.extract', c.extract], ['hud.embed', c.embed]] as const) {
    if (!counts || counts.total === 0) continue;
    parts.push(t(lang, key, { d: counts.done, n: counts.total }));
    done += counts.done;
    total += counts.total;
    failed += counts.failed;
  }
  if (failed) parts.push(t(lang, 'hud.failed', { n: failed }));
  return { kind: 'busy', text: parts.join(' · '), fraction: total ? done / total : null };
}

/** When the view next changes by itself (an outcome or "done" expiring), or `null`. */
export function nextChange(state: HudState, now: number): number | null {
  const times = [
    state.request?.phase === 'done' ? state.request.until : null,
    state.progress && 'finishedUntil' in state.progress ? state.progress.finishedUntil : null,
  ].filter((x): x is number => x !== null && x > now);
  return times.length ? Math.min(...times) : null;
}

/** `GET /v1/conversations/{id}/coverage` → counts. */
export function parseCoverage(json: unknown): Coverage {
  const body = (json ?? {}) as Record<string, Record<string, unknown> | undefined>;
  const counts = (section: Record<string, unknown> | undefined, doneKey: string): Counts | null =>
    section?.generation && typeof section.eligible === 'number'
      ? { done: Number(section[doneKey]) || 0, total: section.eligible, pending: Number(section.pending) || 0,
          failed: Number(section.failed) || 0 }
      : null;
  return { extract: counts(body.extraction, 'compiled'), embed: counts(body.embeddings, 'embedded') };
}
