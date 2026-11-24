// The Status tab's "Model work" card (PHASE-61 S5): its lines from `GET /v1/worker/status`. Pure; no DOM or host calls.

import { t, type Lang, type StringKey } from './i18n';

export interface WorkerStatus {
  queued: Record<string, number>;
  queued_total: number;
  running: number;
  retrying: number;
  dead_recent: number;
  done_recent: number;
  recent_minutes: number;
  dead_hours: number;
  last_error: { kind: string; status: string; at: string; text: string } | null;
}

export interface WorkerShown {
  level: 'idle' | 'working' | 'trouble';
  lines: string[];
}

const KINDS = new Set(['extract', 'reveal', 'summarize', 'canon', 'embed']);
const COUNTS = ['queued_total', 'running', 'retrying', 'dead_recent', 'done_recent', 'recent_minutes', 'dead_hours'];
const isCount = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v) && v >= 0;
const isObject = (v: unknown): v is Record<string, unknown> => typeof v === 'object' && v !== null && !Array.isArray(v);

/** An answer from an older or odd sidecar is not shown at all. */
function valid(s: unknown): s is WorkerStatus {
  if (!isObject(s) || !COUNTS.every((k) => isCount(s[k])) || !isObject(s.queued)) return false;
  if (!Object.values(s.queued).every(isCount)) return false;
  const e = s.last_error;
  return e === null || (isObject(e) && ['kind', 'status', 'at', 'text'].every((k) => typeof e[k] === 'string')
    && !Number.isNaN(Date.parse(e.at as string)));
}

const num = (n: number) => n.toLocaleString('en-US');
const two = (n: number) => String(n).padStart(2, '0');
const kindName = (lang: Lang, kind: string) => (KINDS.has(kind) ? t(lang, `worker.kind.${kind}` as StringKey) : kind);

export function workerLines(lang: Lang, status: unknown, now: Date = new Date()): WorkerShown {
  if (!valid(status)) return { level: 'idle', lines: [] };
  const s = status;
  const kinds = Object.entries(s.queued).filter(([, n]) => n > 0).map(([k, n]) => `${kindName(lang, k)} ${num(n)}`);
  const queue = [s.queued_total > 0 ? t(lang, 'worker.waiting', { n: num(s.queued_total), kinds: kinds.join(' · ') }) : '',
    s.running > 0 ? t(lang, 'worker.running', { n: num(s.running) }) : ''].filter(Boolean);
  const lines = [queue.length ? queue.join(' · ') : t(lang, 'worker.idle')];
  const recent = [s.done_recent > 0 ? t(lang, 'worker.done', { n: num(s.done_recent) }) : '',
    s.retrying > 0 ? t(lang, 'worker.retrying', { n: num(s.retrying) }) : '',
    s.dead_recent > 0 ? t(lang, 'worker.dead', { n: num(s.dead_recent), h: s.dead_hours }) : ''].filter(Boolean);
  if (recent.length) lines.push(t(lang, 'worker.recent', { m: s.recent_minutes, parts: recent.join(' · ') }));
  if (s.last_error) {
    const at = new Date(s.last_error.at);
    const day = at.toDateString() === now.toDateString() ? '' : `${two(at.getMonth() + 1)}-${two(at.getDate())} `;
    lines.push(t(lang, 'worker.error', { at: `${day}${two(at.getHours())}:${two(at.getMinutes())}`,
      kind: kindName(lang, s.last_error.kind), text: s.last_error.text }));
  }
  const level = s.retrying > 0 || s.dead_recent > 0 ? 'trouble' : s.queued_total + s.running > 0 ? 'working' : 'idle';
  return { level, lines };
}
