// Trimming status text for the Status view and the HUD (PHASE-60 S1, ADR 0083). Pure; no DOM or host calls.

import { t, type Lang, type StringKey } from './i18n';

export interface TrimShown {
  dropped: number;
  savedTokens: number;
  reason: string | null;
}

const REASON_KEYS: ReadonlyMap<string, StringKey> = new Map<string, StringKey>([
  ['format', 'trim.reason.format'],
  ['short', 'trim.reason.short'],
  ['uncovered', 'trim.reason.uncovered'],
  ['no_summaries', 'trim.reason.no_summaries'],
  ['stale', 'trim.reason.stale'],
  ['empty_packet', 'trim.reason.empty_packet'],
  ['failed', 'trim.reason.failed'],
  ['unsupported', 'trim.reason.unsupported'],
]);

export function trimReason(lang: Lang, reason: string | null): string {
  if (reason === null) return '';
  const key = REASON_KEYS.get(reason);
  return key ? t(lang, key) : t(lang, 'trim.reason.other', { r: reason });
}

export function trimStatusLine(lang: Lang, trim: TrimShown | null | undefined): string | null {
  if (!trim) return null;
  if (trim.dropped > 0) {
    const locale = lang === 'en' ? 'en-US' : 'ko-KR';
    return t(lang, 'trim.left_out', { n: trim.dropped, t: trim.savedTokens.toLocaleString(locale) });
  }
  if (trim.reason !== null) {
    return t(lang, 'trim.kept', { r: trimReason(lang, trim.reason) });
  }
  return null;
}

/** The latest turn memory is recorded through, for the Status view's last-request card; null when the sidecar sent
 *  no coverage (an older one) or no recorded turn, so the card adds no line. */
export function coverageLine(lang: Lang, coverage: { recordedThroughTurn: number | null } | null | undefined): string | null {
  const n = coverage?.recordedThroughTurn;
  if (typeof n !== 'number' || !Number.isFinite(n)) return null;
  return t(lang, 'trim.recorded_through', { n: n.toLocaleString(lang === 'en' ? 'en-US' : 'ko-KR') });
}

export function trimHudSuffix(lang: Lang, trim: TrimShown | null | undefined): string {
  if (!trim) return '';
  if (trim.dropped > 0) {
    const locale = lang === 'en' ? 'en-US' : 'ko-KR';
    return t(lang, 'hud.trim.left_out', { n: trim.dropped, t: trim.savedTokens.toLocaleString(locale) });
  }
  if (trim.reason !== null) {
    return t(lang, 'hud.trim.kept', { r: trimReason(lang, trim.reason) });
  }
  return '';
}
