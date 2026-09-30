// Floating progress display (HUD, D28): what to show, as pure state. No DOM and no timers: hud-host.ts
// draws the view on the PocketRisu page and polls the sidecar's coverage.

import type { Vectors } from './core';
import { t, type Lang } from './i18n';

/** How long a request outcome and a "done" pill stay up. */
export const OUTCOME_MS = 4000;
export const DONE_MS = 3000;

/** `chat-off`: NMOS is switched off for this chat (ADR 0048). */
export type Outcome = 'injected' | 'nothing-relevant' | 'failed' | 'chat-off';

export interface Counts { done: number; total: number; pending: number; failed: number }
/** Facts and summaries the active generations hold for the chat (PHASE-17 Q6); `null` from older sidecars. */
export interface Produced { facts: number; summaries: number }
/** Coverage of the active extraction and embedding generations; `null` when one is off or has no rows. */
/** Summary jobs of the chat still to run and dead (PHASE-17 Q6: they run last, so "done" waits for them). */
export interface Jobs { pending: number; failed: number }
export interface Coverage { extract: Counts | null; embed: Counts | null; produced?: Produced | null; summarize?: Jobs | null }

/** Request-path activity, emitted by core.ts and never awaited there. */
export type ActivityEvent =
  | { type: 'request-start' }
  | { type: 'request-abandon' }
  | { type: 'request-end'; outcome: Outcome; chars: number; error?: string; deadlineMs?: number; conversationId: string | null;
      /** A packet kept from an earlier identical request (a reroll), and whether its recall searched vectors (K34). */
      reused?: boolean; vectors?: Vectors | null }
  | { type: 'background'; conversationId: string | null };

export type HudEvent = ActivityEvent | { type: 'coverage'; coverage: Coverage } | { type: 'reset' };

export interface HudState {
  request: null | { phase: 'running' }
    | { phase: 'done'; outcome: Outcome; chars: number; error?: string; deadlineMs?: number; until: number;
        reused?: boolean; vectors?: Vectors | null };
  /** `since`: what the chat held when the work was first seen; `made`: what it added by the end (PHASE-17 Q6). */
  progress: null | { coverage: Coverage; since: Produced | null } | { finishedUntil: number; made: Produced | null };
}

export const EMPTY: HudState = { request: null, progress: null };

/** `icon`: NMOS's icon before the text, while memory is being recalled. */
export interface HudView { kind: 'busy' | 'ok' | 'muted' | 'warn'; text: string; fraction: number | null; icon?: true }

export function pending(c: Coverage): number {
  return (c.extract?.pending ?? 0) + (c.embed?.pending ?? 0) + (c.summarize?.pending ?? 0);
}

export function reduce(state: HudState, event: HudEvent, now: number): HudState {
  switch (event.type) {
    case 'request-start':
      return { ...state, request: { phase: 'running' } };
    case 'request-abandon':
      return state.request?.phase === 'running' ? { ...state, request: null } : state;
    case 'request-end':
      return { ...state, request: { phase: 'done', outcome: event.outcome, chars: event.chars, error: event.error,
        deadlineMs: event.deadlineMs, until: now + OUTCOME_MS, reused: event.reused, vectors: event.vectors } };
    case 'coverage': {
      const shown = state.progress && 'coverage' in state.progress ? state.progress : null;
      if (pending(event.coverage) > 0) {
        return { ...state, progress: { coverage: event.coverage, since: shown ? shown.since : event.coverage.produced ?? null } };
      }
      // Work that was on screen has finished: say briefly what it made. Nothing was pending: stay hidden.
      return shown ? { ...state, progress: { finishedUntil: now + DONE_MS, made: added(shown.since, event.coverage.produced) } }
        : state;
    }
    case 'reset':
      return EMPTY;
    case 'background':
      return state;
  }
}

/** Running request > its outcome > pending work > "done" > nothing. */
export function view(state: HudState, now: number, lang: Lang): HudView | null {
  const r = state.request;
  if (r?.phase === 'running') return { kind: 'busy', text: t(lang, 'hud.recalling'), fraction: null, icon: true };
  if (r?.phase === 'done' && now < r.until) {
    if (r.outcome === 'injected') {
      // Served, but reduced or from an earlier request: said plainly, not as a warning (PHASE-17 Q5).
      const how = [r.reused ? t(lang, 'hud.reused') : '', r.vectors === 'fallback' ? t(lang, 'hud.lexical') : '']
        .filter(Boolean).join('');
      return { kind: 'ok', text: t(lang, 'hud.injected', { n: r.chars }) + how, fraction: null };
    }
    if (r.outcome === 'nothing-relevant') return { kind: 'muted', text: t(lang, 'hud.nothing'), fraction: null };
    if (r.outcome === 'chat-off') return { kind: 'muted', text: t(lang, 'hud.chat_off'), fraction: null };
    const reason = r.error?.startsWith('deadline')
      ? t(lang, 'hud.reason.deadline', { s: Math.round((r.deadlineMs ?? 0) / 100) / 10 })
      : t(lang, 'hud.reason.error');
    return { kind: 'warn', text: t(lang, 'hud.skipped', { r: reason }), fraction: null };
  }
  const p = state.progress;
  if (p && 'coverage' in p) return progressView(p.coverage, lang);
  if (p && now < p.finishedUntil) return { kind: 'ok', text: doneText(p.made, lang), fraction: 1 };
  return null;
}

/** What finished work added; `null` when either end is unknown (an older sidecar). */
function added(since: Produced | null, now: Produced | null | undefined): Produced | null {
  if (!since || !now) return null;
  return { facts: Math.max(0, now.facts - since.facts), summaries: Math.max(0, now.summaries - since.summaries) };
}

function doneText(made: Produced | null, lang: Lang): string {
  const parts = [made?.facts ? t(lang, 'hud.made.facts', { n: made.facts }) : '',
    made?.summaries ? t(lang, 'hud.made.summaries', { n: made.summaries }) : ''].filter(Boolean);
  return parts.length ? `✓ ${parts.join(' · ')}` : t(lang, 'hud.done');
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
  if (c.summarize?.pending) parts.push(t(lang, 'hud.summarize', { n: c.summarize.pending }));
  failed += c.summarize?.failed ?? 0;
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
  const jobs = body.summaries;
  const summarize = jobs && typeof jobs.pending === 'number'
    ? { pending: jobs.pending, failed: Number(jobs.failed) || 0 } : null;
  const made = body.produced;
  const produced = made && typeof made.facts === 'number' && typeof made.summaries === 'number'
    ? { facts: made.facts, summaries: made.summaries } : null;
  return { extract: counts(body.extraction, 'compiled'), embed: counts(body.embeddings, 'embedded'), produced, summarize };
}
