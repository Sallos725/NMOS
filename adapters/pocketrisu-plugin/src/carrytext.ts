// Pure helpers and API types for carrying another chat's memory (PHASE-60 S6, ADR 0085). No DOM or HTTP calls.

import { t, type Lang } from './i18n';

export const CARRY_MAX_NAMES = 8;

export type CarryMode = 'continue' | 'regression';

export interface CarrySource {
  id: string;
  character?: string | null;
  chat?: string | null;
}

export interface CarryLink {
  id: string;
  target_conversation_id: string;
  source_conversation_id: string;
  mode: CarryMode;
  entity_names: string[];
  cutoff_commit_id: string;
  cutoff_position: number;
  cutoff_turn: number | null;
  generations?: unknown;
  created_at: string;
  removed_at: string | null;
  source: CarrySource;
}

export interface CarryState {
  in_force: CarryLink | null;
  removed: CarryLink[];
}

export interface CarryPreview {
  mode: CarryMode;
  source: CarrySource;
  cutoff: { commit: string; position: number; turn: number | null };
  counts: { facts: number; aliases: number; threads: number; story: boolean };
  first_lines: string[];
  characters: string[];
  fingerprint: string;
  replaces: string | null;
}

export interface CarryRequestBody {
  source_conversation_id: string;
  mode: CarryMode;
  entity_names: string[];
  cutoff_turn: number | null;
  expect?: string;
}

const SIZE_REFUSAL = /the reading holds (\d+) rows; a link carries at most (\d+)/;

/** Parse the sidecar's size-limit 422 sentence into `{ rows, max }`, or null for any other error text. */
export function carryRefusal(message: string): { rows: number; max: number } | null {
  const m = SIZE_REFUSAL.exec(message);
  if (!m) return null;
  return { rows: Number(m[1]), max: Number(m[2]) };
}

function rawMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

/** Whether an API error is HTTP 404 (older sidecar without carry, or missing chat/link). */
export function isCarryNotFound(error: unknown): boolean {
  return /\bHTTP 404\b|^404\b/.test(rawMessage(error));
}

/** Whether an API error is HTTP 409 (the source changed since the preview). */
export function isCarryConflict(error: unknown): boolean {
  return /\bHTTP 409\b|^409\b/.test(rawMessage(error));
}

/** Parse the optional cutoff-turn input: empty -> null, whole number >= 0 -> number, anything else -> invalid. */
export function parseCutoffTurn(raw: string): { ok: true; value: number | null } | { ok: false } {
  const trimmed = raw.trim();
  if (!trimmed) return { ok: true, value: null };
  if (!/^\d+$/.test(trimmed)) return { ok: false };
  const n = Number(trimmed);
  return Number.isSafeInteger(n) ? { ok: true, value: n } : { ok: false };
}

/** Readable source chat label ("character · chat"), falling back cleanly when either half is missing or identical. */
export function carrySourceLabel(source: CarrySource): string {
  const ch = (source.character ?? '').trim();
  const chat = (source.chat ?? '').trim();
  return ch && chat && chat !== ch ? `${ch} · ${chat}` : (ch || chat || source.id.slice(0, 8));
}

/** Plain cutoff label ("t42까지" / "끝까지", "through t42" / "through the end"). */
export function carryCutoffLabel(lang: Lang, turn: number | null | undefined): string {
  return typeof turn === 'number' && Number.isFinite(turn)
    ? t(lang, 'carry.cutoff_turn', { t: turn })
    : t(lang, 'carry.cutoff_end');
}

/** One-line summary of the preview's counts in plain language. */
export function carryCountsLine(lang: Lang, counts: CarryPreview['counts']): string {
  return t(lang, 'carry.pv_counts', {
    f: counts.facts,
    a: counts.aliases,
    th: counts.threads,
    story: t(lang, counts.story ? 'carry.story_yes' : 'carry.story_no'),
  });
}

/** Format a carry API error as a plain sentence with no bare HTTP status code. */
export function carryErrorText(
  lang: Lang,
  error: unknown,
  fallback: (lang: Lang, error: unknown) => string,
): string {
  const raw = rawMessage(error);
  const refusal = carryRefusal(raw);
  if (refusal) return t(lang, 'carry.too_large', { n: refusal.rows, m: refusal.max });
  if (isCarryNotFound(error)) {
    return /no link in force/i.test(raw) ? t(lang, 'carry.err_no_link') : t(lang, 'carry.err_not_found');
  }
  if (/^\/v1\/\S+ -> HTTP 422: /.test(raw)) return fallback(lang, error);
  const http = /^(?:\/v1\/\S+ -> )?HTTP \d{3}(?::\s*(.*))?$/.exec(raw.trim());
  if (http) {
    const detail = (http[1] ?? '').trim();
    return detail && detail !== '[object Object]' ? `${t(lang, 'sidecar_error')}${detail}` : t(lang, 'carry.err_failed');
  }
  return fallback(lang, error);
}
