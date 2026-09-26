// Deadline advice (owner decision on audit A-09): when a request ran close to or past the deadline, say so
// and suggest a value. Pure; the panel, the progress display and the one-time popup share it.

import { MAX_DEADLINE_MS } from './form';

/** A request that used this much of its deadline or more gets a "close to the deadline" note. */
export const NEAR_FRACTION = 0.8;

export interface DeadlineAdvice {
  level: 'over' | 'near';
  deadlineMs: number;
  /** How long the request took (for `over`: when recall answered late; null when it never did). */
  tookMs: number | null;
  suggestMs: number;
}

export interface RequestTiming {
  outcome: 'injected' | 'nothing-relevant' | 'failed';
  ms: number;
  deadlineMs: number;
  error?: string;
  /** Set when a request cut at the deadline got its recall answer later: the whole request's time. */
  neededMs?: number;
}

export function deadlineAdvice(r: RequestTiming | null | undefined): DeadlineAdvice | null {
  if (!r || !(r.deadlineMs > 0)) return null;
  let level: DeadlineAdvice['level'];
  let tookMs: number | null;
  if (r.outcome === 'failed') {
    if (!r.error?.startsWith('deadline')) return null;
    level = 'over';
    tookMs = r.neededMs ?? null;
  } else {
    if (r.ms < NEAR_FRACTION * r.deadlineMs) return null;
    level = 'near';
    tookMs = r.ms;
  }
  // Past the deadline the request needed at least the deadline; close to it, what it took.
  const base = level === 'over' ? Math.max(tookMs ?? 0, r.deadlineMs) : r.ms;
  const suggestMs = Math.min(MAX_DEADLINE_MS, Math.max(r.deadlineMs + 500, Math.ceil((base * 1.25) / 500) * 500));
  return { level, deadlineMs: r.deadlineMs, tookMs, suggestMs };
}

/** `3000` → `3,000`. */
export function formatMs(ms: number): string {
  return Math.round(ms).toLocaleString('en-US');
}
